"""Pure hallucination guard for faster-whisper output.

Extracted from ``transcriber.py`` so the keep/drop decision is fixed-input unit-testable without a
loaded model or a GPU. On short/quiet clips Whisper invents stock phrases ("Vielen Dank für's
Zuhören", "Das war's für heute" …); those segments fire when the model thinks the audio is mostly
non-speech (high ``no_speech_prob``) or is low-confidence (low ``avg_logprob``). Drop them.
Thresholds tuned conservatively so real (even mumbled) speech is kept.

A *segment* is anything with ``.text`` / ``.no_speech_prob`` / ``.avg_logprob`` (the faster-whisper
``Segment`` duck-type).
"""
from __future__ import annotations

_NO_SPEECH_MAX = 0.7   # drop a segment whose no_speech_prob exceeds this
_LOGPROB_MIN = -1.0    # …or whose avg_logprob falls below this


def confident_text(segments) -> tuple[str, list[tuple[str, float, float]]]:
    """Join the confident segments into one transcript.

    Returns ``(text, dropped)``: ``text`` is the space-joined, stripped transcript of the kept
    segments; ``dropped`` lists ``(text, no_speech_prob, avg_logprob)`` for each guarded-out
    segment (the caller logs them). Empty/whitespace-only segments are skipped silently.
    """
    kept: list[str] = []
    dropped: list[tuple[str, float, float]] = []
    for seg in segments:
        seg_text = seg.text.strip()
        if not seg_text:
            continue
        if seg.no_speech_prob > _NO_SPEECH_MAX or seg.avg_logprob < _LOGPROB_MIN:
            dropped.append((seg_text, seg.no_speech_prob, seg.avg_logprob))
            continue
        kept.append(seg_text)
    return " ".join(kept).strip(), dropped
