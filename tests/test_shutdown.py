"""The two-stage Ctrl+C guard: first press arms ("Quit?"), second raises KeyboardInterrupt so
discord.py's run() tears down cleanly. We call the installed handler directly (no real signal),
so the test is deterministic and doesn't actually interrupt pytest."""

import signal

import pytest

import dmbot.__main__ as m
from dmbot.__main__ import _install_sigint_guard


def test_two_stage_ctrl_c(capsys, monkeypatch):
    # Stub the animation so the 2nd press doesn't spawn the real infinite dot-animation thread.
    monkeypatch.setattr(m, "_animate_shutdown", lambda: None)
    previous = signal.getsignal(signal.SIGINT)
    try:
        _install_sigint_guard()
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)

        handler(signal.SIGINT, None)  # 1st press → arm, no exit
        assert "Quit?" in capsys.readouterr().out

        with pytest.raises(KeyboardInterrupt):  # 2nd press → shut down (paints "Shutting down")
            handler(signal.SIGINT, None)
        assert "Shutting down" in capsys.readouterr().out
    finally:
        signal.signal(signal.SIGINT, previous)  # don't leave our handler installed for other tests
