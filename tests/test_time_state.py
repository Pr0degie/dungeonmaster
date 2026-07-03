"""The world-state half of in-game time (ADR 048): schema roundtrip + migration of pre-048
states, the ``advance_time`` mutator (mirror string, expiry latched exactly once), deadline
management, the prompt summary lines and the combined pressure panel."""

from __future__ import annotations

import logging

from dmbot.memory.gametime import DEFAULT_START_MINUTES
from dmbot.memory.state import (
    WorldState,
    pressure_panel_de,
    world_state_summary_de,
)


# -- schema roundtrip + migration ------------------------------------------------------------------

def test_fresh_state_starts_day_one_morning() -> None:
    assert WorldState().time_minutes == DEFAULT_START_MINUTES == 480


def test_roundtrip_preserves_time_and_deadlines(tmp_path) -> None:
    s = WorldState()
    s.advance_time(90)
    s.add_deadline("Der Zug nach Hive Sibellus", 1440)
    path = tmp_path / "state.json"
    s.save(path)

    again = WorldState.load(path)
    assert again is not None
    assert again.time_minutes == 480 + 90
    assert again.time_ingame == "Tag 1, 09:30"  # the rendered mirror survives too
    assert len(again.deadlines) == 1
    dl = again.deadlines[0]
    assert dl.id == "der-zug-nach-hive-sibellus"
    assert dl.due_minutes == 480 + 90 + 1440 and not dl.notified


def test_deadlines_and_notified_are_omitted_when_empty(tmp_path) -> None:
    d = WorldState().to_dict()
    assert "deadlines" not in d
    s = WorldState()
    s.add_deadline("Zug", 100)
    dumped = s.to_dict()["deadlines"][0]
    assert "notified" not in dumped  # False is omitted; True persists
    s.advance_time(200)
    assert s.to_dict()["deadlines"][0]["notified"] is True


def test_pre_048_state_migrates_to_day_one_morning(caplog) -> None:
    legacy = {"session_id": "x", "system": "im", "characters": [], "npcs": [], "quests": [],
              "location": "Unterstadt", "time_ingame": "am späten Abend", "recap": "",
              "scene_id": ""}
    with caplog.at_level(logging.INFO):
        s = WorldState.from_dict(legacy)
    assert s.time_minutes == DEFAULT_START_MINUTES
    assert s.time_ingame == "am späten Abend"  # legacy prose stays until the first advance
    assert "migration" in caplog.text and "Tag 1, 08:00" in caplog.text
    s.advance_time(30)
    assert s.time_ingame == "Tag 1, 08:30"  # first advance re-renders the mirror


# -- advance_time ----------------------------------------------------------------------------------

def test_advance_time_is_forward_only_and_renders_the_mirror() -> None:
    s = WorldState()
    assert s.advance_time(0) == [] and s.advance_time(-10) == []
    assert s.time_minutes == 480
    s.advance_time(6 * 60)
    assert s.time_minutes == 480 + 360 and s.time_ingame == "Tag 1, 14:00"


def test_deadline_expiry_fires_exactly_once() -> None:
    s = WorldState()
    s.add_deadline("Zug", 60)
    assert s.advance_time(30) == []          # not due yet
    expired = s.advance_time(30)             # crosses due exactly
    assert [dl.label for dl in expired] == ["Zug"]
    assert s.advance_time(999) == []          # latched — never re-fires
    assert s.deadlines[0].notified            # …and persists as notified


def test_deadline_ids_dedupe_with_numeric_suffix() -> None:
    s = WorldState()
    a = s.add_deadline("Zug", 10)
    b = s.add_deadline("Zug", 20)
    assert (a.id, b.id) == ("zug", "zug-2")
    assert s.find_deadline("ZUG") is a        # case-tolerant lookup
    assert s.remove_deadline("zug-2") is b and len(s.deadlines) == 1
    assert s.remove_deadline("nope") is None


# -- prompt summary + pressure panel ----------------------------------------------------------------

def test_summary_carries_time_phase_and_deadlines() -> None:
    s = WorldState()
    s.advance_time(15 * 60)                   # → day 1, 23:00 (Nacht)
    s.add_deadline("Der Zug nach Hive Sibellus", 1440)
    out = world_state_summary_de(s)
    assert "Zeit: Tag 1, 23:00 (Nacht)" in out
    assert "Fristen: [der-zug-nach-hive-sibellus] Der Zug nach Hive Sibellus — noch ~1 Tag" in out


def test_summary_marks_expired_deadlines() -> None:
    s = WorldState()
    s.add_deadline("Zug", 30)
    s.advance_time(60)
    assert "ABGELAUFEN" in world_state_summary_de(s)


def test_pressure_panel_shows_time_deadlines_and_clocks() -> None:
    s = WorldState()
    s.add_deadline("Zug", 1440)
    s.add_clock("Alarm", 4)
    panel = pressure_panel_de(s)
    lines = panel.splitlines()
    assert lines[0].startswith("🕐") and "Tag 1, 08:00" in lines[0] and "Morgen" in lines[0]
    assert any("Zug" in ln and "noch ~1 Tag" in ln for ln in lines)
    assert any("◉" in ln or "○" in ln for ln in lines)  # the clock block rides below


def test_pressure_panel_without_clocks_has_no_clock_header() -> None:
    s = WorldState()
    s.add_deadline("Zug", 60)
    assert "Uhren" not in pressure_panel_de(s)
