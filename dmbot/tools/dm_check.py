"""One check command: ruff (F), the test suite and dm-eval, with one overall verdict.

    uv run dm-check            # run all three; on green, remember the checked tree
    uv run dm-check --fresh    # exit 0 if the remembered tree matches the working tree (no checks)

On green, the fingerprint of ``dmbot/``, ``tests/`` and ``data/systems/`` is written to
``.dm-check.stamp`` (git-ignored). The pre-commit hook (``tools/hooks/pre-commit``) skips its
check when ``--fresh`` says the stamp still matches.

**The fingerprint** is the git tree hash of exactly those three paths as they stand in the working
tree: ``git add -A`` into a throwaway index (``GIT_INDEX_FILE``), then ``git write-tree``. It is
content-addressed, so any edit, deletion, rename or new untracked (non-ignored) file under the
three paths changes it; the real index is never touched. Rules that keep a stale stamp from
passing:

* the stamp is deleted *before* the checks start, so a red or interrupted run leaves none;
* it is written only if the fingerprint after the checks equals the one before (no edit slipped
  in mid-run);
* a missing, unreadable or foreign stamp counts as "not fresh" → the hook runs ``dm-check``.

Standard library only, so a broken ``dmbot`` import can't break the freshness probe itself.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STAMP_NAME = ".dm-check.stamp"
WATCHED = ("dmbot", "tests", "data/systems")
STAMP_VERSION = 1

# (label, command) — ruff and pytest are not project dependencies, hence `uv run --with`.
CHECKS: tuple[tuple[str, list[str]], ...] = (
    ("ruff (F)", ["uv", "run", "--with", "ruff", "ruff", "check", "--select", "F", "dmbot", "tests"]),
    ("pytest", ["uv", "run", "--with", "pytest", "python", "-m", "pytest", "-q", "--tb=short"]),
    ("dm-eval", ["uv", "run", "dm-eval"]),
)


def _git_env(**extra: str) -> dict[str, str]:
    """Environment for our git calls: drop every inherited GIT_* variable (a hook runs with
    GIT_INDEX_FILE/GIT_DIR set, which would point the calls at the commit's index)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra)
    return env


def fingerprint(root: Path = REPO_ROOT, paths: tuple[str, ...] = WATCHED) -> str:
    """Git tree hash of ``paths`` as they stand in the working tree of the repo at ``root``,
    untracked non-ignored files included. Raises ``RuntimeError`` if git fails."""
    fd, tmp = tempfile.mkstemp(prefix="dm-check-index-")
    os.close(fd)
    os.unlink(tmp)  # git wants to create the index itself; an empty file is "corrupt"
    env = _git_env(GIT_INDEX_FILE=tmp)
    try:
        existing = [p for p in paths if (root / p).exists()]
        if existing:
            add = subprocess.run(["git", "add", "-A", "--", *existing], cwd=root, env=env,
                                 capture_output=True, text=True)
            if add.returncode != 0:
                raise RuntimeError(f"git add failed: {add.stderr.strip()}")
        tree = subprocess.run(["git", "write-tree"], cwd=root, env=env, capture_output=True, text=True)
        if tree.returncode != 0:
            raise RuntimeError(f"git write-tree failed: {tree.stderr.strip()}")
        return tree.stdout.strip()
    finally:
        for leftover in (tmp, tmp + ".lock"):
            try:
                os.unlink(leftover)
            except FileNotFoundError:
                pass


def read_stamp(stamp: Path) -> str | None:
    """The remembered tree hash, or None if the stamp is missing, unreadable or foreign."""
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
        if data.get("version") != STAMP_VERSION:
            return None
        tree = data.get("tree")
        return tree if isinstance(tree, str) and tree else None
    except (OSError, ValueError, AttributeError):
        return None


def is_fresh(root: Path = REPO_ROOT) -> bool:
    remembered = read_stamp(root / STAMP_NAME)
    if remembered is None:
        return False
    try:
        return fingerprint(root) == remembered
    except (RuntimeError, OSError):
        return False


def _drop_stamp(stamp: Path) -> None:
    try:
        stamp.unlink()
    except FileNotFoundError:
        pass


def run_checks(root: Path = REPO_ROOT, checks=CHECKS) -> int:
    stamp = root / STAMP_NAME
    _drop_stamp(stamp)  # a red or interrupted run must not leave a valid stamp behind
    before = fingerprint(root)
    results: list[tuple[str, bool, float]] = []
    for label, cmd in checks:
        print(f"[dm-check] {label}: {' '.join(cmd)}", flush=True)
        t0 = time.monotonic()
        ok = subprocess.run(cmd, cwd=root).returncode == 0
        results.append((label, ok, time.monotonic() - t0))
    green = all(ok for _, ok, _ in results)

    print("\n[dm-check] summary")
    for label, ok, secs in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {label}  ({secs:.0f}s)")
    if not green:
        print("[dm-check] RED - no stamp written.")
        return 1
    after = fingerprint(root)
    if after != before:
        print("[dm-check] GREEN, but dmbot/ tests/ data/systems/ changed during the run - no stamp written.")
        return 1
    stamp.write_text(json.dumps({
        "version": STAMP_VERSION,
        "tree": after,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "paths": list(WATCHED),
    }) + "\n", encoding="utf-8")
    print(f"[dm-check] GREEN - stamp {after[:12]} written to {STAMP_NAME}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dm-check", description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--fresh", action="store_true",
                        help="only report whether the stamp matches the working tree (exit 0 = fresh)")
    args = parser.parse_args(argv)
    if args.fresh:
        return 0 if is_fresh() else 1
    return run_checks()


if __name__ == "__main__":
    sys.exit(main())
