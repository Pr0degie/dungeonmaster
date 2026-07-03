"""The ``<<UHR id>>`` marker (ADR 047): grammar incl. glued forms, strip-before-TTS, the
finalize seam and streaming parity — mirroring tests/test_erledigt_marker.py, whose flow this
marker copies."""

from __future__ import annotations

from dmbot.llm.stream_assembler import StreamAssembler, finalize_answer
from dmbot.rules.marker import extract_uhr

LABELS = ["Timo", "DM", "Spielleiter"]


# -- grammar ---------------------------------------------------------------------------------

def test_extract_uhr_basic() -> None:
    clean, reqs = extract_uhr("Der Lärm hallt durch die Gasse. <<UHR arbites>>")
    assert clean == "Der Lärm hallt durch die Gasse."
    assert len(reqs) == 1 and reqs[0].parsed and reqs[0].clock_id == "arbites"


def test_extract_uhr_glued_and_separator_forms() -> None:
    for raw in ("<<UHRarbites>>", "<<UHR_arbites>>", "<<UHR: arbites>>", "<<uhr arbites>>"):
        clean, reqs = extract_uhr(f"Text davor. {raw}")
        assert "<<" not in clean and "arbites" not in clean, raw
        assert reqs[0].clock_id == "arbites", raw


def test_extract_uhr_empty_marker_is_stripped_but_unparsed() -> None:
    clean, reqs = extract_uhr("Es wird enger. <<UHR >>")
    assert clean == "Es wird enger."
    assert len(reqs) == 1 and not reqs[0].parsed


def test_extract_uhr_multiple_markers_all_collected() -> None:
    _clean, reqs = extract_uhr("<<UHR arbites>> Dazwischen. <<UHR alarm>>")
    assert [r.clock_id for r in reqs] == ["arbites", "alarm"]


# -- finalize seam + streaming (ADR 017 parity) ------------------------------------------------

def test_finalize_answer_returns_uhr_requests() -> None:
    raw = "Die Ermittler kommen näher. <<UHR arbites>>"
    answer, tests, manifests, scenes, erledigt, uhr, _zeit = finalize_answer(raw, LABELS, None)
    assert "<<" not in answer
    assert tests == [] and manifests == [] and scenes == [] and erledigt == []
    assert len(uhr) == 1 and uhr[0].clock_id == "arbites"


def _run(deltas: list[str]):
    a = StreamAssembler(LABELS, None)
    spoken: list[str] = []
    for d in deltas:
        spoken.extend(a.feed(d))
    res = a.finish()
    spoken.extend(res.remaining)
    return spoken, res


def test_uhr_marker_split_across_a_chunk_boundary_is_extracted_not_spoken() -> None:
    deltas = ["Ihr hört Sirenen in der Ferne. <<U", "HR arbites>> Die Nacht bleibt unruhig."]
    spoken, res = _run(deltas)
    joined = " ".join(spoken)
    assert "<<" not in joined and "UHR" not in joined  # no partial/whole marker ever spoken
    assert "<<" not in res.answer
    assert res.uhr and res.uhr[0].clock_id == "arbites"


def test_stream_and_batch_parity_for_uhr_text() -> None:
    deltas = ["Der Alarm schrillt weiter. <<UHR alarm>>", " Niemand schläft heute."]
    _, res = _run(deltas)
    expected, _t, _m, _s, _e, _u, _z = finalize_answer("".join(deltas), LABELS, None)
    assert res.answer == expected
