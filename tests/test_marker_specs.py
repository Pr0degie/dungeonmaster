"""Marker registry (ADR 051) — table invariants + extract_all parity with the chained extractors."""

from __future__ import annotations

import pytest

from dmbot.rules import profile as profile_mod
from dmbot.rules.marker import (
    MARKER_SPECS,
    empty_markers,
    extract_all,
    extract_erledigt,
    extract_manifests,
    extract_scenes,
    extract_tests,
    extract_uhr,
    extract_zeit,
)

_IM = profile_mod.load("imperium_maledictum")

# A turn exercising every marker, glued forms included (the D61 fix must keep holding).
_NASTY = (
    "Der Gang liegt still. <<TEST Wahrnehmung Schwer für Tobi>> Etwas regt sich.\n"
    "<<MANIFEST Smite für Mortn push>> Die Luft flimmert. <<ORTmud_gate>>\n"
    "Ihr habt den Riegel gelöst. <<ERLEDIGT_opp-1>> <<UHR arbites>> <<ZEIT +4h>> Weiter."
)


def _chained(text: str, profile) -> tuple[str, dict[str, list]]:
    """The pre-051 hand-written sequence — the parity oracle for extract_all."""
    out = empty_markers()
    if profile is not None:
        text, out["tests"] = extract_tests(text, profile)
        text, out["manifests"] = extract_manifests(text, profile)
    text, out["scenes"] = extract_scenes(text)
    text, out["erledigt"] = extract_erledigt(text)
    text, out["uhr"] = extract_uhr(text)
    text, out["zeit"] = extract_zeit(text)
    return text, out


def test_registry_order_is_the_journal_key_order() -> None:
    # Load-bearing (ADR 051): extraction order AND markers.* key order in history.jsonl.
    assert [s.kind for s in MARKER_SPECS] == ["tests", "manifests", "scenes", "erledigt", "uhr", "zeit"]
    assert [s.keyword for s in MARKER_SPECS] == ["TEST", "MANIFEST", "ORT", "ERLEDIGT", "UHR", "ZEIT"]


def test_registry_flags_match_the_adr_table() -> None:
    by_kind = {s.kind: s for s in MARKER_SPECS}
    assert by_kind["tests"].needs_profile and by_kind["manifests"].needs_profile
    assert not any(by_kind[k].needs_profile for k in ("scenes", "erledigt", "uhr", "zeit"))
    # UHR/ZEIT are exempt from the results-only suppression (ADR 047 #7 / ADR 048 #6).
    assert [s.kind for s in MARKER_SPECS if not s.suppressible] == ["uhr", "zeit"]


@pytest.mark.parametrize("profile", [_IM, None], ids=["im-profile", "no-profile"])
def test_extract_all_matches_the_chained_extractors(profile) -> None:
    clean, requests = extract_all(_NASTY, profile)
    expected_clean, expected = _chained(_NASTY, profile)
    assert clean == expected_clean  # byte-identical narration
    assert requests == expected


def test_extract_all_without_profile_leaves_test_markers_in_the_text() -> None:
    # The historical profile-guard behaviour: no profile → TEST/MANIFEST are not stripped.
    clean, requests = extract_all(_NASTY, None)
    assert "<<TEST" in clean and "<<MANIFEST" in clean
    assert requests["tests"] == [] and requests["manifests"] == []
    assert "<<ORT" not in clean and "<<UHR" not in clean


def test_extract_all_marker_free_text_is_untouched_content() -> None:
    clean, requests = extract_all("Nur Erzählung, keine Marker.", _IM)
    assert clean == "Nur Erzählung, keine Marker."
    assert requests == empty_markers()
