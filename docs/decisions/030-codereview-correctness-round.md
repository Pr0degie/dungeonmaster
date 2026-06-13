# ADR 030 — Code-review correctness round (post-cog-split)

- **Status:** Accepted
- **Date:** 2026-06-13
- **Refs:** decision log D61 in progress.md; follows the day's feature work (ADR 022 psyker,
  ADR 026 auto-scene, ADR 027 auto-recap, ADR 029 cog split); relates to ADR 005
  (system-agnostic engine), ADR 016/017 (delivery), ADR 003/013 (feedback mute / pause)

## Context

After the day's heavy feature accretion (psyker/warp, augmetics, auto-scene marker, auto-recap,
the cog split) Tobi asked for a `/code-review` over the day's commits with the constraint **"die
Funktionalität soll bleiben"**. A multi-agent review (9 finder angles + per-finding verifiers over
`5d672b6~1..HEAD`) cleared the cog split itself as behaviour-faithful and surfaced a set of real
defects in the **parallel feature work**, plus cleanup/efficiency items. This ADR records the round:
what was fixed, the few choices that had a real trade-off, and — deliberately — what was **not**
done and why.

The headline correctness defects (all verified against the code, not guessed):

1. **Warp-containment Test rolled against the wrong characteristic.** The "do Perils erupt"
   containment Test used `resolved.base` — the *Psi-Meisterschaft* skill value — instead of
   *Disziplin (Psi)* (IM p.163). The profile already declared `purge_skill: "Disziplin (Psi)"` and
   exposed `psyker_purge_skill()`, but nothing called it. A strong-Mastery/weak-Discipline psyker
   held the Warp far too easily.
2. **A party psyker not seeded into the WorldState had its Warp Charge silently dropped.** The
   bookkeeping was gated on `combatant is not None`; with the psyker absent, the Manifest rolled and
   showed but Warp Charge never accumulated (reset to 0 each call) and Perils never fired.
3. **The dice button was lost when the batch speak task raised.** `_deliver_answer` fire-and-forgot
   `dice_task`/`scene_task` and awaited them *after* `await speak_task` with no `finally`; a bridge
   error skipped the dice post and orphaned the tasks' exceptions.
4. **Auto-recap could drop a turn.** `clear_history` popped the whole history after `summarize`
   awaited the LLM (seconds); a dice turn appended during that await was lost from both recap and
   history.
5. **Glued markers leaked into TTS.** `<<\s*ORT\b…>>` (and TEST/MANIFEST) failed to match a marker
   with no separator (`<<ORT1>>`, `<<ORTmud_gate>>`, `<<MANIFESTSmite>>`): the marker survived into
   the spoken text and the action never fired.
6. **`resolve_test` swallowed genuine errors.** `try: resolver(…, advantage=…) except TypeError:
   resolver(…)` caught *any* `TypeError` from inside the resolver and silently re-rolled — a second
   `rng.randint`, masking the bug (golden rule #2: no silent dice errors).
7. **Streaming delivery leaked an orphaned task + WAV on a mid-stream bridge failure.** `gather(sw,
   pw)` re-raises on the first exception without cancelling the sibling, leaving `synth_worker`
   blocked forever on the full `wav_q`. (The verified review **refuted** a "permanent mute" — the
   `finally` always unmutes — so the mute logic was left untouched.)
8. **Layer-2 feedback mute was a shared boolean, not a refcount.** Two owners (DM-speaking paths,
   operator pause/resume) drove one `_muted`; an operator resume mid-playback unmuted the VAD while
   Bot A was still speaking. (Low severity today — layer 2 is off by default and layer 1 blocks Bot
   A's own frames — but a latent breach if layer 2 ever goes default-on.)
9. **Soak lookup drifted on whitespace.** `_toughness_bonus` matched the characteristic with
   `.lower()` but not `.strip()`, so a sheet key like `"Tgh "` yielded 0 soak (full damage).

## Decision

Fix all nine, plus the cleanup/efficiency items, **without changing intended behaviour**, fanned out
across agents owning disjoint files; verify centrally with the full suite. The four choices that had a
real trade-off:

- **#2 — warn, don't auto-seed.** There is no safe way to add a single party character to the live
  WorldState: `seed_from_store` rebuilds the whole state (would wipe NPCs/quests) and `add_npc` would
  mistype a PC as an NPC. Rather than invent new state API mid-fix, a known party psyker that
  manifests outside the encounter gets a **one-time German channel warning**
  (`⚠️ Warp-Aufladung wird nicht verfolgt …`) + a log line; the in-combat path is untouched.
- **#6 — signature dispatch, not exception-catch.** `resolve_test` now decides whether to pass
  `advantage` via a cached `inspect.signature` check (`_accepts_advantage`), so any error from inside
  the resolver propagates and the d100 is drawn at most once.
- **#8 — depth counter, not bool.** `VadSink` keeps a `_mute_depth`; `mute()` increments (flush only
  on the 0→1 transition), `unmute()` decrements clamped at 0, and `_muted` becomes a property
  (`depth > 0`). Verified precondition: every caller (`_speak`, `_deliver_streaming`, `set_paused`)
  uses balanced mute/unmute pairs, so nesting is correct.
- **#1 — wire the existing, unused accessor.** Added `ResolvedManifest.contain_base` (computed from
  `psyker_purge_skill()`) and pointed the containment Test at it, rather than introducing a parallel
  skill path.

