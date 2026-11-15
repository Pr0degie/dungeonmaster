"""Archive run logs and the debug sandbox instead of overwriting or deleting them.

Layout under ``logs/archive/``:

- ``runs/<YYYY-MM-DD_HHMMSS>/`` — one bot start each: the ``terminal.log``, ``debug.log`` and
  ``transcript.log`` of that run, moved here by the **next** start (:func:`rotate_run_logs`). The
  stamp is the start of the archived run (its ``=== DMbot starting (…)`` line), so ``logs/`` itself
  always holds the running or the last stopped run.
- ``sandbox/<YYYY-MM-DD_HHMMSS>_<channel-id>/`` — the ``.debug`` files of one session directory,
  moved here by ``ingest_session --wipe-debug`` (:func:`archive_sandbox`). Deliberately outside
  ``data/sessions/`` so the session ingest never reads an archived journal back in.
- ``pinned/<name>/`` — runs kept for good (comparison runs); never pruned. ``dmbot.tools.logruns
  --pin N`` moves a run here.

Pruning: ``runs/`` keeps the newest ``DM_LOG_ARCHIVE_KEEP`` (default 30) runs with at least one
turn, plus the newest :data:`KEEP_EMPTY` runs without one (a start that never played does not push
a played evening out); ``sandbox/`` keeps the newest ``DM_LOG_ARCHIVE_KEEP`` folders.

Every function here reports failures instead of raising — a locked file or a full disk must never
stop the bot from starting (the caller logs the report loudly).
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = REPO_ROOT / "logs"
LOG_NAMES = ("terminal.log", "debug.log", "transcript.log")
DEFAULT_KEEP = 30
KEEP_EMPTY = 5  # runs without a single turn: only the newest five survive, outside DEFAULT_KEEP
_KINDS = ("runs", "sandbox", "pinned")
_LAYOUT_MARKER = "LAYOUT"  # written once the pre-archive logs/ layout has been migrated
_PIN_MARKER = "PIN"  # in logs/: `logruns --pin 0` — the next start archives this run into pinned/

_START_RE = re.compile(r"=== DMbot starting \((\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})\)")
_TURN_RE = re.compile(r"\[latency\] turn=")
_ADVENTURE_RE = re.compile(r"loaded adventure '([^']+)'")
_LINE_TIME_RE = re.compile(r"^(\d{2}:\d{2}:\d{2})\b", re.MULTILINE)
_TAGGED_RE = re.compile(r"^(terminal|debug|transcript)-(.+)\.log$")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def archive_keep(env: dict[str, str] | None = None) -> int:
    """``DM_LOG_ARCHIVE_KEEP`` (default 30, at least 1 — the run just archived always stays)."""
    raw = (os.environ if env is None else env).get("DM_LOG_ARCHIVE_KEEP", "").strip()
    try:
        return max(1, int(raw)) if raw else DEFAULT_KEEP
    except ValueError:
        return DEFAULT_KEEP


@dataclass
class ArchiveReport:
    """What one archive step did. ``errors`` non-empty = something stayed where it was."""

    archived: Path | None = None
    moved: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pruned: list[Path] = field(default_factory=list)
    migrated: list[str] = field(default_factory=list)


@dataclass
class RunInfo:
    """The numbers of one run folder (or of ``logs/`` itself)."""

    path: Path
    start: str | None  # "YYYY-MM-DD HH:MM:SS" of the first bot start in it
    end: str | None  # "HH:MM:SS" of the last log line
    starts: int  # bot starts inside — pre-archive logs hold many
    turns: int
    adventure: str | None
    pinned: bool = False


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _created(path: Path) -> float:
    """When the file was created (Windows/macOS ``st_birthtime``), else its mtime — the earlier
    of the two, since a copy keeps its mtime but gets a new birth time. A log file is created at
    its run's start, so this is the start for a run without a start line."""
    st = path.stat()
    birth = getattr(st, "st_birthtime", None)
    return min(birth, st.st_mtime) if birth else st.st_mtime


