"""Ollama chat client (Phase 5).

A thin async wrapper over Ollama's ``/api/chat``. The host and model come from config
(``OLLAMA_HOST`` / ``OLLAMA_MODEL``) — never hardcoded, so moving Ollama to the 5080 over
Tailscale stays a one-line change (ADR 002). Async because discord.py runs an event loop and a
generation takes seconds; blocking it would freeze the whole bot.

Non-streaming for now: Phase 5 just needs the finished German answer. Streaming is a later
latency optimisation (it pairs with streaming TTS, not an MVP must — CLAUDE.md).
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

# A storyteller wants some spark but must stay coherent and in-world.
_DEFAULT_OPTIONS = {"temperature": 0.8, "top_p": 0.9}


class OllamaClient:
    """Minimal async Ollama chat client. One per bot; close it on shutdown."""

    def __init__(self, host: str, model: str, *, timeout: float = 120.0) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        options: dict | None = None,
    ) -> str:
        """Send a system prompt + role-tagged messages, return the assistant's text.

        ``messages`` is the running history as ``[{"role": "user"|"assistant", "content": …}]``.
        Raises ``httpx.HTTPError`` on transport/HTTP failure (the caller decides what to tell
        the players).
        """
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {**_DEFAULT_OPTIONS, **(options or {})},
        }
        resp = await self._client.post(f"{self._host}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"].strip()

    async def aclose(self) -> None:
        await self._client.aclose()
