# ADR 029 — SessionRuntime injection + the voice cog split

- **Status:** Accepted
- **Date:** 2026-06-13
- **Refs:** decision log D60 in progress.md; architecture.md §12; relates to ADR 013 (pause),
  ADR 017 (streaming), ADR 019 (adventure/RAG), ADR 022 (psyker), ADR 026 (auto scene),
  ADR 027 (auto-recap) — the features that had all accreted onto the one cog

## Context

`dmbot/voice/commands.py` had grown to **2300 lines in a single `VoiceReceiveCog`** owning voice
wiring, the dice/combat flow, session memory, TTS delivery, the streaming pipeline, scene control,
auto-recap and all Discord UI — with a **~26-kwarg constructor**. Every session that touched the file
paid for the whole thing, and the boundaries between concerns had blurred. We wanted to split it into
focused cogs **without changing any behaviour** (a pure structural refactor: moved code, not rewritten;
no flag-default, log-format, string, prompt or data change).

The hard part is that the concerns are genuinely entangled: a dice button (dice) rolls and then makes
the DM narrate the consequence (delivery); the delivery path posts the dice button and re-anchors the
mic button (voice); `!join` (voice) posts the turn-order panel (dice). A naive split would need cogs to
reach into each other (`bot.get_cog`), which couples them right back together.

## Decision

A plain **`SessionRuntime`** object (`dmbot/runtime.py`), built once in `__main__.setup_hook` from the
`Config` and **injected into every cog** (`Cog(bot, runtime)`), holds all shared session state — the
LLM brain (incl. the `OllamaClient` with `num_ctx`), STT/TTS, the bridge, the rules profile +
characters, the RAG retriever, the adventure compendium, the per-channel world state, the
push-to-talk/pause/mute flags — plus the state-mutating helpers (`_persist_and_refresh`, `_set_scene`,
`_load_*`, `_build_turn_order`, `_send_with_retry`) and the STT/VAD callbacks (the transcriber is built
here with `_on_transcript`; `!join` wires the VadSink to `_on_utterance`). The 26 kwargs collapse into
this one config-derived object.

The cog grows into **three thin cogs**: **VoiceCog** (`!join`/`!leave`/`!vstatus`/`!mic`/`!pausebutton`,
VAD-sink wiring, pause control), **DiceCog** (`!roll`/`!test`/`!turn`/`!rules`/`!npc`/`!damage`/`!heal`,
dice + manifest buttons, auto-combat, turn-order render), **DMCog** (`!dm`/`!redo`/`!start`/`!wrap`/
`!say`/`!voice`, the batch + streaming delivery path, TTS speak, auto-recap, **and** the scene commands
`!ort`/`!szenen`/`!ortmodus` + the `<<ORT>>` marker + `!lore`).

**No cog reaches into another cog.** The handful of genuine cross-cog calls go through **five hooks**
registered on the runtime by their owning cog in its `__init__` (`runtime.<hook> = self._<method>`):
`run_and_deliver` (←DMCog, called by DiceCog roll callbacks), `auto_dm_turn` (←DMCog, called by
VoiceCog mic release), `handle_dice` (←DiceCog, called by DMCog delivery), `reanchor_mic` (←VoiceCog,
called by DMCog delivery end), `post_turn_order` (←DiceCog, called by VoiceCog `!join`). All are first
invoked only after `!join`, so registration order doesn't matter.

## Alternatives

- **`bot.get_cog()` for cross-cog calls.** Rejected: it re-introduces the coupling the split is meant
  to remove (a cog has to know another cog's name + method shape) and makes the dependency implicit.
  The registered-hook indirection is explicit and greppable.
- **A fourth `AdventureCog`** for the scene/lore commands. Considered (the spec left it open); the
  owner chose to fold scenes/lore into DMCog (3 cogs) because the `<<ORT>>` marker is drained inside the
  delivery path anyway, so keeping it in DMCog avoids a sixth hook. Trade-off: DMCog is the largest cog.
- **Fatten the runtime with the shared UI panels** (mic button, turn-order) to drop two hooks. Rejected:
  it would pull Discord-View construction into the runtime; keeping the runtime "boring state + helpers"
  and paying two trivial hooks is the cleaner line.
- **Leave it as one cog.** Rejected: that is the problem.

## Consequences

- **Positive:** each cog is independently readable; the shared surface is one explicit object plus five
  named hooks. The 26-kwarg constructor is gone. Boot path unchanged (preflights run once, same order;
  `DMBot.close()` still sums `TEARDOWN_STEPS` = 4, all on VoiceCog, so the shutdown `[i/n]` display is
  byte-identical). Suite **263 green** with no test-logic change beyond import paths + one fixture rewire
  (`test_autorecap` now backs the bare cog with a stub runtime; assertions unchanged).
- **Binds:** future work hangs off the runtime, not a cog — Phase 10b (profile bootstrap, ADR 005) adds
  its state/services here; any new cross-cog flow adds a named hook rather than a `get_cog` lookup; the
  ADR-027 prompt order and ADR-019 prompt assembly are untouched (they live in the brain/orchestrator).
- **Refinements vs. the plan (no behaviour change):** the STT/VAD callbacks `_on_utterance`/
  `_on_transcript` live on the runtime (not VoiceCog) because the runtime constructs the transcriber with
  `_on_transcript`; `_speak`/`_synthesize` stayed in DMCog (its only caller once lore moved there).
- **Cosmetic:** moved log calls now carry their new module name in the opt-in `debug.log` `%(name)s`
  column and in WARNING console lines (e.g. `runtime`/`voice.dmcog` instead of `voice.commands`). The log
  *messages* and the green-chat/transcript formatting are unchanged (the filters key on message content +
  the `dmbot` prefix, not the exact module — verified).
