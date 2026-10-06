"""Loud failover between two LLM backends (ADR 061, Phase 11).

Wraps a ``primary`` and a ``fallback`` :class:`~dmbot.llm.client.LLMClient` and is itself one.
When the primary raises :class:`~dmbot.llm.client.LLMBackendError`, the **same** call is re-issued
on the fallback, the pair is marked degraded for a cooldown, and one notice is queued for the
table — a failed backend costs quality, not the evening. While degraded, calls go straight to the
fallback; after the cooldown the next call tries the primary again, and a recovery is announced
once.

The fallback is not silent infrastructure (lesson ``unwired-knobs-and-silent-fallbacks``): every
switch is logged at ERROR with its cause, announces itself through :attr:`degraded_event`, and
``last_stats`` names the backend that answered.

Streaming fails over only **before the first delta**. Once text has been yielded it may already
be spoken (lesson ``spoken-audio-cannot-be-retracted``), so a later failure is re-raised to the
orchestrator's existing mid-stream degradation — and still marks the pair degraded, so the next
call does not walk into the same failure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from .client import LLMBackendError, LLMClient

log = logging.getLogger(__name__)

#: ``!backend`` modes: follow the cooldown, or pin one side for the session.
MODES = ("auto", "primary", "fallback")


@dataclass(frozen=True, slots=True)
class FailoverStatus:
    """A snapshot for ``!backend``."""

    mode: str
    primary: str
    primary_model: str
    fallback: str
    fallback_model: str
    degraded_until: float | None  # unix time; None = not degraded
    last_backend: str | None      # which side answered the most recent call
    last_error: str | None


class FailoverClient:
    """``primary`` with a loud fallback. One per bot; :meth:`aclose` closes both sides."""

    def __init__(
        self,
        primary: LLMClient,
        fallback: LLMClient,
        *,
        cooldown_s: float = 600.0,
        primary_name: str = "claude",
        fallback_name: str = "ollama",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._cooldown_s = cooldown_s
        self._names = {id(primary): primary_name, id(fallback): fallback_name}
        self._clock = clock
        self._mode = "auto"
        self._degraded_until: float | None = None
        self._last_error: str | None = None
        self._answered: LLMClient | None = None
        self._notices: list[str] = []
        #: Set whenever a notice for the table is waiting (degraded / recovered). The DMCog awaits
        #: it, posts :meth:`take_notices` and so clears it.
        self.degraded_event = asyncio.Event()

    # ---- the seam: proxies to whichever side answered ------------------------------------

    @property
    def model(self) -> str:
        return (self._answered or self._primary).model

    @property
    def last_stats(self) -> dict | None:
        """The answering side's stats plus ``backend`` — a copy, the side's own dict is untouched."""
        if self._answered is None:
            return None
        stats = self._answered.last_stats
        if stats is None:
            return None
        return {**stats, "backend": self._names[id(self._answered)]}

    # ---- state -----------------------------------------------------------------------------

    @property
    def degraded(self) -> bool:
        return self._degraded_until is not None

    def status(self) -> FailoverStatus:
        return FailoverStatus(
            mode=self._mode,
            primary=self._names[id(self._primary)],
            primary_model=self._primary.model,
            fallback=self._names[id(self._fallback)],
            fallback_model=self._fallback.model,
            degraded_until=self._degraded_until,
            last_backend=self._names[id(self._answered)] if self._answered is not None else None,
            last_error=self._last_error,
        )

    def force(self, mode: str) -> None:
        """Pin one side for the session (``"primary"`` / ``"fallback"``) or follow the cooldown
        again (``"auto"``). Leaving ``"fallback"`` clears a running cooldown, so the operator's
        "back to the primary" takes effect on the next call. Not persisted."""
        if mode not in MODES:
            raise ValueError(f"unknown failover mode {mode!r}")
        if mode != "fallback":
            self._degraded_until = None
        self._mode = mode
        log.info("LLM backend mode: %s", mode)

    def take_notices(self) -> list[str]:
        """The pending table notices, oldest first; clears :attr:`degraded_event`."""
        notices, self._notices = self._notices, []
        self.degraded_event.clear()
        return notices

    def _try_primary(self) -> bool:
        if self._mode == "primary":
            return True
        if self._mode == "fallback":
            return False
        return self._degraded_until is None or self._clock() >= self._degraded_until

    def _notify(self, text: str) -> None:
        self._notices.append(text)
        self.degraded_event.set()

    def _degrade(self, exc: LLMBackendError) -> None:
        """The primary failed: log the cause, start (or extend) the cooldown, tell the table once."""
        primary, fallback = self._names[id(self._primary)], self._names[id(self._fallback)]
        first = self._degraded_until is None
        # A reported rate-limit reset beats the cooldown: retrying before it lifts cannot work.
        self._degraded_until = max(self._clock() + self._cooldown_s, float(exc.resets_at or 0))
        self._last_error = str(exc)
        until = time.strftime("%H:%M", time.localtime(self._degraded_until))
        log.error("LLM backend %s failed — falling back to %s until %s: %s", primary, fallback, until, exc)
        if first:
            self._notify(
                f"⚠ {primary.capitalize()} antwortet nicht — die Spielleitung läuft bis etwa {until} "
                f"über das lokale Modell ({self._fallback.model}) weiter."
            )

    def _primary_answered(self) -> None:
        self._answered = self._primary
        if self._degraded_until is not None:
            self._degraded_until = None
            self._last_error = None
            primary = self._names[id(self._primary)]
            log.info("LLM backend %s recovered — back on the primary.", primary)
            self._notify(f"✅ {primary.capitalize()} antwortet wieder ({self._primary.model}).")

    # ---- calls -----------------------------------------------------------------------------

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        options: dict | None = None,
        format: dict | str | None = None,
    ) -> str:
        if self._try_primary():
            try:
                answer = await self._primary.chat(system, messages, options=options, format=format)
            except LLMBackendError as exc:
                self._degrade(exc)
            else:
                self._primary_answered()
                return answer
        self._answered = self._fallback
        return await self._fallback.chat(system, messages, options=options, format=format)

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        options: dict | None = None,
    ) -> AsyncIterator[str]:
        if self._try_primary():
            self._answered = self._primary
            stream = self._primary.chat_stream(system, messages, options=options)
            yielded = False
            try:
                try:
                    async for delta in stream:
                        if not yielded:
                            yielded = True
                            self._primary_answered()  # a first delta is proof enough of recovery
                        yield delta
                finally:
                    # Also reached when OUR consumer closes early (pause / speaker-label abort):
                    # the close has to travel down to the backend's stream.
                    await stream.aclose()
            except LLMBackendError as exc:
                self._degrade(exc)
                if yielded:
                    raise  # text is out and may be spoken — no second answer on top of it
            else:
                self._primary_answered()
                return
        self._answered = self._fallback
        stream = self._fallback.chat_stream(system, messages, options=options)
        try:
            async for delta in stream:
                yield delta
        finally:
            await stream.aclose()

    async def aclose(self) -> None:
        try:
            await self._primary.aclose()
        finally:
            await self._fallback.aclose()
