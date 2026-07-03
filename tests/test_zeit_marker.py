"""The <<ZEIT …>> marker (ADR 048): extraction grammar (tolerant units, glue forms, broken
payloads), the finalize seam and streaming parity — mirroring tests/test_uhr_marker.py."""

from __future__ import annotations

from dmbot.llm.stream_assembler import StreamAssembler, finalize_answer
from dmbot.rules.marker import extract_zeit

LABELS = ["Timo", "Spielleiter", "DM"]


# -- extraction grammar --------------------------------------------------------------------------

def test_extract_zeit_parses_minutes_and_hours() -> None:
    clean, reqs = extract_zeit("Ihr durchsucht das Archiv. <<ZEIT +45m>>")
    assert "<<" not in clean and "ZEIT" not in clean
    assert len(reqs) == 1 and reqs[0].parsed and reqs[0].minutes == 45

    _clean, reqs = extract_zeit("Die Fahrt zieht sich. <<ZEIT +4h>>")
    assert reqs[0].minutes == 240

    _clean, reqs = extract_zeit("Ihr rastet. <<ZEIT 2 Std>>")  # + optional, German unit
    assert reqs[0].minutes == 120


def test_extract_zeit_tolerates_glued_and_colon_forms() -> None:
    for raw in ("<<ZEIT+30m>>", "<<ZEIT: +30m>>", "<<zeit +30m>>", "<<ZEIT_30m>>"):
        _clean, reqs = extract_zeit(f"Es vergeht Zeit. {raw}")
        assert reqs and reqs[0].parsed and reqs[0].minutes == 30, raw


def test_extract_zeit_broken_payloads_are_stripped_but_unparsed() -> None:
    for raw in ("<<ZEIT>>", "<<ZEIT bald>>", "<<ZEIT -2h>>", "<<ZEIT +0m>>"):
        clean, reqs = extract_zeit(f"Etwas passiert. {raw} Weiter geht es.")
        assert "<<" not in clean and "ZEIT" not in clean, raw  # never spoken
        assert len(reqs) == 1 and not reqs[0].parsed and reqs[0].minutes is None, raw


def test_extract_zeit_collects_all_markers_in_order() -> None:
    _clean, reqs = extract_zeit("<<ZEIT +1h>> Dazwischen. <<ZEIT +30m>>")
    assert [r.minutes for r in reqs] == [60, 30]


# -- finalize seam + streaming (ADR 017 parity) ------------------------------------------------

def test_finalize_answer_returns_zeit_requests() -> None:
    raw = "Die Durchsuchung dauert. <<ZEIT +2h>>"
    answer, tests, manifests, scenes, erledigt, uhr, zeit = finalize_answer(raw, LABELS, None)
    assert "<<" not in answer
    assert tests == [] and manifests == [] and scenes == [] and erledigt == [] and uhr == []
    assert len(zeit) == 1 and zeit[0].minutes == 120


def _run(deltas: list[str]):
    a = StreamAssembler(LABELS, None)
    spoken: list[str] = []
    for d in deltas:
        spoken.extend(a.feed(d))
    res = a.finish()
    spoken.extend(res.remaining)
    return spoken, res


def test_zeit_marker_split_across_a_chunk_boundary_is_extracted_not_spoken() -> None:
    deltas = ["Ihr wartet, bis es dunkel wird. <<ZE", "IT +3h>> Die Stadt wird still."]
    spoken, res = _run(deltas)
    joined = " ".join(spoken)
    assert "<<" not in joined and "ZEIT" not in joined  # no partial/whole marker ever spoken
    assert "<<" not in res.answer
    assert res.zeit and res.zeit[0].minutes == 180


def test_stream_and_batch_parity_for_zeit_text() -> None:
    deltas = ["Der Marsch kostet euch Stunden. <<ZEIT +5h>>", " Endlich seht ihr die Tore."]
    _, res = _run(deltas)
    expected, _t, _m, _s, _e, _u, _z = finalize_answer("".join(deltas), LABELS, None)
    assert res.answer == expected
