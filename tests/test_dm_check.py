"""dm-check stamp: the guarantees the pre-commit hook relies on (dmbot/tools/dm_check.py).

Every test builds a throwaway git repo, so the real working tree and index are never touched.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from dmbot.tools import dm_check

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

PASS = [sys.executable, "-c", "pass"]
FAIL = [sys.executable, "-c", "raise SystemExit(1)"]


@pytest.fixture
def repo(tmp_path):
    env = dm_check._git_env()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "dmbot").mkdir()
    (tmp_path / "dmbot" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test(): pass\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def _green(repo) -> None:
    assert dm_check.run_checks(repo, checks=(("ok", PASS),)) == 0
    assert dm_check.is_fresh(repo)


def test_any_change_under_watched_paths_invalidates_the_stamp(repo):
    _green(repo)
    (repo / "dmbot" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert not dm_check.is_fresh(repo)

    _green(repo)
    (repo / "tests" / "test_new.py").write_text("", encoding="utf-8")  # new untracked file
    assert not dm_check.is_fresh(repo)

    _green(repo)
    (repo / "dmbot" / "a.py").unlink()
    assert not dm_check.is_fresh(repo)


def test_unwatched_and_ignored_files_keep_the_stamp(repo):
    _green(repo)
    (repo / "README.md").write_text("docs\n", encoding="utf-8")
    (repo / "dmbot" / "__pycache__").mkdir()
    (repo / "dmbot" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    assert dm_check.is_fresh(repo)


def test_red_run_leaves_no_valid_stamp(repo):
    _green(repo)
    assert dm_check.run_checks(repo, checks=(("ok", PASS), ("bad", FAIL))) == 1
    assert not (repo / dm_check.STAMP_NAME).exists()
    assert not dm_check.is_fresh(repo)


def test_missing_or_unreadable_stamp_is_not_fresh(repo):
    assert not dm_check.is_fresh(repo)
    (repo / dm_check.STAMP_NAME).write_text("{not json", encoding="utf-8")
    assert not dm_check.is_fresh(repo)
