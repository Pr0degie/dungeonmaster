# ADR 012 — Phase 8 dice flow: difficulty ladder, minimal character store, marker grammar

- **Status:** Accepted
- **Date:** 2026-06-07
- **Refs:** decision log D26 in `progress.md`; ADR 005 (generic engine + profile), ADR 004
  (test marker + character JSON), ADR 001 (IM specifics); `architecture.md` §7 + §9

## Context

Phase 8 builds the deterministic core: the LLM *requests* a test, code *rolls and resolves* it
(golden rule #2). ADR 004 sketched the marker as `<<TEST Perception +10>>` — an **explicit
numeric modifier from the LLM**. But the playtests (open item K) showed the table wants the GM to
roll **for** the player with the **difficulty coming from the rulebook/profile, not improvised by
the model**. A raw `+10` from a 12B model is exactly the LLM inventing a number. We also hit open
item F: the model confuses the Discord display name ("SezBoss69") with the character ("Seskin").

Three intertwined questions had to be settled before writing the engine: where the difficulty
number comes from, whether character stats exist yet, and how to seed turn order.

## Decision

1. **Difficulty is a *word*, resolved to a number in code (the difficulty ladder).** The profile
   declares a `difficulty_ladder` (name → modifier) and a `default_difficulty`. The marker carries
   a rung name (`<<TEST Wahrnehmung Schwer für Tobi>>`); the engine maps *Schwer* → −20. The LLM
   never emits the number. An explicit `±N` is still accepted as a **manual override** (kept from
   ADR 004), but the primary path keeps the number in code. The target is then fully code-resolved:
   `target = skill value + difficulty modifier`.

2. **Pull a minimal character store into Phase 8** (rather than waiting for Phase 9 memory).
   Characters live as lean JSON (`data/sessions/<channel>/characters.json`, ADR 004), the *shape*
   following the profile schema. This is what lets the engine resolve the skill value, so the GM
   rolls *for* the player. The same file carries a **display-name → character alias map**, injected
   as a light prompt hint — which also addresses open item F. An example party ships so the engine,
   `!test` and the unit tests run out of the box; the real sheets are transferred once by hand.

3. **Turn order is seeded from the voice-channel members** at `!join` (Bot A + bots filtered),
   preferring each player's character name via the alias map. No registration flow (ADR 003's
   guided registration stays a later concern); a rotate-button view (`discord_ui/turnorder.py`)
   covers the Phase-8 gate ("turn order rotates").

4. **Marker parsing is a pure, tolerant module** (`rules/marker.py`): it strips every `<<TEST …>>`
   from the spoken text (so TTS never reads it) and returns structured requests; an unparseable
   marker still yields a generic manual button (ADR 004 fallback). The engine
   (`rules/engine.py`) stays system-agnostic with a resolver registry — IM `roll_under` first.

## Alternatives

- **Explicit numeric modifier from the LLM (original ADR 004 example):** simplest, but the number
  comes from the model — weakens "dice = code" and contradicts open item K. Kept only as an override.
- **Manual-button-only (engine rolls, target typed in):** fully deterministic but least automatic;
  the GM-rolls-for-you feel the table asked for would be lost.
- **Defer character stats to Phase 9:** the marker/test would carry an explicit target, leaving the
  engine unable to roll stat-aware now. Rejected — it's the heart of K, and a lean JSON party is
  cheap. (Full guided registration, ADR 003, is still deferred.)
- **Turn order from the character JSON:** ties turn order to registration; the voice channel is a
  zero-setup source that's correct often enough.

## Consequences

- **Positive:** the number behind a test lives in the profile/character data, never the LLM; the GM
  rolls for the player; the alias map quietly fixes F; one hand-written IM profile + an example
  party make the whole flow testable and demoable immediately.
- **Binding:** the profile must carry a `difficulty_ladder` + `default_difficulty`; the character
  JSON schema follows the active profile (D12); the persona now documents the marker grammar and
  the allowed difficulty words.
- **Verified against the rulebook (2026-06-07):** the IM Core Rulebook was converted with the new
  `tools/pdf_to_md.py` and the profile numbers confirmed/corrected against it — Difficulty Table
  (Very Easy +60 … Very Hard −30), SL = tens-difference, Automatic Success/Failure 01–05/96–00 as
  *Marginal* (engine now sets SL 0 + suppresses crit/fumble on an auto result). Two corrections:
  crit/fumble-on-doubles is IM's **combat** rule (a double on a Melee/Ranged attack Test with
  positive SL = Critical; on a failure = Fumble) — flagged, not silently universal; and damage is
  **weapon Damage + SL**, not the inherited d10/d5 guess. Everything still lives in the editable
  profile JSON — nothing hardcoded. (Phase 10's RAG bootstrap will later propose such profiles
  from the PDF automatically.)
- **Prerequisite (human):** transfer the real party's sheets into `characters.json` once
  (`docs/SETUP.md`); until then the example party stands in.
