# ADR 010 — Network speak bridge (hybrid path/bytes transport)

- **Status:** Accepted
- **Date:** 2026-06-05
- **Refs:** decision log D15 (blocking `/speak`) + D16 (Windows runtime, co-location) in
  `progress.md`; ADR 002 (deployment topology, Tailscale); `architecture.md` §3 (bridge contract)

## Context

The `/speak` bridge (DMbot → Bot A) was **localhost-only and file-path based**: DMbot wrote a WAV
to its temp dir and sent Bot A only the *path*; Bot A read it off the **same disk** and played it
(blocking until done = the "done" signal, D15). That hard-wired both bots onto one machine
(ADR 002 / D16). It surfaced when a colleague ran DMbot on his RTX 5080 while Bot A ran elsewhere:
`All connection attempts failed` (bridge is on his localhost, where no Bot A runs) and, when a path
did arrive, `404 file not found` (the path doesn't exist on the other machine's disk). The wish:
run the two bots on **two machines over Tailscale** (e.g. Bot A on the 5080, DMbot on the 4070) —
**without breaking the proven localhost setup**.

## Decision

A **hybrid transport, chosen by DMbot from the configured `DM_BRIDGE_HOST`**:

- **Loopback host** (`127.0.0.1`/`localhost`/`::1`) → send the WAV **path** as JSON, exactly as
  before. Zero-copy, no secret, byte-identical to the old behavior.
- **Remote host** → send the WAV **bytes** (`POST /speak`, `Content-Type: audio/wav`, raw body);
  Bot A writes them to its **own** temp dir (`tempfile.gettempdir()`), plays, and deletes them.
  `guild_id` and a **shared secret** ride as headers (`X-DM-Guild-Id`, `X-DM-Secret`).

Bot A's `/speak` accepts **both** shapes (dispatch on `Content-Type`) and, off-loopback, requires
`X-DM-Secret == DM_BRIDGE_SECRET` (constant-time compare); the check is skipped for a loopback peer
or when no secret is configured, so localhost stays zero-config. The D15 blocking-until-played
contract is preserved in both modes. Transport is **raw body**, not multipart (httpx `content=` ⇄
aiohttp `await request.read()`) — simplest, no new deps; a sentence WAV is a few hundred KB–~2 MB,
negligible over Tailscale.

## Alternatives

- **Shared network filesystem / UNC path:** keep sending a path that resolves on both machines.
  Fragile on Windows, path-translation pain (the very reason D16 rejected WSL), extra attack
  surface. Rejected.
- **Always send bytes** (drop path mode): one code path, but a needless in-memory copy for the
  common localhost case and forces a secret where none is needed. Rejected — localhost must stay
  exactly as proven.
- **Multipart upload:** standard for file uploads, but adds a parser/boundary handling for no
  benefit at these sizes. Rejected in favour of a raw body.

## Consequences

- **Positive:** DMbot and Bot A can run on different machines over Tailscale; localhost is
  untouched (path mode, no secret). One env var (`DM_BRIDGE_HOST`) flips the topology; the code
  picks the transport automatically.
- **Relaxes D16 / ADR 002:** the "both bots on one machine / shared filesystem" prerequisite no
  longer holds for the bridge — ADR 002 is **partially superseded** on that point. (Two-bot
  isolation and the rest of D16 still stand.)
- **New config:** `DM_BRIDGE_SECRET` on both bots, required off-loopback (set the same value);
  empty for localhost. Bot A must bind `DM_BRIDGE_HOST` to its Tailscale IP (or `0.0.0.0`) to be
  reachable — no code change, `web.TCPSite` already binds the configured host.
- **Cross-repo:** the Bot A change lives in the music bot repo (`cogs/dm_bridge.py`, `config.py`,
  `.env.example`) as its own minimal commit; music/queue logic untouched.
- **Failure modes now explicit** (DMbot logs them): `401` secret mismatch, `404`/`409` as before,
  connection-refused = Bot A not running. Bot A cleans up its received temp WAV in a `finally`.
