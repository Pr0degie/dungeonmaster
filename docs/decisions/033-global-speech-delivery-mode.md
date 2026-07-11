# ADR 033 — Global spoken-delivery mode (delivery × intonation, runtime-switchable)

- **Status:** Accepted
- **Date:** 2026-06-14
- **Refs:** decision log D68 in progress.md; builds on ADR 031 (intro monologue + the seamless
  one-track delivery, D64/D65/D66) and ADR 002 (LLM offload → GPU); see also ADR 016/D53/D55
  (XTTS punctuation babble) and ADR 017 (streaming pipeline).

## Context
The `!intro` work surfaced two independent levers on how a DM turn is *spoken*, and Tobi wants to
settle on **one** style for **all** spoken output ("alle gesprochenen Texte … damit sich das besser
anhört und der keine Anfälle kriegt"). The two levers, learned over the session:
- **Delivery:** stream sentence-by-sentence (`_deliver_streaming`, fast first audio but audible
  inter-sentence gaps) vs. synth-the-whole-turn-then-play-one-continuous-track (`_speak_seamless`,
  gapless but waits for the full synthesis). `!intro` vs `!intro test` are exactly these two; they
  speak the *same words with the same synthesis* — the only audible difference is gaps vs. continuous.
- **Intonation:** strip ALL punctuation (no XTTS babble/"Anfälle", D55, but flatter) vs. keep
  `.,!?;:-` (the wrapper's `normalize_for_tts` — sentence/question prosody, but XTTS may babble).

Tobi prefers the **continuous** (nahtlos) sound; its only downside is the up-front synthesis wait,
which is a property of **XTTS running on CPU** (`.env TTS_DEVICE=cpu`, deliberate — the 4070 VRAM is
full with nemo + Whisper; cuda XTTS crashes the process, ADR 002). On CPU, fast-start and gapless are
mutually exclusive (synth is slower than realtime). He wants to A/B both axes live before committing.

## Decision
Make spoken delivery a **global, runtime-switchable mode over two orthogonal axes**, applied to
**every** DM turn (normal turns, `!start`, `!intro`, after-roll narration, auto-turns):
- `DM_SPEECH_MODE` = `stream` | `nahtlos` (delivery).
- `DM_SPEECH_PUNCT` = `flach` | `intoniert` (intonation).
Both are read from `Config` into `SessionRuntime` and exposed via two helpers
(`speech_transform()` → `strip_speech_punctuation` for `flach` else `None`; `deliver_seamless()`)
and a live command **`!sprechmodus [stream|nahtlos] [flach|intoniert]`** (aliases `!sprache`,
`!voicemode`). The six turn-dispatch sites read these helpers instead of hardcoding the path; the
delivery methods (`_deliver_streaming`, `_deliver_answer`/`_speak`/`_speak_seamless`) pull the
transform/seamless flag from the runtime rather than taking per-call args. **Default `stream` +
`flach`** (consistent, gibberish-free, practical on CPU). `!intro test` stays a fixed
`nahtlos`+`flach` comparison anchor regardless of the global mode.

## Alternatives
- **Keep it intro-only (`!intro` vs `!intro test`):** rejected — Tobi wants the chosen style for
  *all* spoken text, and a fair A/B needs to hear both on normal conversational turns too.
- **One axis only (just stream vs seamless, always punctuation-free):** rejected — Tobi noticed the
  flatness and wants to test an intonation-preserving variant too, hence the second axis.
- **Default `intoniert` (preserve today's normal-turn sound):** rejected — it would regress the
  intro back to babble by default and isn't the gibberish-free end state Tobi is steering toward.
  Default is `flach`; normal turns become punctuation-free by default (documented; flip with
  `!sprechmodus intoniert`).
- **Prep the GPU offload now so `nahtlos` is fast everywhere:** deferred (Tobi: "nur den
  Umschalter"). The offload (Ollama → 5080/Tailscale → `TTS_DEVICE=cuda`, ADR 002) is the real
  enabler for `nahtlos`-everywhere and is tracked separately.

## Consequences
- **+** Tobi can A/B both axes live on any turn and settle by setting two env vars; reuses the
  existing two delivery paths + the D66 transform plumbing, so little new code (one generalised
  `_speak_seamless`, the `!sprechmodus` command, the config/runtime knobs).
- **+** Delivery methods read the mode from the runtime, so the six dispatch sites change only their
  path-selection condition — no per-call threading.
- **−** `nahtlos` on CPU waits for the whole turn's synthesis before any audio (~seconds for short
  turns, minutes for the intro) — only fluid for live play on a GPU. Surfaced in the `!sprechmodus`
  reply and docs.
- **−** Default `flach` makes normal turns punctuation-free (flatter) than before; intentional, one
  command reverts it per session.
- **Binds later work:** once the LLM is offloaded (ADR 002), `nahtlos` everywhere becomes the likely
  default — that's a one-line flip; the seamless mid-track pause limitation (Esc takes effect after
  the current track) carries over from the `!intro test` delivery.

## Addendum (2026-06-14) — `puffer` head-start mode (D69)

Tobi's idea ("warum lädst du nicht die ersten 3 Sätze und spielst den ersten ab und lädst die
anderen parallel?"): a **head-start buffer** on the streaming pipeline — synthesise the first N
sentences before the first plays, then keep synthesising in parallel. Added as a **third delivery
value** `puffer` (between `stream` and `nahtlos`): the `_deliver_streaming` `play_worker` accumulates
`DM_SPEECH_PREBUFFER` (default 3) WAVs before the first playback (`wav_q` maxsize bumped to the depth
so the cushion is held during playback); `prebuffer == 1` is exactly the old `stream` behaviour. A
number in `!sprechmodus` sets the depth live (`!sprechmodus puffer 4`). Buffered-but-unplayed WAVs
are removed in `play_worker`'s `finally` (no leak on pause/abort).

**Why it's a middle point, not a free lunch (CPU):** the buffer *cushions* CPU synth running slower
than realtime, so gaps appear later. For **short turns** (2–5 sentences) a depth-3 buffer usually
covers the whole turn → near-gapless with a modest start delay. For the **long intro** (~32 sentences)
it only delays the gaps — synth still falls behind — but it starts far sooner than `nahtlos`. A small
inter-sentence bridge gap remains (each sentence is its own `/speak`); truly gapless still needs
`nahtlos` (or a GPU). So `puffer` is the tunable compromise; the full fix for gapless-everywhere
remains the GPU offload (ADR 002).

## Addendum — detail preserved from decision log D68 (2026-07-11)

- The six turn-dispatch sites that read the mode instead of hardcoding the path are `!dm`, `!redo`,
  `!start`, `!intro`, `_auto_dm_turn` and `_run_and_deliver`.
- The knobs are wired `Config.speech_mode`/`Config.speech_punct` → `runtime._speech_mode`/
  `runtime._speech_punct`, exposed via the two runtime helpers.
- The generalised `_speak_seamless(text, …, transform=…)` (formerly `_intro_speak_seamless`) is
  reused by `_deliver_answer` (nahtlos) and by `!intro test`.
- +6 tests; suite **316 green**.

## Addendum — detail preserved from decision log D69 (2026-07-11)

- The prebuffer depth is exposed via a new `runtime.prebuffer_count()` helper.
- +3 tests; suite **319 green**.
