# ADR 044 — NPC memory: per-NPC Erinnerungen, code-clamped attitude drift, faction gossip

- **Status:** Accepted
- **Date:** 2026-07-03
- **Refs:** decision log **D91** in progress.md, architecture.md §7 (memory). Builds on
  **ADR 015** (sheet/state split — `state.json` is the code-owned mutable layer), **ADR 043**
  (the scene-change seam this hooks into) and mirrors the request/validate/apply pattern of
  **ADR 022/026/043** (LLM requests, code decides — golden rules #2/#3). Touches
  `dmbot/memory/state.py`, new `dmbot/memory/npc_memory.py`, `dmbot/llm/prompt_assembly.py`,
  `dmbot/orchestrator.py`, `dmbot/runtime.py`, `dmbot/voice/scenecog.py`,
  `dmbot/voice/delivery.py`, `dmbot/voice/dmcog.py`, `dmbot/rag/adventure.py`,
  new `prompts/npc_memory_extract_de.md`.

## Context

NPCs forget everything between scenes: what the party told them, what they promised, what
they were *lied to about*. A human GM tracks that per NPC — including believed falsehoods —
and lets it colour the NPC's attitude. The recap covers the party's thread, not any one NPC's
knowledge, and the world state only stores an `attitude` string with no history behind it.

The tension: memories are LLM-generated prose, but golden rule #3 forbids writing hard state
from LLM free text. `attitude` in particular is a hard field the state summary renders and
play decisions hang off.

## Decision

1. **Memories are a narrative layer inside `state.json`** — a `memories: list[NpcMemory]`
   on NPC `Combatant`s (gist + optional verbatim quote, `about` scope, `believed`,
   `importance` 1–5, `source: direct|gossip`, origin scene, timestamp). Like the recap
   (§7b), the *text* is LLM-generated but code stores, caps and serialises it. This does not
   soften rule #3: no hard field is derived from memory text.
2. **Hard fields stay code-owned.** The extractor returns an `attitude_proposal`; code
   validates it against the fixed scale `hostile → wary → neutral → friendly → loyal`
   (`ATTITUDE_SCALE` + `step_attitude` in `state.py`) and clamps to **max one step per
   scene** relative to the current value. Unknown proposed values → no-op + log. An
   off-scale/empty *current* attitude (legacy free-text states) anchors at `neutral` for the
   step so old states can still drift. Same pattern as dice: the LLM requests, code decides.
3. **Extraction runs at scene exit + `wrap up`, never per turn.** The trigger hangs on the
   deterministic scene-change seam (ADR 043): `!ort` and the confirmed `<<ORT>>` move
   schedule a fire-and-forget extraction of the just-left scene's history slice; `!wrap`
   awaits one for the current scene as the catch-all. One LLM call per scene (structured
   JSON via Ollama `format`, like the roll router), off the hot path — no added turn
   latency on local hardware. Parse is tolerant (fence-stripping), one retry, then skip +
   warn — a broken extraction never blocks the scene change.
4. **The extraction window is a history mark, approximate by design.** The runtime tracks
   per channel how many history messages were already extracted (`min`-clamped, reset on
   auto-compaction and seeded on `!join` so restored history isn't re-mined). Compaction can
   blur the seam, so `apply` additionally dedupes on (npc, gist) — a duplicate window never
   produces duplicate memories.
5. **Lies are memories too.** The NPC stores what it *believes* (`believed: true` covers a
   player's lie). When the extractor reports a lie as revealed (`revealed_lies` indexes into
   the existing entries it was shown), **code** flips `believed = False`, appends a new
   importance-5 entry („Wurde von X belogen …") and steps the attitude one step toward
   `hostile` — on top of (and after) the normal proposal clamp, so a revealed lie can move
   attitude even in a scene whose proposal already used the one step.
6. **Gossip is deterministic propagation, not another LLM call.** After applying a scene's
   direct memories, each **new `direct` entry with importance ≥ 4** is copied to every other
   NPC with the same non-empty `faction`: `source: "gossip"`, quote dropped, importance −1.
   No gossip-of-gossip (only direct entries propagate), no duplicates (same gist at the
   recipient → skip). `faction` is a new optional field on `Combatant` and on the
   `npcs.json` statblock (`AdventureNpc.faction`), copied in when an NPC is registered —
   authored data, never LLM output.
7. **Injection is per-scene, capped.** `_persist_and_refresh` renders a compact German
   block for each *living* NPC of the current scene (card `npcs_here` ∩ registered NPCs;
   without an adventure, all registered NPCs with memories): top-K entries
   (`DM_NPC_MEMORY_TOP_K`, default 6) ranked believed-false first (the NPC *knows* it was
   lied to), then importance, then recency; gists hard-truncated at 200 chars; gossip
   rendered as „(Hörensagen)" so the DM keeps it vague. New order-explicit slice in
   `assemble_system_prompt` between state summary and RAG. `DM_NPC_MEMORY=0` switches the
   whole subsystem off (house style: every subsystem has a kill switch).
8. **Cap 30 memories per NPC.** On overflow the lowest-importance (tie: oldest) entry is
   pruned; `believed: False` entries and importance 5 are prune-protected. If everything is
   protected the oldest entry goes anyway (hard cap wins, warn log).
9. **Registration side effect, accepted:** a memory for an NPC not yet in `state.npcs`
   registers it (statblock values when the adventure knows it, else defaults, attitude
   `neutral`) — memories need a place to live, and this matches what `!npc add` would do.
   Debug: `!npcmem <name>` prints an NPC's stored memories read-only.

## Alternatives

- **LLM writes memories/attitude directly into state (tool call / free text):** rejected —
  golden rule #3. Attitude is a rendered hard field; the proposal+clamp keeps drift bounded
  and auditable (every step is logged).
- **Extraction per DM turn:** rejected — one extra 12B call per turn on local hardware is
  exactly the latency budget the delivery pipeline fights for; scene granularity matches
  what a human GM would note down anyway.
- **Embedding/RAG retrieval over memories:** rejected for the first cut — top-K by
  importance/recency over ≤30 entries is enough and keeps the prompt path free of another
  vector query. Revisit if NPCs accumulate long lives.
- **Gossip via a second LLM pass ("what would spread?"):** rejected — a deterministic
  importance threshold is predictable, testable and free; the vagueness is handled at
  render time („Hörensagen"), not by rewriting the gist.
- **Storing memories in a separate `memories.json`:** rejected — they are per-NPC session
  state with the same lifecycle as `state.json` (reset by deleting it, survive restarts);
  a second file adds a sync seam for no gain. Cap 30/NPC keeps the file small.
- **A confirm button per memory (ADR 026-style):** rejected — memories only change prompt
  colour, not world facts or plot position; the stakes are the `DM_FLAG_CONFIRM=0` tier.
  The one hard effect (attitude) is already clamped to ±1 per scene.

## Consequences

- **+** NPCs remember conversations, promises and lies across scenes and restarts; a
  revealed lie visibly sours the relationship — all replayable from `state.json`.
- **+** The full pipeline is pure-function testable: parse, clamp, flip, gossip, prune,
  ranking, rendering all run without Discord or an LLM.
- **−** One extra LLM call per scene change (skippable, `DM_NPC_MEMORY=0`).
- **−** The prompt grows by ~K lines per scene NPC (hard-capped: K entries × ≤200 chars).
- **−** The extraction window is approximate around auto-compaction; the gist-dedup makes
  that a coverage gap (a turn can go unmined), never duplication. Accepted for the first cut.
- **−** `memories` in `state.json` are LLM prose; anyone reading the file must not treat
  them as facts (the field lives on the NPC, clearly separated from wounds/attitude).
- **Live-unverified:** whether nemo extracts useful memories/lies (and doesn't flag
  small talk as importance 5) is a model-behaviour claim — the gate is a live run: lie to
  an NPC, change scene, come back, check the DM remembers and the attitude drifted.

## Addendum — detail preserved from decision log D91 (2026-07-11)

- Test evidence from the round: suite **486 green** (+27 new tests).
- Prompt-injection detail: lies are always included in the top-K memory block (the
  believed-false-first ranking guarantees it within the cap).
