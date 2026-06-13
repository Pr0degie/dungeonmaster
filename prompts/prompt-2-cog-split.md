# Refactor: split the voice cog (pure structure, zero behavior change)

Start with the session ritual (CLAUDE.md): read `progress.md` and the highest-numbered
ADR, then give the handshake. This is a **pure structural refactor** — no behavior change,
no new flags, no prompt/persona/data changes. Log it in `progress.md` per the ritual.

**Run this in plan mode first:** show me the cut — which command/method lands in which
cog, and exactly what moves into the shared service object — before touching code.

## The problem

`dmbot/voice/commands.py` is ~1700 lines (grown again with streaming delivery and the
ADR-019 scene commands) with one cog owning voice wiring, dice flow, session memory, TTS
delivery, scene control, and all Discord UI. Its constructor takes ~20 kwargs. Every
session that touches it pays for the whole file.

## Target structure

- **`SessionRuntime`** (new module, e.g. `dmbot/runtime.py`): the shared state that today
  lives as cog attributes — `DMBrain`, `Transcriber`, TTS engine, `BridgeClient`,
  `SystemProfile`, `CharacterStore`, `WorldState` handling, the sink handle, the
  push-to-talk / pause / mute flags — **plus the ADR-019 additions**: the RAG retriever,
  the adventure compendium / scene state, and the NPC statblock resolution. Built once in
  `__main__` from the config object and **injected into every cog via constructor**.
  Replace the kwarg avalanche by passing the config object (or the runtime) — not 20
  scalars. Phase 10b (profile bootstrap, ADR 005) will hang off this object too — keep it
  boring and explicit.
- **`VoiceCog`**: `!join` / `!leave` / `!vstatus`, mic button, pause panel + Esc wiring
  (ADR 013), VAD-sink wiring, preflight calls.
- **`DiceCog`**: `!roll` / `!test`, dice buttons + auto-combat flow (target select,
  damage), `!turn` / `!order`, `!rules`, `!npc` / `!damage` / `!heal`.
- **`DMCog`**: `!dm` / `!redo`, the streaming speak/delivery path, `!say` / `!voice` /
  `!voices`, `!wrap`/`!wrapup`, recap/state injection into the brain.
- The **scene/adventure commands** (`!ort`, `!szenen`, the compendium side of `!npc add`)
  need a home: either inside DMCog or a fourth `AdventureCog` — propose one in the plan
  with a reason; don't decide by default.

Rules for the cut:

- **No cog reaches into another cog** — no `bot.get_cog()` lookups; everything shared
  goes through `SessionRuntime`.
- Don't be dogmatic about my Cog assignment above if the code says otherwise (e.g. the
  dice-result → next-turn feedback path may bind DiceCog and DMCog through the runtime) —
  but justify deviations in the plan.
- Mind the lifecycle: join/leave own setup/teardown of shared state; make explicit in the
  plan who resets what (today `!leave` clears brain + state + buffers, rotates the
  autosave, and must keep doing exactly that).
- The streaming pipeline (ADR 017) and the concurrent roll-router task cross what will
  become cog boundaries — the plan must show where the in-flight task handles
  (stream/fold/router) live so cancellation on `!leave`/pause keeps working.
- Golden rule 4 (feedback protection) — the Bot-A user-ID filter and the layer-2 mute
  must survive the move untouched; call out in the plan where they end up.

## Verification

- `uv run pytest` green; test imports adjusted. No test *logic* changes — if a test
  forces a logic change, stop and tell me, that's a smell.
- After the move, run `git diff --stat` and a spot-check: moved code should be
  **moved**, not rewritten. Flag any place you had to genuinely change code (signature
  adaptations to the runtime are expected; algorithm changes are not).
- Boot path check: `__main__` builds runtime + registers all cogs; preflights still run
  once, in the same order.

## Docs (per the repo's own rules)

- `progress.md`: ritual end-of-session update.
- `architecture.md` §12 (project structure): update the layout to the new modules.
- `CLAUDE.md`: **only** the repo-layout block (it lists `voice/` contents and
  `orchestrator.py` placement) — bring it in line with reality, change nothing else in
  that file.
- ADR: the `SessionRuntime` injection pattern is a structural decision that binds later
  work (Phase 10 RAG will hang off it) — next free number, README format, refs D-entry.

## Constraints

- **Never commit.** I commit manually.
- Zero behavior change — no flag defaults, no log-format changes, no string changes
  visible to players.
- Final summary: file map old → new, plus the quickest manual smoke test
  (`!join` → speak → `!dm` → dice button → `!leave`) and what to watch for.
