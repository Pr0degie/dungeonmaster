"""Debug-run sandbox (ADR 055/056): a debug campaign plays in the SAME voice channel as live
play, so channel isolation alone doesn't protect the real campaign. ADR 055 split the rotated
archives (``history.<stamp>.debug.jsonl``) and the RAG source (``session_debug_<id>``); ADR 056
finishes the job for the *live* per-session artifacts — state, conversation autosave, Chekhov
list and the human-readable recap all get a ``.debug`` twin.

The invariant these pin: playing the debug campaign must not read or write a single byte of the
live campaign's session files, and vice versa.
"""

from __future__ import annotations

import json
from pathlib import Path

from dmbot.memory import history as history_store
from dmbot.runtime import SessionRuntime

CID = 1343673766487654464


def _runtime(adventure_dir: Path | None) -> SessionRuntime:
    """A bare runtime shell: ``session_file`` only reads ``_adventure_dir`` (via is_debug_run)."""
    rt = object.__new__(SessionRuntime)
    rt._adventure_dir = adventure_dir
    return rt


def _adv_dir(tmp_path: Path, *, testplan: bool) -> Path:
    d = tmp_path / "adventures" / ("debug-kampagne" if testplan else "chemical_burn")
    d.mkdir(parents=True)
    (d / "adventure.json").write_text("{}", encoding="utf-8")
    if testplan:
        (d / "testplan.json").write_text("{}", encoding="utf-8")
    return d


# --- is_debug_run: the testplan sidecar is the only signal --------------------------------

def test_is_debug_run_follows_the_testplan_sidecar(tmp_path) -> None:
    assert _runtime(_adv_dir(tmp_path, testplan=True)).is_debug_run is True
    assert _runtime(_adv_dir(tmp_path, testplan=False)).is_debug_run is False
    assert _runtime(None).is_debug_run is False  # no adventure at all → live paths


# --- path isolation -------------------------------------------------------------------------

def test_live_run_keeps_the_plain_file_names(tmp_path) -> None:
    rt = _runtime(_adv_dir(tmp_path, testplan=False))
    assert rt._state_path(CID).name == "state.json"
    assert rt._history_path(CID).name == "history.jsonl"
    assert rt._chekhov_path(CID).name == "chekhov.json"
    assert rt.session_file(CID, "recap", "md").name == "recap.md"


def test_debug_run_writes_its_own_twins(tmp_path) -> None:
    rt = _runtime(_adv_dir(tmp_path, testplan=True))
    assert rt._state_path(CID).name == "state.debug.json"
    assert rt._history_path(CID).name == "history.debug.jsonl"
    assert rt._chekhov_path(CID).name == "chekhov.debug.json"
    assert rt.session_file(CID, "recap", "md").name == "recap.debug.md"


def test_both_modes_share_the_session_directory(tmp_path) -> None:
    # Same channel, same folder — only the file names differ. The committed characters.json
    # (the read-only sheet) is therefore shared by both modes, which is what we want.
    live = _runtime(_adv_dir(tmp_path, testplan=False))
    debug = _runtime(_adv_dir(tmp_path, testplan=True))
    assert live._state_path(CID).parent == debug._state_path(CID).parent
    assert live._state_path(CID).parent.name == str(CID)


def test_no_live_artifact_path_is_reachable_from_a_debug_run(tmp_path) -> None:
    """The whole point, stated as one assertion: no debug path collides with a live path."""
    live = _runtime(_adv_dir(tmp_path, testplan=False))
    debug = _runtime(_adv_dir(tmp_path, testplan=True))
    artifacts = [("state", "json"), ("history", "jsonl"), ("chekhov", "json"), ("recap", "md")]
    live_paths = {live.session_file(CID, s, e) for s, e in artifacts}
    debug_paths = {debug.session_file(CID, s, e) for s, e in artifacts}
    assert live_paths.isdisjoint(debug_paths)


# --- the write path actually lands in the twin ----------------------------------------------

def test_debug_turns_append_to_the_debug_autosave_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("dmbot.runtime._DATA_DIR", tmp_path)
    live = _runtime(_adv_dir(tmp_path, testplan=False))
    debug = _runtime(_adv_dir(tmp_path, testplan=True))
    live._history_path(CID).parent.mkdir(parents=True, exist_ok=True)

    history_store.append_turn(live._history_path(CID), ts="t0",
                              user_msg="Wir gehen rein.", answer="Die Tür knarrt.")
    history_store.append_turn(debug._history_path(CID), ts="t0",
                              user_msg="Test.", answer="Testantwort.")

    live_lines = live._history_path(CID).read_text(encoding="utf-8").strip().splitlines()
    debug_lines = debug._history_path(CID).read_text(encoding="utf-8").strip().splitlines()
    assert len(live_lines) == 1 and len(debug_lines) == 1
    assert json.loads(live_lines[0])["answer"] == "Die Tür knarrt."
    assert json.loads(debug_lines[0])["answer"] == "Testantwort."


def test_rotating_the_debug_autosave_keeps_the_debug_marker(tmp_path, monkeypatch) -> None:
    # The rotated archive must stay recognisable as a debug record forever (ADR 055) — and
    # rotating one mode must not touch the other mode's live file.
    monkeypatch.setattr("dmbot.runtime._DATA_DIR", tmp_path)
    live = _runtime(_adv_dir(tmp_path, testplan=False))
    debug = _runtime(_adv_dir(tmp_path, testplan=True))
    live._history_path(CID).parent.mkdir(parents=True, exist_ok=True)
    history_store.append_turn(live._history_path(CID), ts="t0", user_msg="a", answer="b")
    history_store.append_turn(debug._history_path(CID), ts="t0", user_msg="c", answer="d")

    rotated = history_store.rotate(debug._history_path(CID), stamp="20260815-1617", debug=True)

    assert rotated is not None and rotated.name == "history.20260815-1617.debug.jsonl"
    assert not debug._history_path(CID).exists()   # rotated away
    assert live._history_path(CID).exists()        # the live thread is untouched
