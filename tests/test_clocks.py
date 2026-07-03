"""Consequence-clock schema + helpers (ADR 047): Clock roundtrip, backward-compatible
WorldState (de)serialisation, slug ids, tick/untick semantics, the prompt summary line and the
pure render helpers. Plus the GM-note seam: _prepare_turn injects queued ``[Regie]`` lines and
records them for the replay journal (ADR 046)."""

from __future__ import annotations

from dmbot.memory.state import (
    Clock,
    WorldState,
    clock_full_note_de,
    clock_line_de,
    clock_segments,
    clocks_panel_de,
    slugify_clock_id,
    world_state_summary_de,
)
from dmbot.orchestrator import DMBrain


# -- schema roundtrip ------------------------------------------------------------------------

def test_clock_roundtrip_and_omit_when_empty() -> None:
    state = WorldState(session_id="s")
    assert "clocks" not in state.to_dict()  # old shape untouched without clocks
    state.add_clock("Arbites-Ermittlung", 6)
    state.tick_clock("arbites-ermittlung")
    d = state.to_dict()
    assert d["clocks"] == [
        {"id": "arbites-ermittlung", "name": "Arbites-Ermittlung", "size": 6, "filled": 1}
    ]  # visible=True is omitted (default)
    loaded = WorldState.from_dict(d)
    assert loaded.clocks[0] == state.clocks[0]


def test_old_state_without_clocks_loads_unchanged() -> None:
    loaded = WorldState.from_dict({"session_id": "s", "characters": [], "npcs": []})
    assert loaded.clocks == []


def test_clock_from_dict_is_tolerant() -> None:
    c = Clock.from_dict({"id": "x", "name": "X", "size": 4, "filled": 99, "visible": False})
    assert c.filled == 4  # clamped to size
    assert c.visible is False and c.full
    assert Clock.from_dict({"id": "y", "name": "Y", "size": 0}).size == 6  # degrade, don't die


# -- slug ids --------------------------------------------------------------------------------

def test_slugify_transliterates_and_stays_marker_safe() -> None:
    assert slugify_clock_id("Arbites-Ermittlung") == "arbites-ermittlung"
    assert slugify_clock_id("Zorn des Häretikers!") == "zorn-des-haeretikers"
    assert slugify_clock_id("  ??? ") == "uhr"  # empty degrades
    # never ends in -/_ (the glued-marker strip would peel it, ADR 043's binding)
    assert not slugify_clock_id("Alarm...").endswith(("-", "_"))


def test_add_clock_dedups_ids_with_numeric_suffix() -> None:
    state = WorldState()
    a = state.add_clock("Alarm", 4)
    b = state.add_clock("Alarm", 6)
    assert (a.id, b.id) == ("alarm", "alarm-2")
    assert state.find_clock("ALARM") is a  # case-insensitive lookup


# -- tick / untick ---------------------------------------------------------------------------

def test_tick_stops_at_full_and_untick_stops_at_zero() -> None:
    state = WorldState()
    state.add_clock("Alarm", 4)
    for _ in range(4):
        assert state.tick_clock("alarm") is not None
    assert state.find_clock("alarm").full
    assert state.tick_clock("alarm") is None  # a full clock is not tickable
    assert state.tick_clock("nope") is None   # unknown id
    for _ in range(4):
        assert state.untick_clock("alarm") is not None
    assert state.untick_clock("alarm").filled == 0  # clamped at 0, no underflow


# -- rendering -------------------------------------------------------------------------------

def test_segments_line_and_panel_render() -> None:
    c = Clock(id="arbites", name="Arbites-Ermittlung", size=6, filled=3)
    assert clock_segments(c) == "◉◉◉○○○"
    assert clock_line_de(c) == "[arbites] Arbites-Ermittlung 3/6"
    full = Clock(id="alarm", name="Alarm", size=4, filled=4)
    assert clock_line_de(full).endswith("— VOLL")
    panel = clocks_panel_de([c, full])
    assert "⏱ **Uhren**" in panel and "◉◉◉○○○" in panel and "**VOLL**" in panel
    # visible-to-all first cut: a visible=False clock still renders (UI ignores the field)
    hidden = Clock(id="geheim", name="Geheim", size=4, filled=1, visible=False)
    assert "geheim" in clocks_panel_de([hidden])


def test_summary_includes_clock_line() -> None:
    state = WorldState()
    assert "Uhren" not in world_state_summary_de(state)
    state.add_clock("Arbites-Ermittlung", 6)
    state.tick_clock("arbites-ermittlung")
    summary = world_state_summary_de(state)
    assert "Uhren (Druck/Fortschritt): [arbites-ermittlung] Arbites-Ermittlung 1/6" in summary


# -- GM notes ([Regie] injection, ADR 047 #8) ------------------------------------------------

class _NoCallClient:
    async def chat(self, *a, **k):  # pragma: no cover - _prepare_turn never calls the LLM
        raise AssertionError("no LLM call expected")


def test_prepare_turn_injects_and_records_gm_notes() -> None:
    brain = DMBrain(_NoCallClient())
    brain.add_player_line(1, "Timo", "Ich lausche.")
    brain.add_gm_note(1, "Die Uhr „Alarm“ ist voll — die Konsequenz tritt JETZT ein.")
    user_msg, _labels, _history = brain._prepare_turn(1, None)
    assert "[Regie] Die Uhr „Alarm“ ist voll" in user_msg
    assert "Timo: Ich lausche." in user_msg
    # replay capture (ADR 046): dm-eval re-feeds the notes to compose the same user_msg
    assert brain._replay_turn[1]["notes"] == [
        "Die Uhr „Alarm“ ist voll — die Konsequenz tritt JETZT ein."
    ]
    # one-shot: the next turn does not repeat the note
    brain.add_player_line(1, "Timo", "Weiter.")
    user_msg2, _l, _h = brain._prepare_turn(1, None)
    assert "[Regie]" not in user_msg2


def test_empty_turn_does_not_swallow_gm_notes() -> None:
    brain = DMBrain(_NoCallClient())
    brain.add_gm_note(1, "Hinweis.")
    assert brain._prepare_turn(1, None) is None  # nothing to respond to
    brain.add_player_line(1, "Timo", "Jetzt.")
    user_msg, _l, _h = brain._prepare_turn(1, None)
    assert "[Regie] Hinweis." in user_msg  # the note survived the empty turn


def test_discard_gm_notes_by_substring() -> None:
    brain = DMBrain(_NoCallClient())
    brain.add_gm_note(1, clock_full_note_de(Clock(id="alarm", name="Alarm", size=4, filled=4)))
    brain.add_gm_note(1, "Anderes.")
    assert brain.discard_gm_notes(1, containing="„Alarm“") == 1
    brain.add_player_line(1, "Timo", "Weiter.")
    user_msg, _l, _h = brain._prepare_turn(1, None)
    assert "Alarm" not in user_msg and "[Regie] Anderes." in user_msg


def test_reset_drops_pending_gm_notes_and_uhr_queue() -> None:
    brain = DMBrain(_NoCallClient())
    brain.add_gm_note(1, "Hinweis.")
    brain._pending_uhr[1] = [object()]
    brain.reset(1)
    assert brain._gm_notes == {} and brain._pending_uhr == {}
