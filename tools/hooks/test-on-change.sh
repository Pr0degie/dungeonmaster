#!/usr/bin/env bash
# Stop-hook guard (.claude/settings.json -> hooks.Stop): run the test suite only when bot
# code, tests, or profiles changed, and stay SILENT on success — output is emitted only when
# a test FAILS, so green turns cost nothing. A failure is shown to you in the terminal
# (non-blocking, exit 1); it is not pushed into the model context / does not force a retry.
set -uo pipefail

# Common case: nothing under the watched paths changed -> instant, silent.
changed="$(git status --porcelain -- dmbot tests data/systems 2>/dev/null || true)"
[ -z "$changed" ] && exit 0

# Run the suite, capturing combined output; surface it only on failure.
output="$(uv run --with pytest python -m pytest -q --tb=short 2>&1)"
status=$?
if [ "$status" -ne 0 ]; then
  {
    echo "[test-on-change] pytest FAILED (changes under dmbot/ tests/ data/systems):"
    echo "$output"
  } >&2
  exit 1
fi
exit 0
