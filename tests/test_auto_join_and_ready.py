"""D130: any DMbot command joins voice first (like !j), and a soft pop once the bot is ready."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dmbot.ready_sound import ReadySound
from dmbot.voice.voicecog import VoiceCog

# --- auto-join -------------------------------------------------------------------------------


def _cog(*, enabled: bool = True, join_fails: bool = False):
    joined: list[str] = []
    cog = VoiceCog.__new__(VoiceCog)
    cog._rt = SimpleNamespace(_auto_join=enabled)
    cog._auto_join_lock = asyncio.Lock()

    async def fake_join(self, ctx):
        if join_fails:
            raise RuntimeError("no permission to connect")
        joined.append(ctx.command.name)
        ctx.voice_client = object()

    cog.join = SimpleNamespace(callback=fake_join)
    return cog, joined


def _ctx(command: str, *, in_voice: bool = True, bot_in_voice: bool = False):
    voice = SimpleNamespace(channel=SimpleNamespace(name="circlejerk")) if in_voice else None
    return SimpleNamespace(
        command=SimpleNamespace(name=command), guild=object(),
        author=SimpleNamespace(voice=voice, display_name="Tobi"),
        voice_client=object() if bot_in_voice else None,
    )


def test_a_command_joins_the_callers_voice_channel_first() -> None:
    cog, joined = _cog()
    asyncio.run(cog.auto_join(_ctx("test")))
    assert joined == ["test"]


def test_no_join_when_already_in_voice_or_the_caller_is_not() -> None:
    cog, joined = _cog()
    asyncio.run(cog.auto_join(_ctx("test", bot_in_voice=True)))
    asyncio.run(cog.auto_join(_ctx("roll", in_voice=False)))
    assert joined == []


def test_join_leave_status_and_help_never_auto_join() -> None:
    cog, joined = _cog()
    for name in ("join", "leave", "vstatus", "help"):
        asyncio.run(cog.auto_join(_ctx(name)))
    assert joined == []


def test_the_switch_turns_it_off() -> None:
    cog, joined = _cog(enabled=False)
    asyncio.run(cog.auto_join(_ctx("test")))
    assert joined == []


def test_a_failed_join_never_blocks_the_command() -> None:
    cog, _ = _cog(join_fails=True)
    asyncio.run(cog.auto_join(_ctx("test")))  # no exception: the command still runs


def test_two_quick_commands_join_only_once() -> None:
    cog, joined = _cog()
    shared = _ctx("test")

    async def both():
        await asyncio.gather(cog.auto_join(shared), cog.auto_join(shared))

    asyncio.run(both())
    assert joined == ["test"]


# --- ready sound ------------------------------------------------------------------------------


def test_it_pops_once_at_login_not_again_on_reconnects() -> None:
    played: list[int] = []
    sound = ReadySound(play=lambda: played.append(1))
    sound.logged_in().join(timeout=5)
    assert sound.logged_in() is None                  # a reconnect's on_ready: no second pop
    assert played == [1]
