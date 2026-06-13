#!/usr/bin/env bash
# Stop-hook guard: run the test suite only when bot code, tests, or profiles changed,
# so pure conversation turns don't trigger pytest on every Stop.
# Wired in .claude/settings.json -> hooks.Stop.
set -euo pipefail

# Any tracked-or-untracked change under the code/test/profile paths?
changed="$(git status --porcelain -- dmbot tests data/systems 2>/dev/null || true)"

if [ -z "$changed" ]; then
  exit 0
fi

echo "[test-on-change] changes under dmbot/ tests/ data/systems — running suite..."
uv run --with pytest python -m pytest -q
