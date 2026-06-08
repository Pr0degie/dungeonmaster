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

# A storyteller wants some spark but must stay coherent and in-world. num_ctx is capped well
# below nemo's 16k default: the KV cache for 16k context costs ~2 GB of VRAM we don't have to
# spare on the 12 GB 4070 (history is trimmed anyway), and a smaller cache loads faster.
_DEFAULT_OPTIONS = {"temperature": 0.8, "top_p": 0.9, "num_ctx": 8192}


class OllamaClient:
    """Minimal async Ollama chat client. One per bot; close it on shutdown."""

    def __init__(
        self,
        host: str,
        model: str,
        *,
        timeout: float = 120.0,
        keep_alive: str = "30m",
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        # Keep the model resident between DM turns so it isn't cold-loaded each time (a cold
        # load of a ~9 GB model under VRAM pressure is the dominant latency — measured 15 s).
        self._keep_alive = keep_alive
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
        format: dict | str | None = None,
    ) -> str:
        """Send a system prompt + role-tagged messages, return the assistant's text.

        ``messages`` is the running history as ``[{"role": "user"|"assistant", "content": …}]``.
        ``format`` (a JSON schema dict or ``"json"``) constrains the output via Ollama's structured
        outputs — used by the roll-detection router (ADR 014) to force a tiny valid-JSON verdict.
        Raises ``httpx.HTTPError`` on transport/HTTP failure (the caller decides what to tell
        the players).
        """
        payload = {
            "model": self._model,
            "stream": False,
            "keep_alive": self._keep_alive,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {**_DEFAULT_OPTIONS, **(options or {})},
        }
        if format is not None:
            payload["format"] = format
        resp = await self._client.post(f"{self._host}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"].strip()

    async def aclose(self) -> None:
        await self._client.aclose()
