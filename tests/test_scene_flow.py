"""The pure scene-advancement helpers (ADR 057): exit resolution with machine-readable
rejection reasons, the flag gate, the exhaustion exit choice and the undo record."""

from __future__ import annotations

import dataclasses

import pytest

from dmbot.rag.adventure import Scene
from dmbot.rules.scene_flow import (
    MoveRejection,
    MoveTrigger,
    SceneUndo,
    apply_scene_undo,
    capture_scene_undo,
    has_authored_opportunity_ids,
    is_scene_exhausted,
    next_scene_on_exhaustion,
    reachable_exits,
    resolve_exit,
)

KNOWN = ("zollhaus", "schrein", "pfandhalle", "pier-neun")


def _scene(
    *,
    id: str = "zollhaus",
    opportunities: list[str] | None = None,
    opportunity_ids: list[str] | None = None,
    secrets: list[str] | None = None,
    secret_ids: list[str] | None = None,
    leads_to: list[str] | None = None,
    exit_requires: dict[str, str] | None = None,
) -> Scene:
    """A minimal scene card — only the fields the flow helpers read."""
    opportunities = ["Zoll bestechen", "Manifest stehlen"] if opportunities is None else opportunities
    opportunity_ids = ["opp-bestechen", "opp-manifest"] if opportunity_ids is None else opportunity_ids
    return Scene(
        id=id,
        title_de="Zollhaus",
        opportunities_de=opportunities,
        opportunity_ids=opportunity_ids,
        secrets_de=secrets or [],
        secret_ids=secret_ids or [],
        leads_to=leads_to if leads_to is not None else ["schrein"],
        exit_requires=exit_requires or {},
    )


# -- resolve_exit --------------------------------------------------------------------------------

def test_valid_neighbour_is_permitted() -> None:
    verdict = resolve_exit(_scene(), "schrein", known_scene_ids=KNOWN)
    assert verdict.permitted is True
    assert verdict.reason is None
    assert verdict.target_id == "schrein"


def test_unknown_scene_id_is_rejected_as_unknown() -> None:
    verdict = resolve_exit(_scene(), "hafenbecken", known_scene_ids=KNOWN)
    assert verdict.permitted is False
    assert verdict.reason is MoveRejection.UNKNOWN_SCENE


def test_known_scene_that_is_not_a_neighbour_is_rejected_as_not_connected() -> None:
    verdict = resolve_exit(_scene(), "pfandhalle", known_scene_ids=KNOWN)
    assert verdict.permitted is False
    assert verdict.reason is MoveRejection.NOT_CONNECTED


def test_without_a_known_id_list_an_unknown_target_collapses_to_not_connected() -> None:
    verdict = resolve_exit(_scene(), "hafenbecken")
    assert verdict.permitted is False
    assert verdict.reason is MoveRejection.NOT_CONNECTED


def test_locked_gate_with_unmet_requirement_is_rejected_and_names_the_requirement() -> None:
    scene = _scene(leads_to=["schrein", "pier-neun"], exit_requires={"pier-neun": "opp-manifest"})
    verdict = resolve_exit(scene, "pier-neun", resolved_ids=["opp-bestechen"], known_scene_ids=KNOWN)
    assert verdict.permitted is False
    assert verdict.reason is MoveRejection.LOCKED
    assert verdict.required_element_id == "opp-manifest"


def test_locked_gate_with_met_requirement_is_permitted() -> None:
    scene = _scene(leads_to=["schrein", "pier-neun"], exit_requires={"pier-neun": "opp-manifest"})
    verdict = resolve_exit(scene, "pier-neun", resolved_ids=["opp-manifest"], known_scene_ids=KNOWN)
    assert verdict.permitted is True
    assert verdict.reason is None
    assert verdict.required_element_id == ""


def test_move_to_the_current_scene_is_rejected_as_same_scene() -> None:
    verdict = resolve_exit(_scene(), "zollhaus", known_scene_ids=KNOWN)
    assert verdict.permitted is False
    assert verdict.reason is MoveRejection.SAME_SCENE


