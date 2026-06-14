#!/usr/bin/env bash
# Stop-hook guard (.claude/settings.json -> hooks.Stop): when bot code, tests, or profiles
# changed, lint (ruff) + run the test suite, and stay SILENT on success — output is emitted
# only when a check FAILS, so green turns cost nothing. A failure is shown to you in the
# terminal (non-blocking, exit 1); it is not pushed into the model context / does not force a
# retry.
#
# ruff scope is deliberately `--select F` (pyflakes only: unused imports/names, undefined
# names, f-string slips) — the high-signal, low-noise set that catches exactly the dead-import
# cruft an extraction/refactor leaves behind (e.g. an import whose user moved to another module).
# Line-length and style rules (E*) stay OFF on purpose: this codebase uses long doc lines by
# design, and re-export shims keep intentional "unused" imports marked `# noqa: F401`.
set -uo pipefail

# Common case: nothing under the watched paths changed -> instant, silent.
changed="$(git status --porcelain -- dmbot tests data/systems 2>/dev/null || true)"
[ -z "$changed" ] && exit 0

fail=0

# 1) Lint (fast, pyflakes-only). ruff via `uv run --with` — it is not a project dependency.
if ! lint="$(uv run --with ruff ruff check --select F dmbot tests 2>&1)"; then
  {
    echo "[test-on-change] ruff (F / pyflakes) FAILED — fix with: uv run --with ruff ruff check --select F --fix dmbot tests"
    echo "$lint"
  } >&2
  fail=1
fi

# 2) Test suite.
if ! output="$(uv run --with pytest python -m pytest -q --tb=short 2>&1)"; then
  {
    echo "[test-on-change] pytest FAILED (changes under dmbot/ tests/ data/systems):"
    echo "$output"
  } >&2
  fail=1
fi

exit $fail
