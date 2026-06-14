# ADR 020 — Visible step-wise shutdown + non-blocking TTS at exit

- **Status:** Accepted (code-complete; live verification pending)
- **Date:** 2026-06-13
- **Refs:** decision log D44 in `progress.md`; supersedes the bare dots animation of the
  two-stage Ctrl+C (the **D27/ADR 013** groundwork is unrelated — that's pause, this is exit);
  touches **ADR 017** (streaming synth pipeline) by changing how its synth threads are spawned.
  Suite 157 → 181 (note: count includes adventure/RAG tests landed between sessions).

## Context

Tobi: "der Bot geht nur sehr schwer aus und neuerdings dauert das sehr lange" — and he wanted
to see *what* is being shut down and *how many* things. Two separate problems:

1. **Slow exit.** TTS synthesis ran via `asyncio.to_thread`, i.e. on asyncio's **default
   ThreadPoolExecutor**, whose worker threads are **non-daemon**. At interpreter exit Python
   joins them. A streamed turn (ADR 017) keeps a synth thread near-permanently busy, so a Ctrl+C
   landing mid-synth blocked the whole shutdown for the synth's full remaining time (seconds of
   GPU XTTS). The WAV being produced is worthless once we're quitting, so that wait buys nothing.

2. **No feedback.** The second Ctrl+C painted a single animated `Shutting down...` dots line with
   no structure — the operator couldn't tell which teardown stage (STT join, Ollama client, RAG
   retriever, bridge, gateway) was running or stuck, or how many remained.

## Decision

New module **`dmbot/shutdown.py`** with two pieces:

- **`to_daemon_thread(fn, *args)`** — an `asyncio.to_thread` replacement that runs `fn` on a
  **daemon** thread and awaits its result over `loop.call_soon_threadsafe`. The interpreter
  abandons daemon threads at exit, so an in-flight call can never delay shutdown. Both synth call
  sites (`_speak` and the streaming `synth_worker`) use it. An `_inflight` counter (lock-guarded)
  tracks running jobs so the final summary can name abandoned work. **Scope:** only TTS synthesis
  — work whose output is moot once we exit. STT/LLM/bridge close paths keep their normal threads.

- **`ShutdownProgress` (singleton `progress`)** — a thread-safe `[i/n] label` console display. A
  painter daemon animates the *current* step; finishing a step rewrites the line with `✓` + its
  duration; `finish()` prints a `done/total in Ns` summary that names any abandoned daemon work.
  Outside a shutdown (`begin()` never called) `step()` degrades to a plain log line, so a cog
  unloaded at **runtime** (not exit) prints nothing.

**`DMBot.close()` override** declares the total step count up front —
`len(voice_clients) + Σ cog.TEARDOWN_STEPS + 1` — disconnects each voice client as its own step,
runs each cog's `cog_unload` (which wraps its four closes — STT/LLM/RAG/bridge — in `progress.step`),
then closes the Discord connection as the final step. `is_closed()` guards against the double-call
that `commands.Bot.close()`'s own cog loop would otherwise cause. `VoiceReceiveCog.TEARDOWN_STEPS`
is a class constant kept in sync with its `cog_unload` body.

## Alternatives

- **Just mark the executor threads daemon / use a custom daemon executor:** would fix the join-block
  globally but also for work we *do* want to finish (none today, but fragile). A targeted helper at
  the two synth sites keeps the "abandon only TTS" intent explicit and local.
- **Bounded join with a timeout instead of daemon threads:** still waits up to the timeout on every
  exit for nothing, and a too-short timeout truncates a real (non-synth) close. Daemon-abandon is
  zero-wait and only applied where truncation is harmless.
- **Cancel the synth mid-call:** XTTS synthesis isn't cooperatively cancelable; the thread would run
  to completion regardless. Abandoning the *result* is the only lever we actually have.
- **Keep the dots, just log each stage:** the log already records stages; the ask was a visible,
  counted display at the terminal during the (now short) teardown. A structured `[i/n]` line is that.

## Consequences

- **Positive:** Ctrl+C returns promptly even mid-synth; the operator sees each teardown stage, its
  duration, the remaining count, and whether synth work was dropped.
- **Binding:** any cog added to `DMBot` that does async teardown should define `TEARDOWN_STEPS` and
  wrap each close in `progress.step(...)`, or the up-front count under-reports (the display still
  works, the denominator is just low). New "abandon-on-exit" work uses `to_daemon_thread`; anything
  that must finish before exit keeps `asyncio.to_thread`.
- **Risk:** a dropped synth on exit means the last sentence may not play — acceptable, we're quitting.
  The `TEARDOWN_STEPS` constant can drift from `cog_unload`; a wrong count is cosmetic, not fatal.
- **To verify live:** Ctrl+C twice during a streamed DM turn → shutdown is prompt (no multi-second
  hang) and prints `[1/n] … ✓` per stage plus a summary naming the dropped synth.

## Addendum (2026-06-14, D67) — bound the voice disconnect confirmation wait

A later run showed the **"Voice-Channel verlassen"** step itself as the slow stage (up to ~30s),
even though the bot left the channel instantly. Root cause was **not** our code: discord.py's
`VoiceClient.disconnect(force=True)` does the real leave first (closes the voice ws + UDP socket),
then in `VoiceConnectionState.disconnect` (`voice_state.py`) **awaits a gateway `voice_state_update`
confirmation for up to `VoiceClient.timeout` = 30s** (`wait=True` is hardcoded). At exit that
confirmation often doesn't arrive promptly (the main gateway is closed in the very next step), so
the step hung. The wait only guards a disconnect→immediate-reconnect race — moot when quitting.
(Likely resurfaced with the discord.py voice-state rewrite, which introduced this confirmation wait;
the recv reader is **not** involved — its `stop()` runs on a non-joined daemon thread.)

**Fix:** new `dmbot/shutdown.py` helper **`disconnect_voice(vc, timeout=VOICE_DISCONNECT_TIMEOUT=2.0)`**
wraps `vc.disconnect(force=True)` in `asyncio.wait_for`; `DMBot.close()` calls it per voice client
and logs a `voice confirm wait abandoned` warning on timeout. Safe because the network leave happens
*before* the wait, and discord.py catches the resulting `CancelledError` and still runs its own
`cleanup()`. Suite 309 → **311** (+2 `disconnect_voice` tests in `tests/test_shutdown.py`).

**Note vs. the "bounded join" rejected above:** there, daemon-abandon was the zero-wait lever for
*our* synth threads. Here the blocking `await` lives **inside** discord.py's own coroutine — we have
no daemon lever — so a bounded `wait_for` is the correct (and only clean public-API) tool, and it
truncates nothing real (the leave already happened).