Cleanup landed alongside: a shared `SystemProfile._catalog_lookup` (de-dups `power`/`augmetic`/
`weapon_damage`), a shared `dmbot/tts/wavio.write_silent_wav` (de-dups the Piper/XTTS silent-WAV
write), removal of the dead `state.reduce_warp_charge`, dropped no-op `[:80]` slices on constant
button labels, a **thread-local cached sqlite connection** in `rag/retrieve.py` (the vec extension was
re-`dlopen`'d every call), and a `<<`-free fast path in `StreamAssembler._body` (skip the three marker
regex passes when the buffer holds no marker).

## Alternatives

- **#2 auto-seed the psyker into the encounter.** Rejected for this round (needs new, careful
  WorldState API — out of scope for a behaviour-preserving fix); the warning makes the gap visible so
  it can be designed properly later.
- **Generalise the engine now (the altitude findings).** The review flagged that `warp_charge_gain` /
  `reverse_d100`+advantage hardcode IM arithmetic into the "generic" engine; that `marker.py` +
  `finalize_answer`'s widening tuple + the three parallel `_pending_*` dicts grow per-marker; and that
  `retrieve._SOURCES` / `_is_junk_hit` are IM-/OCR-specific in code. **Deliberately deferred** — see
  Consequences.
- **One big commit.** Rejected in favour of scoped commits per subsystem so the history stays
  bisectable.

## Consequences

- **Positive:** the signature dice bug (#1) and the silent Warp-Charge drop (#2) are gone; the dice
  button and the recap survive their respective failure/race windows (#3/#4); glued markers can no
  longer be read aloud (#5); no dice error can pass silently (#6); the streaming path no longer leaks
  tasks/WAVs (#7); the feedback mute nests correctly (#8); soak is whitespace-robust (#9). Suite
  **293 green** (was 263 after the cog split; +~30 fixed-seed/unit tests across the fixed areas, one
  RAG fixture mkdir fix). RAG retrieval drops a per-call extension reload on the hot turn path.
- **Deferred debt (recorded, not forgotten):** the **system-agnostic generalisation** of the engine,
  the marker pipeline, and the RAG source catalog is **postponed to the second-profile / Phase-10b
  point** (ADR 005's profile bootstrap). Rationale: IM is by design the *first* profile (D1); there is
  no second system yet to generalise against, the changes are large and behaviour-risky, and the
  project's whole stance is "generalise when the second system actually arrives". Doing it now would be
  speculative. This binds: **when a second system is loaded, revisit `warp_charge_gain`/`reverse_d100`
  (move the charge/advantage rules into the profile), the per-marker plumbing (one keyed marker
  structure instead of three parallel dicts + an ever-widening tuple), and `_SOURCES`/`_is_junk_hit`
  (move the corpus catalog + ingest-time denoise out of `retrieve.py`).**
- **Unchanged on purpose:** layer-2 mute stays off by default (D25); the XTTS sampling levers (D55)
  and all prompt/persona text were not touched; the `marker.py` `profile` param was **not** removed
  (a test outside the owning fileset calls `extract_manifests(..., profile)` — a cross-file break was
  not worth a cosmetic cleanup).
