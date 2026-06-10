# ADR 017 — Streaming pipeline: LLM stream → sentence-chunked TTS → sequential bridge playback

- **Status:** Accepted (code-complete; live verification pending)
- **Date:** 2026-06-10
- **Refs:** decision log D39 in `progress.md`; builds on **D15** (blocking `/speak` = the resume
  signal / natural queue), **ADR 011 / 016** (latency context — spoken chars dominate the turn),
  **D35** (`[latency]` instrumentation); `architecture.md` §4 (data flow), §6 (when the DM speaks).
  Commits: this change. Flag `DM_STREAMING` (default `1`).

## Context

A DM turn was strictly serial: generate the **whole** answer (Ollama), synthesise the **whole**
answer (XTTS), then one blocking `POST /speak` for the whole WAV. Time-to-first-audio = full
generation + full synthesis. The `[latency]` line (D35) makes this visible — even after ADR 016
shortened turns, the table still waits `trigger→llm_done + tts` of silence before any sound.

The blocking `/speak` (D15) already serialises playback per WAV and returns exactly when Bot A goes
quiet — a natural queue. So the win is to **shrink the unit of work** from one-WAV-per-turn to
one-WAV-per-sentence and pipeline the stages, speaking sentence 1 while sentences 2..N still
generate. XTTS already chunks a long answer internally (`tts/textsplit.chunk_text`); we just feed
it sentence by sentence as they arrive.

The risk is correctness: the sanitizers in `orchestrator.py` (leading meta-preamble / role label,
trailing 'Was tut ihr?' / parenthetical, `<<TEST …>>` markers, the anti-puppeting speaker-label
cut, the mid-sentence `num_predict` trim) all assume they see the **whole** answer. Streamed, they
must run on a growing buffer without ever speaking something a later strip would remove, and the
**stored history must stay identical** to the batch path for the same raw text.

## Decision

Add `OllamaClient.chat_stream()` (a `stream:true` async generator of text deltas; `chat()` stays
the non-streaming entry the roll router, recap and tests use). A pure `StreamAssembler` turns the
deltas into speakable sentences under three hold-back rules, and a synth→playback pipeline in the
cog speaks them. `DM_STREAMING=1` by default; `0` is the byte-identical batch path; it only engages
when a TTS backend loaded.

**Hold-back rules (`StreamAssembler`):**
- **First-chunk hold** — withhold until the view is one complete sentence (or 80 chars), so a
  leading meta-preamble / role label is stripped before anything is spoken.
- **Last-sentence hold-back** — emit sentence N only when N+1 exists, so the trailing strips
  (parenthetical, 'Was tut ihr?', mid-word cut) apply to the held tail before it's spoken.
- **Marker / label withholding** — text is withheld from any unmatched `<<` (a `<<TEST …>>` marker
  may span deltas); a mid-text speaker label (`_cut_at_labels`) sets `stopped` so the caller aborts
  the HTTP stream and keeps only the pre-label narration (the client-side label cut is the safety
  net behind the server-side `options.stop`).

**Parity by construction.** The batch chain is factored into one `finalize_answer(raw, labels,
profile)` used by *both* paths. `StreamAssembler.finish()` recomputes the canonical answer with
`finalize_answer` on the accumulated raw and speaks only the part not already emitted — so the
**stored answer equals the batch path's** and equals what was spoken. `_sanitize` is split into
`_sanitize_leading` (applied incrementally) + `_sanitize_trailing` (only the held tail) so the two
can't drift.

**Cog pipeline.** A producer drives the brain's streaming turn; a synth worker (`asyncio.to_thread`)
and a play worker run with a bounded WAV queue, so sentence N+1 synthesises while N plays. The
Discord text post and the 🎲 dice button happen at generation-end (mid-playback). The `[latency]`
line gains `first_audio=…ms` (trigger → first `/speak` POST) and a `stream` marker; `tts/wav/
bridge_wait` become per-turn sums; `total` still means "trigger → last `/speak` returned".

**Feature interactions.** Layer-2 mute (`DM_PAUSE_VAD_WHILE_SPEAKING`) is taken **once** around the
whole streamed answer, not flapped per sentence. Pause (ADR 013) stops emission and playback
cleanly mid-stream via `should_abort`; resume doesn't replay (the turn just ends early, history
holds the canonical partial). A mid-stream httpx error keeps what was spoken, logs loudly, and
appends the partial answer to history with a `… [Antwort unterbrochen]` note (the note is never
spoken). `!redo` has its own streaming path.

## Alternatives

- **Streaming TTS** (XTTS's own streaming inference API): finer-grained but heavier and a bigger
  surface; the sentence granularity already gets most of the win. Deferred to Part 2 (it was always
  the "later" half of CLAUDE.md's "streaming TTS is a later optimisation").
- **Progressive Discord edits** (edit the message as sentences arrive): noisy and risks rate
  limits; we post the full text once at generation-end (which lands mid-playback) instead.
- **Re-implement the sanitizers incrementally** rather than recompute-and-diff at `finish()`: the
  global self-correction frame (`_META_SELFCORRECT`) can retroactively drop already-spoken text, so
  a pure incremental emitter can't guarantee parity. Recompute-with-`finalize_answer` does; the rare
  divergence (a mid-text self-correction) is logged and the canonical remainder is still spoken.

## Consequences

- **Positive:** first audio plays after the **first sentence** is generated + synthesised, not the
  whole turn; generation and playback overlap; history/spoken text stay identical to the batch path;
  the dice button appears while the DM still speaks (folds in D40). Suite 136/136.
- **Binding:** `finalize_answer` is now the single source of truth for the post-processing chain —
  change the sanitizers there, not inline. The streaming path needs a TTS backend; text-only runs
  use the batch path. `StreamAssembler` carries the hold-back contract; its parity is unit-tested.
- **Known limitation:** a rare mid-text self-correction frame can cause a sentence to be spoken that
  the canonical answer later drops — logged as a WARNING; history still stores the canonical text.
- **To verify live:** `[latency] first_audio=` markedly below the old (`trigger→llm_done + tts`)
  silent gap; the spoken answer still clean (no preamble / 'Was tut ihr?' / markers); pause + redo
  behave; `DM_STREAMING=0` reproduces the old single-WAV path.
