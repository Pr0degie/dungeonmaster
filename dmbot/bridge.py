"""Bridge client to Bot A's `/speak` server (Phase 6).

DMbot is a pure *outbound* HTTP client toward the music bot's bridge (the only contact
surface between the two bots — two-bot isolation, CLAUDE.md). Contract (architecture.md §3):

- ``GET /health`` → ``{"status":"ok","bot":"<name>"}``
- ``POST /speak`` ``{"path":"<abs WAV path>","guild_id":<optional>}`` → plays the WAV and
  **blocks until playback finishes**, then returns ``{"status":"played",...}``. The blocking
  return is the only "done" signal (D15) — when ``speak`` resolves, playback is over.

Localhost only; both bots share the filesystem, so we pass a WAV *path*, not bytes.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class BridgeClient:
    """Async client for Bot A's DMBridge. One per bot; close it on shutdown."""

    def __init__(self, host: str, port: int, *, timeout: float = 300.0) -> None:
        # Long timeout: /speak blocks for the whole playback, which can be many seconds.
        self._base = f"http://{host}:{port}"
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
        """POST the WAV path and wait for playback to finish. Returns True if it played."""
        payload: dict = {"path": wav_path}
        if guild_id is not None:
            payload["guild_id"] = guild_id
        try:
            resp = await self._client.post(f"{self._base}/speak", json=payload)
            resp.raise_for_status()
            return resp.json().get("status") == "played"
        except httpx.HTTPError as exc:
            log.error("bridge /speak failed (%s) for %s", exc, wav_path)
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
