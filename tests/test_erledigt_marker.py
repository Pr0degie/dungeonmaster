"""Stateful scene cards (ADR 043): the ``<<ERLEDIGT id>>`` marker parser + its ride through the
shared finalize seam and the streaming assembler. Pure + deterministic — the model only *requests*
a flag; code validates and applies it (golden rule #3), exactly like ``<<ORT>>`` (ADR 026)."""

from __future__ import annotations

from dmbot.llm.stream_assembler import StreamAssembler, finalize_answer
from dmbot.orchestrator import _ROLE_LABELS
from dmbot.rules.marker import extract_erledigt

LABELS = ["Timo", *_ROLE_LABELS]


# -- parser: extract_erledigt ----------------------------------------------------------------------

def test_erledigt_parsed_and_stripped() -> None:
    clean, reqs = extract_erledigt("Ihr nehmt die Papiere an euch. <<ERLEDIGT opp-1>>")
    assert "<<" not in clean and clean == "Ihr nehmt die Papiere an euch."
    assert len(reqs) == 1
    assert reqs[0].element_id == "opp-1" and reqs[0].parsed


def test_no_marker_leaves_text_untouched() -> None:
    clean, reqs = extract_erledigt("Die Gruppe berät ihr weiteres Vorgehen.")
    assert reqs == [] and clean == "Die Gruppe berät ihr weiteres Vorgehen."


def test_erledigt_never_survives_in_spoken_text() -> None:
    clean, _ = extract_erledigt("Es ist getan. <<ERLEDIGT geh-2>> Die Wahrheit liegt offen.")
    assert "<<" not in clean and "ERLEDIGT" not in clean and "geh-2" not in clean


def test_erledigt_glued_forms_resolve_to_the_same_id() -> None:
    # Spaced, glued, colon-separated and glued via `_`/`-` — all match and strip the leading glue,
    # mirroring the <<ORT>> tolerance (a `\b` after the keyword would let the glued form be spoken).
    for marker, expected in (
        ("<<ERLEDIGT opp-1>>", "opp-1"),
        ("<<ERLEDIGTopp-1>>", "opp-1"),
        ("<<ERLEDIGT: opp-1>>", "opp-1"),
        ("<<ERLEDIGT_geh-2>>", "geh-2"),
        ("<<erledigt geh-2 >>", "geh-2"),
    ):
        clean, reqs = extract_erledigt(f"Etwas geschieht. {marker}")
        assert "<<" not in clean, marker
        assert len(reqs) == 1 and reqs[0].element_id == expected and reqs[0].parsed, marker


def test_empty_erledigt_stripped_unparsed() -> None:
    clean, reqs = extract_erledigt("Nichts weiter. <<ERLEDIGT >>")
    assert "<<" not in clean
    assert reqs[0].element_id == "" and reqs[0].parsed is False


def test_multiple_erledigt_all_collected_in_order() -> None:
    # Unlike <<ORT>> (one move per turn), ALL valid flags in a turn are processed downstream.
    clean, reqs = extract_erledigt("<<ERLEDIGT opp-1>> Und mehr. <<ERLEDIGT geh-1>>")
    assert "<<" not in clean
    assert [r.element_id for r in reqs] == ["opp-1", "geh-1"]


# -- finalize seam + streaming (ADR 017 parity) ----------------------------------------------------

def test_finalize_answer_returns_erledigt_requests() -> None:
    raw = "Ihr habt den Schmuggel aufgedeckt. <<ERLEDIGT geh-1>>"
    answer, tests, manifests, scenes, erledigt = finalize_answer(raw, LABELS, None)
    assert "<<" not in answer
    assert tests == [] and manifests == [] and scenes == []
    assert len(erledigt) == 1 and erledigt[0].element_id == "geh-1"


def _run(deltas: list[str]):
    a = StreamAssembler(LABELS, None)
    spoken: list[str] = []
    for d in deltas:
        spoken.extend(a.feed(d))
    res = a.finish()
    spoken.extend(res.remaining)
    return spoken, res


def test_erledigt_marker_split_across_a_chunk_boundary_is_extracted_not_spoken() -> None:
    deltas = ["Ihr schafft es tatsächlich. <<ERLED", "IGT opp-1>> Die Menge jubelt euch zu."]
    spoken, res = _run(deltas)
    joined = " ".join(spoken)
    assert "<<" not in joined and "ERLEDIGT" not in joined  # no partial/whole marker ever spoken
    assert "<<" not in res.answer
    assert res.erledigt and res.erledigt[0].element_id == "opp-1"


def test_stream_and_batch_parity_for_erledigt_text() -> None:
    deltas = ["Die Kiste ist offen. <<ERLEDIGT opp-2>>", " Ihr seht die Wahrheit."]
    _, res = _run(deltas)
    expected, _t, _m, _s, _e = finalize_answer("".join(deltas), LABELS, None)
    assert res.answer == expected
