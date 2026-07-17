"""Per-turn conversation autosave (D41) — the append-only history.jsonl helpers + restore.

Pins the round-trip the crash-recovery gate relies on: a turn appended survives, a redo record
replaces the prior turn (so a restored session doesn't resurrect a superseded answer), corrupt
lines are tolerated, rotation keeps the record, and restore only fills an empty brain history.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from dmbot.memory import history
from dmbot.orchestrator import DMBrain
from dmbot.runtime import SessionRuntime


def test_append_and_load_roundtrip(tmp_path):
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="Timo: a", answer="A1")
    history.append_turn(p, ts="t2", user_msg="Timo: b", answer="A2")
    assert history.load_recent(p, 10) == [("Timo: a", "A1"), ("Timo: b", "A2")]


def test_redo_record_replaces_the_prior_turn(tmp_path):
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="Timo: a", answer="A1")
    history.append_turn(p, ts="t2", user_msg="Timo: a", answer="A1b", redo=True)
    assert history.load_recent(p, 10) == [("Timo: a", "A1b")]


def test_max_turns_caps_to_the_tail(tmp_path):
    p = tmp_path / "history.jsonl"
    for i in range(5):
        history.append_turn(p, ts=f"t{i}", user_msg=f"u{i}", answer=f"a{i}")
    assert history.load_recent(p, 2) == [("u3", "a3"), ("u4", "a4")]


def test_corrupt_line_is_skipped(tmp_path):
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="u1", answer="a1")
    with p.open("a", encoding="utf-8") as fh:
        fh.write("{ this is a torn line\n")  # e.g. a crash mid-write
    history.append_turn(p, ts="t2", user_msg="u2", answer="a2")
    assert history.load_recent(p, 10) == [("u1", "a1"), ("u2", "a2")]


def test_load_missing_file_is_empty(tmp_path):
    assert history.load_recent(tmp_path / "nope.jsonl", 5) == []


def test_replay_journal_records_are_invisible_to_the_crash_restore(tmp_path):
    """ADR 046 backward compatibility: typed events (session header) and turn extras (raw,
    markers, …) must not change what load_recent returns — the D41 restore contract holds."""
    p = tmp_path / "history.jsonl"
    history.append_event(p, {"kind": "session", "ts": "t0", "profile": "im"})
    history.append_turn(
        p, ts="t1", user_msg="Timo: a", answer="A1",
        extra={"raw": "A1 <<TEST X>>", "lines": [["Timo", "a"]], "markers": {"tests": []}},
    )
    assert history.load_recent(p, 10) == [("Timo: a", "A1")]


def test_scene_events_are_invisible_to_the_crash_restore(tmp_path):
    """ADR 053: scene-boundary events ride the same journal; load_recent must skip them and a
    redo record must still collapse the prior *turn* across an interleaved scene event."""
    p = tmp_path / "history.jsonl"
    history.append_event(p, {"kind": "scene", "scene_id": "zollhaus", "ts": "t0"})
    history.append_turn(p, ts="t1", user_msg="Timo: a", answer="A1")
    history.append_event(p, {"kind": "scene", "scene_id": "schrein", "ts": "t2"})
    history.append_turn(p, ts="t3", user_msg="Timo: a", answer="A1b", redo=True)
    assert history.load_recent(p, 10) == [("Timo: a", "A1b")]


# ---- ADR 053: the runtime journals scene boundaries ----------------------------------------

def _scene_runtime(tmp_path, *, autosave: bool = True, cid: int = 7):
    """A SessionRuntime with __init__ skipped, wired with only what _set_scene touches
    (the test_seed_session pattern): a two-scene fake adventure and a real history path."""
    rt = SessionRuntime.__new__(SessionRuntime)
    scenes = {sid: SimpleNamespace(id=sid, title_de="") for sid in ("a", "b")}
    rt._adventure = SimpleNamespace(get_scene=lambda sid: scenes.get(sid))
    rt._autosave = autosave
    state = SimpleNamespace(scene_id="a", set_location=lambda loc: None)
    rt._state = {cid: state}
    rt._history_path = lambda channel_id: tmp_path / str(channel_id) / "history.jsonl"
    return rt, state


def _journal_records(tmp_path, cid: int = 7) -> list[dict]:
    p = tmp_path / str(cid) / "history.jsonl"
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]


def test_set_scene_journals_the_transition(tmp_path):
    rt, state = _scene_runtime(tmp_path)
    assert rt._set_scene(state, "b") is not None
    recs = _journal_records(tmp_path)
    assert [r["kind"] for r in recs] == ["scene"]
    assert recs[0]["scene_id"] == "b"
    assert recs[0]["ts"]  # real-time stamp present


def test_set_scene_same_scene_writes_no_event(tmp_path):
    rt, state = _scene_runtime(tmp_path)
    assert rt._set_scene(state, "a") is not None  # !ort to the current scene — no boundary
    assert _journal_records(tmp_path) == []


def test_set_scene_autosave_off_writes_no_event(tmp_path):
    rt, state = _scene_runtime(tmp_path, autosave=False)
    assert rt._set_scene(state, "b") is not None  # the move itself still happens
    assert state.scene_id == "b"
    assert _journal_records(tmp_path) == []


def test_set_scene_unknown_state_is_tolerated(tmp_path):
    """A state not registered in _state (partially-built runtime) moves fine, just unjournaled."""
    rt, _ = _scene_runtime(tmp_path)
    foreign = SimpleNamespace(scene_id="a", set_location=lambda loc: None)
    assert rt._set_scene(foreign, "b") is not None
    assert foreign.scene_id == "b"
    assert _journal_records(tmp_path) == []


def test_append_turn_core_keys_win_over_extra(tmp_path):
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="u", answer="a", extra={"answer": "gefälscht"})
    assert history.load_recent(p, 10) == [("u", "a")]


# ---- ADR 053: in-game time on turn records --------------------------------------------------

def test_turn_records_carry_time_minutes_and_load_fine_without_it(tmp_path):
    """New turns carry the in-game clock via extra; old records lack the field — both load."""
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="u1", answer="a1")  # old-style: no time_minutes
    history.append_turn(p, ts="t2", user_msg="u2", answer="a2", extra={"time_minutes": 510})
    recs = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
    assert "time_minutes" not in recs[0]
    assert recs[1]["time_minutes"] == 510
    assert history.load_recent(p, 10) == [("u1", "a1"), ("u2", "a2")]


def test_autosave_turn_stamps_time_minutes(tmp_path):
    """The cog's autosave stamps the channel's WorldState.time_minutes at turn completion."""
    import asyncio

    from dmbot.voice.dmcog import DMCog

    cog = object.__new__(DMCog)  # __init__ skipped (the test_subcogs pattern)
    cog._rt = SimpleNamespace(
        _autosave=True,
        _brain_channel=lambda ch: 7,
        _brain=SimpleNamespace(last_user_msg=lambda cid: "Timo: hi"),
        _state={7: SimpleNamespace(time_minutes=510)},
        _history_path=lambda cid: tmp_path / "history.jsonl",
    )
    asyncio.run(cog._autosave_turn(SimpleNamespace(id=7), "Antwort", user_msg="Timo: hi"))
    recs = [json.loads(line)
            for line in (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(recs) == 1
    assert recs[0]["time_minutes"] == 510
    assert (recs[0]["user_msg"], recs[0]["answer"]) == ("Timo: hi", "Antwort")


def test_rotate_renames_and_keeps_the_record(tmp_path):
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="u1", answer="a1")
    target = history.rotate(p, stamp="20260610-101010")
    assert target is not None and target.is_file()
    assert not p.exists()
    assert (tmp_path / "history.20260610-101010.jsonl").is_file()


def test_rotate_missing_file_is_noop(tmp_path):
    assert history.rotate(tmp_path / "nope.jsonl", stamp="x") is None


def test_rotate_debug_run_carries_the_debug_marker(tmp_path):
    # ADR 055: debug-campaign archives share the live channel's directory — the marker keeps
    # them distinguishable (and separately routable) forever after
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="u1", answer="a1")
    target = history.rotate(p, stamp="20260610-101010", debug=True)
    assert target is not None and target.name == "history.20260610-101010.debug.jsonl"


def test_restore_history_into_an_empty_brain():
    brain = DMBrain(object())  # restore_history never touches the client
    ch = 1
    n = brain.restore_history(ch, [("Timo: a", "A1"), ("Timo: b", "A2")])
    assert n == 2
    assert brain._history[ch] == [
        {"role": "user", "content": "Timo: a"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Timo: b"},
        {"role": "assistant", "content": "A2"},
    ]


def test_restore_history_is_a_noop_when_history_is_nonempty():
    brain = DMBrain(object())
    ch = 1
    brain._history[ch] = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "y"},
    ]
    assert brain.restore_history(ch, [("a", "b")]) == 0
    assert len(brain._history[ch]) == 2  # untouched


def test_restore_history_respects_the_history_cap():
    brain = DMBrain(object(), max_history_turns=2)
    ch = 1
    turns = [(f"u{i}", f"a{i}") for i in range(5)]
    n = brain.restore_history(ch, turns)
    assert n == 2  # only the last 2 turns kept (4 messages = _max_messages)
    assert brain._history[ch][0]["content"] == "u3"
