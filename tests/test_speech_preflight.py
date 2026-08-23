"""Unit tests for the XTTS speaker preflight — B13's silent fallback made loud.

The 2026-08-22 debug run spoke the whole evening in a random voice because ``TTS_SPEAKER``
held a *device* value (``cuda``) and the wrapper degraded behind a single WARNING line
("XTTS speaker 'cuda' unknown — using Dionisio Schuyler"). These tests pin the pure helpers
that turn that into a loud, actionable boot-time problem
(``docs/lessons/incidents-become-preflights.md``, ``unwired-knobs-and-silent-fallbacks.md``).

Torch-free by construction: everything under test lives in ``dmbot/voice/preflight.py``, so
the XTTS wrapper's behaviour is asserted through the helpers it calls, not by loading XTTS.
"""

from __future__ import annotations

import logging

from dmbot.voice.preflight import (
    DEFAULT_XTTS_SPEAKER,
    KNOWN_XTTS_SPEAKERS,
    check_tts_speaker,
    resolve_speaker,
    speaker_problem,
)

# A tiny stand-in list, so the "names the valid speakers" assertions stay exact.
_KNOWN = ("Dionisio Schuyler", "Damien Black", "Nova Hogarth")


# --- the baked list -------------------------------------------------------------------

def test_known_list_is_unique_and_holds_the_default() -> None:
    assert len(KNOWN_XTTS_SPEAKERS) == len(set(KNOWN_XTTS_SPEAKERS))
    assert DEFAULT_XTTS_SPEAKER in KNOWN_XTTS_SPEAKERS
    assert len(KNOWN_XTTS_SPEAKERS) == 58  # xtts_v2's built-in speaker set


# --- speaker_problem ------------------------------------------------------------------

def test_empty_speaker_is_not_a_problem() -> None:
    """Empty is the documented 'use the default' value, not a misconfiguration."""
    assert speaker_problem("", _KNOWN) is None
    assert speaker_problem("   ", _KNOWN) is None


def test_known_speaker_is_not_a_problem() -> None:
    assert speaker_problem("Damien Black", _KNOWN) is None


def test_unknown_speaker_names_every_valid_speaker_and_the_env_key() -> None:
    problem = speaker_problem("Kevin", _KNOWN)
    assert problem is not None
    assert "Kevin" in problem
    assert "TTS_SPEAKER" in problem  # which env var is wrong
    for name in _KNOWN:
        assert name in problem  # the valid names, spelled out


def test_device_value_calls_out_the_swapped_env_keys() -> None:
    """B13 itself: TTS_SPEAKER=cuda. The message must say the device value landed here."""
    problem = speaker_problem("cuda", _KNOWN)
    assert problem is not None
    assert "TTS_DEVICE" in problem and "TTS_SPEAKER" in problem


def test_close_match_is_suggested() -> None:
    problem = speaker_problem("Dionisio Schuyer", _KNOWN)
    assert problem is not None and "did you mean" in problem.lower()
    assert "Dionisio Schuyler" in problem


# --- resolve_speaker (what the XTTS wrapper actually picks) ---------------------------

def test_resolve_keeps_a_valid_speaker() -> None:
    assert resolve_speaker("Nova Hogarth", _KNOWN) == "Nova Hogarth"


def test_resolve_falls_back_to_the_default() -> None:
    assert resolve_speaker("cuda", _KNOWN) == DEFAULT_XTTS_SPEAKER
    assert resolve_speaker("", _KNOWN) == DEFAULT_XTTS_SPEAKER


def test_resolve_uses_the_first_available_when_the_default_is_gone() -> None:
    """Model-side drift must not leave the DM mute or crash the load."""
    assert resolve_speaker("cuda", ("Nova Hogarth", "Damien Black")) == "Nova Hogarth"


def test_resolve_on_an_empty_model_list_yields_empty() -> None:
    assert resolve_speaker("cuda", ()) == ""


# --- check_tts_speaker (the boot preflight) -------------------------------------------

def test_check_is_clean_for_a_valid_speaker() -> None:
    assert check_tts_speaker("Damien Black", known=_KNOWN) == []


def test_check_is_clean_for_the_empty_default() -> None:
    assert check_tts_speaker("", known=_KNOWN) == []


def test_check_ignores_non_xtts_engines() -> None:
    """TTS_SPEAKER is an XTTS knob; Piper must not produce a phantom problem."""
    assert check_tts_speaker("cuda", engine="piper", known=_KNOWN) == []


def test_check_reports_and_logs_loudly_without_raising(caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="dmbot.voice.preflight"):
        problems = check_tts_speaker("cuda", known=_KNOWN)
    assert len(problems) == 1
    assert "TTS_DEVICE" in problems[0]
    assert any(r.levelno == logging.ERROR for r in caplog.records), "must log at ERROR"
    assert any("TTS_SPEAKER" in r.getMessage() for r in caplog.records)


def test_check_defaults_to_the_baked_speaker_list() -> None:
    """No ``known=`` given → the torch-free baked list, so this runs before XTTS loads."""
    assert check_tts_speaker(DEFAULT_XTTS_SPEAKER) == []
    assert check_tts_speaker("cuda") != []
