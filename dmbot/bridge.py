"""Bridge client to Bot A's `/speak` server (Phase 6; hybrid transport).

DMbot is a pure *outbound* HTTP client toward the music bot's bridge (the only contact
surface between the two bots — two-bot isolation, CLAUDE.md). Contract (architecture.md §3):

- ``GET /health`` → ``{"status":"ok","bot":"<name>"}``
- ``POST /speak`` plays a WAV and **blocks until playback finishes**, then returns
  ``{"status":"played",...}``. The blocking return is the only "done" signal (D15).

**Two transports, chosen by the configured host (ADR 010):**

- **Loopback** (``127.0.0.1``/``localhost``): both bots share the filesystem, so we POST the
  WAV *path* as JSON — unchanged, zero-copy, no secret.
- **Remote** (e.g. a Tailscale IP): we POST the WAV *bytes* (``Content-Type: audio/wav``); Bot A
  writes them to its own temp dir, plays, and deletes. ``guild_id`` and the shared secret ride as
  headers. This is what lets DMbot and Bot A run on different machines.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging

import httpx

log = logging.getLogger(__name__)


def _is_loopback(host: str) -> bool:
    """True if ``host`` refers to the local machine (so we can use the zero-copy path mode)."""
    h = host.strip().lower()
    if h in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False  # a non-localhost hostname → treat as remote (bytes mode)


class BridgeClient:
    """Async client for Bot A's DMBridge. One per bot; close it on shutdown."""

    def __init__(self, host: str, port: int, *, secret: str = "", timeout: float = 300.0) -> None:
        # Long timeout: /speak blocks for the whole playback, which can be many seconds.
        self._base = f"http://{host}:{port}"
        self._secret = secret
        self._loopback = _is_loopback(host)
        self._client = httpx.AsyncClient(timeout=timeout)

    async def health(self) -> dict | None:
        """Return the bridge's health JSON, or None if it is unreachable."""
        try:
            resp = await self._client.get(f"{self._base}/health", timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            log.warning("bridge /health failed (%s) — is Bot A running on %s?", exc, self._base)
            return None

    async def speak(self, wav_path: str, *, guild_id: int | None = None) -> bool:
        """Hand the WAV to Bot A and wait for playback to finish. Returns True if it played.

        Loopback → send the path (Bot A reads the shared disk). Remote → send the bytes (Bot A
        writes its own copy). On failure, log the bridge's *own* reason plus a hint, so the cause
        is obvious instead of a generic failure.
        """
        try:
            if self._loopback:
                payload: dict = {"path": wav_path}
                if guild_id is not None:
                    payload["guild_id"] = guild_id
                resp = await self._client.post(f"{self._base}/speak", json=payload)
            else:
                data = await asyncio.to_thread(_read_file, wav_path)
                if not data:
                    log.error("bridge /speak: WAV %s is missing or empty — nothing to send", wav_path)
                    return False
                headers = {"Content-Type": "audio/wav"}
                if guild_id is not None:
                    headers["X-DM-Guild-Id"] = str(guild_id)
                if self._secret:
                    headers["X-DM-Secret"] = self._secret
                resp = await self._client.post(
                    f"{self._base}/speak", content=data, headers=headers
                )
        except httpx.HTTPError as exc:
            log.error("bridge /speak unreachable (%s) — is Bot A running on %s?", exc, self._base)
            return False

        if resp.status_code == 200:
            return resp.json().get("status") == "played"
        try:
            reason = resp.json().get("error", resp.text)
        except ValueError:
            reason = resp.text
        hint = {
            401: " — shared secret mismatch; DM_BRIDGE_SECRET must match on both bots",
            404: " — Bot A can't find the WAV (both bots on the same machine / shared temp dir?)",
            409: " — Bot A is not in the voice channel; make Bot A join it too (not just DMbot)",
        }.get(resp.status_code, "")
        log.error("bridge /speak refused: HTTP %s %r%s", resp.status_code, reason, hint)
        return False

    async def aclose(self) -> None:
        await self._client.aclose()


def _read_file(path: str) -> bytes:
    """Read a file's bytes; empty bytes if it's missing (run off the event loop)."""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return b""
