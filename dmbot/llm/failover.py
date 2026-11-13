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

**Two positions** (``on_failure``, ADR 061 amendment 2026-11-13, fourth). ``"fallback"`` is
everything above. ``"pause"`` never asks the fallback: the failing call and every call until the
next attempt raise :class:`LLMPausedError`, the table gets one ⏸ notice, and the pair retries the
primary at a doubling interval — by the next call that arrives after the wait, or by
:meth:`FailoverClient.probe`, which the DMCog's watcher calls so a return is noticed while
nobody speaks. The mid-stream rule is the same in both positions. ``force("fallback")``
(``!backend ollama``) still pins the fallback: the operator's deliberate way onto it.
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

#: What a failed primary means: the call goes to the fallback, or the game pauses.
ON_FAILURE = ("fallback", "pause")

#: A pause retries at ``pause_retry_s``, doubling after each failed attempt up to this.
PAUSE_RETRY_MAX_S = 300.0

# The probe of a pause: the smallest call of the shape that failed. A prose probe reaches the
# narration tier, a schema probe the aux tier (the tier rule lives in the client, not here) —
# probing the other tier would report a return the next turn cannot use.
# ``PING_*`` is also the boot preflight's ping (``preflight._claude_ping``) — one definition.
PING_SYSTEM = "Antworte nur mit: OK"
PING_MESSAGES = [{"role": "user", "content": "ping"}]
PING_OPTIONS = {"num_predict": 8}
_PROBE_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


class LLMPausedError(LLMBackendError):
    """The pair is in the ``pause`` position and the primary is out: this call was answered by
    nobody. Raised only while no text of the call has been handed out, so the caller can put
    its input aside and ask again later (the turn core does, for player lines)."""


class Notice(str):
    """A notice for the table: the chat line, plus a short sentence to say aloud (``spoken``,
    empty for none — the ``fallback`` position's notices are text only, as before)."""

    spoken: str
    #: What to post instead when a kept turn is still waiting for its answer. The pair cannot
    #: know that (it is the brain's state); whoever posts the notice asks and picks.
    if_waiting: "Notice | None"

    def __new__(cls, text: str, spoken: str = "", *, if_waiting: "Notice | None" = None) -> "Notice":
        obj = super().__new__(cls, text)
        obj.spoken = spoken
        obj.if_waiting = if_waiting
        return obj


