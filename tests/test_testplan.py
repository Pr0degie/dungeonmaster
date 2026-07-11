"""Testplan sidecar (ADR 052): a `testplan.json` next to `adventure.json` drives the
deterministic 🧪 debug overlay for test play-runs. Fail-open by design: no sidecar → None
(fully dormant), a malformed sidecar → ONE loud log line + None. Pure module — never
touches prompts, personas or RAG (the LLM-invisibility invariant)."""

from __future__ import annotations

import json
from pathlib import Path

from dmbot.rag.testplan import Testplan, TestplanEntry, overlay_line_de


def _write(tmp_path: Path, payload) -> Path:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    (tmp_path / "testplan.json").write_text(text, encoding="utf-8")
    return tmp_path


def test_load_missing_sidecar_is_dormant(tmp_path) -> None:
    # No sidecar → None, silently: zero cost for normal adventures.
    assert Testplan.load(tmp_path) is None


def test_load_parses_scene_entries(tmp_path) -> None:
    plan = Testplan.load(_write(tmp_path, {"scenes": {
        "s1": {"gates": ["G4 Gated Exit"], "hint_de": "Die Tür ohne Schlüssel öffnen."},
        "s2": {},
    }}))
    assert plan is not None and len(plan) == 2
    assert plan.entry_for("s1") == TestplanEntry(
        gates=["G4 Gated Exit"], hint_de="Die Tür ohne Schlüssel öffnen.")
    assert plan.entry_for("s2") == TestplanEntry(gates=[], hint_de="")
    assert plan.entry_for("unbekannt") is None


def test_load_malformed_json_logs_and_stays_dormant(tmp_path, caplog) -> None:
    with caplog.at_level("ERROR"):
        assert Testplan.load(_write(tmp_path, "{kein json")) is None
    assert any("testplan" in r.message.lower() for r in caplog.records)


def test_load_wrong_scenes_shape_stays_dormant(tmp_path, caplog) -> None:
    # "scenes" must be an object of scene-id → entry; anything else = malformed → dormant.
    with caplog.at_level("ERROR"):
        assert Testplan.load(_write(tmp_path, {"scenes": ["s1", "s2"]})) is None
    assert any("testplan" in r.message.lower() for r in caplog.records)


def test_load_wrong_entry_shape_stays_dormant(tmp_path, caplog) -> None:
    with caplog.at_level("ERROR"):
        assert Testplan.load(_write(tmp_path, {"scenes": {"s1": "G4"}})) is None
    assert any("testplan" in r.message.lower() for r in caplog.records)


def test_overlay_line_carries_scene_gates_and_hint() -> None:
    line = overlay_line_de("s1", "Die Docks", TestplanEntry(
        gates=["G4 Gated Exit", "G7 Uhr"], hint_de="Die Tür ohne Schlüssel öffnen."))
    assert line.startswith("🧪")
    assert "Die Docks" in line and "`s1`" in line
    assert "G4 Gated Exit" in line and "G7 Uhr" in line
    assert "Die Tür ohne Schlüssel öffnen." in line


def test_overlay_line_without_entry_says_no_gates() -> None:
    line = overlay_line_de("s9", "Leere Gasse", None)
    assert line.startswith("🧪") and "Leere Gasse" in line and "keine Gates" in line


def test_overlay_line_falls_back_to_scene_id_without_title() -> None:
    line = overlay_line_de("s3", "", TestplanEntry(gates=["G1"], hint_de=""))
    assert "`s3`" in line and "G1" in line
