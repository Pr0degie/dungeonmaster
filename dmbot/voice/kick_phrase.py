"""The table's running gag as a voice command: "Der Timo war ein sehr böser Junge." disconnects
Timo from the voice channel.

Pure helpers only — :func:`parse_kick_phrase` finds the sentence in a transcript and names the
culprit, :func:`find_culprit` picks the matching voice-channel member. The runtime schedules the
actual ``member.move_to(None)`` on the event loop (``SessionRuntime._maybe_kick``). Nothing here
touches Discord, so it tests without a bot.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

# "der Timo war ein sehr böser Junge" — article optional (STT drops it at times), the
# intensifier optional ("sehr", "ganz", "wirklich", "echt", "so"), "böser Junge" / "böses
# Mädchen" / "böses Kind" all count. The name is one word — a Discord display name as spoken.
_PATTERN = re.compile(
    r"(?:^|\b)(?:der|die|das)?\s*(?P<name>[^\W\d_][\w'\-]*)\s+war\s+ein(?:e)?\s+"
    r"(?:(?:sehr|ganz|wirklich|echt|so)\s+)*böse[rs]?\s+(?:junge|bub|bube|mädchen|kind)\b",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"[\s|_\-.,:;/()\[\]]+")
_NOT_A_NAME = {"der", "die", "das", "ein", "eine", "er", "sie", "es", "ich", "du", "wer"}


def parse_kick_phrase(text: str) -> str | None:
    """The spoken name of the "sehr böse Junge" in ``text``, or ``None`` when the sentence is not
    in it. Punctuation and case are STT noise and ignored."""
    m = _PATTERN.search(text or "")
    if m is None:
        return None
    name = m.group("name")
    # A pronoun or doubled article in the name slot ("er war ein böser Junge") is not a command.
    if _fold(name) in _NOT_A_NAME:
        return None
    return name


def _fold(value: str) -> str:
    """Case- and accent-insensitive comparison key: "Timo" == "timo" == "TÍMO"."""
    stripped = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in stripped if not unicodedata.combining(ch)).casefold().strip()


def _member_names(member: Any, char_by_user: Mapping[int, str]) -> list[str]:
    names = [
        getattr(member, "display_name", "") or "",
        getattr(member, "name", "") or "",
        getattr(member, "global_name", "") or "",
        char_by_user.get(getattr(member, "id", -1), "") or "",
    ]
    return [n for n in names if n]


def find_culprit(
    name: str,
    members: Iterable[Any],
    char_by_user: Mapping[int, str] | None = None,
    bot_a_user_id: int | None = None,
) -> Any | None:
    """The voice-channel member the spoken ``name`` refers to, or ``None``.

    A whole-name match wins (display name, account name, global name, or the character the
    player runs via ``char_by_user``); failing that, a word of one of those names ("Timo" in
    "Timo | Gellicus", "Gellicus" in "Gellicus Schulz"). Bots and Bot A are never culprits.
    """
    char_by_user = char_by_user or {}
    key = _fold(name)
    if not key:
        return None
    humans = [
        m for m in members
        if not getattr(m, "bot", False)
        and not (bot_a_user_id and getattr(m, "id", None) == bot_a_user_id)
    ]
    for m in humans:
        if any(_fold(n) == key for n in _member_names(m, char_by_user)):
            return m
    for m in humans:
        for n in _member_names(m, char_by_user):
            if key in (_fold(part) for part in _SPLIT.split(n) if part):
                return m
    return None


def is_kick_master(master: str, speaker_name: str, speaker_id: int | None) -> bool:
    """Whether the speaker may give the command. ``master`` is a Discord user id (digits) or a
    display/account name; empty = everyone at the table may."""
    master = (master or "").strip()
    if not master:
        return True
    if master.isdigit():
        return speaker_id is not None and int(master) == speaker_id
    return _fold(master) == _fold(speaker_name)
