"""Scene-element flags (ADR 043): the code-owned ``WorldState.scene_flags`` store + the runtime
mutator that validates an id against the *current* scene before flagging (golden rule #3)."""

from __future__ import annotations

import json

from dmbot.memory.state import WorldState
from dmbot.rag.adventure import Adventure, Scene
from dmbot.runtime import SessionRuntime


# -- storage: WorldState.scene_flags ----------------------------------------------------------------

def test_scene_flags_survive_a_state_round_trip(tmp_path) -> None:
    state = WorldState(session_id="t")
    state.mark_resolved("mud_gate", "opp-1")
    state.mark_resolved("mud_gate", "geh-2")
    state.mark_resolved("edifice", "opp-3")
    path = tmp_path / "state.json"
    state.save(path)
    loaded = WorldState.load(path)
    assert loaded.scene_flags == {"mud_gate": ["opp-1", "geh-2"], "edifice": ["opp-3"]}
    assert loaded.resolved_ids("mud_gate") == ["opp-1", "geh-2"]


def test_empty_scene_flags_omitted_from_json(tmp_path) -> None:
    path = tmp_path / "state.json"
    WorldState(session_id="t").save(path)
    assert "scene_flags" not in json.loads(path.read_text(encoding="utf-8"))


def test_from_dict_without_scene_flags_defaults_empty() -> None:
    state = WorldState.from_dict({"session_id": "old"})  # a pre-ADR-043 state.json
    assert state.scene_flags == {} and state.resolved_ids("anywhere") == []


def test_mark_resolved_and_mark_open_are_idempotent() -> None:
    state = WorldState()
    assert state.mark_resolved("a", "opp-1") is True
    assert state.mark_resolved("a", "opp-1") is False  # already set → no duplicate
    assert state.scene_flags == {"a": ["opp-1"]}
    assert state.mark_open("a", "opp-1") is True
    assert state.mark_open("a", "opp-1") is False  # already open
    assert state.scene_flags == {}  # empty scene key dropped → to_dict stays clean


# -- the runtime mutator: _set_scene_flag ------------------------------------------------------------

def _runtime() -> SessionRuntime:
    """A SessionRuntime with __init__ skipped — _set_scene_flag only needs _adventure."""
    rt = object.__new__(SessionRuntime)
    rt._adventure = Adventure(scenes=[
        Scene(id="a", title_de="A", opportunities_de=["Die Kiste öffnen."], secrets_de=["Wahrheit."]),
        Scene(id="b", title_de="B", opportunities_de=["Woanders."]),
    ])
    return rt


def test_set_scene_flag_validates_against_the_current_scene() -> None:
    rt = _runtime()
    state = WorldState(scene_id="a")
    assert rt._set_scene_flag(state, "nope", resolved=True) is None       # unknown id
    assert rt._set_scene_flag(state, "opp-1", resolved=True) is not None  # a's element …
    state_b = WorldState(scene_id="b")
    # … but a's "geh-1" is foreign to scene b (b has no secrets) → rejected, state untouched
    assert rt._set_scene_flag(state_b, "geh-1", resolved=True) is None
    assert state_b.scene_flags == {}


def test_set_scene_flag_resolves_and_reopens() -> None:
    rt = _runtime()
    state = WorldState(scene_id="a")
    assert rt._set_scene_flag(state, "opp-1", resolved=True) == "Die Kiste öffnen."
    assert state.resolved_ids("a") == ["opp-1"]
    assert rt._set_scene_flag(state, "opp-1", resolved=False) == "Die Kiste öffnen."
    assert state.resolved_ids("a") == []


def test_set_scene_flag_without_adventure_returns_none() -> None:
    rt = object.__new__(SessionRuntime)
    rt._adventure = None
    assert rt._set_scene_flag(WorldState(scene_id="a"), "opp-1", resolved=True) is None
