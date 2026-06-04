"""Rules: a GENERIC dice + resolution engine (engine.py) driven by the active system profile
(data/systems/<system>.json), plus the profile loader. Fully decoupled from the LLM: the LLM
requests a test via marker, this engine rolls (RNG) and resolves (success, degrees, damage).
No single game is hardcoded — IM is just the first profile. Pure functions, unit-tested with a
fixed seed. Phase 8 (engine + hand-written IM profile); profile bootstrap from PDF in Phase 10."""
