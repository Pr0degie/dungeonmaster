# ADR 049 — NPC agendas: goals + one offscreen step per scene change

- **Status:** Accepted
- **Date:** 2026-07-03
- **Refs:** decision log **D96** in progress.md, architecture.md §7 (memory). Extends
  **ADR 044** (NPC memory — this rides the *same* scene-change extractor call) and is bound
  by **ADR 015** / golden rule #3 (hard state is advanced by code, never by LLM free text).
  Uses the in-game clock from **ADR 048** for step timestamps. Touches
  `dmbot/memory/state.py`, `dmbot/memory/npc_memory.py`, `dmbot/runtime.py`,
  `dmbot/voice/dicecog.py`, `dmbot/rag/adventure.py`, `prompts/npc_memory_extract_de.md`.

## Context

NPCs are frozen between scenes: the smuggler the party betrayed is still sitting politely in
his bar on the next visit. A human GM moves important NPCs *offscreen* — they pursue goals
while the party is elsewhere, and the world shows traces of it (rumours, a cleared-out
hideout, a new bodyguard). NPC memory (ADR 044) gave NPCs a past; this round gives a few of
them a *direction*.

The tension is scope: a general world simulator would burn context and extraction tokens on
NPCs nobody cares about, and offscreen "movement" written by the LLM must not mutate hard
state (that is exactly the golden-rule-#3 failure mode). And latency is already spent: ADR 044
budgets **one** LLM call per scene change — a second agenda call is off the table.

## Decision

1. **Only explicitly marked agenda NPCs.** An NPC with a non-empty `goal: str` (one sentence)
   on its `Combatant` is an agenda NPC; everyone else stays frozen. Goals are set by humans
   (`!agenda`) or authored data (`goal_de` on the `npcs.json` statblock, copied in at
   registration like `faction`) — never by the LLM. Intended scale is **2–5 NPCs**; the
   command warns (does not refuse — the human is the authority, the `!zeit` argument) when a
   sixth goal is set.
2. **Max one offscreen step per NPC per scene change, clamped by code.** The ADR-044
   extractor call gains an optional `agenda_step` (1–2 sentences: what the NPC did for its
   goal since the last scene) per agenda NPC. Code accepts at most one step per NPC per
   extraction (duplicate payload entries are dropped), only for living NPCs whose `goal` is
   non-empty (a step proposed for a non-agenda NPC or a PC is discarded + logged), truncated
   to the ADR-044 gist cap.
3. **Steps are narrative, not state.** A step is a log entry
   `AgendaStep{ts_ingame, text}` appended to `agenda_log` (capped at the **last 10**, oldest
   pruned — plain FIFO, no importance tiers: unlike memories, agenda steps age out
   naturally). Hard mutations (NPC death, moving a scene NPC, scene flags) remain
   code/command territory; the DM narrates consequences, the table makes them real.
   `ts_ingame` is the rendered ADR-048 clock ("Tag 2, 14:30") at extraction time — display
   data, never parsed back.
4. **One call, not two.** The extractor *input* gains, per agenda NPC, its goal + the last 2
   `agenda_log` entries, plus the current in-game time — so steps stay plausible against the
   elapsed time ("overnight the smuggler moved his stash", not "built a fortress"). Output
   parsing stays ADR-044-defensive: parse failure → skip, never block the scene change.
5. **Injection, two-sided.** *Present* agenda NPC: its memory block (ADR 044 rendering)
   additionally carries `Ziel:` + the last 2–3 steps — same token-cap regime; an agenda NPC
   without memories now renders a (goal-only) block too. *Absent* agenda NPC: the world-state
   summary gets **one line per living agenda NPC** (goal + newest step) with the instruction
   to surface offscreen movement as rumours and traces — so the world feels alive even when
   the NPC is off-stage.
6. **Maintenance commands** next to the other NPC-upkeep commands (`!npc`, `!npcmem` in
   DiceCog — no new cog; two small commands on existing NPC state don't justify one):
   `!agenda <npc> "<Ziel>"` sets/changes, `!agenda <npc> weg` removes (log survives removal —
   history is cheap and informative), `!agenden` lists goals + recent steps.
7. **Kill switch inherited:** the whole feature rides inside the ADR-044 extraction
   (`DM_NPC_MEMORY=0` disables it); no goal set → zero cost. No new env knob.

## Alternatives

- **A general world simulator (all NPCs / factions advance):** rejected — context + token
  cost scales with the roster, and nobody at the table notices NPC #17 moving. Faction-level
  agendas are explicitly out of scope for the same reason.
- **A second, dedicated agenda LLM call per scene change:** rejected — ADR 044's latency
  budget is one call; the marginal quality of a separate call doesn't buy back the wait.
- **Agenda steps mutate state (NPC relocates, spawns, dies):** rejected — golden rule #3;
  an LLM-written step that kills an NPC or teleports a scene NPC is exactly the unauditable
  drift the code-owned layer exists to prevent.
- **LLM proposes goals (self-assigned agendas):** rejected — which NPCs *matter* is GM-table
  framing, same authority argument as clocks/deadlines (ADR 047/048).
- **Cap agenda_log by importance (memory-style pruning):** rejected — steps are a timeline,
  not facts; the newest 10 are the useful ones, FIFO is simpler and predictable.
- **Hard cap of 5 agenda NPCs (refuse the 6th):** rejected — humans stay unclamped
  (ADR 048 precedent); a warning communicates the budget without patronising the GM.

## Consequences

- **+** Important NPCs move between scenes; returning to a betrayed smuggler's bar can
  plausibly find it empty — and the DM can foreshadow it through rumours while the party is
  elsewhere.
- **+** Fully replayable from `state.json`; the whole pipeline (schema, clamp, parsing,
  rendering) is pure-function testable like ADR 044.
- **−** The extractor prompt + input grow (goal + 2 steps per agenda NPC); bounded by the
  2–5-NPC guidance and the caps.
- **−** Agenda steps are LLM prose living in `state.json` — like `memories`, they must never
  be read as hard facts.
- **−** Offscreen steps are only as plausible as the model; the live gate (give one NPC a
  goal, play two scenes, check its situation moved believably) is the real test.
- **Bound for later work:** faction agendas, hard availability/relocation from steps,
  agenda-aware scene seeding — all explicitly deferred.

## Addendum — detail preserved from decision log D96 (2026-07-11)

- `goal_de` is not only copied at registration but also **backfilled** onto
  already-registered NPCs, like `faction`.
- Test evidence from the round: suite **659 green** (+24, `tests/test_agenda.py`).
