# ADR 035 — Extract the DM turn delivery pipeline out of dmcog.py (composition)

- **Status:** Accepted (delivery pipeline landed; the scene/lore sub-cog splits still deferred)
- **Date:** 2026-06-14
- **Refs:** decision log D74 in progress.md; continues the context-leanness line of **ADR 034**
  (orchestrator pure-module extraction) and **ADR 032** (lean live docs). Builds on **ADR 029**
  (SessionRuntime + the cog split) whose deferred follow-up this is. Governed by golden rules:
  dice = code (the delivery path only *drains* the `<<ORT>>`/dice markers, never rolls), prompt
  order stays in the brain (ADR 019), feedback-protection layers untouched (golden rule #4).

## Context
After ADR 029 split the 2300-line voice god-cog into VoiceCog/DiceCog/DMCog, **DMCog was still the
largest file at ~1188 lines** — an agent fixing any one thing (a TTS-tuning sanitiser, a scene
command, the auto-recap) loaded the whole turn pipeline. ADR 034 had drained the cheap byte-exact
"free function" lever almost dry (only ~120 lines of pure helpers left repo-wide), so the remaining
volume sat in **methods on cog classes**, which bind `self` and can't be moved like a free function.

A structural scan found DMCog is really two concerns interleaved:
1. **The delivery pipeline** — turn an answer (or a streaming generation) into spoken audio (Bot A's
   `/speak` bridge), the posted Discord text, the 🎲 dice button + scene-change proposal, and the
   per-turn `[latency]` line. This is ~520 lines and is *the* most-edited block (every "the model
   read X aloud" / gap / babble fix lands in `_speak` / `_deliver_streaming` / `_speak_seamless`).
2. **The session/recap tail + the commands** — `!dm`/`!redo`/`!start`/`!intro`/`!wrap`/`!say`/
   scenes/`!lore`, plus the post-turn tail (autosave history → re-anchor mic → rolling auto-recap).

The two are entangled exactly the way ADR 029 described cross-cog flow: the delivery path calls the
post-turn tail; the commands call the delivery path; both call TTS speak. The auto-recap tail is also
the one piece with unit tests (`test_autorecap` calls `cog._maybe_compact`, monkeypatches
`cog._persist_recap`).

## Decision
Extract the delivery pipeline into a new module **`dmbot/voice/delivery.py`** as a class
**`DeliveryPipeline`**, by **composition, not inheritance**: DMCog constructs
`self._delivery = DeliveryPipeline(runtime, post_deliver=self._post_deliver)` and calls into it.

- The pipeline **holds the shared `SessionRuntime`** (`self._rt`) and reaches everything shared
  through it (TTS, bridge, brain, sink, speech-mode flags) **exactly as the cog did** — every moved
  method body is **byte-identical** to its original (verified: the 29 835 moved characters match
  `HEAD` exactly; the move was a line-slice script, not a retype).
- **Moved (12 methods):** `_synthesize`, `_speak`, `_speak_seamless`, `_begin_turn`,
  `_use_streaming`, `_handle_scene`, `_make_scene_confirm`, `_deliver_answer`, `_await_dice_scene`,
  `_deliver_streaming`, and the two turn-running hooks `_auto_dm_turn` / `_run_and_deliver` (the cog
  registers them on the runtime: `runtime.run_and_deliver = self._delivery._run_and_deliver`).
- **Stays on DMCog:** the **post-turn tail** (`_post_deliver`, `_autosave_turn`, `_maybe_compact`,
  `_persist_recap`) — a session/recap concern, and the one with tests. The pipeline calls it back
  through a **single injected `post_deliver` callback** (the ADR-029 hook pattern, object-local), so
  the two delivery paths keep one source of truth for the tail without the pipeline knowing about
  recap. Also staying: all `@commands.command` methods, `_deliver_intro_chunked`, the `!lore`
  helpers — they now call `self._delivery._<method>`.

`dmcog.py` **1188 → 662** lines; `delivery.py` is **575**. Suite **319 green, zero test edits**
(the auto-recap tests are undisturbed because their methods stayed on the cog), ruff clean.

## Alternatives
- **Mixin extraction** (`class DMCog(commands.Cog, _DeliveryMixin)`): rejected for the delivery
  pipeline. Mixins keep `self`-coupling implicit and raise the discord.py `CogMeta` command-collection
  question (commands defined on a non-Cog base may not register). Composition gives an explicit,
  isolated, independently-testable object and sidesteps the metaclass entirely. (A mixin may still be
  the right tool for the *scene* split below, where the methods are commands.)
- **Move the post-turn tail into the pipeline too** (no callback): rejected — it would drag
  auto-recap/compaction (a session concern, conceptually not "delivery") into the pipeline and force
  ~5 `test_autorecap` rewires to `cog._delivery._maybe_compact`. Keeping the tail on the cog with one
  callback is cleaner *and* yields zero test edits — the strongest "no behaviour change" signal.
- **Fatten the runtime with the delivery methods** instead of a new object: rejected — ADR 029
  deliberately keeps the runtime "boring state + helpers"; delivery builds Discord views and posts
  messages (UI/flow), which is cog territory, not runtime.
- **Hand-typed Edits** of ~520 lines: rejected — the streaming pipeline is fragile concurrent code;
  a byte-exact slice eliminates transcription risk (the point of "no functional change").

## Consequences
- **+** DMCog drops to 662 lines; the most-edited block (TTS delivery + streaming) is now a focused
  575-line module an agent loads in isolation. The remaining DMCog is commands + the recap tail.
- **+** Behaviour provably unchanged: moved bodies byte-identical to `HEAD`, 319-green suite with
  **zero** test edits, ruff clean. No flag-default / prompt / string / log-message change.
- **+** `DeliveryPipeline` is constructible without a cog (just a runtime + a callback) → unit-testable
  in isolation later.
- **−** One explicit back-reference: the pipeline calls `self._post_deliver` (the injected cog
  callback). It's the same indirection ADR 029 already uses for cross-cog hooks, greppable and
  documented; a broken wire is caught instantly by the suite.
- **Cosmetic:** the moved `log.*` calls now carry the new module name in the opt-in `debug.log`
  `%(name)s` column and in WARNING console lines (`voice.delivery` instead of `voice.dmcog`). The log
  *messages* (🎭/🔊/📖/🧩/⏱) and the green-chat/transcript formatting are unchanged — the filters key
  on message content + the `dmbot` prefix, not the exact module (same note as ADR 029/034).
- **Still deferred:** the **scene** commands (`!ort`/`!szenen`/`!ortmodus`) and **`!lore`** → their
  own mixin or sub-cog. Those are commands (the `CogMeta` question above), so they need the mixin/
  sub-cog idiom rather than this composition move — a later round under this same ADR's umbrella.
