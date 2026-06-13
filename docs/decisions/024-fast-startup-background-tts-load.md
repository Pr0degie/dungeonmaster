# ADR 024 — Fast startup: background TTS load + parallel Ollama warm-up

- **Status:** Accepted (code-complete; live verification pending)
- **Date:** 2026-06-13
- **Refs:** sibling to **ADR 020** (visible/fast *shutdown* — this is the *startup* counterpart);
  touches **ADR 017** (streaming synth pipeline — the synth call sites) and **ADR 008/009**
  (Piper/XTTS engine + GPU load); see the 2026-06-13 startup entry in `progress.md`. Suite 230.

## Context

Tobi liked the fast, visible shutdown (ADR 020) and asked whether the bot could also **start**
a bit faster. Two costs ran **synchronously** before the bot was "ready":

1. **XTTS/Coqui load** (a `torch` import + a multi-second GPU model load) ran inside the cog's
   `__init__`, blocking `setup_hook` → `on_ready`.
2. **`start_dmbot.bat`'s `ollama run` warm-up** (~15 s on a cold start) ran *before* the bot
   launched at all.

The old eager design was **deliberate**, not accidental slowness — it bought two robustness
properties we must not lose (Tobi: "ich möchte, dass der Bot robust und zuverlässig ist"):
- **Fail-fast & visible:** a broken model/DLL surfaced *at boot* ("Started here so a broken
  cuDNN surfaces at boot"), not mid-game.
- **First-turn-instant:** the LLM was resident before the bot needed it, so the first DM turn
  couldn't hit a cold-load timeout (there was a real cold-start `ReadTimeout` incident).

The constraint: remove the boot block **without** weakening that robustness.

## Decision

**Move the heavy loads off the critical boot path, then restore fail-fast by other means.**

- **TTS loads on a daemon thread.** `on_ready` fires immediately. A new `_tts_enabled` flag
  ("a backend is configured and hasn't failed") drives the *is-speech-on* checks
  (`_use_streaming`, `_speak`, `!say`/`!lore`), replacing the old `self._tts is not None` test.
  A `_synthesize()` helper waits on a `threading.Event` `_tts_ready` **inside the worker thread**
  (`to_daemon_thread`), so the wait never blocks the event loop; the first spoken line waits for
  the model only if it's still loading — virtually always done before anyone `!join`s and speaks.
- **Hardening (keeps the old fail-fast intent):**
  - **Bounded wait:** `_synthesize` waits at most `_TTS_LOAD_TIMEOUT_S` (90 s); a hung load
    degrades to **text-only** (disable speech + loud `ERROR`) instead of freezing every line.
  - **Loud boot logging:** `loading TTS '…' in the background` → `ready in N s`, or a prominent
    `ERROR` on failure — visible despite being off the critical path.
  - **`!join` guard:** announces "⚠ no speech" / "⏳ still loading" once, so the table isn't left
    wondering about silence.
- **Parallel Ollama warm-up:** `start_dmbot.bat` backgrounds the `ollama run` model load
  (`start "" /b …`) so it overlaps the bot's startup + Discord connect instead of preceding it.
  Single-GPU Ollama just queues the first turn behind the warm-up if it isn't done; the 300 s read
  timeout (ADR 017 follow-up) covers the race. The boot-time `check_ollama` preflight (reachability
  + model pulled) is **unchanged** — only model *residency* is deferred, not the reachability check.

## Alternatives

- **Keep the eager load.** Simplest and fail-fast, but blocks boot for seconds every start — the
  exact cost we set out to remove.
- **Lazy-on-first-synth (like the STT model).** Also frees the boot path, but the first spoken line
  pays the whole load, and the model is *not* warm by first use; the background preload is strictly
  better (usually warm by the time anyone speaks) for the same boot speed.
- **Block the event loop on `_tts_ready.wait()` in `_speak`.** Would freeze the loop while the model
  loads; waiting *inside the worker thread* avoids that — the loop stays responsive.
- **Bounded join / timeout on an eager load.** Still waits at boot for nothing; the daemon-thread
  approach is zero-wait on the critical path.

## Consequences

- **Positive:** the bot reaches `on_ready` immediately; the Ollama warm-up overlaps boot. Robustness
  is preserved — graceful text-only on failure (as before), a hung load can't freeze speech, the
  failure is loud, and Ollama reachability is still checked at boot.
- **Trade-off (documented):** a TTS *failure* now surfaces a few seconds later (background log + the
  `!join` notice) rather than synchronously at the "starting" instant — mitigated by the loud
  logging and the join guard. The first spoken line may wait briefly if the load isn't finished
  (rare; capped at 90 s, then text-only).
- **Binding:** `self._tts is not None` is no longer the "speech enabled" predicate — use
  `_tts_enabled`. New heavy boot-time loads should follow this shape (daemon thread + readiness
  event + enabled flag + bounded wait + loud outcome log), not block `setup_hook`. Work that must
  be ready before the bot serves a turn still belongs in the boot preflight, not a background thread.
- **To verify live:** the console reaches `logged in as …` quickly; `!join` shows the ⏳/⚠ notice
  when relevant; the first DM sentence is still spoken.
