"""Test-marker parsing (ADR 004) — turns the LLM's ``<<TEST …>>`` request into structured data.

The DM narrates and, when a roll is due, emits a machine-readable marker the model can produce
more reliably than strict JSON. Grammar (tolerant):

    <<TEST <skill> [<difficulty>|±N] [für <name>]>>

e.g. ``<<TEST Wahrnehmung Schwer für Tobi>>`` or ``<<TEST Heimlichkeit +10>>``. The difficulty
is a word from the active profile's ladder (the *number* stays in code — golden rule #2); an
explicit ``±N`` is accepted as a manual override. ``für``/``for`` names the player/character.

:func:`extract_tests` returns the narration with markers removed (so TTS never reads them aloud)
plus the parsed requests. An unparseable ``<<TEST …>>`` is still stripped and yields a generic
manual request (``parsed=False``), so a dice button appears and the flow never breaks (ADR 004
fallback). Pure + profile-driven, unit-tested without Discord.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .profile import SystemProfile

_MARKER_RE = re.compile(r"<<\s*TEST\b(.*?)>>", re.IGNORECASE | re.DOTALL)
_FUER_RE = re.compile(r"\b(?:für|fuer|for)\b", re.IGNORECASE)
_MOD_RE = re.compile(r"([+\-−]\s*\d+)")  # ASCII +/- and the unicode minus the LLM may emit


@dataclass(frozen=True, slots=True)
class TestRequest:
    """A parsed (or fallback) test request from a DM turn."""

    skill: str
    difficulty: str | None = None   # a ladder word, resolved against the profile later
    modifier: int | None = None     # explicit ±N override (wins over difficulty)
    target_name: str | None = None  # player/character named after "für"
    raw: str = ""                   # the original marker text
    parsed: bool = True             # False → unparseable; show a generic manual button


def _difficulty_phrases(profile: SystemProfile) -> list[str]:
    """Known difficulty phrases (ladder labels + aliases), longest first so multi-word
    phrases like 'sehr schwer' match before 'schwer'."""
    phrases = list(profile.difficulty_ladder) + list(profile.difficulty_aliases)
    return sorted({p.lower() for p in phrases}, key=lambda p: len(p.split()), reverse=True)


def _split_trailing_difficulty(text: str, phrases: list[str]) -> tuple[str, str | None]:
    """Peel a trailing difficulty phrase off ``text``; return (skill, difficulty|None)."""
    words = text.split()
    for phrase in phrases:
        plen = len(phrase.split())
        if plen <= len(words) and " ".join(words[-plen:]).lower() == phrase:
            return " ".join(words[:-plen]).strip(), " ".join(words[-plen:])
    return text.strip(), None


def _parse_one(inner: str, profile: SystemProfile) -> TestRequest:
    raw = f"<<TEST{inner}>>"
    body = inner.strip()
    target_name: str | None = None
    m = _FUER_RE.search(body)
    if m:
        target_name = body[m.end():].strip(" :.-") or None
        body = body[: m.start()].strip()

    modifier: int | None = None
    mod_m = _MOD_RE.search(body)
    if mod_m:
        modifier = int(mod_m.group(1).replace(" ", "").replace("−", "-"))
        body = (body[: mod_m.start()] + body[mod_m.end():]).strip()

    difficulty: str | None = None
    if modifier is None:
        body, difficulty = _split_trailing_difficulty(body, _difficulty_phrases(profile))

    skill = re.sub(r"\s{2,}", " ", body).strip(" :,-")
    if not skill:
        return TestRequest(skill="", target_name=target_name, raw=raw, parsed=False)
    return TestRequest(
        skill=skill, difficulty=difficulty, modifier=modifier,
        target_name=target_name, raw=raw, parsed=True,
    )


def _clean(text: str) -> str:
    """Tidy narration after markers are removed: collapse spaces, fix space-before-punctuation."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_tests(text: str, profile: SystemProfile) -> tuple[str, list[TestRequest]]:
    """Strip every ``<<TEST …>>`` from ``text`` and return (clean narration, parsed requests)."""
    requests = [_parse_one(m.group(1), profile) for m in _MARKER_RE.finditer(text)]
    clean = _clean(_MARKER_RE.sub("", text))
    return clean, requests
