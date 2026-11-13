"""Who writes the ✂ line of a narration call that hit the output cap (ADR 061, amendment
2026-11-13, second).

A DM turn's answer is cut back to its last complete sentence in the turn core
(``finalize_answer_trimmed``), so only the turn core knows how many characters fell away; it writes
the ✂ line itself and wraps its LLM call in :func:`caller_reports_cut`. Every other prose call —
recap, ``!rules``, NSC memory — is not trimmed, and a backend that logs cuts (``ClaudeClient``)
keeps writing the line for those. A context variable rather than a call argument, so the
``LLMClient`` protocol and ``OllamaClient`` stay untouched; it follows the awaits of one task,
including the iteration of a streamed answer.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_CALLER_REPORTS_CUT: ContextVar[bool] = ContextVar("caller_reports_cut", default=False)


@contextmanager
def caller_reports_cut() -> Iterator[None]:
    """Within this block the caller writes the ✂ line of a cut narration call."""
    token = _CALLER_REPORTS_CUT.set(True)
    try:
        yield
    finally:
        _CALLER_REPORTS_CUT.reset(token)


def caller_reports() -> bool:
    """True when the running call's caller writes the ✂ line (the backend stays quiet)."""
    return _CALLER_REPORTS_CUT.get()
