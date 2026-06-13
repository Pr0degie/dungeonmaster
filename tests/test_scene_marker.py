"""Auto scene transitions (ADR 026): the ``<<ORT id>>`` marker parser + the ``leads_to``-gated move
validation. Both halves are pure + deterministic — no Discord, no LLM, like the rules engine
(golden rule #3: the scene pointer is code state, the model only *requests* a move)."""

from __future__ import annotations

from dmbot.rag.adventure import Adventure, Scene
from dmbot.rules.marker import extract_manifests, extract_scenes, extract_tests
from dmbot.rules.profile import SystemProfile


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


# -- glued markers (Finding #5): no separator after the keyword must still match + strip -----------

def test_ort_glued_id_is_stripped_and_parsed() -> None:
    # `<<ORTmud_gate>>` has no space — the old `\b` regex let it survive into the spoken text AND
    # never fired the move. Both must now hold: stripped from narration, scene_id parsed.
    clean, reqs = extract_scenes("Ihr tretet hinaus. <<ORTmud_gate>>")
    assert "<<" not in clean and "ORT" not in clean and clean == "Ihr tretet hinaus."
    assert len(reqs) == 1 and reqs[0].scene_id == "mud_gate" and reqs[0].parsed


def test_ort_spaced_and_glued_resolve_to_the_same_id() -> None:
    # `<<ORT mud_gate>>`, `<<ORTmud_gate>>`, `<<ORT_mud>>` and `<<ORT1>>` — spaced, glued, glued via
    # an underscore separator, and a glued digit id — all match and strip the leading glue.
    for marker, expected in (
        ("<<ORT mud_gate>>", "mud_gate"),
        ("<<ORTmud_gate>>", "mud_gate"),
        ("<<ORT_mud>>", "mud"),
        ("<<ORT-mud>>", "mud"),
        ("<<ORT1>>", "1"),
    ):
        clean, reqs = extract_scenes(f"Etwas geschieht. {marker}")
        assert "<<" not in clean, marker
        assert len(reqs) == 1 and reqs[0].scene_id == expected and reqs[0].parsed, marker


def _im_profile() -> SystemProfile:
    """A minimal profile so the TEST/MANIFEST extractors run without the on-disk system file."""
    return SystemProfile.from_dict({
        "name": "im",
        "dice": "1d100",
        "resolution": "roll_under",
        "difficulty_ladder": {"schwer": -10},
    })


def test_test_marker_glued_id_is_stripped_and_parsed() -> None:
    # `<<TEST1>>` — the glued form for a TEST marker — must strip and yield a request, not be spoken.
    clean, reqs = extract_tests("Du spähst. <<TEST1>>", _im_profile())
    assert "<<" not in clean and "TEST" not in clean and clean == "Du spähst."
    assert len(reqs) == 1 and reqs[0].skill == "1"


def test_test_marker_modifier_still_parses_after_the_fix() -> None:
    # Regression guard: the separator class must NOT swallow a leading `-`/`+` that is a modifier.
    _, reqs = extract_tests("<<TEST Heimlichkeit +10>>", _im_profile())
    assert reqs[0].skill == "Heimlichkeit" and reqs[0].modifier == 10


def test_manifest_marker_glued_power_is_stripped_and_parsed() -> None:
    # `<<MANIFESTSmite>>` — the glued form for a MANIFEST marker — strips + parses the power.
    clean, reqs = extract_manifests("Mortn hebt die Hand. <<MANIFESTSmite>>", _im_profile())
    assert "<<" not in clean and "MANIFEST" not in clean and clean == "Mortn hebt die Hand."
    assert len(reqs) == 1 and reqs[0].power == "Smite"


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