@dataclass(frozen=True, slots=True)
class FailoverStatus:
    """A snapshot for ``!backend``."""

    mode: str
    primary: str
    primary_model: str
    fallback: str
    fallback_model: str
    degraded_until: float | None  # unix time; None = not degraded. In a pause: the next attempt
    last_backend: str | None      # which side answered the most recent call
    last_error: str | None
    on_failure: str = "fallback"
    paused_since: float | None = None  # unix time; None = not paused


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
        on_failure: str = "fallback",
        pause_retry_s: float = 30.0,
        pause_auto_turn_s: float = 180.0,
    ) -> None:
        if on_failure not in ON_FAILURE:
            raise ValueError(f"unknown on_failure {on_failure!r}")
        if pause_retry_s <= 0:
            # 0 would double to 0 forever: the watcher would start one CLI after another.
            raise ValueError(f"pause_retry_s must be positive, got {pause_retry_s!r}")
        self._primary = primary
        self._fallback = fallback
        self._cooldown_s = cooldown_s
        self._on_failure = on_failure
        self._pause_retry_s = pause_retry_s
        # A probe that ends a pause shorter than this asks for the waiting turn to be answered.
        self._pause_auto_turn_s = pause_auto_turn_s
        self._paused_since: float | None = None
        self._retry_s = pause_retry_s      # the current wait of a pause (doubles per failed attempt)
        self._probe_schema = False         # the shape of the call that started the pause
        self._resume = False               # a short pause just ended (see take_resume)
        self._names = {id(primary): primary_name, id(fallback): fallback_name}
        self._clock = clock
        self._mode = "auto"
        self._degraded_until: float | None = None
        # Counts degrades (and, in the pause position, the ends of pauses). A primary call
        # remembers the count it started under, and its success only ends a degraded period that
        # already existed then (see _primary_answered); in a pause its failure only counts when
        # nothing changed since it started (see _pause).
        self._degrades = 0
        self._last_error: str | None = None
        self._answered: LLMClient | None = None
        # The side that answered the most recent PROSE call (no `format`). `last_stats` follows
        # this one, not `_answered`: a classifier that fails over while a narration stream is open
        # must not point the turn's [latency] line at the other backend's numbers.
        self._narrated: LLMClient | None = None
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
        """The stats of the side that answered the last prose call, plus ``backend`` — a copy, the
        side's own dict is untouched. Schema calls don't move it (see ``_narrated``)."""
        if self._narrated is None:
            return None
        stats = self._narrated.last_stats
        if stats is None:
            return None
        return {**stats, "backend": self._names[id(self._narrated)]}

    # ---- state -----------------------------------------------------------------------------

    @property
    def degraded(self) -> bool:
        return self._degraded_until is not None

    @property
    def on_primary(self) -> bool:
        """Whether the next call goes to the primary first (not pinned to the fallback, not in a
        cooldown). A call that then fails over still reaches the fallback as issued."""
        return self._try_primary()

    @property
    def on_failure(self) -> str:
        return self._on_failure

    @property
    def paused(self) -> bool:
        """Whether the game is paused: the ``pause`` position, and the primary is out."""
        return self._on_failure == "pause" and self._degraded_until is not None

    def retry_in(self) -> float | None:
        """Seconds until the next attempt on the primary is due in a pause — what the watcher
        sleeps before :meth:`probe`. ``None`` when there is nothing to wait for: not paused, or
        the operator pinned a side."""
        if not self.paused or self._mode != "auto":
            return None
        return max(0.0, self._degraded_until - self._clock())

    def take_resume(self) -> bool:
        """Whether a pause shorter than ``pause_auto_turn_s`` has just ended — once per return.
        The watcher then answers the turn the table is waiting for, if the brain still holds one
        (a turn that ended the pause itself has taken its lines along and is not waiting)."""
        resume, self._resume = self._resume, False
        return resume

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
            on_failure=self._on_failure,
            paused_since=self._paused_since,
        )

    def force(self, mode: str) -> None:
        """Pin one side for the session (``"primary"`` / ``"fallback"``) or follow the cooldown
        again (``"auto"``). Leaving ``"fallback"`` clears a running cooldown, so the operator's
        "back to the primary" takes effect on the next call. Not persisted."""
        if mode not in MODES:
            raise ValueError(f"unknown failover mode {mode!r}")
        if mode != "fallback":
            self._degraded_until = None
            self._paused_since = None
            self._last_error = None
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

    def _asks_primary(self, *, schema: bool) -> bool:
        """Whether this call goes to the primary. As :meth:`_try_primary`, and in a pause only a
        call of the shape that failed is an attempt: the other tier answering proves nothing
        about the one that is out, and its turns would run without their side calls."""
        if not self._try_primary():
            return False
        return not (self.paused and self._mode == "auto" and schema != self._probe_schema)

    def _holds(self) -> bool:
        """Whether a call the primary is not tried for is refused instead of handed to the
        fallback: the ``pause`` position, unless the operator pinned the fallback."""
        return self._on_failure == "pause" and self._mode != "fallback"

    def _notify(self, text: str) -> None:
        self._notices.append(text)
        self.degraded_event.set()

    def _degrade(self, exc: LLMBackendError) -> None:
        """The primary failed: log the cause, start (or extend) the cooldown, and tell the table
        once per announced period (not per call)."""
        primary, fallback = self._names[id(self._primary)], self._names[id(self._fallback)]
        # A fresh outage, or a retry that failed after the announced time ran out — either way
        # what the table was last told is no longer true, so it is told again.
        announce = self._degraded_until is None or self._clock() >= self._degraded_until
        # A reported rate-limit reset beats the cooldown: retrying before it lifts cannot work.
        self._degraded_until = max(self._clock() + self._cooldown_s, float(exc.resets_at or 0))
        self._degrades += 1
        self._last_error = str(exc)
        until = time.strftime("%H:%M", time.localtime(self._degraded_until))
        log.error("LLM backend %s failed — falling back to %s until %s: %s", primary, fallback, until, exc)
        if announce:
            self._notify(
                f"⚠ {primary.capitalize()} antwortet nicht — die Spielleitung läuft bis etwa {until} "
                f"über das lokale Modell ({self._fallback.model}) weiter."
            )

    def _primary_failed(self, exc: LLMBackendError, started_under: int, *, schema: bool) -> None:
        if self._on_failure == "pause":
            self._pause(exc, started_under, schema=schema)
        else:
            self._degrade(exc)

    def _pause(self, exc: LLMBackendError, started_under: int, *, schema: bool) -> None:
        """The primary failed in the ``pause`` position: start the pause and tell the table, or —
        when an attempt made during the pause failed — wait twice as long and say nothing. A
        call that began before the newest failure (the other two post-turn classifiers) tells
        nothing new and changes nothing — and neither does one that began during a pause and
        fails after another call has ended it (a late probe must not announce a second outage
        while the primary is answering)."""
        primary = self._names[id(self._primary)]
        now = self._clock()
        if started_under != self._degrades:
            log.info("LLM backend %s: a call from before the last change failed as well: %s", primary, exc)
            return
        fresh = self._degraded_until is None
        if fresh:
            self._paused_since = now
            self._retry_s = self._pause_retry_s
            self._probe_schema = schema
        else:
            self._retry_s = min(self._retry_s * 2, max(PAUSE_RETRY_MAX_S, self._pause_retry_s))
        # A reported rate-limit reset beats the interval: retrying before it lifts cannot work.
        self._degraded_until = max(now + self._retry_s, float(exc.resets_at or 0))
        self._degrades += 1
        self._last_error = str(exc)
        until = time.strftime("%H:%M:%S", time.localtime(self._degraded_until))
        log.error("LLM backend %s failed — the game is paused, next attempt at %s: %s", primary, until, exc)
        if fresh:
            limit = ""
            if exc.resets_at and float(exc.resets_at) > now + self._retry_s:
                limit = f" (Limit bis etwa {time.strftime('%H:%M', time.localtime(exc.resets_at))})"
            self._notify(Notice(
                f"⏸ {primary.capitalize()} antwortet nicht — das Spiel pausiert{limit}. Eure Zeilen "
                f"bleiben vorgemerkt, ich melde mich, sobald {primary.capitalize()} wieder da ist.",
                spoken="Die Spielleitung ist gerade nicht erreichbar, das Spiel pausiert.",
            ))

    def _end_pause(self, *, by_probe: bool) -> bool:
        """The primary answers again. Tells the table once. After a short pause the kept turn
        is to be answered right away (:meth:`take_resume`); after a long one the table is told
        to speak first and what was put aside stays where it is. Returns whether a probe ended a
        short pause.

        A call that got through after a long pause may be the waiting turn itself (then the game
        simply goes on) or a side call (``!rules``, a recap) while a turn still waits — the pair
        cannot tell, so the notice carries the "I wait for your next line" text as
        ``if_waiting``."""
        primary = self._names[id(self._primary)]
        paused_s = self._clock() - (self._paused_since or self._clock())
        self._degraded_until = None
        self._paused_since = None
        self._last_error = None
        self._degrades += 1  # calls still in flight from the pause no longer speak for the present
        short = paused_s < self._pause_auto_turn_s
        self._resume = short
        log.info("LLM backend %s answers again after %.0f s%s.", primary, paused_s,
                 "" if short else " — waiting for the table to speak")
        goes_on = Notice(
            f"▶ {primary.capitalize()} antwortet wieder — es geht weiter.",
            spoken="Die Spielleitung ist wieder da, es geht weiter.",
        )
        waits = Notice(
            f"▶ {primary.capitalize()} antwortet wieder. Die Pause war lang, darum warte ich auf "
            "eure nächste Zeile — das Vorgemerkte beantworte ich dann mit.",
            spoken="Die Spielleitung ist wieder da und wartet auf eure nächste Ansage.",
        )
        if short:
            self._notify(goes_on)
        elif by_probe:
            self._notify(waits)
        else:
            self._notify(Notice(goes_on, spoken=goes_on.spoken, if_waiting=waits))
        return by_probe and short

    async def probe(self, *, timeout: float = 30.0) -> bool:
        """One minimal call on the primary while the game is paused, in the shape of the call that
        failed. ``True`` when this probe ended the pause *and* the waiting turn should be answered
        now (see :meth:`_end_pause`); ``False`` when the primary is still out (the wait doubles),
        when something else ended the pause meanwhile, or when there was nothing to probe."""
        if self.retry_in() is None:
            return False
        started_under = self._degrades
        try:
            await asyncio.wait_for(
                self._primary.chat(
                    PING_SYSTEM, list(PING_MESSAGES), options=dict(PING_OPTIONS),
                    format=_PROBE_SCHEMA if self._probe_schema else None,
                ),
                timeout,
            )
        except Exception as exc:  # not only backend errors: whatever it was, the primary is not back
            if not isinstance(exc, LLMBackendError):
                exc = LLMBackendError(f"probe got no answer: {type(exc).__name__}: {exc}")
            self._pause(exc, started_under, schema=self._probe_schema)
            return False
        if self._degraded_until is None or started_under != self._degrades:
            return False  # a call ended the pause first, or a newer failure outdated this answer
        return self._end_pause(by_probe=True)

    def _paused_error(self) -> LLMPausedError:
        return LLMPausedError(f"{self._names[id(self._primary)]} is out, the game is paused: {self._last_error}")

    def _primary_answered(self, started_under: int, *, schema: bool = False) -> None:
        """The primary answered a call that began at degrade count ``started_under``. That is
        proof of recovery only if no degrade happened since: a narration stream that was already
        open when a classifier failed says nothing about the failure, and letting it clear the
        cooldown would send the next call into the same error and announce it again."""
        self._answered = self._primary
        if self._degraded_until is not None and started_under == self._degrades:
            if self._on_failure == "pause":
                # Only the shape that failed ends a pause (reachable for the other shape when the
                # operator pinned the primary): Opus answering says nothing about Haiku.
                if schema == self._probe_schema:
                    self._end_pause(by_probe=False)
                return
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
        if self._asks_primary(schema=format is not None):
            started_under = self._degrades
            try:
                answer = await self._primary.chat(system, messages, options=options, format=format)
            except LLMBackendError as exc:
                self._primary_failed(exc, started_under, schema=format is not None)
                if self._on_failure == "pause":
                    raise self._paused_error() from exc
            else:
                self._primary_answered(started_under, schema=format is not None)
                if format is None:
                    self._narrated = self._primary
                return answer
        elif self._holds():
            raise self._paused_error()
        self._answered = self._fallback
        answer = await self._fallback.chat(system, messages, options=options, format=format)
        if format is None:
            self._narrated = self._fallback
        return answer

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        options: dict | None = None,
    ) -> AsyncIterator[str]:
        if self._asks_primary(schema=False):
            started_under = self._degrades
            self._answered = self._narrated = self._primary
            stream = self._primary.chat_stream(system, messages, options=options)
            yielded = False
            try:
                try:
                    async for delta in stream:
                        if not yielded:
                            yielded = True
                            self._primary_answered(started_under)  # a first delta is proof enough of recovery
                        yield delta
                finally:
                    # Also reached when OUR consumer closes early (pause / speaker-label abort):
                    # the close has to travel down to the backend's stream.
                    await stream.aclose()
            except LLMBackendError as exc:
                self._primary_failed(exc, started_under, schema=False)
                if yielded:
                    raise  # text is out and may be spoken — no second answer on top of it
                if self._on_failure == "pause":
                    raise self._paused_error() from exc
            else:
                self._primary_answered(started_under)
                return
        elif self._holds():
            raise self._paused_error()
        self._answered = self._narrated = self._fallback
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
