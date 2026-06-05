# ADR 006 — DAVE/E2EE on voice receive: decrypt via dave_session

- **Status:** Accepted
- **Date:** 2026-06-04
- **Refs:** decision log D19 in `progress.md`; `architecture.md` §4 (data flow), §5 (feedback);
  Phase 2 in `roadmap.md`/`progress.md`

## Context

Phase 2 (voice receive) worked end to end — DMbot joined the channel, the
`discord-ext-voice-recv` sink delivered per-user audio, and the layer-1 Bot A filter held —
but **~40 % of audio packets failed to decode** with `OpusError('corrupted stream')`, and
the rest decoded to subtly wrong audio. A live diagnostic (logging packet head/tail bytes)
showed **every received frame ends in the magic `0xFAFA`** with an incrementing per-frame
nonce + ~13-byte supplemental block.

That is Discord **DAVE** (the MLS-based end-to-end voice encryption). discord.py 2.7.1 ships
with the native `davey` library and therefore **advertises DAVE support**
(`max_dave_protocol_version = davey.DAVE_PROTOCOL_VERSION`, verified = 1 in our session), so
the call became end-to-end encrypted. `discord-ext-voice-recv` only undoes the **transport**
layer (`aead_xchacha20_poly1305_rtpsize`) on receive — it does **not** run the DAVE/MLS layer
— so the bytes it handed the Opus decoder were still E2EE-ciphertext + trailer → garbage.
(Upstream voice-recv issue #38 reports the same, unresolved.)

## Decision

**Keep DAVE enabled and decrypt the E2EE layer ourselves on receive**, inside the sink:
the sink takes `wants_opus() == True` (raw frames), and for each frame runs
`voice_client._connection.dave_session.decrypt(user_id, MediaType.audio, frame)` — once the
MLS group is `ready` — **before** Opus-decoding. discord.py already builds and maintains that
`dave_session` over the voice gateway (MLS key package / welcome / commit); we just use it,
which voice-recv neglects to.

## Alternatives

- **Decline DAVE (`max_dave_protocol_version = 0`)** so the call downgrades to transport-only
  encryption (which voice-recv can decrypt): tried first; Discord's voice gateway **rejected
  the connection with close code 4017**. Not viable — Discord does not let us opt out this way.
- **Strip the DAVE trailer and decode the remainder as Opus:** the bytes are genuinely
  E2EE-encrypted, not merely trailer-padded — validated offline (no consistent strip offset
  recovers a clean 20 ms frame). Doesn't work.
- **Let the library decode (`wants_opus = False`):** it decodes the *still-encrypted* frame
  in its packet-router thread, which is fatal (one `OpusError` → `stop_listening()`), and
  there is no seam to inject DAVE-decrypt before its decode. Rejected (this is also the second
  reason the sink owns decoding).

## Consequences

- **Positive:** voice receive yields clean Opus again — consistent TOC (`0x78…`), ~100 %
  decode, 0 dropped in testing. E2EE stays on for the human players (we decrypt as a
  legitimate group member), so privacy is preserved, unlike the downgrade path.
- **Binding / version-sensitive:** the sink reaches into a discord.py internal
  (`voice_client._connection.dave_session`) and depends on `davey` being installed and on
  discord.py driving the MLS handshake. Re-verify on a discord.py/voice-recv/davey upgrade
  (kept isolated in `voice/recv.py`, per CLAUDE.md's "voice-recv is the only research part").
  **Safeguards (added 2026-06-05) so a drift can't break this silently:**
  - the three voice distributions are pinned `==` in `pyproject.toml` (not `>=`), so an
    unrelated `uv add` / `uv lock --upgrade` can't move the kernel;
  - `voice/preflight.py` runs at boot (`check_static` — versions + sink/DAVE attribute paths)
    and at join (`check_dave_session` — the live `_connection.dave_session` handle), logging
    loud warnings on any drift;
  - `recv.py` detects a DAVE-encrypted frame (trailer magic `0xFAFA`) arriving with no
    reachable `dave_session` and warns + skips, instead of Opus-decoding ciphertext to garbage;
  - `tests/test_voice_stack.py` is the offline canary — run it after any dependency change.

## Verified stack

The exact set this receive path was verified against (live, 2026-06-04). Bumping any of these
is a deliberate act: change `voice/preflight.py` `KNOWN_GOOD` + the `==` pins, run
`tests/test_voice_stack.py`, re-verify a live session, then update this table.

| Distribution | Verified version |
|---|---|
| `discord.py` (`discord-py[voice]`) | 2.7.1 |
| `discord-ext-voice-recv` | 0.5.2a179 |
| `davey` | 0.1.5 |
| `onnxruntime` (VAD, ADR 007) | 1.26.0 |
| `soxr` (resample, ADR 007) | 1.1.0 |
| Opus | discord.py bundled DLL |
- **Behaviour:** frames received before the MLS group is `ready`, or from a user not yet in
  the group, are skipped (brief startup gap). Single lost/late RTP packets still produce
  benign "lost being flushed" jitter warnings (sender-side voice-activation), quieted in logs.
- **Heavy dep note (golden rule #9):** `davey` arrived transitively with `discord.py[voice]` /
  `discord-ext-voice-recv`; this ADR is its justification — it is required for DAVE decrypt.
