# ADR 043 — Stateful scene cards: element flags (`<<ERLEDIGT>>`), dead-NPC render, gated exits

- **Status:** Accepted
- **Date:** 2026-07-02
- **Refs:** decision log **D87** in progress.md. Builds on **ADR 019** (scene tracker) and
  **ADR 026** (the `<<ORT>>` marker flow this mirrors); bound by **ADR 015** (memory state split)
  and **golden rule #3** (world state is advanced by code, never by LLM free text). Touches
  `dmbot/rag/adventure.py`, `dmbot/rules/marker.py`, `dmbot/llm/stream_assembler.py`,
  `dmbot/orchestrator.py`, `dmbot/voice/delivery.py`, `dmbot/voice/scenecog.py`,
  `dmbot/memory/state.py`, `dmbot/runtime.py`, `dmbot/discord_ui/flag.py`, `prompts/dm_core_de.md`.

## Context
Scene cards (ADR 019/026) are static; the world isn't. On a revisit — or late in a long scene —
the same fresh card is injected: the DM re-offers Gelegenheiten the party already used, re-hides
Geheimnisse that are already out in the open, and NPCs the engine knows are at 0 wounds stand
around alive in „Anwesende NSCs". The card must reflect what has already happened — without the
LLM ever writing state.

## Decision
1. **Element ids, backward compatible.** `opportunities_de`/`secrets_de` entries are a plain
   string (the existing form) or `{"id": ..., "text_de": ...}`. Plain entries get deterministic
   positional ids (`opp-1`…/`geh-1`…, position counted across the whole list so mixed forms stay
   stable). Ids must be unique within a scene across both lists — collision logs `ERROR` and falls
   back to a positional id (degrade, don't die). The existing Chemical-Burn `adventure.json`
   keeps working untouched.
2. **`WorldState.scene_flags: dict[str, list[str]]`** (scene_id → resolved element ids) — the
   code-owned flag store (ADR 015), persisted in `state.json` omit-when-empty, so `!leave`/restart
   semantics are identical to `scene_id` (only deleting `state.json` resets). Dumb storage
   (`mark_resolved`/`mark_open`/`resolved_ids`); validation lives in
   `runtime._set_scene_flag`, which only accepts elements of the *current* scene.
3. **Stateful render.** `adventure_block_de` takes `resolved_ids` + `dead_npcs` (plain
   collections — `rag/` stays decoupled from `memory/`): a resolved Gelegenheit moves to
   „Bereits geschehen:", a revealed Geheimnis moves out of the never-say block to
   „Bekannt (bereits enthüllt):", a dead NPC (wounds ≤ 0, case-insensitive name join like
   `WorldState.find`) renders as `<Name> (tot)`. Element ids render inline (`- [opp-1] …`) so the
   model can cite them. Untouched scenes gain no new sections.
4. **Fourth marker `<<ERLEDIGT <id>>>`,** mirroring `<<ORT>>` at every seam: same grammar incl.
   glued-id tolerance, same strip-before-TTS via the shared `<<…>>` delimiter (keep it — ADR 026's
   binding), same streaming partial-withholding (free via `_open_marker_index`), same pending
   queue under the post-roll suppression guard, drained by the delivery pipeline. **Unlike ORT,
   all valid markers in a turn are processed** — resolving a Gelegenheit and revealing a Geheimnis
   can legitimately happen in one narration, and flags are idempotent + low-stakes.
5. **Confirm by default, auto-apply as a knob.** A valid request posts a `FlagView` confirm
   button (the ADR-026 human-in-the-loop argument); `DM_FLAG_CONFIRM=0` applies valid flags
   immediately. Manual override: `!erledigt <id>` / `!offen <id>` apply without a button — the
   human IS the confirm; `!ort`/`!szenen` list the current scene's element ids with ✅/⬜.
6. **Gated exits.** `leads_to` entries are `"scene-id"` or `{"ziel": ..., "requires":
   "<element-id>"}`, where `requires` names an element of the scene *owning* the list. A locked
   exit is hidden from „Mögliche nächste Orte" until unlocked (the persona says "use only the
   offered ids" — a visible-but-locked id would invite rejected moves and hint at a target that
   isn't due yet), and `resolve_move` in `verbunden` mode rejects it like an unknown target — the
   missing condition is named in the console log only, never spoken/sent (spoiler discipline).
   `frei` bypasses gates as it bypasses adjacency; manual `!ort` stays free (it is the override).
   A `requires` naming no element fails open (gate dropped, `ERROR` logged) — a typo must not
   lock an exit forever.

## Alternatives
- **LLM writes the flags (free text / tool call):** rejected — golden rule #3. The model only
  *requests*; code validates against the current card and applies.
- **Auto-apply without any confirm (no knob):** rejected as the default — a 12B model will
  occasionally flag things that merely got talked about; the button is the same human-in-the-loop
  guarantee ADR 026 chose for scene moves. But unlike the scene pointer, flags only change what
  the card renders (no history/location side effects), so auto-apply is acceptable as an opt-in
  (`DM_FLAG_CONFIRM=0`) once the marker proves reliable at the table.
- **A `SceneElement` object model instead of parallel id lists:** rejected — tests and callers
  construct `Scene(...)` directly and `resolve_move` relies on `leads_to` staying a plain id list;
  the object model would ripple through both for no behavioural gain.
- **First-marker-only, strict ORT parity:** rejected — one narration can resolve several elements;
  forcing one flag per turn would make the model (or the humans) re-emit the rest.
- **Global `requires` scope (any scene's flags):** rejected for now — derived ids repeat across
  scenes, so a global lookup is ambiguous without a qualified `"szene:element"` form. Current-scene
  scope is well-defined; cross-scene gates can be added later as an explicit extension.

## Consequences
- **+** The card now tells the DM what already happened („Bereits geschehen"/„Bekannt"), so
  revisits and long scenes stop re-offering used content and re-hiding known secrets.
- **+** Dead NPCs are presented as a fact (`(tot)`) instead of active presences — a render-time
  join, no new persistence (NPC wounds already survive scene changes and restarts).
- **+** Adventure authors get simple progression gates without any new state machinery.
- **−** Element ids ride in the prompt (`- [opp-1] `, ~9 chars/entry) and one more persona bullet —
  immaterial against `OLLAMA_NUM_CTX`.
- **−** An explicit element id must not *end* in `-`/`_` (the glued-marker strip set would peel
  it); derived ids are digit-final and safe.
- **Live-unverified:** whether nemo emits `<<ERLEDIGT>>` reliably (and not for merely-discussed
  things) is a model-behaviour claim — confirm at the table; `DM_FLAG_CONFIRM=1` keeps misfires
  harmless meanwhile.

## Addendum — detail preserved from decision log D87 (2026-07-11)

- **Forced seam cost (declared in the approved plan):** `finalize_answer` widened from a 4-tuple to
  a **5-tuple** → **3 mechanical unpack widenings** in existing tests, **zero assertion changes**.
- **Test delta:** **+49 tests**; suite **444 green** at commit time.
- **Implementation notes:** `scene_flags` is the **first dict-typed field** on `WorldState`; the
  streaming partial-withholding rides on the shared `<<` delimiter; the pending `<<ERLEDIGT>>` queue
  is drained as a **third delivery task** in the pipeline (alongside the existing drains).