def read_run(path: Path, *, pinned: bool = False) -> RunInfo:
    """Read a run folder. Turns = ``[latency] turn=`` lines of debug.log (or of the terminal
    mirror without one); with neither, the narrator's lines in transcript.log stand in. Start =
    the first ``DMbot starting`` line, else the creation time of the oldest log in the folder."""
    debug, terminal, transcript = (_read(path / n) for n in ("debug.log", "terminal.log", "transcript.log"))
    main = debug or terminal
    starts = _START_RE.findall(main)
    if starts:
        start = f"{starts[0][0]} {starts[0][1]}:{starts[0][2]}:{starts[0][3]}"
    else:
        files = [path / n for n in LOG_NAMES if (path / n).is_file()]
        start = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(min(_created(f) for f in files)))
            if files else None
        )
    turns = len(_TURN_RE.findall(main)) if main else transcript.count("  Spielleiter: ")
    times = _LINE_TIME_RE.findall(main or transcript)
    adventures = _ADVENTURE_RE.findall(main)
    return RunInfo(
        path=path, start=start, end=times[-1] if times else None, starts=len(starts),
        turns=turns, adventure=adventures[-1] if adventures else None, pinned=pinned,
    )


def _has_turn(path: Path) -> bool:
    """Whether a run folder holds at least one turn — streamed, stops at the first one (a played
    run's first turn sits near the top), so pruning at start stays cheap however big the logs."""
    for name, needle in (("debug.log", "[latency] turn="), ("terminal.log", "[latency] turn="),
                         ("transcript.log", "  Spielleiter: ")):
        f = path / name
        if not f.is_file():
            continue
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                return any(needle in line for line in fh)
        except OSError:
            return True  # unreadable: never treat it as empty (the stricter limit)
    return False


def _stamp(files: list[Path]) -> str:
    """Folder name for the run in ``files``: its start line, else the oldest file's creation."""
    for name in ("debug.log", "terminal.log"):
        for f in files:
            if f.name == name:
                m = _START_RE.search(_read(f))
                if m:
                    return f"{m[1]}_{m[2]}{m[3]}{m[4]}"
    created = [_created(f) for f in files if f.exists()]
    return time.strftime("%Y-%m-%d_%H%M%S", time.localtime(min(created) if created else time.time()))


def _chronological(dirs: list[Path]) -> list[Path]:
    """Oldest first: by the stamp the name starts with, then (same stamp, ``_2``, ``_10``) by when
    the folder was created — a plain name sort would put ``_10`` before ``_2``."""
    return sorted(dirs, key=lambda d: (d.name[:17], _created(d), d.name))


def _unique_dir(parent: Path, name: str) -> Path:
    path, i = parent / name, 2
    while path.exists():
        path, i = parent / f"{name}_{i}", i + 1
    return path


def _unique_file(path: Path) -> Path:
    candidate, i = path, 2
    while candidate.exists():
        candidate, i = path.with_name(f"{path.stem}-{i}{path.suffix}"), i + 1
    return candidate


