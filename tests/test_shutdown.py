"""Shutdown UX: the two-stage Ctrl+C guard, the [i/n] step progress display, and the
abandonable daemon-thread worker that keeps an in-flight TTS synth from join-blocking exit."""

import asyncio
import signal
import threading
import time

import pytest

from dmbot.__main__ import _install_sigint_guard
from dmbot.shutdown import ShutdownProgress, to_daemon_thread, inflight_daemon_threads


def test_two_stage_ctrl_c(capsys):
    """First press arms ("Quit?") and does NOT exit; the second raises KeyboardInterrupt so
    discord.py's run() tears down. We call the installed handler directly (no real signal)."""
    previous = signal.getsignal(signal.SIGINT)
    try:
        _install_sigint_guard()
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)

        handler(signal.SIGINT, None)  # 1st press → arm, no exit
        assert "Quit?" in capsys.readouterr().out

        with pytest.raises(KeyboardInterrupt):  # 2nd press → shut down
            handler(signal.SIGINT, None)
        assert "Shutting down" in capsys.readouterr().out
    finally:
        signal.signal(signal.SIGINT, previous)  # don't leave our handler installed for other tests


def test_progress_counts_steps(capsys):
    """begin(n) + n step() blocks → each finished step prints '[i/n] label ✓' and finish()
    summarises 'n/n Schritte'. Outside begin(), step() degrades to no console output."""
    prog = ShutdownProgress()
    prog.begin(2)
    with prog.step("erste Sache"):
        pass
    with prog.step("zweite Sache"):
        pass
    prog.finish()
    out = capsys.readouterr().out
    assert "[1/2] erste Sache" in out
    assert "[2/2] zweite Sache" in out
    assert "2/2 Schritte" in out


def test_step_without_begin_is_silent(capsys):
    """A cog unloaded at runtime (no shutdown in progress) must not paint step lines."""
    prog = ShutdownProgress()
    assert not prog.active
    with prog.step("runtime unload"):
        pass
    assert "runtime unload" not in capsys.readouterr().out


def test_to_daemon_thread_returns_result_and_propagates_error():
    async def go():
        assert await to_daemon_thread(lambda: 21 * 2) == 42
        with pytest.raises(ValueError):
            await to_daemon_thread(_raise)
    asyncio.run(go())


def _raise():
    raise ValueError("boom")


def test_to_daemon_thread_uses_a_daemon_thread_and_tracks_inflight():
    seen = {}
    started = threading.Event()
    release = threading.Event()

    def work():
        seen["daemon"] = threading.current_thread().daemon
        seen["inflight_during"] = inflight_daemon_threads()
        started.set()
        release.wait(2)
        return "ok"

    async def go():
        task = asyncio.ensure_future(to_daemon_thread(work))
        await asyncio.to_thread(started.wait, 2)
        assert seen["daemon"] is True            # abandoned at interpreter exit, never joined
        assert seen["inflight_during"] == 1       # counted while running
        release.set()
        assert await task == "ok"
        # settles back to 0 once the worker's finally runs
        for _ in range(20):
            if inflight_daemon_threads() == 0:
                break
            await asyncio.sleep(0.02)
        assert inflight_daemon_threads() == 0
    asyncio.run(go())
