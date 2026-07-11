# ADR 039 — Split scenes + lore out of DMCog into thin sub-cogs (the deferred ADR-035 follow-up)

- **Status:** Accepted
- **Date:** 2026-06-16
- **Refs:** decision log **D81** in progress.md; `/improve-architecture` candidate "dmcog-Paket"
  (`scene-subcog` + `lore-subcog` + this mixin-vs-sub-cog decision). Resolves the design fork
  **ADR 035** left open and continues the context-leanness line of ADR 034/035 + **ADR 029**
  (SessionRuntime + the cog split). Governed by golden rules: scene pointer = deterministic code
  (#3); the `/speak` bridge stays the only Bot-A surface (#5); `!lore <frage>` is deterministic
  chunk display, no LLM (#7).

## Context
After ADR 035 pulled the turn-delivery pipeline out, `DMCog` was still **662 lines** — the largest
hand-maintained file. ADR 035 explicitly deferred two follow-up splits ("a later round under this
same ADR's umbrella"): the scene commands (`!ort`/`!szenen`/`!ortmodus`) and the `!lore` reader. An
agent editing scene-pointer behaviour or the world-knowledge reader had to load the whole
turn-pipeline cog — turn glue, intro chunking, TTS commands, the post-turn recap tail — none of
which a scene or lore edit needs. Tobi's framing for the whole `/improve-architecture` round: *an
agent should only have to read what its task needs, not the whole file.*

ADR 035 also left an explicit, **undecided design fork** and flagged its risk: scenes/lore into
"their own mixin **or** sub-cog" — warning that "commands defined on a non-Cog base may not
register" (the discord.py `CogMeta` command-collection question). The wrong choice (a mixin whose
`@commands` silently fail to register) is a correctness bug the type checker won't catch and only a
live `!ort` would reveal.

## Decision
Resolve the fork toward **sub-cogs, not a mixin**, and split into **two** cogs (not one combined
`AdventureCog`):
- `dmbot/voice/scenecog.py` — `SceneCog`: `!ort`/`!szenen`/`!ortmodus`, bodies **byte-identical** to
  their DMCog originals. Reaches only `SessionRuntime` state (`_adventure`, `_state`,
  `_brain_channel`, `_set_scene`, `_persist_and_refresh`, `_scene_mode`). **No hook needed** — no
  other cog calls these commands.
- `dmbot/voice/lorecog.py` — `LoreCog`: `!lore` + the three helpers
  (`_lore_rundown`/`_lore_speak`/`_lore_question`) + the three lore dicts, bodies byte-identical
  **except the one cross-cog dependency**. The automatic `<<ORT>>` scene-change drain already lives
  in `delivery.py` (ADR 035), so the human commands and the automatic transition were already split.

`CogMeta` collects `@commands` while scanning a Cog subclass body; commands declared on a plain
mixin base land in the MRO/metaclass grey zone — exactly ADR 035's risk. Sub-cogs sidestep the
metaclass entirely; each is a first-class cog whose commands register like DiceCog/VoiceCog
(verified: `SceneCog.__cog_commands__` = ort/ortmodus/szenen, `LoreCog` = lore). **Two** cogs not one
because scenes and lore share no state and an agent rarely edits both — two narrow files beat one
medium file for context-leanness.

The one cross-cog dependency — `_lore_speak` passing `self._delivery._speak` to `LoreReadView` — is
resolved via a new runtime hook **`runtime.speak`** (set by DMCog in `__init__`, the ADR-029
cross-cog hook pattern), so `LoreCog` calls `self._rt.speak` and never reaches into another cog or
the bridge. This is precisely what ADR 034 foresaw ("lore → its own cog after moving `_speak` to the
runtime").

`dmcog.py` 662 → **502** lines; `scenecog.py` 84, `lorecog.py` 126. Suite **369 green** (359 + 10
new sub-cog tests), **0** existing-test edits, ruff clean.

## Alternatives
- **A mixin (`class DMCog(commands.Cog, _SceneMixin, _LoreMixin)`):** rejected — the `CogMeta`
  command-collection risk ADR 035 named, plus it introduces a second cog-composition idiom
  (self-coupling via MRO) where sub-cogs reuse the proven `add_cog` + runtime-hook one.
- **One combined `AdventureCog`** (scenes + lore together): rejected — they share no state; two
  narrow files serve "read only what the task needs" better than one medium file.
- **Keep them on DMCog** (status quo): rejected — DMCog stays the biggest file and every scene/lore
  edit pays for the whole turn pipeline.
- **Reach the speak callable via `bot.get_cog("DMCog")`:** rejected — ADR 029 deliberately routes
  cross-cog flow through runtime hooks, not `get_cog`; a hook is greppable and the suite catches a
  broken wire.

## Consequences
- **+** An agent editing scene-pointer behaviour loads ~84 lines instead of 662 (~88% less); a
  lore-reader edit loads ~126, and the lore-only imports (`RulesView`, `LoreReadView`,
  `available_topics`/`lore_pages`, `_DATA_DIR`) leave the DMCog header entirely (`discord` too — it
  was only used by `_lore_question`'s embed).
- **+** Scenes + lore gain a real unit-test seam (`tests/test_subcogs.py`, 10 tests via
  `object.__new__` + `Cog.<cmd>.callback` + a stub runtime) — there was **zero** scene/lore command
  coverage before.
- **+** Behaviour provably unchanged: moved bodies byte-identical to HEAD (150/150 moved-region
  lines verified), one deliberate change (`speak_fn=self._delivery._speak` → `self._rt.speak`),
  369-green suite with 0 existing-test edits.
- **+** The fork ADR 035 left open is now closed with a recorded reason, so a future review won't
  re-derive the `CogMeta` question.
- **−** One new runtime hook (`runtime.speak`) and two more `add_cog` lines in `__main__`. Same
  indirection ADR 029 already uses; greppable, suite-checked. DMCog is added before LoreCog so the
  hook is wired (though hooks only fire after `!join` anyway).
- **Cosmetic:** moved `log.*` lines now carry `voice.scenecog`/`voice.lorecog` in the opt-in
  `debug.log` `%(name)s` column (messages unchanged; filters key on content + the `dmbot` prefix —
  same note as ADR 029/034/035).
- **Done:** this completes the ADR-035 deferred-split umbrella for DMCog. (`dicecog.py` at 557 lines
  is the next-largest cog, but has no analogous clean command-cluster to peel off — out of scope.)

## Addendum — detail preserved from decision log D81 (2026-07-11)

- **How the candidate was surfaced and chosen:** via a `/improve-architecture` workflow — **3 finder
  subagents** plus a **3-lens adversarial verify**; of **13 candidates, 7 survived** the verify, and
  this "dmcog-Paket" was one of them.
