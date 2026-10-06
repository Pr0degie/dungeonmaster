"""The ``[latency]`` line (``dmbot/turn_timing.py``): the Claude extras appear when the backend
reports them (ADR 061), and an Ollama turn's line is unchanged."""

from __future__ import annotations

import logging

from dmbot.turn_timing import _TurnTiming

_OLLAMA = {"prompt_eval_count": 9000, "eval_count": 180, "num_ctx": 24576}


def _line(stats: dict | None, caplog) -> str:
    timing = _TurnTiming(turn=3, trigger=10.0, llm_done=12.5, end=20.0, answer_chars=400)
    timing.take_llm_stats(stats)
    with caplog.at_level(logging.INFO, logger="dmbot.turn_timing"):
        timing.log_line()
    return caplog.records[0].getMessage()


def test_an_ollama_turn_shows_none_of_the_claude_extras(caplog):
    line = _line(_OLLAMA, caplog)
    assert "ctx=9000/24576 gen=180 chars=400" in line
    assert "spawn=" not in line and "cache=" not in line and "cut" not in line


def test_a_claude_turn_shows_spawn_and_cache_after_gen(caplog):
    line = _line({**_OLLAMA, "spawn_ms": 712, "cache_read": 8400, "truncated": False,
                  "model": "opus", "backend": "claude"}, caplog)
    assert "gen=180 spawn=712ms cache=8400 chars=400" in line
    assert "cut" not in line


def test_a_truncated_turn_is_marked_cut(caplog):
    line = _line({**_OLLAMA, "spawn_ms": 650, "cache_read": 0, "truncated": True}, caplog)
    assert "spawn=650ms cache=0 cut chars=400" in line


def test_an_aborted_stream_without_a_spawn_time_still_logs(caplog):
    line = _line({**_OLLAMA, "spawn_ms": None, "cache_read": 0, "truncated": False}, caplog)
    assert "spawn=" not in line and "cache=0" in line


def test_no_stats_at_all(caplog):
    line = _line(None, caplog)
    assert "ctx=" not in line and "spawn=" not in line and "cut" not in line
