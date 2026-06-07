"""Test-marker parsing (ADR 004) — <<TEST …>> → structured request, markers stripped from text."""

from __future__ import annotations

from dmbot.rules import profile as profile_mod
from dmbot.rules.marker import extract_tests

_IM = profile_mod.load("imperium_maledictum")


def test_full_marker_skill_difficulty_and_name() -> None:
    clean, reqs = extract_tests("Du spähst in den Gang. <<TEST Wahrnehmung Schwer für Tobi>>", _IM)
    assert "<<" not in clean and clean == "Du spähst in den Gang."
    assert len(reqs) == 1
    r = reqs[0]
    assert r.skill == "Wahrnehmung" and r.difficulty == "Schwer"
    assert r.target_name == "Tobi" and r.modifier is None and r.parsed


def test_explicit_modifier_form() -> None:
    _, reqs = extract_tests("<<TEST Heimlichkeit +10>>", _IM)
    assert reqs[0].skill == "Heimlichkeit" and reqs[0].modifier == 10 and reqs[0].difficulty is None


def test_unicode_minus_modifier() -> None:
    _, reqs = extract_tests("<<TEST Heimlichkeit −5 für Seskin>>", _IM)
    assert reqs[0].modifier == -5 and reqs[0].target_name == "Seskin"


def test_multiword_difficulty() -> None:
    _, reqs = extract_tests("<<TEST Fernkampf Sehr schwer für Vask>>", _IM)
    assert reqs[0].skill == "Fernkampf" and reqs[0].difficulty == "Sehr schwer"


def test_difficulty_alias_is_kept_verbatim_and_resolves_later() -> None:
    _, reqs = extract_tests("<<TEST Nahkampf hart>>", _IM)
    assert reqs[0].skill == "Nahkampf" and reqs[0].difficulty == "hart"
    assert _IM.difficulty_modifier(reqs[0].difficulty) == -20


def test_skill_without_difficulty() -> None:
    _, reqs = extract_tests("<<TEST Spurenlesen für Seskin>>", _IM)
    assert reqs[0].skill == "Spurenlesen" and reqs[0].difficulty is None
    assert reqs[0].target_name == "Seskin"


def test_multiple_markers_in_one_turn() -> None:
    clean, reqs = extract_tests(
        "Seskin schleicht <<TEST Heimlichkeit für Seskin>> und Vask lauscht <<TEST Wahrnehmung>>.", _IM
    )
    assert len(reqs) == 2 and "<<" not in clean
    assert reqs[0].target_name == "Seskin" and reqs[1].skill == "Wahrnehmung"


def test_unparseable_marker_is_stripped_and_flagged() -> None:
    clean, reqs = extract_tests("Etwas geschieht. <<TEST>>", _IM)
    assert "<<" not in clean and clean == "Etwas geschieht."
    assert len(reqs) == 1 and not reqs[0].parsed and reqs[0].skill == ""


def test_case_insensitive_marker_keyword() -> None:
    _, reqs = extract_tests("<<test Athletik für Vask>>", _IM)
    assert reqs[0].skill == "Athletik" and reqs[0].target_name == "Vask"
