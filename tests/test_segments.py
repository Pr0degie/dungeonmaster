"""Unit tests for the pure hallucination guard in dmbot.stt.segments.

Fixed, hand-built fake segments (no model, no GPU) — exercise the keep/drop decision,
the strict-comparison boundaries, empty-text skipping, and the dropped-tuple shape.
"""
from __future__ import annotations

import types

from dmbot.stt.segments import confident_text


def _seg(text: str, no_speech_prob: float = 0.0, avg_logprob: float = 0.0):
    """A faster-whisper Segment duck-type: just .text / .no_speech_prob / .avg_logprob."""
    return types.SimpleNamespace(
        text=text, no_speech_prob=no_speech_prob, avg_logprob=avg_logprob
    )


def test_confident_segments_kept_and_space_joined_stripped():
    text, dropped = confident_text([_seg("  Hallo  "), _seg(" Welt ")])
    assert text == "Hallo Welt"
    assert dropped == []


def test_high_no_speech_prob_is_dropped():
    text, dropped = confident_text([_seg("rauschen", no_speech_prob=0.9)])
    assert text == ""
    assert [d[0] for d in dropped] == ["rauschen"]


def test_low_avg_logprob_is_dropped():
    text, dropped = confident_text([_seg("geraten", avg_logprob=-2.0)])
    assert text == ""
    assert [d[0] for d in dropped] == ["geraten"]


def test_boundary_values_are_kept():
    # Strict comparisons (> and <): exactly at the threshold is KEPT, not dropped.
    text, dropped = confident_text(
        [_seg("grenzwert", no_speech_prob=0.7, avg_logprob=-1.0)]
    )
    assert text == "grenzwert"
    assert dropped == []


def test_empty_and_whitespace_only_segments_skipped_silently():
    text, dropped = confident_text([_seg(""), _seg("   "), _seg("echt")])
    assert text == "echt"
    # Skipped silently: absent from both the joined text and the dropped list.
    assert dropped == []


def test_dropped_carries_stripped_text_and_probs():
    text, dropped = confident_text(
        [_seg("  murmel  ", no_speech_prob=0.95, avg_logprob=-0.3)]
    )
    assert text == ""
    assert dropped == [("murmel", 0.95, -0.3)]


def test_all_dropped_returns_empty_text_and_nonempty_dropped():
    text, dropped = confident_text(
        [_seg("a", no_speech_prob=0.8), _seg("b", avg_logprob=-1.5)]
    )
    assert text == ""
    assert len(dropped) == 2
    assert [d[0] for d in dropped] == ["a", "b"]
