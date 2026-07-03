"""The pure in-game-time helpers (ADR 048): duration parsing (tolerant units), time/phase
rendering, the next-morning jump, coarse deadline remaining-time and the expiry-note framing."""

from __future__ import annotations

import pytest

from dmbot.memory.gametime import (
    DEFAULT_START_MINUTES,
    MAX_MARKER_ADVANCE_MINUTES,
    day_phase_de,
    deadline_line_de,
    deadline_note_de,
    next_morning,
    parse_duration_de,
    remaining_de,
    render_time_de,
    render_time_phase_de,
)


# -- parse_duration_de ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,minutes", [
    ("+30m", 30), ("30m", 30), ("+ 30 min", 30), ("45 Minuten", 45), ("1 minute", 1),
    ("+4h", 240), ("4 h", 240), ("2 Std", 120), ("2std", 120), ("1 Stunde", 60),
    ("3 stunden", 180), ("+2 STD.", 120),
    ("1,5h", 90), ("0.5 h", 30),
])
def test_parse_duration_accepts_tolerant_german_forms(text: str, minutes: int) -> None:
    assert parse_duration_de(text) == minutes


@pytest.mark.parametrize("text", [
    "", "bald", "-30m", "30", "30 tage", "h", "++2h", "2hh", "eine Stunde", "0m", "0,4m",
])
def test_parse_duration_rejects_garbage_negative_and_zero(text: str) -> None:
    assert parse_duration_de(text) is None


# -- rendering -----------------------------------------------------------------------------------

def test_render_time_counts_days_from_one() -> None:
    assert render_time_de(0) == "Tag 1, 00:00"
    assert render_time_de(DEFAULT_START_MINUTES) == "Tag 1, 08:00"
    assert render_time_de(1440 + 14 * 60 + 30) == "Tag 2, 14:30"
    assert render_time_de(-5) == "Tag 1, 00:00"  # clamped, never negative


def test_day_phase_boundaries() -> None:
    for hour, phase in ((4, "Nacht"), (5, "Morgen"), (10, "Morgen"), (11, "Tag"),
                        (16, "Tag"), (17, "Abend"), (21, "Abend"), (22, "Nacht"), (0, "Nacht")):
        assert day_phase_de(hour * 60) == phase, f"{hour:02d}:00"
    assert day_phase_de(3 * 1440 + 12 * 60) == "Tag"  # phase depends on hour-of-day, not day


def test_render_time_phase_combines_both() -> None:
    assert render_time_phase_de(1440 + 23 * 60 + 10) == "Tag 2, 23:10 (Nacht)"


# -- next_morning (!zeit tag) ----------------------------------------------------------------------

def test_next_morning_from_evening_is_tomorrow_0800() -> None:
    assert next_morning(20 * 60) == 1440 + 480  # day 1, 20:00 → day 2, 08:00


def test_next_morning_from_small_hours_is_the_same_day() -> None:
    assert next_morning(1440 + 2 * 60) == 1440 + 480  # day 2, 02:00 → day 2, 08:00


def test_next_morning_is_strictly_in_the_future_at_exactly_0800() -> None:
    assert next_morning(480) == 1440 + 480  # day 1, 08:00 → day 2, 08:00


# -- deadlines -------------------------------------------------------------------------------------

def test_remaining_is_coarse_by_magnitude() -> None:
    assert remaining_de(100, 80) == "noch ~20 Min"
    assert remaining_de(480, 300) == "noch ~3 Std"
    assert remaining_de(3 * 1440, 1440) == "noch ~2 Tage"
    assert remaining_de(1440 + 100, 100) == "noch ~1 Tag"
    assert remaining_de(100, 100) == "ABGELAUFEN"
    assert remaining_de(100, 500) == "ABGELAUFEN"


def test_deadline_line_carries_id_label_and_remaining() -> None:
    line = deadline_line_de("zug", "Der Zug nach Hive Sibellus", 2 * 1440, 1440)
    assert line == "[zug] Der Zug nach Hive Sibellus — noch ~1 Tag"


def test_deadline_note_names_the_label_in_quotes() -> None:
    note = deadline_note_de("Der Zug nach Hive Sibellus")
    assert "„Der Zug nach Hive Sibellus“" in note and "JETZT" in note


def test_marker_clamp_is_twelve_hours() -> None:
    assert MAX_MARKER_ADVANCE_MINUTES == 720