def _migrate_legacy(logs_dir: Path, report: ArchiveReport) -> None:
    """One-time move of the pre-archive layout into ``pinned/`` — nothing is deleted:
    old folders directly under ``archive/`` keep their name; hand-copied logs
    (``debug-d1.log``, ``debug-bis-2026-11-14.log``) go to ``pinned/<tag>/<kind>.log`` (a tag
    without a date gets the file's date in front: ``d1`` → ``2026-11-14_d1``); the live
    ``transcript.log``, which the old layout appended across every run, goes to
    ``pinned/bis-<date>/``. The live ``debug.log``/``terminal.log`` rotate as a normal run."""
    archive = logs_dir / "archive"
    pinned = archive / "pinned"
    moves: list[tuple[Path, Path]] = []
    if archive.is_dir():
        for d in sorted(archive.iterdir()):
            if d.is_dir() and d.name not in _KINDS:
                moves.append((d, pinned / d.name))
    for f in sorted(logs_dir.glob("*.log")):
        m = _TAGGED_RE.match(f.name)
        if m:
            kind, tag = m[1], m[2]
            if not _DATE_RE.search(tag):
                tag = f"{time.strftime('%Y-%m-%d', time.localtime(f.stat().st_mtime))}_{tag}"
            moves.append((f, pinned / tag / f"{kind}.log"))
        elif f.name not in LOG_NAMES:
            moves.append((f, pinned / "legacy" / f.name))
    transcript = logs_dir / "transcript.log"
    if transcript.is_file():
        date = time.strftime("%Y-%m-%d", time.localtime(transcript.stat().st_mtime))
        moves.append((transcript, pinned / f"bis-{date}" / "transcript.log"))
    for src, dst in moves:
        # one move at a time: a locked file stays where it is and is reported, the rest still moves
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst = _unique_dir(dst.parent, dst.name) if src.is_dir() else _unique_file(dst)
            os.replace(src, dst)
            report.migrated.append(f"{src.name} → {dst.relative_to(logs_dir).as_posix()}")
        except OSError as e:
            report.errors.append(f"old layout: {src.name} stays in {src.parent} ({e})")


def prune(kind_dir: Path, *, keep: int, keep_empty: int | None = None) -> tuple[list[Path], list[str]]:
    """Delete the oldest folders of ``kind_dir`` beyond ``keep`` (names sort chronologically).
    With ``keep_empty`` set (runs), folders without a turn are counted apart and only the newest
    ``keep_empty`` of them stay. Returns (removed, errors)."""
    if not kind_dir.is_dir():
        return [], []
    dirs = _chronological([d for d in kind_dir.iterdir() if d.is_dir()])
    if keep_empty is None:
        doomed = dirs[: max(0, len(dirs) - keep)]
    else:
        played = [d for d in dirs if _has_turn(d)]
        empty = [d for d in dirs if d not in played]
        doomed = played[: max(0, len(played) - keep)] + empty[: max(0, len(empty) - keep_empty)]
    removed, errors = [], []
    for d in doomed:
        try:
            shutil.rmtree(d)
            removed.append(d)
        except OSError as e:
            errors.append(f"could not prune {d.name}: {e}")
    return removed, errors


def rotate_run_logs(
    logs_dir: Path = LOGS_DIR, *, keep: int = DEFAULT_KEEP, keep_empty: int = KEEP_EMPTY
) -> ArchiveReport:
    """Move the previous run's logs from ``logs_dir`` to ``archive/runs/<stamp>/`` so this run
    starts with empty files, then prune. A file that cannot be moved stays where it is (the new
    run appends to it) and lands in ``errors``; this function never raises."""
    report = ArchiveReport()
    archive = logs_dir / "archive"
    if not (archive / _LAYOUT_MARKER).is_file():
        try:
            _migrate_legacy(logs_dir, report)
        except Exception as e:  # noqa: BLE001
            report.errors.append(f"old layout: {type(e).__name__}: {e}")
        try:
            # written even after a partial failure: a retry would pin the NEW transcript.log as
            # old history; what could not move stays in logs/ (named in the ERROR), never lost
            archive.mkdir(parents=True, exist_ok=True)
            (archive / _LAYOUT_MARKER).write_text("runs/sandbox/pinned\n", encoding="utf-8")
        except OSError as e:
            report.errors.append(f"old layout: marker not written ({e})")
    try:
        runs = archive / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        live = [logs_dir / n for n in LOG_NAMES if (logs_dir / n).is_file()]
        pin = logs_dir / _PIN_MARKER
        if live:
            name = _stamp(live)
            parent = runs
            if pin.is_file():  # `logruns --pin 0`: this run goes straight to pinned/
                parent = archive / "pinned"
                parent.mkdir(parents=True, exist_ok=True)
                name += _pin_suffix(_read(pin).strip())
            dest = _unique_dir(parent, name)
            dest.mkdir()
            for f in live:
                try:
                    os.replace(f, dest / f.name)
                    report.moved.append(f.name)
                except OSError as e:
                    report.errors.append(f"{f.name}: {e}")
            if report.moved:
                report.archived = dest
                if pin.is_file():
                    pin.unlink()
            else:
                dest.rmdir()
        removed, errors = prune(runs, keep=keep, keep_empty=keep_empty)
        report.pruned += removed
        report.errors += errors
    except Exception as e:  # noqa: BLE001 — a disk/permission surprise must not stop the bot
        report.errors.append(f"{type(e).__name__}: {e}")
    return report


