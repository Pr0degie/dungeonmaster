"""The "sehr böser Junge" voice command: phrase parsing, culprit lookup and the runtime hook
that disconnects the member (``SessionRuntime._maybe_kick``)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dmbot.runtime import SessionRuntime
from dmbot.voice.kick_phrase import find_culprit, is_kick_master, parse_kick_phrase


# ----- parse_kick_phrase ---------------------------------------------------------------------

@pytest.mark.parametrize("text, name", [
    ("Der Timo war ein sehr böser Junge.", "Timo"),
    ("der timo war ein sehr böser junge", "timo"),
    ("Timo war ein böser Junge", "Timo"),
    ("Also, der Timo war ein ganz sehr böser Junge, oder?", "Timo"),
    ("Die Anna war ein sehr böses Mädchen.", "Anna"),
    ("Der Sezgin war ein sehr böses Kind!", "Sezgin"),
])
def test_the_phrase_names_the_culprit(text: str, name: str) -> None:
    assert parse_kick_phrase(text) == name


@pytest.mark.parametrize("text", [
    "Der Timo war böse.",
    "Timo ist ein sehr böser Junge.",
    "War Timo ein Junge?",
    "Er war ein sehr böser Junge.",
    "Ein sehr böser Junge kommt herein.",
    "",
])
def test_other_sentences_do_not_trigger(text: str) -> None:
    assert parse_kick_phrase(text) is None


# ----- find_culprit / is_kick_master -----------------------------------------------------------

def _member(mid: int, display: str, *, bot: bool = False):
    return SimpleNamespace(id=mid, display_name=display, name=display.lower(), global_name=None,
                           bot=bot)


def test_culprit_by_display_name_case_insensitive() -> None:
    timo = _member(2, "Timo")
    assert find_culprit("timo", [_member(1, "Pr0degie"), timo]) is timo


def test_culprit_by_character_name() -> None:
    timo = _member(2, "Timo")
    assert find_culprit("Gellicus", [timo], char_by_user={2: "Gellicus Schulz"}) is timo


def test_culprit_by_a_word_of_the_display_name() -> None:
    timo = _member(2, "Timo | Gellicus")
    assert find_culprit("Timo", [timo]) is timo


def test_bots_and_bot_a_are_never_culprits() -> None:
    bot = _member(9, "Timo", bot=True)
    bot_a = _member(5, "Timo")
    assert find_culprit("Timo", [bot, bot_a], bot_a_user_id=5) is None


def test_nobody_matching_is_none() -> None:
    assert find_culprit("Timo", [_member(1, "Pr0degie")]) is None


def test_kick_master_by_name_id_or_nobody() -> None:
    assert is_kick_master("", "anyone", None)
    assert is_kick_master("Pr0degie", "pr0degie", None)
    assert not is_kick_master("Pr0degie", "Timo", 2)
    assert is_kick_master("1", "Pr0degie", 1)
    assert not is_kick_master("1", "Pr0degie", None)


# ----- SessionRuntime._maybe_kick ---------------------------------------------------------------

class _KickableMember:
    def __init__(self, mid: int, display: str) -> None:
        self.id, self.display_name, self.name = mid, display, display
        self.global_name, self.bot = None, False
        self.moves: list[tuple[object, str]] = []

    async def move_to(self, channel, *, reason: str = "") -> None:
        self.moves.append((channel, reason))


class _Channel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content or "")
        return SimpleNamespace(content=content)


def _runtime(members, *, master: str = "") -> SessionRuntime:
    rt = SessionRuntime.__new__(SessionRuntime)
    rt._kick_phrase = True
    rt._kick_master = master
    rt._speaker_ids = {}
    rt._speaker_names = {}
    rt._char_by_user = {}
    rt._bot_a_user_id = None
    rt._voice_channel = SimpleNamespace(members=members)
    rt._text_channel = _Channel()
    rt._post_player_lines = False
    rt._active_vc_id = None
    rt._last_stt_ms = {}
    rt._brain = SimpleNamespace(add_player_line=lambda *a: None)
    return rt


def _transcribe(rt: SessionRuntime, speaker: str, text: str, *, for_dm: bool = False) -> None:
    """Feed one STT result the way the worker thread does, then let the loop drain the kick."""
    async def run() -> None:
        rt._loop = asyncio.get_running_loop()
        await asyncio.to_thread(rt._on_transcript, speaker, text, 1.0, 100.0, for_dm)
        for _ in range(50):
            await asyncio.sleep(0.01)
            if rt._text_channel.sent:
                break

    asyncio.run(run())


def test_the_phrase_disconnects_the_named_member_and_tells_the_channel() -> None:
    timo = _KickableMember(2, "Timo")
    rt = _runtime([_KickableMember(1, "Pr0degie"), timo])

    _transcribe(rt, "Pr0degie", "Der Timo war ein sehr böser Junge.")

    assert timo.moves and timo.moves[0][0] is None
    assert "Pr0degie" in timo.moves[0][1]
    assert rt._text_channel.sent and "Timo" in rt._text_channel.sent[0]


def test_only_the_kick_master_may_say_it() -> None:
    timo = _KickableMember(2, "Timo")
    tobi = _KickableMember(1, "Pr0degie")
    rt = _runtime([tobi, timo], master="Pr0degie")

    _transcribe(rt, "Timo", "Der Pr0degie war ein sehr böser Junge.")
    assert tobi.moves == []

    _transcribe(rt, "Pr0degie", "Der Timo war ein sehr böser Junge.")
    assert timo.moves and timo.moves[0][0] is None


def test_the_kick_master_can_be_a_user_id() -> None:
    timo = _KickableMember(2, "Timo")
    rt = _runtime([timo], master="1")
    rt._speaker_ids = {"Pr0degie": 1, "Timo": 2}

    _transcribe(rt, "Timo", "Der Timo war ein sehr böser Junge.")
    assert timo.moves == []

    _transcribe(rt, "Pr0degie", "Der Timo war ein sehr böser Junge.")
    assert len(timo.moves) == 1


def test_the_command_line_is_not_routed_to_the_dm() -> None:
    timo = _KickableMember(2, "Timo")
    rt = _runtime([timo])
    rt._active_vc_id = 7
    lines: list = []
    rt._brain = SimpleNamespace(add_player_line=lambda cid, name, text: lines.append(text))

    _transcribe(rt, "Pr0degie", "Der Timo war ein sehr böser Junge.", for_dm=True)

    assert lines == []
    assert len(timo.moves) == 1


def test_nobody_in_the_channel_matching_does_nothing() -> None:
    rt = _runtime([_KickableMember(1, "Pr0degie")])
    _transcribe(rt, "Pr0degie", "Der Timo war ein sehr böser Junge.")
    assert rt._text_channel.sent == []


def test_switched_off_ignores_the_phrase() -> None:
    timo = _KickableMember(2, "Timo")
    rt = _runtime([timo])
    rt._kick_phrase = False
    _transcribe(rt, "Pr0degie", "Der Timo war ein sehr böser Junge.")
    assert timo.moves == []
