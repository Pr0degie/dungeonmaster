# ADR 041 — Make the !intro monologue reliable: fixed low temperature + a hardened director brief

- **Status:** Accepted
- **Date:** 2026-06-16
- **Refs:** decision log **D83** in progress.md. Builds on **ADR 031** (the `!intro` opening
  monologue) and **ADR 034** (`director_msgs.py`, the pure GM-side director text). Touches the
  orchestrator's opening path (`respond_opening` / `respond_opening_streaming`) and the delivery
  wiring (`_deliver_streaming`, `_deliver_intro_chunked`). Governed by golden rule #8 (German play
  content stays German).

## Context
`!intro` (and `!intro test`) was a coin-flip. The best run (2026-06-14) produced a rich, multi-
paragraph opening that established setting + mission and gave **each** named character a personal
beat from the sheet (Fridolin's Aquila brand, Gellicus the seducer, Rektalus' pleasure-houses) — the
table loved it. A later run (2026-06-16, after the party-loading fix D82 was confirmed: party loaded,
config aligned, teammate pulled) produced a short, generic turn that named **no** characters, opened
with meta-narration ("**Als Spielleitung beginne ich die Sitzung:** …") and closed like an ordinary
turn ("Jetzt seid ihr dran. Was tut ihr als nächstes?").

The director instruction and roster were both intact (verified: `intro_roster_de()` returns the full
roster, `build_intro_director_msg` embeds it). So this was not a missing-party bug — it was **model
variance**: the opening turns set no temperature, so they ran at mistral-nemo's default (~0.8). At
that temperature a 12B model intermittently *narrates* the `[Regie]` brief instead of executing it,
and bails after a few sentences. With the long, structured intro brief, that failure is frequent
enough to ruin the campaign opener.

## Decision
Two changes, one commit, targeting reliability rather than a single bug:

1. **A fixed, lower temperature for `!intro` only.** New config `dm_intro_temperature` (env
   `DM_INTRO_TEMPERATURE`, default **0.5**), stored as `SessionRuntime._intro_temperature`. It is
   threaded as an optional `temperature` parameter parallel to the existing `num_predict` through the
   opening path: `respond_opening` / `respond_opening_streaming` → `_generate` / `_stream_and_store`
   → `_chat_once` → `_build_request`, which adds `"temperature"` to the Ollama options **only when
   set**. `!start` and every normal turn pass `None` → the model default, unchanged. Both `!intro`
   (streaming, via `_deliver_streaming(opening_temperature=…)`) and `!intro test` (batch, via
   `_deliver_intro_chunked`) forward the runtime value.

2. **A hardened director brief** (`director_msgs.py`, applies to both intro variants):
   - HEAD: "Beginne sofort als Erzähler mitten in der Szene — schreibe **NICHT**, dass du die Sitzung
     eröffnest oder was du als Spielleitung gerade tust, und kündige den Monolog nicht an" + ask for
     "mehrere Absätze". Kills the "Als Spielleitung beginne ich…" meta-open.
   - TAIL: "nimm dir Raum … darf deutlich länger sein", and "Schließe ihn stimmungsvoll ab und lade
     die Gruppe in die Szene ein … brich nicht nach wenigen Sätzen mit einer knappen „Was tut
     ihr?\"-Frage ab." Kills the curt normal-turn close while still allowing a thematic invitation
     (the good run ended by asking which lead they follow).

Suite **376 green** (+2: `temperature` reaches options when set, and is absent by default so normal
turns are untouched). The existing director-shape asserts (`[Regie]` / `Monolog` / `Probe` /
`folgenden Figuren`) still hold.

## Alternatives
- **Director hardening only, no temperature:** rejected as insufficient — the failure is sampling
  variance; a stronger brief lowers but doesn't remove it at temp ~0.8. The two changes are
  complementary (better instruction + steadier sampling).
- **Temperature 0 (greedy):** rejected — kills the flair that made the 2026-06-14 opener great; the
  intro is the one turn where some richness is wanted. 0.5 is the steadier-but-still-creative middle,
  tunable by ear via the env (like `DM_INTRO_NUM_PREDICT`).
- **A global default temperature for all turns:** rejected — normal turns are fine at the model
  default; only the long, structured intro brief exposes the variance. Scope the change to the
  opening to avoid perturbing the rest of play.
- **Hidden instance attribute instead of threading a parameter:** rejected — `num_predict` is already
  threaded explicitly through these methods; a parallel `temperature` parameter matches that pattern
  and is greppable, where a mutable `self._opening_temperature` read deep in `_build_request` could
  leak across interleaved channel turns.

## Consequences
- **+** `!intro` reliably produces the long, character-weaving monologue instead of a coin-flip; the
  observed "meta-open + generic + no figures" failure mode is directly addressed by both levers.
- **+** Tunable without code (`DM_INTRO_TEMPERATURE`), consistent with `DM_INTRO_NUM_PREDICT`.
- **+** Normal turns, `!start`, redo and streaming play are provably unchanged (temperature omitted →
  model default; the +1 test pins this).
- **−** One more config knob and a `temperature` parameter on six orchestrator methods (mechanical,
  mirrors `num_predict`). The right value is empirical — 0.5 is a starting point to tune live.
- **Live-unverified:** the quality win is a model-behaviour claim; confirm at the table and adjust
  `DM_INTRO_TEMPERATURE` / the brief wording if nemo still wanders.
