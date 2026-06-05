"""The clean session transcript file (logs/transcript.log): only the conversation, with timestamps.

A separate log handler keeps a pasteable record of what was said — player lines (📝, incl. table
talk) + DM answers (🎭) — while the debug chatter (PCM heartbeats, model loading, …) stays out.
"""

from __future__ import annotations

import logging

from dmbot.logsetup import _TranscriptFilter, _TranscriptFormatter


def _rec(msg: str) -> logging.LogRecord:
    return logging.LogRecord("dmbot.voice.commands", logging.INFO, __file__, 1, msg, None, None)


def test_filter_passes_only_conversation() -> None:
    f = _TranscriptFilter()
    assert f.filter(_rec("📝 Timo | 2.3s·190ms | Hallo"))
    assert f.filter(_rec("🎭 Der Priester nickt."))
    assert not f.filter(_rec("PCM ⟳ Timo: +100 decoded (333 KiB)"))
    assert not f.filter(_rec("joined voice 'circlejerk' (id=1) and started VAD pipeline"))


def test_formatter_player_keeps_dm_marker_drops_metric() -> None:
    fmt = _TranscriptFormatter()
    routed = fmt.format(_rec("📝 Timo | 2.3s·190ms →DM | Ich öffne die Tür."))
    assert routed.endswith("Timo →DM: Ich öffne die Tür.")
    assert "190ms" not in routed  # the debug metric is dropped from the transcript

    table_talk = fmt.format(_rec("📝 SezBoss69 | 1.1s·100ms | Hahaha"))
    assert table_talk.endswith("SezBoss69: Hahaha")
    assert "→DM" not in table_talk  # table talk is kept, just not marked


def test_formatter_dm_answer() -> None:
    out = _TranscriptFormatter().format(_rec("🎭 Der Tech-Priester weicht zurück."))
    assert out.endswith("Spielleiter: Der Tech-Priester weicht zurück.")
