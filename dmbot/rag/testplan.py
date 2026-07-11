"""Testplan sidecar for the deterministic 🧪 debug overlay (ADR 052).

An adventure meant for a test play-run may ship a ``testplan.json`` next to its
``adventure.json``::

    {"scenes": {"<scene-id>": {"gates": ["G4 Gated Exit", ...],
                               "hint_de": "one line: what to do to trigger it"}}}

The overlay is pure Discord output for the humans at the table. The core invariant is
**LLM-invisibility**: this module is loaded by ``SessionRuntime`` only and consumed only by
``update_debug_overlay`` — it is never handed to ``Adventure``, any prompt builder, or any
RAG path (pinned by ``tests/test_debug_overlay.py``). Fail-open: no sidecar → ``None``
(fully dormant, zero cost for normal adventures); a malformed sidecar → one loud log line,
then dormant.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TestplanEntry:
    """What a scene is testing: the open gates under test + a one-line German hint."""

    __test__ = False  # the Test* name prefix is domain, not a pytest test class

    gates: list[str] = field(default_factory=list)
    hint_de: str = ""


class Testplan:
    """The parsed sidecar: scene-id → :class:`TestplanEntry`."""

    __test__ = False  # the Test* name prefix is domain, not a pytest test class

    def __init__(self, entries: dict[str, TestplanEntry]) -> None:
        self._entries = entries

    def __len__(self) -> int:
        return len(self._entries)

    def entry_for(self, scene_id: str) -> TestplanEntry | None:
        return self._entries.get((scene_id or "").strip())

    @classmethod
    def load(cls, directory: Path) -> "Testplan | None":
        """Load ``testplan.json`` from ``directory``. Missing file → ``None`` silently (the
        normal case); malformed content → one loud log line + ``None`` — the overlay must
        never take a session down."""
        path = directory / "testplan.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            scenes = data.get("scenes")
            if not isinstance(scenes, dict):
                raise ValueError("'scenes' must be an object of scene-id → entry")
            entries: dict[str, TestplanEntry] = {}
            for sid, raw in scenes.items():
                if not isinstance(raw, dict):
                    raise ValueError(f"scene {sid!r}: entry must be an object")
                gates = [str(g) for g in raw.get("gates", []) or []]
                entries[str(sid).strip()] = TestplanEntry(
                    gates=gates, hint_de=str(raw.get("hint_de", "") or ""))
            return cls(entries)
        except (OSError, ValueError, AttributeError):
            log.exception("broken testplan.json under %s — debug overlay stays dormant", directory)
            return None


def overlay_line_de(scene_id: str, title_de: str, entry: TestplanEntry | None) -> str:
    """Render the compact OOC overlay text for the current scene — pure, deterministic,
    zero prompt bytes. A scene the plan doesn't cover renders a 'nothing to test here'
    line so testers know to move on."""
    head = f"🧪 [Testplan] Szene: **{title_de or scene_id}** (`{scene_id}`)"
    if entry is None or not (entry.gates or entry.hint_de):
        return head + " — keine Gates in dieser Szene."
    parts = [head]
    if entry.gates:
        parts.append("Gates: " + ", ".join(entry.gates))
    if entry.hint_de:
        parts.append(f"→ {entry.hint_de}")
    return "\n".join(parts)
