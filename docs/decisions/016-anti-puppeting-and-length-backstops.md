# ADR 016 — Curbing LLM puppeting & runaway length with deterministic backstops

- **Status:** Accepted (code-complete; live verification pending)
- **Date:** 2026-06-10
- **Refs:** decision log D37/D38 in `progress.md`; playtest-tuning rounds 2026-06-09/10; builds on
  **ADR 014** ("don't trust the model — add a deterministic step") + **ADR 012** (character store /
  alias map) + ADR 005 (generic engine); persona `prompts/dm_core_de.md`; D35 (`[latency]` line).
  Commits `17adcfe` / `dc33d64` / `f36b5de` / `4564ecb`.

## Context

Three live sessions (logs pasted by Tobi: one 2026-06-09 box, two from one continued 2026-06-10
session — **all pre-change**) surfaced one dominant, repeatedly-voiced failure and its hidden cost.

- The DM **spoke and acted for the player characters** — scripting `Pr0degie: …`, `Seskin: …`,
  `Als Spielleitung beschreibe ich: …` for the whole party. Players: *"hat noch nicht gerafft, dass
  es mehrere Spieler gibt"*; one dictated a corrected persona aloud (*"… du spielst nur die Rolle
  der NSCs, Gegner und Umgebung. Du erzählst keine Geschichte von selbst."*).
- The `[latency]` instrumentation (D35) revealed that **this puppeting IS the latency**: a scripted
  turn ballooned to 700+ chars, and since each spoken char ≈ 0.1 s of XTTS audio that Bot A's
  blocking `/speak` waits through, single turns ran `wav=55–80 s`, `total` up to **183 s**. Clean
  short turns ran ~15 s.

The persona **already** forbade puppeting in several rules, and nemo ignored them across all three
sessions — a model-adherence problem, not a missing instruction. This is the same shape ADR 014
already faced with dice markers (the model won't reliably emit/obey, so add a deterministic step).

A separate, concrete player wish (W6): XTTS reads quotes/punctuation aloud (*"er liest die
Interpunktion mit vor — Komma, Punkt, Ausrufezeichen … das ist Müll"*); the TTS path had **no** text
normalization.

## Decision

**1. Deterministic speaker-label backstop (chosen), plus prompt reframing.** Two layers:
- *Prompt:* positive, hoisted-to-top persona scoping (the DM voices **only** NSCs/enemies/
  environment, never speaks/thinks/acts for the PCs, plays *with multiple players*), and the alias
  hint reframed from a neutral cast list ("Am Tisch: X spielt Seskin; …") into a hard boundary
  ("these figures belong to the players, never control them"), placed **last** for recency.
- *Code (the actual fix):* `CharacterStore.speaker_labels()` (every character + player name) is
  registered on the brain via `DMBrain.set_known_speakers` (wired on join) and joins the turn's own
  speakers as `_cut_at_labels` cut-points **and** Ollama stop sequences. An appended `Seskin: …` /
  `Pr0degie: …` script is truncated post-hoc **even when those names didn't speak this turn**. This
  kills the puppet *display* and the runaway *length* in one move — it does not depend on the model
  obeying.

**2. Tighter length ceiling.** `num_predict` 220 → 160 and the persona's brevity rule sharpened to
"zwei bis drei kurze Sätze, die Gruppe wartet beim Vorlesen" — a hard cap on genuinely-long-but-
legit narration (e.g. a bar-scene description that hit the 220 cap at 776 chars). The orchestrator
already trims a capped turn to its last full sentence.

**3. Speech-only TTS normalization (W6).** `normalize_for_tts()` (in `tts/textsplit.py`, applied in
both XTTS + Piper `synthesize`, **never** to the Discord post): drop quotation marks of every
flavour, brackets and stray symbols; map the ellipsis + em/en dashes to a pause; **keep**
`. , ! ? ; :` (they carry the intonation players want — *"durch die Betonung erkennt man es
sowieso"*) and word hyphens (Hive-Stadt). Also fixed XTTS's single-chunk branch, which had
synthesised the raw text instead of the processed chunk.

**4. Robustness.** `!npc add` parses wounds/TB/armour tolerantly (clear usage hint instead of the
`BadArgument` traceback that blocked the Phase-9 gate); `_sanitize` drops a "…als Sprachmodell …
Hier ist die korrekte Antwort:" self-correction frame the model emitted once.

## Alternatives

- **Prompt-only (strengthen the persona, no code guard):** it already forbade puppeting and nemo
  ignored it across three sessions. Rejected as insufficient alone; kept as the first layer.
- **Aggressive PC-dialogue stripper** (drop any sentence whose subject is a player character):
  would catch inline puppeting without a leading `Name:` label, but risks gutting legitimate
  attribution ("auf **Seskins** Worte hin …") and is hard to get right without live iteration.
  Deferred; the label-cut covers the observed `Name:`-script shape, which is what actually occurred.
- **Bigger/other model:** the gemma3-vs-nemo taste test (D29/ADR 014) already showed this class of
  failure is model-size-independent and nemo's tone is preferred. Same reasoning here.
- **Strip all punctuation for W6:** kills prosody **and** the sentence splitter (`[.!?…]`).
  Rejected — keep the prosody-bearing punctuation, strip only what XTTS verbalises.

## Consequences

- **Positive:** the puppet-script cannot reach the channel/voice even when the model emits it; turns
  shrink, cutting the dominant latency **without** touching the (Part-2) streaming-TTS work; the
  spoken text is cleaner; `!npc add` no longer crashes the gate. Suite 113/113.
- **Binding:** `speaker_labels` are part of the per-channel turn setup; the brain carries a
  `_known_speakers` map (cleared on `reset`); `num_predict` default is 160 (env `DM_NUM_PREDICT`).
  `normalize_for_tts` sits on the spoken path only.
- **To verify live (this round's logs were all pre-change — none of it is proven yet):** no more
  `Name:` / „Als Spielleitung beschreibe ich:" scripts (W1); `[latency] wav=/total=` markedly lower
  (W2 cheap win); XTTS no longer reading quotes/punctuation (W6 — confirm by ear). **Open player
  wishes not addressed here:** within-session repetition (W4), answering the *exact* question asked
  (W5), engaging provocative content (W8) — persona/adherence/Phase-9 items; deep latency (W2) is
  Part-2 streaming TTS. The Phase-9 memory gate (HP survives restart + recap) is still unrun.

## Follow-up (2026-06-13, D53) — TTS normalization hardened to a whitelist

Decision #3's `normalize_for_tts` was a **blocklist** (it dropped only an enumerated set of
ASCII/Latin-1 symbols + smart quotes). Live, the voice still spoke gibberish "especially at
punctuation" — the blocklist missed **emojis** (🎲🌀🜏💥, including the engine's `describe_*`
glyphs the model can echo), **arrows/bullets/middle-dot** (→ • ·), dash/minus variants and exotic
whitespace; none of which show in the transcript. Two changes (suite 233):
- `normalize_for_tts` is now a **whitelist**: NFKC-normalize, map dash/minus variants + ellipsis to a
  spoken pause, then keep only letters/digits/whitespace and `. , ! ? ; : -`, dropping everything
  else. Future stray glyphs can't leak through. It may now legitimately return `""`.
- A **per-chunk speakability guard**: `chunk_text` drops chunks with no letter/digit, and the XTTS/
  Piper `synthesize` paths emit a short silence (never call the model) when nothing is speakable —
  so a lone-punctuation chunk can't make XTTS read a bare "." for ~15 s or hallucinate.
- Deferred (only if needed after live test): XTTS `repetition_penalty` / `enable_text_splitting=False`.
