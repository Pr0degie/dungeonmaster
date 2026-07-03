"""The golden-transcript replay harness (`uv run dm-eval`, ADR 046).

Pins the harness itself: the PlaybackClient contract (recorded order, exhaustion, batch-only),
the loader's tolerance/strictness split (redo folding + suppressed-turn skip vs clean
TranscriptError on broken JSON / pre-ADR-046 journals), the diff logic per category (a tampered
golden must report exactly the right category), and the end-to-end contract that the two
committed goldens replay clean with exit 0. Bot content German; tests English (CLAUDE.md).
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

from dmbot.tools.eval_replay import (
    GOLDEN_DIR,
    PlaybackClient,
    PlaybackExhausted,
    TranscriptError,
    load_golden,
    main,
    replay_file,
)

_HEADER = {"kind": "session", "ts": "t", "profile": "", "adventure": "", "scene_mode": "verbunden"}


def _turn(user_msg: str = "Tobi: Hallo.", answer: str = "Es hallt.", raw: str | None = None,
          **extra) -> dict:
    rec = {"ts": "t", "user_msg": user_msg, "answer": answer, "redo": False,
           "raw": raw if raw is not None else answer,
           "lines": [["Tobi", "Hallo."]], "results": [],
           "markers": {"tests": [], "manifests": [], "scenes": [], "erledigt": []}}
    rec.update(extra)
    return rec


def _write_jsonl(path, records) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                    encoding="utf-8")


# ---- PlaybackClient -----------------------------------------------------------------------


def test_playback_client_returns_recorded_responses_in_order() -> None:
    client = PlaybackClient()
    client.load(["erste", "zweite"])
    assert asyncio.run(client.chat("sys", [])) == "erste"
    assert asyncio.run(client.chat("sys", [])) == "zweite"
    assert client.unused == 0 and client.calls == 2


def test_playback_client_raises_cleanly_when_exhausted() -> None:
    client = PlaybackClient()
    client.load([])
    with pytest.raises(PlaybackExhausted):
        asyncio.run(client.chat("sys", []))


def test_playback_client_is_batch_only() -> None:
    with pytest.raises(RuntimeError):
        asyncio.run(PlaybackClient().chat_stream("sys", []))


# ---- loader --------------------------------------------------------------------------------


def test_load_golden_rejects_broken_json_with_line_number(tmp_path) -> None:
    path = tmp_path / "g.jsonl"
    path.write_text(json.dumps(_HEADER) + "\n{kaputt\n", encoding="utf-8")
    with pytest.raises(TranscriptError, match="Zeile 2"):
        load_golden(path)


def test_load_golden_requires_a_session_header(tmp_path) -> None:
    path = tmp_path / "g.jsonl"
    _write_jsonl(path, [_turn()])
    with pytest.raises(TranscriptError, match="Session-Header"):
        load_golden(path)


def test_load_golden_refuses_pre_adr046_turns(tmp_path) -> None:
    old = {"ts": "t", "user_msg": "Tobi: Hi.", "answer": "Hallo.", "redo": False}  # D41 shape
    path = tmp_path / "g.jsonl"
    _write_jsonl(path, [_HEADER, old])
    with pytest.raises(TranscriptError, match="raw"):
        load_golden(path)


def test_load_golden_folds_redo_and_skips_suppressed_turns(tmp_path) -> None:
    first = _turn(answer="Erster Wurf.")
    redo = _turn(answer="Zweiter Wurf.")
    redo["redo"] = True
    suppressed = _turn(answer="")  # never entered history live — dropped, not an error
    path = tmp_path / "g.jsonl"
    _write_jsonl(path, [_HEADER, first, suppressed, redo])
    _header, turns = load_golden(path)
    assert [t["answer"] for t in turns] == ["Zweiter Wurf."]


def test_load_golden_missing_file_is_a_transcript_error(tmp_path) -> None:
    with pytest.raises(TranscriptError, match="fehlt"):
        load_golden(tmp_path / "nope.jsonl")


# ---- diff logic (tampered goldens must hit exactly the right category) ----------------------


def _tampered(tmp_path, name: str, mutate) -> object:
    """Copy a committed golden with a mutation applied; fixture paths are made absolute so the
    copy still resolves them from tmp_path."""
    src = GOLDEN_DIR / name
    records = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    if records[0].get("adventure_path"):
        records[0]["adventure_path"] = str((GOLDEN_DIR / records[0]["adventure_path"]).resolve())
    mutate(records)
    out = tmp_path / name
    _write_jsonl(out, records)
    return out


def _deviations(path) -> list:
    return asyncio.run(replay_file(path)).deviations


def test_committed_goldens_replay_clean() -> None:
    for name in ("dice_flow.jsonl", "scene_flags.jsonl"):
        result = asyncio.run(replay_file(GOLDEN_DIR / name))
        assert result.deviations == [], f"{name}: {result.deviations}"
        assert result.turns >= 2


def test_tampered_answer_is_an_answer_deviation(tmp_path) -> None:
    def mutate(records):
        records[1]["answer"] = "Ein ganz anderer Text."
    devs = _deviations(_tampered(tmp_path, "dice_flow.jsonl", mutate))
    assert [d.category for d in devs] == ["answer"] and devs[0].turn == 1


def test_tampered_marker_soll_is_a_marker_deviation(tmp_path) -> None:
    def mutate(records):
        records[1]["markers"]["tests"] = []  # recording claims: no test was queued
    devs = _deviations(_tampered(tmp_path, "dice_flow.jsonl", mutate))
    assert [d.category for d in devs] == ["marker"]


def test_tampered_router_decision_is_a_router_deviation(tmp_path) -> None:
    def mutate(records):
        records[1]["router"]["decision"]["skill"] = "Athletik"
    devs = _deviations(_tampered(tmp_path, "dice_flow.jsonl", mutate))
    assert [d.category for d in devs] == ["router"]


def test_tampered_scene_verdict_is_a_state_deviation(tmp_path) -> None:
    def mutate(records):
        records[2]["scene_verdict"]["accepted"] = True  # recording claims the gated move passed
    devs = _deviations(_tampered(tmp_path, "scene_flags.jsonl", mutate))
    assert [d.category for d in devs] == ["state"] and devs[0].turn == 2


def test_missing_adventure_skips_state_with_a_note(tmp_path) -> None:
    def mutate(records):
        records[0]["adventure_path"] = "gibt/es/nicht"
    result = asyncio.run(replay_file(_tampered(tmp_path, "scene_flags.jsonl", mutate)))
    assert result.deviations == []
    assert any("übersprungen" in n for n in result.notes)


# ---- entry point ---------------------------------------------------------------------------


def test_main_is_green_on_the_committed_goldens(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["dm-eval"])
    assert main() == 0
    out = capsys.readouterr().out
    assert "[eval]" in out and "OK" in out


def test_main_exit_1_on_a_deviation(monkeypatch, capsys, tmp_path) -> None:
    def mutate(records):
        records[1]["answer"] = "Anders."
    path = _tampered(tmp_path, "dice_flow.jsonl", mutate)
    monkeypatch.setattr(sys, "argv", ["dm-eval", str(path)])
    assert main() == 1
    assert "DIFF" in capsys.readouterr().out


def test_main_exit_2_on_an_unusable_transcript(monkeypatch, capsys, tmp_path) -> None:
    path = tmp_path / "old.jsonl"
    _write_jsonl(path, [{"ts": "t", "user_msg": "u", "answer": "a", "redo": False}])
    monkeypatch.setattr(sys, "argv", ["dm-eval", str(path)])
    assert main() == 2
    assert "FEHLER" in capsys.readouterr().out