def archive_sandbox(
    session_dir: Path,
    channel_id: int | str,
    *,
    archive_dir: Path | None = None,
    keep: int = DEFAULT_KEEP,
    now: datetime | None = None,
) -> ArchiveReport:
    """Move every file with ``.debug`` in its name out of ``session_dir`` into
    ``archive/sandbox/<stamp>_<channel_id>/`` (ADR 055/056 sandbox reset), then prune. Files
    without ``.debug`` are never touched; nothing to move → no folder."""
    report = ArchiveReport()
    sandbox = (archive_dir or LOGS_DIR / "archive") / "sandbox"
    try:
        files = (
            sorted(f for f in session_dir.iterdir() if f.is_file() and ".debug" in f.name)
            if session_dir.is_dir() else []
        )
        if files:
            stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
            dest = _unique_dir(sandbox, f"{stamp}_{channel_id}")
            dest.mkdir(parents=True)
            for f in files:
                try:
                    shutil.move(str(f), str(dest / f.name))
                    report.moved.append(f.name)
                except OSError as e:
                    report.errors.append(f"{f.name}: {e}")
            if report.moved:
                report.archived = dest
            else:
                dest.rmdir()
        removed, errors = prune(sandbox, keep=keep)
        report.pruned += removed
        report.errors += errors
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"{type(e).__name__}: {e}")
    return report


def list_runs(logs_dir: Path = LOGS_DIR) -> list[RunInfo]:
    """Index 0 = ``logs/`` itself (running or last stopped run) if it holds a log; then every
    folder of ``runs/`` and ``pinned/``, newest start first."""
    out: list[RunInfo] = []
    if any((logs_dir / n).is_file() for n in LOG_NAMES):
        out.append(read_run(logs_dir, pinned=(logs_dir / _PIN_MARKER).is_file()))
    archived: list[RunInfo] = []
    for kind in ("runs", "pinned"):
        d = logs_dir / "archive" / kind
        if d.is_dir():
            archived += [read_run(p, pinned=kind == "pinned") for p in d.iterdir() if p.is_dir()]
    # read_run always yields a "YYYY-MM-DD HH:MM:SS" start (start line, else file creation), so
    # one key orders runs/ and pinned/ alike; a folder without any log sorts last
    archived.sort(key=lambda r: (r.start or "", r.path.name), reverse=True)
    return out + archived


def _pin_suffix(name: str | None) -> str:
    slug = re.sub(r"[^\w.-]+", "-", (name or "").strip()).strip("-")
    return f"_{slug}" if slug else ""


def pin_run(runs: list[RunInfo], index: int, name: str | None = None, logs_dir: Path = LOGS_DIR) -> Path:
    """Pin run ``index`` of :func:`list_runs`. An archived run moves into ``pinned/`` now. The
    live run (index 0 = ``logs/``) is marked instead: the bot may still be writing it, so the next
    start archives it into ``pinned/`` rather than ``runs/`` — one copy, never two. Returns the
    new folder, or the marker file for the live run."""
    run = runs[index]
    if run.pinned:
        raise ValueError(f"already pinned: {run.path}")
    if run.path == logs_dir:
        marker = logs_dir / _PIN_MARKER
        marker.write_text((name or "").strip() + "\n", encoding="utf-8")
        return marker
    pinned = logs_dir / "archive" / "pinned"
    pinned.mkdir(parents=True, exist_ok=True)
    dest = _unique_dir(pinned, run.path.name + _pin_suffix(name))
    os.replace(run.path, dest)
    return dest
