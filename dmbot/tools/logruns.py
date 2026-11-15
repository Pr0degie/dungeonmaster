"""List, locate and pin the bot's archived runs — ``uv run python -m dmbot.tools.logruns``.

Every bot start is one run. ``logs/`` holds the running or the last stopped run (index 0); the
next start moves it to ``logs/archive/runs/<start-stamp>/`` (:mod:`dmbot.logarchive`). An evening
of several starts is therefore several consecutive runs.

    uv run python -m dmbot.tools.logruns
        # the list: index, start, end, turns, bot starts, adventure, folder; 📌 = pinned
    uv run python -m dmbot.tools.logruns --path 1
        # the folder of run 1 (the run before the current one) — for measurements:
        # $d = uv run python -m dmbot.tools.logruns --path 1; Select-String -Path "$d\\debug.log" ...
    uv run python -m dmbot.tools.logruns --pin 1 --name abend-d2
        # keep run 1 for good: moved to logs/archive/pinned/<stamp>_abend-d2/ (never pruned);
        # --pin 0 marks the live run: the next bot start archives it into pinned/ instead of runs/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..logarchive import LOGS_DIR, list_runs, pin_run


def format_runs(runs, logs_dir: Path = LOGS_DIR) -> list[str]:
    lines = [f"{'#':>3}  {'start':19}  {'end':8}  {'turns':>5}  {'starts':>6}  {'adventure':24}  folder"]
    for i, r in enumerate(runs):
        folder = "logs (running or last stopped)" if r.path == logs_dir else r.path.relative_to(logs_dir).as_posix()
        mark = "📌" if r.pinned else "  "
        lines.append(
            f"{i:>3}{mark}{r.start or '?':19}  {r.end or '?':8}  {r.turns:>5}  {r.starts:>6}  "
            f"{(r.adventure or '—')[:24]:24}  {folder}"
        )
    return lines


def main(argv: list[str] | None = None, logs_dir: Path = LOGS_DIR) -> int:
    parser = argparse.ArgumentParser(prog="logruns", description=(__doc__ or "").split("\n\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--path", type=int, metavar="N", help="print the folder of run N")
    group.add_argument("--pin", type=int, metavar="N", help="move run N to logs/archive/pinned/")
    parser.add_argument("--name", default=None, help="with --pin: a name appended to the folder")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    runs = list_runs(logs_dir)
    index = args.path if args.path is not None else args.pin
    if index is not None and not 0 <= index < len(runs):
        print(f"[logruns] no run {index} — {len(runs)} known (0..{len(runs) - 1})", file=sys.stderr)
        return 2
    if args.path is not None:
        print(runs[index].path)
        return 0
    if args.pin is not None:
        try:
            dest = pin_run(runs, index, args.name, logs_dir=logs_dir)
        except (ValueError, OSError) as e:
            print(f"[logruns] not pinned: {e}", file=sys.stderr)
            return 1
        if dest.parent == logs_dir:
            print("[logruns] run 0 marked: the next bot start moves it to logs/archive/pinned/ "
                  "instead of runs/")
        else:
            print(f"[logruns] pinned -> {dest}")
        return 0
    print("\n".join(format_runs(runs, logs_dir)) if runs else f"[logruns] no runs in {logs_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
