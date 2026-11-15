"""Run logs and the debug sandbox are archived, never overwritten or deleted (dmbot/logarchive.py)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest

from dmbot import logarchive
from dmbot.logsetup import setup_logging
from dmbot.rag.ingest_session import reset_debug_sandbox
from dmbot.tools import logruns, text_replay


def _start(stamp: str) -> str:
    return f"{stamp[11:]} INFO    dmbot | === DMbot starting ({stamp}) — logs: … ===\n"


def _run_log(stamp: str, turns: int) -> str:
    body = "".join(
        f"{stamp[11:]} INFO    turn_timing | [latency] turn={i + 1} stream chars=500\n" for i in range(turns)
    )
    return _start(stamp) + f"{stamp[11:]} INFO    runtime | loaded adventure 'Die Mitternachtsfracht' (6 scenes)\n" + body


def _new_layout(logs: Path) -> Path:
    """A logs dir that has already been migrated (the one-time legacy step is its own test)."""
    (logs / "archive").mkdir(parents=True)
    (logs / "archive" / "LAYOUT").write_text("x", encoding="utf-8")
    return logs


def _archived_run(logs: Path, stamp: str, turns: int) -> Path:
    d = logs / "archive" / "runs" / stamp.replace(" ", "_").replace(":", "")
    d.mkdir(parents=True)
    (d / "debug.log").write_text(_run_log(stamp, turns), encoding="utf-8")
    return d


@pytest.fixture
def clean_root_logger():
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()


# --- rotation at start ---------------------------------------------------------------------------

def test_start_moves_the_previous_run_into_a_folder_named_after_its_start(tmp_path, clean_root_logger) -> None:
    logs = _new_layout(tmp_path / "logs")
    (logs / "debug.log").write_text(_run_log("2026-11-15 19:02:11", 3), encoding="utf-8")
    (logs / "terminal.log").write_text(_start("2026-11-15 19:02:11"), encoding="utf-8")
    (logs / "transcript.log").write_text("19:03:00  Spielleiter: Es regnet.\n", encoding="utf-8")

    setup_logging("INFO", to_file=True, transcript_file=True, logs_dir=logs)
    logging.getLogger("dmbot").info("first line of the new run")

    run = logs / "archive" / "runs" / "2026-11-15_190211"
    assert sorted(p.name for p in run.iterdir()) == ["debug.log", "terminal.log", "transcript.log"]
    assert "[latency] turn=3" in (run / "debug.log").read_text(encoding="utf-8")
    # the new run starts with empty files: none of the previous run's lines are in them
    new_debug = (logs / "debug.log").read_text(encoding="utf-8")
    assert "first line of the new run" in new_debug and "[latency]" not in new_debug
    assert new_debug.count("=== DMbot starting") == 1
    assert "previous run archived" in new_debug
    assert (logs / "transcript.log").read_text(encoding="utf-8") == ""
    # and that run is index 0, the archived one index 1
    runs = logarchive.list_runs(logs)
    assert runs[0].path == logs and runs[1].path == run and runs[1].turns == 3


def test_two_starts_in_the_same_second_get_separate_folders(tmp_path) -> None:
    logs = _new_layout(tmp_path / "logs")
    _archived_run(logs, "2026-11-15 19:02:11", 1)
    (logs / "debug.log").write_text(_run_log("2026-11-15 19:02:11", 2), encoding="utf-8")
    report = logarchive.rotate_run_logs(logs)
    assert report.archived == logs / "archive" / "runs" / "2026-11-15_190211_2" and not report.errors


# --- failure: the bot starts anyway and says so loudly --------------------------------------------

def test_a_locked_log_does_not_stop_the_start_and_is_reported_at_error(
    tmp_path, monkeypatch, clean_root_logger
) -> None:
    logs = _new_layout(tmp_path / "logs")
    (logs / "debug.log").write_text(_run_log("2026-11-15 19:02:11", 2), encoding="utf-8")
    (logs / "terminal.log").write_text("old console\n", encoding="utf-8")
    real_replace = os.replace

    def locked(src, dst):
        if Path(src).name == "terminal.log":
            raise PermissionError(13, "The process cannot access the file", str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(logarchive.os, "replace", locked)
    setup_logging("INFO", to_file=True, logs_dir=logs)  # must not raise

    terminal = (logs / "terminal.log").read_text(encoding="utf-8")
    assert terminal.startswith("old console\n")  # appended to, not truncated away
    debug = (logs / "debug.log").read_text(encoding="utf-8")
    assert "ERROR" in debug and "LOG ARCHIVE FAILED" in debug and "terminal.log" in debug
    # what could be moved was moved
    assert (logs / "archive" / "runs" / "2026-11-15_190211" / "debug.log").is_file()


def test_rotation_never_raises(tmp_path, monkeypatch) -> None:
    logs = _new_layout(tmp_path / "logs")
    (logs / "debug.log").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(logarchive, "_unique_dir", lambda *a: (_ for _ in ()).throw(OSError(28, "No space left")))
    report = logarchive.rotate_run_logs(logs)
    assert report.archived is None and "No space left" in report.errors[0]
    assert (logs / "debug.log").is_file()


# --- archive limit ---------------------------------------------------------------------------------

def test_only_the_newest_runs_survive_and_pinned_ones_are_never_touched(tmp_path) -> None:
    logs = _new_layout(tmp_path / "logs")
    for day in range(1, 6):
        _archived_run(logs, f"2026-11-0{day} 20:00:00", 4)
    pinned = logs / "archive" / "pinned" / "2026-10-25_vergleich"
    pinned.mkdir(parents=True)
    (pinned / "debug.log").write_text(_run_log("2026-10-25 20:51:23", 47), encoding="utf-8")
    (logs / "debug.log").write_text(_run_log("2026-11-06 20:00:00", 4), encoding="utf-8")

    report = logarchive.rotate_run_logs(logs, keep=3)

    left = sorted(p.name for p in (logs / "archive" / "runs").iterdir())
    assert left == ["2026-11-04_200000", "2026-11-05_200000", "2026-11-06_200000"]
    assert [p.name for p in report.pruned] == ["2026-11-01_200000", "2026-11-02_200000", "2026-11-03_200000"]
    assert (pinned / "debug.log").is_file()


def test_runs_without_a_turn_do_not_count_and_only_five_of_them_stay(tmp_path) -> None:
    logs = _new_layout(tmp_path / "logs")
    _archived_run(logs, "2026-11-01 20:00:00", 12)
    _archived_run(logs, "2026-11-02 20:00:00", 9)
    for minute in range(10, 17):  # seven starts that never played
        _archived_run(logs, f"2026-11-03 20:{minute}:00", 0)

    removed, errors = logarchive.prune(logs / "archive" / "runs", keep=2, keep_empty=5)

    left = sorted(p.name for p in (logs / "archive" / "runs").iterdir())
    assert not errors
    assert "2026-11-01_200000" in left and "2026-11-02_200000" in left  # the played ones stay
    assert [p.name for p in removed] == ["2026-11-03_201000", "2026-11-03_201100"]
    assert len(left) == 7


def test_archive_keep_comes_from_the_environment() -> None:
    assert logarchive.archive_keep({}) == 30
    assert logarchive.archive_keep({"DM_LOG_ARCHIVE_KEEP": "12"}) == 12
    assert logarchive.archive_keep({"DM_LOG_ARCHIVE_KEEP": "0"}) == 1
    assert logarchive.archive_keep({"DM_LOG_ARCHIVE_KEEP": "viele"}) == 30


# --- pinning ---------------------------------------------------------------------------------------

def test_pin_moves_a_run_out_of_reach_of_the_limit_and_the_list_shows_it(tmp_path, capsys) -> None:
    logs = _new_layout(tmp_path / "logs")
    _archived_run(logs, "2026-11-14 18:59:32", 41)
    _archived_run(logs, "2026-11-15 19:02:11", 7)
    (logs / "debug.log").write_text(_run_log("2026-11-15 21:00:00", 2), encoding="utf-8")

    assert logruns.main(["--pin", "2", "--name", "abend d1"], logs_dir=logs) == 0
    dest = logs / "archive" / "pinned" / "2026-11-14_185932_abend-d1"
    assert (dest / "debug.log").is_file()
    assert not (logs / "archive" / "runs" / "2026-11-14_185932").exists()

    capsys.readouterr()
    assert logruns.main([], logs_dir=logs) == 0
    listing = capsys.readouterr().out.splitlines()
    assert "📌" in listing[3] and "pinned/2026-11-14_185932_abend-d1" in listing[3]
    assert "📌" not in listing[2] and "runs/2026-11-15_190211" in listing[2]
    # the limit never reaches it, even at keep=1
    logarchive.prune(logs / "archive" / "runs", keep=1, keep_empty=1)
    assert (dest / "debug.log").is_file()
    # --path finds the previous start of the evening
    assert logruns.main(["--path", "1"], logs_dir=logs) == 0
    assert capsys.readouterr().out.strip() == str(logs / "archive" / "runs" / "2026-11-15_190211")


def test_the_first_start_pins_the_old_layout_and_deletes_nothing(tmp_path) -> None:
    logs = tmp_path / "logs"
    (logs / "archive" / "2026-06-15").mkdir(parents=True)
    (logs / "archive" / "2026-06-15" / "debug.log").write_text("juni\n", encoding="utf-8")
    nov14 = time.mktime((2026, 11, 14, 19, 39, 0, 0, 0, -1))
    for kind in ("debug", "terminal", "transcript"):
        f = logs / f"{kind}-d1.log"
        f.write_text(f"{kind} d1\n", encoding="utf-8")
        os.utime(f, (nov14, nov14))
    (logs / "debug-bis-2026-11-14.log").write_text(_run_log("2026-10-25 02:07:53", 47), encoding="utf-8")
    (logs / "transcript.log").write_text("20:52:00  Spielleiter: 25.10.\n", encoding="utf-8")
    os.utime(logs / "transcript.log", (nov14, nov14))
    (logs / "debug.log").write_text(_run_log("2026-11-14 20:40:32", 0), encoding="utf-8")

    report = logarchive.rotate_run_logs(logs)

    pinned = logs / "archive" / "pinned"
    assert not report.errors
    assert sorted(p.name for p in (pinned / "2026-11-14_d1").iterdir()) == [
        "debug.log", "terminal.log", "transcript.log"]
    assert sorted(p.name for p in (pinned / "bis-2026-11-14").iterdir()) == ["debug.log", "transcript.log"]
    assert (pinned / "2026-06-15" / "debug.log").read_text(encoding="utf-8") == "juni\n"
    assert (logs / "archive" / "runs" / "2026-11-14_204032" / "debug.log").is_file()
    assert sorted(p.name for p in logs.iterdir()) == ["archive"]
    # a second start does not migrate again
    (logs / "transcript.log").write_text("21:00:00  Spielleiter: neu\n", encoding="utf-8")
    assert logarchive.rotate_run_logs(logs).migrated == []


def test_pinning_the_live_run_marks_it_and_the_next_start_files_it_under_pinned(tmp_path, capsys) -> None:
    logs = _new_layout(tmp_path / "logs")
    _archived_run(logs, "2026-11-15 18:00:00", 3)
    (logs / "debug.log").write_text(_run_log("2026-11-15 19:02:11", 30), encoding="utf-8")

    assert logruns.main(["--pin", "0", "--name", "!!"], logs_dir=logs) == 0  # a name of only signs
    runs = logarchive.list_runs(logs)
    assert runs[0].pinned and runs[0].path == logs and len(runs) == 2  # marked, not copied
    assert logruns.main(["--path", "1"], logs_dir=logs) == 0
    assert capsys.readouterr().out.strip().endswith("2026-11-15_180000")

    report = logarchive.rotate_run_logs(logs)
    assert report.archived == logs / "archive" / "pinned" / "2026-11-15_190211"  # no trailing "_"
    assert not (logs / "PIN").exists()
    assert not (logs / "archive" / "runs" / "2026-11-15_190211").exists()


def test_a_pinned_folder_without_a_start_line_sorts_by_its_files_date(tmp_path) -> None:
    logs = _new_layout(tmp_path / "logs")
    _archived_run(logs, "2026-11-15 18:00:00", 3)
    old = logs / "archive" / "pinned" / "bis-2026-11-14"
    old.mkdir(parents=True)
    (old / "transcript.log").write_text("02:08:38  Spielleiter: 25.10.\n", encoding="utf-8")
    oct25 = time.mktime((2026, 10, 25, 2, 8, 38, 0, 0, -1))
    os.utime(old / "transcript.log", (oct25, oct25))
    (logs / "debug.log").write_text(_run_log("2026-11-15 19:02:11", 2), encoding="utf-8")

    runs = logarchive.list_runs(logs)
    assert [r.path.name for r in runs[1:]] == ["2026-11-15_180000", "bis-2026-11-14"]
    assert runs[2].start == "2026-10-25 02:08:38" and runs[2].turns == 1


def test_a_run_with_only_the_terminal_mirror_still_counts_its_turns(tmp_path) -> None:
    d = tmp_path / "run"
    d.mkdir()
    (d / "terminal.log").write_text(_run_log("2026-11-15 19:02:11", 4), encoding="utf-8")
    assert logarchive.read_run(d).turns == 4
    assert logarchive._has_turn(d)


def test_pruning_orders_same_stamp_folders_by_age_not_by_name(tmp_path) -> None:
    sandbox = tmp_path / "sandbox"
    names = ["2026-11-15_190000_42"] + [f"2026-11-15_190000_42_{i}" for i in range(2, 11)]
    for age, name in enumerate(names):
        (sandbox / name).mkdir(parents=True)
        t = time.mktime((2025, 1, 1, 19, 0, age, 0, 0, -1))  # long before any real birth time
        os.utime(sandbox / name, (t, t))
    removed, _ = logarchive.prune(sandbox, keep=2)
    assert sorted(p.name for p in sandbox.iterdir()) == ["2026-11-15_190000_42_10", "2026-11-15_190000_42_9"]
    assert "2026-11-15_190000_42_10" not in [p.name for p in removed]


def test_a_locked_old_file_does_not_stop_the_migration_or_the_rotation(tmp_path, monkeypatch) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "debug-d1.log").write_text("d1\n", encoding="utf-8")
    (logs / "terminal-d1.log").write_text("d1\n", encoding="utf-8")
    (logs / "debug.log").write_text(_run_log("2026-11-15 19:02:11", 2), encoding="utf-8")
    real_replace = os.replace

    def locked(src, dst):
        if Path(src).name == "debug-d1.log":
            raise PermissionError(13, "locked", str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(logarchive.os, "replace", locked)
    report = logarchive.rotate_run_logs(logs)

    assert any("debug-d1.log stays" in e for e in report.errors)
    assert (logs / "debug-d1.log").is_file()  # left where it was, not lost
    assert report.archived == logs / "archive" / "runs" / "2026-11-15_190211"  # rotation still ran
    assert (logs / "archive" / "LAYOUT").is_file()  # and no second migration on the next start
    assert len(list((logs / "archive" / "pinned").rglob("terminal.log"))) == 1


def test_wipe_debug_with_a_wrong_channel_wipes_nothing(tmp_path, capsys) -> None:
    (tmp_path / "sessions").mkdir()
    code = reset_debug_sandbox(99, sessions_dir=tmp_path / "sessions", db_path=tmp_path / "none.db",
                               archive_dir=tmp_path / "archive", keep=30)
    out = capsys.readouterr().out
    assert code == 1 and "store NOT wiped" in out and "wiped 0 chunks" not in out


def test_text_replay_reads_the_pinned_evening() -> None:
    assert text_replay.DEFAULT_LOG.parts[-4:] == ("archive", "pinned", "2026-11-14_d1", "debug.log")


# --- sandbox reset ---------------------------------------------------------------------------------

def test_wipe_debug_moves_the_sandbox_files_instead_of_deleting_them(tmp_path, capsys) -> None:
    session = tmp_path / "sessions" / "42"
    session.mkdir(parents=True)
    for name in ("state.debug.json", "history.debug.jsonl", "history.20261114-1939.debug.jsonl",
                 "recap.debug.md", "state.json", "history.jsonl", "characters.json"):
        (session / name).write_text(name, encoding="utf-8")
    archive = tmp_path / "logs" / "archive"

    code = reset_debug_sandbox(42, sessions_dir=tmp_path / "sessions", db_path=tmp_path / "none.db",
                               archive_dir=archive, keep=30)

    assert code == 0
    (dest,) = list((archive / "sandbox").iterdir())
    assert dest.name.endswith("_42")
    assert sorted(p.name for p in dest.iterdir()) == [
        "history.20261114-1939.debug.jsonl", "history.debug.jsonl", "recap.debug.md", "state.debug.json"]
    assert (dest / "history.debug.jsonl").read_text(encoding="utf-8") == "history.debug.jsonl"
    assert sorted(p.name for p in session.iterdir()) == ["characters.json", "history.jsonl", "state.json"]
    assert "wiped 0 chunks" in capsys.readouterr().out


def test_a_sandbox_file_that_cannot_move_stays_and_the_store_is_not_wiped(tmp_path, monkeypatch, capsys) -> None:
    session = tmp_path / "sessions" / "42"
    session.mkdir(parents=True)
    (session / "state.debug.json").write_text("{}", encoding="utf-8")

    def locked(src, dst):
        raise PermissionError(13, "locked", src)

    monkeypatch.setattr(logarchive.shutil, "move", locked)
    code = reset_debug_sandbox(42, sessions_dir=tmp_path / "sessions", db_path=tmp_path / "none.db",
                               archive_dir=tmp_path / "archive", keep=30)
    out = capsys.readouterr().out
    assert code == 1 and "store NOT wiped" in out and "wiped 0 chunks" not in out
    assert (session / "state.debug.json").is_file()


def test_sandbox_archive_keeps_the_newest_folders(tmp_path) -> None:
    sandbox = tmp_path / "archive" / "sandbox"
    for day in range(1, 5):
        (sandbox / f"2026-11-0{day}_200000_42").mkdir(parents=True)
    session = tmp_path / "42"
    session.mkdir()
    (session / "state.debug.json").write_text("{}", encoding="utf-8")
    from datetime import datetime

    report = logarchive.archive_sandbox(session, 42, archive_dir=tmp_path / "archive", keep=2,
                                        now=datetime(2026, 11, 15, 20, 0, 0))
    assert sorted(p.name for p in sandbox.iterdir()) == ["2026-11-04_200000_42", "2026-11-15_200000_42"]
    assert len(report.pruned) == 3