@pytest.mark.parametrize("target", ["", "   ", None])
def test_empty_target_is_rejected_as_no_target(target: str | None) -> None:
    verdict = resolve_exit(_scene(), target, known_scene_ids=KNOWN)
    assert verdict.permitted is False
    assert verdict.reason is MoveRejection.NO_TARGET


def test_target_is_whitespace_trimmed_before_matching() -> None:
    verdict = resolve_exit(_scene(), "  schrein\n", known_scene_ids=KNOWN)
    assert verdict.permitted is True
    assert verdict.target_id == "schrein"


def test_missing_current_scene_is_rejected_as_no_current_scene() -> None:
    verdict = resolve_exit(None, "schrein", known_scene_ids=KNOWN)
    assert verdict.permitted is False
    assert verdict.reason is MoveRejection.NO_CURRENT_SCENE


def test_a_rejected_verdict_carries_the_reachable_exits_for_the_director_note() -> None:
    scene = _scene(leads_to=["schrein", "pier-neun"], exit_requires={"pier-neun": "opp-manifest"})
    verdict = resolve_exit(scene, "pfandhalle", resolved_ids=(), known_scene_ids=KNOWN)
    assert verdict.reachable_exits == ("schrein",)


def test_the_verdict_is_immutable() -> None:
    verdict = resolve_exit(_scene(), "schrein", known_scene_ids=KNOWN)
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.permitted = False  # type: ignore[misc]


# -- reachable_exits -----------------------------------------------------------------------------

def test_reachable_exits_hides_a_gated_exit_until_its_requirement_is_resolved() -> None:
    scene = _scene(leads_to=["schrein", "pier-neun"], exit_requires={"pier-neun": "opp-manifest"})
    assert reachable_exits(scene, ()) == ("schrein",)
    assert reachable_exits(scene, ["opp-manifest"]) == ("schrein", "pier-neun")


def test_reachable_exits_of_a_missing_scene_is_empty() -> None:
    assert reachable_exits(None, ()) == ()


# -- is_scene_exhausted (the flag gate) ----------------------------------------------------------

def test_scene_is_exhausted_when_every_authored_opportunity_is_resolved() -> None:
    assert is_scene_exhausted(_scene(), ["opp-bestechen", "opp-manifest"]) is True


def test_scene_is_not_exhausted_while_one_opportunity_is_open() -> None:
    assert is_scene_exhausted(_scene(), ["opp-bestechen"]) is False


def test_secrets_do_not_count_towards_exhaustion() -> None:
    scene = _scene(secrets=["Der Zöllner lügt"], secret_ids=["geh-luege"])
    assert is_scene_exhausted(scene, ["opp-bestechen", "opp-manifest"]) is True


def test_foreign_flags_are_ignored() -> None:
    flags = ["opp-bestechen", "opp-manifest", "geh-luege", "opp-aus-einer-anderen-szene"]
    assert is_scene_exhausted(_scene(), flags) is True


def test_a_scene_without_opportunities_is_never_exhausted() -> None:
    scene = _scene(opportunities=[], opportunity_ids=[])
    assert is_scene_exhausted(scene, []) is False


def test_positionally_derived_ids_never_exhaust_a_scene() -> None:
    """The deliberate deviation from ADR 057: an id-less campaign (chemical_burn) must not
    slip through the gate on its first turn."""
    scene = _scene(opportunities=["a", "b"], opportunity_ids=["opp-1", "opp-2"])
    assert has_authored_opportunity_ids(scene) is False
    assert is_scene_exhausted(scene, ["opp-1", "opp-2"]) is False


def test_one_authored_id_among_derived_ones_makes_the_scene_gateable() -> None:
    scene = _scene(opportunities=["a", "b"], opportunity_ids=["opp-1", "opp-manifest"])
    assert has_authored_opportunity_ids(scene) is True
    assert is_scene_exhausted(scene, ["opp-1", "opp-manifest"]) is True


