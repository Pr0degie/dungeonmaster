"""Ollama chat client (Phase 5; streaming added ADR 017).

A thin async wrapper over Ollama's ``/api/chat``. The host and model come from config
(``OLLAMA_HOST`` / ``OLLAMA_MODEL``) — never hardcoded, so moving Ollama to the 5080 over
Tailscale stays a one-line change (ADR 002). Async because discord.py runs an event loop and a
generation takes seconds; blocking it would freeze the whole bot.

Two entry points: :meth:`OllamaClient.chat` returns the finished German answer (roll router,
recap, tests use it); :meth:`OllamaClient.chat_stream` yields text deltas as they generate so the
DM turn can synthesise + speak the first sentence before the rest is done (ADR 017). Both set
``last_stats`` from the final response object identically.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

log = logging.getLogger(__name__)


def _parse_stream_line(line: str) -> tuple[str, dict | None]:
    """Parse one NDJSON line of Ollama's streaming ``/api/chat`` response.

    Returns ``(text delta, final-stats | None)``: the delta is the line's ``message.content``;
    only the terminal ``done: true`` object carries ``prompt_eval_count`` / ``eval_count`` (every
    intermediate line returns ``None`` for the second item). A blank or unparseable line yields
    ``("", None)`` so the stream loop skips it instead of crashing the turn.
    """
    line = line.strip()
    if not line:
        return "", None
    try:
        data = json.loads(line)
    except ValueError:
        return "", None
    delta = (data.get("message") or {}).get("content", "") or ""
    if data.get("done"):
        return delta, {
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
        }
    return delta, None

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
        # Token accounting from the most recent chat() call (prompt_eval_count / eval_count and the
        # num_ctx in effect). Surfaced for the per-turn [latency] line — answers, for free, whether
        # the growing system prompt is creeping toward the num_ctx cap. None until the first call;
        # overwritten each call, so read it right after the call you care about. Does NOT change
        # chat()'s return type (existing callers keep getting the answer string).
        self.last_stats: dict | None = None

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
        # Ollama returns prompt_eval_count (context tokens) + eval_count (generated tokens) on the
        # final response object; keep them (with the num_ctx we asked for) for the [latency] line.
        self.last_stats = {
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            "num_ctx": payload["options"].get("num_ctx"),
        }
        return data["message"]["content"].strip()

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        options: dict | None = None,
    ) -> AsyncIterator[str]:
        """Like :meth:`chat`, but stream the answer as text deltas (``stream: true``).

        Yields each ``message.content`` delta as it arrives, so the DM turn can synthesise +
        speak the first sentence while the rest is still generating (ADR 017). ``last_stats`` is
        set from the terminal ``done`` object, same shape as :meth:`chat`. The caller stops the
        generation early simply by stopping iteration / calling ``aclose`` on this generator —
        httpx closes the underlying stream (the client-side stop-label abort). Server-side
        ``options.stop`` still applies. Raises ``httpx.HTTPError`` on transport/HTTP failure.
        """
        payload = {
            "model": self._model,
            "stream": True,
            "keep_alive": self._keep_alive,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {**_DEFAULT_OPTIONS, **(options or {})},
        }
        num_ctx = payload["options"].get("num_ctx")
        # Generous read timeout for the stream: the first delta can take minutes on a cold start
        # (model load + prompt eval under GPU contention) — the client default (120 s) killed a
        # live greeting turn mid-stream (ReadTimeout, 2026-06-12). Between-delta stalls that long
        # mean Ollama is loading, not hanging; the abort path for a wedged stream is pause/stop.
        stream_timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
        async with self._client.stream(
            "POST", f"{self._host}/api/chat", json=payload, timeout=stream_timeout
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                delta, final = _parse_stream_line(line)
                if final is not None:
                    self.last_stats = {**final, "num_ctx": num_ctx}
                if delta:
                    yield delta

    async def aclose(self) -> None:
        await self._client.aclose()
