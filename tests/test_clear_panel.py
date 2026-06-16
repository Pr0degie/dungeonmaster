"""Unit tests for SessionRuntime.clear_panel — the shared "delete the previously-pinned panel
message and null the handle" helper extracted from the four re-post/teardown sites (mic / turn-order
/ pause). Best-effort: a panel already gone (discord.HTTPException on delete) is swallowed and the
handle is still nulled; an already-None handle is a no-op.

Built with SessionRuntime.__new__ (no Config/voice-stack boot) + a fake message whose async
.delete() records that it ran. Logs/tests English (CLAUDE.md)."""

from __future__ import annotations

import asyncio

import discord

from dmbot.runtime import SessionRuntime


class _FakeMessage:
    """Stands in for a discord.Message panel handle: records whether .delete() ran."""

    def __init__(self) -> None:
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


class _GoneMessage(_FakeMessage):
    """A panel already gone from Discord: .delete() raises discord.HTTPException, like a 404/410."""

    async def delete(self) -> None:
        self.deleted = True
        raise _Gone()


class _Gone(discord.HTTPException):
    """A minimal HTTPException stand-in (no real response object needed) so the fake delete can
    raise something clear_panel must catch."""

    def __init__(self) -> None:
        Exception.__init__(self, "panel already gone")


def _runtime() -> SessionRuntime:
    """A bare SessionRuntime without running __init__ (which boots the voice stack / Config)."""
    return SessionRuntime.__new__(SessionRuntime)


def test_clear_panel_deletes_and_nulls_handle():
    """A present panel is deleted and its handle reset to None."""
    rt = _runtime()
    msg = _FakeMessage()
    rt._mic_message = msg
    asyncio.run(rt.clear_panel("_mic_message"))
    assert msg.deleted is True
    assert rt._mic_message is None


def test_clear_panel_swallows_http_error_and_still_nulls():
    """A panel already gone raises discord.HTTPException on delete — swallowed, handle still nulled."""
    rt = _runtime()
    msg = _GoneMessage()
    rt._turn_message = msg
    asyncio.run(rt.clear_panel("_turn_message"))  # must not raise
    assert msg.deleted is True
    assert rt._turn_message is None


def test_clear_panel_is_noop_when_handle_already_none():
    """No stored panel → clear_panel is a no-op (no error, attr stays None)."""
    rt = _runtime()
    rt._pause_message = None
    asyncio.run(rt.clear_panel("_pause_message"))  # must not raise
    assert rt._pause_message is None
