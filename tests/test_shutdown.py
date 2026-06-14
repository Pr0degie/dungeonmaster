"""Shutdown UX: the two-stage Ctrl+C guard, the [i/n] step progress display, and the
abandonable daemon-thread worker that keeps an in-flight TTS synth from join-blocking exit."""

import asyncio
import signal
import threading
import time

import pytest

from dmbot.__main__ import _install_sigint_guard
from dmbot.shutdown import (
    ShutdownProgress,
    disconnect_voice,
    inflight_daemon_threads,
    to_daemon_thread,
)


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


def test_disconnect_voice_bounds_a_slow_confirmation():
    """discord.py's disconnect leaves immediately but then awaits a gateway confirmation for up to
    30s — moot at exit. The real coroutine SWALLOWS the cancel from our bounding wait_for and still
    runs its own cleanup() (voice_state.py), so wait_for *returns* rather than raising TimeoutError.
    disconnect_voice must still report the wait as abandoned (False, detected by elapsed time), stay
    bounded, and leave the cleanup intact — so the mock models that real swallow-and-cleanup
    contract, not a bare sleep that lets the cancel propagate (which would mask the False path)."""

    class RealisticVC:
        def __init__(self):
            self.cleaned = False

        async def disconnect(self, *, force=False):
            try:
                await asyncio.sleep(30)  # the post-leave gateway-confirmation wait
            except asyncio.CancelledError:
                pass  # discord.py catches the cancel from our bounding wait_for...
            finally:
                self.cleaned = True  # ...and still runs cleanup(), so the leave stays clean

    async def go():
        vc = RealisticVC()
        t0 = time.monotonic()
        ok = await disconnect_voice(vc, timeout=0.1)
        assert ok is False                  # the confirmation wait was abandoned (by elapsed time)
        assert time.monotonic() - t0 < 1.0  # bounded — didn't wait out the 30s
        assert vc.cleaned is True           # the swallowed-cancel cleanup still ran (clean leave)
    asyncio.run(go())


def test_disconnect_voice_propagated_cancel_also_reports_abandoned():
    """If the confirmation coroutine instead lets the cancel propagate (an older discord.py, or a VC
    that doesn't swallow it), our bounding wait_for raises TimeoutError — disconnect_voice must report
    abandoned (False) on that path too, and still return fast."""

    class PropagatingVC:
        async def disconnect(self, *, force=False):
            await asyncio.sleep(30)  # no CancelledError handling → the cancel propagates out

    async def go():
        t0 = time.monotonic()
        ok = await disconnect_voice(PropagatingVC(), timeout=0.1)
        assert ok is False
        assert time.monotonic() - t0 < 1.0
    asyncio.run(go())


def test_disconnect_voice_fast_path_returns_true():
    """A voice client that confirms promptly returns True (no abandonment)."""

    class FastVC:
        async def disconnect(self, *, force=False):
            return None

    async def go():
        assert await disconnect_voice(FastVC(), timeout=2.0) is True
    asyncio.run(go())


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
