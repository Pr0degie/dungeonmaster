"""Auto scene transitions (ADR 026): the ``<<ORT id>>`` marker parser + the ``leads_to``-gated move
validation. Both halves are pure + deterministic — no Discord, no LLM, like the rules engine
(golden rule #3: the scene pointer is code state, the model only *requests* a move)."""

from __future__ import annotations

from dmbot.rag.adventure import Adventure, Scene
from dmbot.rules.marker import extract_scenes


# -- parser: extract_scenes -----------------------------------------------------------------------

def test_marker_parsed_and_stripped() -> None:
    clean, reqs = extract_scenes("Ihr tretet hinaus auf den Platz. <<ORT mud_gate>>")
    assert "<<" not in clean and clean == "Ihr tretet hinaus auf den Platz."
    assert len(reqs) == 1
    assert reqs[0].scene_id == "mud_gate" and reqs[0].parsed


def test_no_marker_leaves_text_untouched() -> None:
    clean, reqs = extract_scenes("Die Gruppe berät, wohin als Nächstes.")
    assert reqs == [] and clean == "Die Gruppe berät, wohin als Nächstes."


def test_marker_never_survives_in_spoken_text() -> None:
    clean, _ = extract_scenes("Du gehst weiter. <<ORT cathedrum>> Ein Tor öffnet sich.")
    assert "<<ORT" not in clean and "cathedrum" not in clean


def test_whitespace_and_case_tolerance() -> None:
    _, reqs = extract_scenes("<<ort   mud_gate >>")
    assert reqs[0].scene_id == "mud_gate" and reqs[0].parsed


def test_empty_marker_unparsed_but_stripped() -> None:
    clean, reqs = extract_scenes("Nichts passiert. <<ORT >>")
    assert "<<" not in clean
    assert reqs[0].scene_id == "" and reqs[0].parsed is False


def test_multiple_markers_all_stripped() -> None:
    clean, reqs = extract_scenes("<<ORT a>> Mitte. <<ORT b>>")
    assert "<<" not in clean
    assert [r.scene_id for r in reqs] == ["a", "b"]  # cog later takes only the first


# -- validation: Adventure.resolve_move -----------------------------------------------------------

def _adv() -> Adventure:
    # A → B connected; C exists but is NOT a neighbour of A.
    return Adventure(scenes=[
        Scene(id="a", title_de="A", leads_to=["b"]),
        Scene(id="b", title_de="B"),
        Scene(id="c", title_de="C"),
    ])


def test_verbunden_neighbour_moves() -> None:
    moved = _adv().resolve_move("a", "b", "verbunden")
    assert moved is not None and moved.id == "b"


def test_verbunden_illegal_jump_rejected() -> None:
    assert _adv().resolve_move("a", "c", "verbunden") is None  # C exists but isn't connected to A


def test_unknown_id_rejected_in_both_modes() -> None:
    adv = _adv()
    assert adv.resolve_move("a", "nope", "verbunden") is None
    assert adv.resolve_move("a", "nope", "frei") is None


def test_same_scene_is_noop() -> None:
    assert _adv().resolve_move("a", "a", "verbunden") is None
    assert _adv().resolve_move("a", "a", "frei") is None


def test_frei_allows_unconnected_known_scene() -> None:
    moved = _adv().resolve_move("a", "c", "frei")
    assert moved is not None and moved.id == "c"


def test_empty_target_rejected() -> None:
    assert _adv().resolve_move("a", "", "verbunden") is None
