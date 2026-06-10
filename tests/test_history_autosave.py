"""Per-turn conversation autosave (D41) — the append-only history.jsonl helpers + restore.

Pins the round-trip the crash-recovery gate relies on: a turn appended survives, a redo record
replaces the prior turn (so a restored session doesn't resurrect a superseded answer), corrupt
lines are tolerated, rotation keeps the record, and restore only fills an empty brain history.
"""

from __future__ import annotations

from dmbot.memory import history
from dmbot.orchestrator import DMBrain


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


def test_rotate_renames_and_keeps_the_record(tmp_path):
    p = tmp_path / "history.jsonl"
    history.append_turn(p, ts="t1", user_msg="u1", answer="a1")
    target = history.rotate(p, stamp="20260610-101010")
    assert target is not None and target.is_file()
    assert not p.exists()
    assert (tmp_path / "history.20260610-101010.jsonl").is_file()


def test_rotate_missing_file_is_noop(tmp_path):
    assert history.rotate(tmp_path / "nope.jsonl", stamp="x") is None


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
