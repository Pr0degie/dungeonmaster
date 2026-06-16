# ADR 040 — A committed default party so the real party isn't bound to one voice-channel id

- **Status:** Accepted
- **Date:** 2026-06-16
- **Refs:** decision log **D82** in progress.md. Touches the Phase 8 character-loading path
  (`SessionRuntime._load_characters`, the D43 example-party fallback warning) and the `data/`
  git allowlist. Governed by golden rule #3 (hard state = code) and #8 (German play content).

## Context
The party is loaded per **voice-channel id**: `!join` reads `data/sessions/<channel_id>/characters.json`,
and if that file is missing it falls back to the generic `_example` party (Seskin/Vask/Mortn) with a
loud D43 warning. Two things make this brittle in practice:

1. **The repo is public**, so the `.gitignore` is an allowlist: only *named* files under `data/` ship.
   Exactly one live party — `data/sessions/1343673766487654464/characters.json` ("circlejerk") — was
   hand-allowlisted. Every other channel's `characters.json` is git-ignored.
2. **The bot runs on a teammate's clone.** A session in a *different* voice channel ("fett",
   `1355…`) has no committed sheet → on the teammate's machine the file does not exist → the
   `_example` party loads → `!intro` produces a polished monologue about the **wrong** characters.
   Observed live (2026-06-16): the intro named Seskin/Vask/Mortn; the table expected Fridolin & co.
   and read it as "the intro went generic."

So the real party only ever travels for one specific channel id, and any new voice channel silently
degrades to the example party. Binding the party to a volatile channel id is the root cause.

## Decision
Add a **committed default party**, loaded for any channel that has no own sheet, *before* the
`_example` fallback:

- New config `default_party` (env `DM_DEFAULT_PARTY`, default `"_default"`).
- `SessionRuntime._load_characters` resolves in order: channel-specific
  `data/sessions/<id>/characters.json` → `data/sessions/<default_party>/characters.json` →
  `data/sessions/_example/characters.json`. The D43 **`fallback` warning fires only for the
  `_example` case** — the default party is the *intended* fallback and loads silently.
- `data/sessions/_default/characters.json` is committed (a copy of the live party), allowlisted in
  `.gitignore` next to `_example`. Being committed, it travels to the teammate's clone via git and
  serves **every** voice channel — the party is no longer bound to one channel id.

A channel that *does* have its own sheet still wins (per-channel overrides are unaffected). Boot-time
`_load_characters(None)` now also picks up the default party, so `!test`/`!roll` work out of the box
with the real party instead of the example one.

## Alternatives
- **Hand-allowlist each new channel's `characters.json`** (status quo, extended): rejected — every
  new voice channel needs a fresh `.gitignore` `!`-rule + commit + the teammate pulling, and it
  commits per-channel runtime dirs. Doesn't remove the channel-id binding.
- **Wildcard `!data/sessions/*/characters.json`** (commit every channel's sheet): rejected — still
  per-channel, and it would auto-commit *future* channels' sheets (and tempt committing their
  runtime state). One committed `_default` is the smaller, channel-independent surface.
- **`DM_DEFAULT_PARTY` pointing at a channel id, no new file** (reuse circlejerk's committed sheet):
  rejected as the *primary* mechanism — `.env` does not travel via git, so the teammate would have to
  set it by hand; the whole point is zero manual steps on the clone. (The env override still exists
  for power users; it just isn't required.)
- **Commit the bought adventure / PDFs too** (the broader "track folders, not files" wish): rejected
  while the repo is public — `adventures/` scene cards are bought-book-derived and the PDFs are the
  rulebooks; publishing them is a copyright problem. Only self-authored party data ships.

## Consequences
- **+** The real party loads in **every** voice channel and on a teammate's clone with no manual
  setup — the "intro went generic in a new channel" failure cannot recur.
- **+** The loud D43 warning now means what it says: a genuine misconfig (no channel sheet *and* no
  default party), not the everyday "played in a fresh channel" case.
- **+** Tests: `tests/test_load_characters.py` (5) pins the resolution order; suite **374 green**.
- **−** The default party duplicates the live circlejerk sheet on disk; if the roster changes, update
  both (or repoint `DM_DEFAULT_PARTY`). Acceptable — rosters change rarely and the character-build
  skill owns deployment.
- **−** One more committed file under `data/sessions/`; the allowlist gains a `_default` entry. Runtime
  state (`state.json`/`history.jsonl`/recaps) under any channel stays ignored as before.