def test_a_missing_scene_is_never_exhausted() -> None:
    assert is_scene_exhausted(None, ["opp-bestechen"]) is False


# -- next_scene_on_exhaustion --------------------------------------------------------------------

def test_a_single_exit_is_chosen_automatically() -> None:
    choice = next_scene_on_exhaustion(_scene(), ())
    assert choice.auto_target == "schrein"
    assert choice.candidates == ("schrein",)


def test_several_exits_are_offered_without_a_decision() -> None:
    scene = _scene(leads_to=["schrein", "pfandhalle"])
    choice = next_scene_on_exhaustion(scene, ())
    assert choice.auto_target is None
    assert choice.candidates == ("schrein", "pfandhalle")


def test_a_gate_that_locks_the_second_exit_leaves_exactly_one_candidate() -> None:
    scene = _scene(leads_to=["schrein", "pier-neun"], exit_requires={"pier-neun": "opp-manifest"})
    assert next_scene_on_exhaustion(scene, ()).auto_target == "schrein"
    assert next_scene_on_exhaustion(scene, ["opp-manifest"]).auto_target is None


def test_a_dead_end_offers_nothing() -> None:
    choice = next_scene_on_exhaustion(_scene(leads_to=[]), ())
    assert choice.auto_target is None
    assert choice.candidates == ()


# -- the undo record -----------------------------------------------------------------------------

@dataclasses.dataclass
class _FakeState:
    """The narrow slice of WorldState a scene change overwrites."""

    scene_id: str = ""
    time_minutes: int = 0
    time_ingame: str = ""


def test_capture_records_the_overwritten_state_and_is_immutable() -> None:
    state = _FakeState(scene_id="zollhaus", time_minutes=480, time_ingame="Tag 1, 08:00")
    undo = capture_scene_undo(state, "schrein", trigger=MoveTrigger.FLAG_GATE)
    assert undo == SceneUndo(
        scene_id="zollhaus",
        time_minutes=480,
        time_ingame="Tag 1, 08:00",
        target_scene_id="schrein",
        trigger=MoveTrigger.FLAG_GATE,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        undo.scene_id = "schrein"  # type: ignore[misc]


def test_apply_restores_pointer_and_time() -> None:
    state = _FakeState(scene_id="zollhaus", time_minutes=480, time_ingame="Tag 1, 08:00")
    undo = capture_scene_undo(state, "schrein", trigger=MoveTrigger.CLASSIFIER)
    state.scene_id, state.time_minutes, state.time_ingame = "schrein", 495, "Tag 1, 08:15"
    assert apply_scene_undo(undo, state) is True
    assert (state.scene_id, state.time_minutes, state.time_ingame) == (
        "zollhaus", 480, "Tag 1, 08:00",
    )


def test_apply_refuses_when_the_pointer_has_moved_on_since() -> None:
    state = _FakeState(scene_id="zollhaus", time_minutes=480, time_ingame="Tag 1, 08:00")
    undo = capture_scene_undo(state, "schrein", trigger=MoveTrigger.MARKER)
    state.scene_id, state.time_minutes = "pfandhalle", 510
    assert apply_scene_undo(undo, state) is False
    assert (state.scene_id, state.time_minutes) == ("pfandhalle", 510)


def test_apply_is_idempotent_a_second_press_does_nothing() -> None:
    state = _FakeState(scene_id="zollhaus", time_minutes=480, time_ingame="Tag 1, 08:00")
    undo = capture_scene_undo(state, "schrein", trigger=MoveTrigger.COMMAND)
    state.scene_id, state.time_minutes = "schrein", 495
    assert apply_scene_undo(undo, state) is True
    assert apply_scene_undo(undo, state) is False
    assert (state.scene_id, state.time_minutes) == ("zollhaus", 480)
