"""The pure in-game-time helpers (ADR 048): duration parsing (tolerant units), time/phase
rendering, the next-morning jump, coarse deadline remaining-time and the expiry-note framing.

Plus the clock that runs without the model (ADR 059): the per-turn and per-scene-change
increments on ``WorldState`` and the adventure-seeded start time, deadlines and clocks."""

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
from dmbot.memory.state import (
    SCENE_CHANGE_ADVANCE_MINUTES,
    TURN_ADVANCE_MINUTES,
    WorldState,
    absolute_minutes,
    parse_campaign_time_de,
    parse_time_of_day,
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


# -- the clock runs without the model: per-turn / per-scene-change advance (ADR 059) -------

def test_a_turn_costs_a_small_fixed_amount_of_ingame_time() -> None:
    s = WorldState()
    assert s.time_minutes == DEFAULT_START_MINUTES
    assert s.advance_turn() == []                       # no deadlines → nothing expires
    assert s.time_minutes == DEFAULT_START_MINUTES + TURN_ADVANCE_MINUTES
    assert s.time_ingame == render_time_de(s.time_minutes)   # the mirror is re-rendered


def test_a_scene_change_costs_more_than_a_turn() -> None:
    assert SCENE_CHANGE_ADVANCE_MINUTES > TURN_ADVANCE_MINUTES
    s = WorldState()
    s.advance_scene_change()
    assert s.time_minutes == DEFAULT_START_MINUTES + SCENE_CHANGE_ADVANCE_MINUTES


def test_turn_advance_crosses_a_deadline_exactly_once() -> None:
    s = WorldState()
    s.add_deadline("Mitternachtssirene", TURN_ADVANCE_MINUTES + 1)
    assert s.advance_turn() == []                        # not due yet
    assert [dl.label for dl in s.advance_turn()] == ["Mitternachtssirene"]
    assert s.advance_turn() == []                        # latched — never fires twice


def test_turn_advance_can_be_switched_off_with_zero() -> None:
    s = WorldState()
    assert s.advance_turn(minutes=0) == []
    assert s.advance_scene_change(minutes=0) == []
    assert s.time_minutes == DEFAULT_START_MINUTES and s.time_ingame == ""


# -- the adventure ships its own clock (ADR 059) -------------------------------------------

@pytest.mark.parametrize("text,minutes", [
    ("21:00", 1260), ("00:00", 0), ("08:05", 485), ("23:59", 1439), (" 7:30 ", 450),
])
def test_parse_time_of_day_accepts_hh_mm(text: str, minutes: int) -> None:
    assert parse_time_of_day(text) == minutes


@pytest.mark.parametrize("text", ["", "abends", "24:00", "21:60", "21", "21:00:00", "-1:00"])
def test_parse_time_of_day_rejects_everything_else(text: str) -> None:
    assert parse_time_of_day(text) is None


def test_campaign_time_reads_back_what_render_time_de_prints() -> None:
    assert parse_campaign_time_de("Tag 1, 21:00") == 1260
    assert parse_campaign_time_de("Tag 2, 00:00") == 1440
    assert parse_campaign_time_de("tag 3, 07:05") == 2 * 1440 + 425
    assert parse_campaign_time_de("21:00") is None and parse_campaign_time_de("Tag 1") is None
    for minutes in (0, 485, 1260, 4321):
        assert parse_campaign_time_de(render_time_de(minutes)) == minutes


def test_absolute_minutes_takes_ints_and_clock_times_with_a_day() -> None:
    assert absolute_minutes(1260) == 1260
    assert absolute_minutes("1260") == 1260
    assert absolute_minutes("21:00") == 1260
    assert absolute_minutes("Tag 1, 21:00") == 1260      # the day rides in the string
    assert absolute_minutes("Tag 2, 00:00", day=9) == 1440
    assert absolute_minutes("00:00", day=2) == 1440      # midnight *after* day 1
    assert absolute_minutes("21:00", day=3) == 2 * 1440 + 1260
    assert absolute_minutes(None) is None
    assert absolute_minutes("bald") is None
    assert absolute_minutes(-5) is None


def test_seed_time_from_adventure_sets_start_deadlines_and_clocks() -> None:
    s = WorldState()
    assert s.seed_time_from_adventure(
        start_time="21:00",
        deadlines=[{"label": "Mitternachtssirene", "at": "00:00", "day": 2}],
        clocks=[{"name": "Arbites-Ermittlung", "size": 6, "filled": 1}],
    ) is True
    assert s.time_minutes == 1260 and s.time_ingame == "Tag 1, 21:00"
    assert s.time_seeded is True
    dl = s.deadlines[0]
    assert (dl.id, dl.label, dl.due_minutes) == ("mitternachtssirene", "Mitternachtssirene", 1440)
    assert remaining_de(dl.due_minutes, s.time_minutes) == "noch ~3 Std"
    c = s.clocks[0]
    assert (c.id, c.name, c.size, c.filled) == ("arbites-ermittlung", "Arbites-Ermittlung", 6, 1)


def test_seeded_deadlines_also_accept_a_relative_offset() -> None:
    s = WorldState()
    s.seed_time_from_adventure(start_time=1260, deadlines=[
        {"label": "Die Barke legt ab", "in_minutes": 180},
        {"label": "Absolut", "due_minutes": 1400},
    ])
    assert [dl.due_minutes for dl in s.deadlines] == [1440, 1400]


def test_seeding_reads_the_shape_the_adventure_file_ships() -> None:
    # Exactly the block data/adventures/debug-kampagne/adventure.json carries: the rendered
    # start time, a deadline as a duration from the start, clocks with their own ids.
    s = WorldState()
    assert s.seed_time_from_adventure(
        start_time="Tag 1, 21:00",
        deadlines=[{"id": "mitternachtssirene",
                    "label": "Mitternachtssirene: Der Leichter legt ab", "due_in": "+3h"}],
        clocks=[{"id": "wachsamkeit", "name": "Wachsamkeit des Kettenbunds",
                 "size": 6, "filled": 0}],
    ) is True
    assert s.time_ingame == "Tag 1, 21:00"
    dl = s.deadlines[0]
    assert dl.id == "mitternachtssirene"          # the file's id wins over the slugified label
    assert dl.due_minutes == 1440 and remaining_de(dl.due_minutes, s.time_minutes) == "noch ~3 Std"
    assert s.clocks[0].id == "wachsamkeit" and s.clocks[0].filled == 0


def test_seeding_skips_a_deadline_whose_duration_does_not_parse() -> None:
    s = WorldState()
    s.seed_time_from_adventure(deadlines=[{"label": "Sirene", "due_in": "bald"}])
    assert s.deadlines == []


def test_seeding_twice_is_a_no_op_unless_forced() -> None:
    s = WorldState()
    s.seed_time_from_adventure(start_time="21:00", deadlines=[{"label": "Sirene", "at": "23:00"}])
    s.advance_turn()
    assert s.seed_time_from_adventure(start_time="21:00",
                                      deadlines=[{"label": "Sirene", "at": "23:00"}]) is False
    assert len(s.deadlines) == 1 and s.time_minutes == 1260 + TURN_ADVANCE_MINUTES
    assert s.seed_time_from_adventure(start_time="06:00", force=True) is True
    assert s.time_minutes == 360


def test_seeding_skips_malformed_entries_without_touching_the_rest() -> None:
    s = WorldState()
    assert s.seed_time_from_adventure(
        start_time="nachts",                       # unparseable → the default start survives
        deadlines=[{"at": "23:00"}, {"label": "Sirene", "at": "quatsch"},
                   {"label": "Echt", "at": "23:00"}],
        clocks=[{"size": 6}, {"name": "Schief", "size": 5}, {"name": "Gut"}],
    ) is True
    assert s.time_minutes == DEFAULT_START_MINUTES
    assert [dl.label for dl in s.deadlines] == ["Echt"]
    assert [(c.name, c.size) for c in s.clocks] == [("Gut", 6)]
