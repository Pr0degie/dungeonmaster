"""Pure hallucination guard for faster-whisper output.

Extracted from ``transcriber.py`` so the keep/drop decision is fixed-input unit-testable without a
loaded model or a GPU. Two independent layers, because they catch different failures:

**By confidence.** On short/quiet clips Whisper invents stock phrases; those segments usually fire
when the model thinks the audio is mostly non-speech (high ``no_speech_prob``) or is low-confidence
(low ``avg_logprob``). Thresholds tuned conservatively so real (even mumbled) speech is kept.

**By content** (D114). The live run of 2026-08-22 showed the hole in that: a *fluently generated*
outro scores high confidence, so the thresholds never see it. "Das war's für heute. Tschüss!"
reached the table as a player utterance six times in one evening, twice routed straight at the DM,
where it became the group's next declared action. Whisper's German training data is full of
subtitle tracks, and their closing lines are what it falls back on when there is nothing to
transcribe.

Tobi set the rule at the table: block the *combination*, not the individual phrase. "Tschüss" on
its own is something a person says at a table; "Das war's für heute, tschüss" is a subtitle track.
So a lone pleasantry survives, two or more chained together do not, and phrases that are only ever
outro boilerplate ("Ich hoffe, dass euch das Video gefallen hat") are blocked even alone.

A *segment* is anything with ``.text`` / ``.no_speech_prob`` / ``.avg_logprob`` (the faster-whisper
``Segment`` duck-type).
"""
from __future__ import annotations

import re
import unicodedata

_NO_SPEECH_MAX = 0.7   # drop a segment whose no_speech_prob exceeds this
_LOGPROB_MIN = -1.0    # …or whose avg_logprob falls below this


# Outro boilerplate that is never table speech: blocked even as the whole utterance on its own.
_HARD_ARTEFACTS = (
    "vielen dank furs zuhoren",
    "vielen dank fur ihre aufmerksamkeit",
    "danke furs zuschauen",
    "vielen dank furs zuschauen",
    "ich hoffe dass euch das video gefallen hat",
    "ich hoffe das video hat euch gefallen",
    "wenn ihr meinen kanal abonnieren wollt",
    "wenn ihr meinen kanal abonnierten wollt",
    "schreibt es in die kommentare",
    "abonniert meinen kanal",
    "vergesst nicht zu abonnieren",
    "bis zum nachsten video",
    "untertitel im auftrag des zdf",
    "untertitel von stephanie geiges",
    "untertitelung des zdf",
    "mehr infos auf",
)

# Pleasantries that a player might genuinely say. Blocked only when the utterance is nothing but
# two or more of them chained together — the shape Tobi named.
_WEAK_ARTEFACTS = (
    "das wars fur heute",
    "das war es fur heute",
    "und das wars fur heute",
    "tschuss",
    "tschuess",
    "auf wiedersehen",
    "bis zum nachsten mal",
    "bis dann",
    "vielen dank",
    "danke",
    "danke schon",
    "wir sehen uns",
)

# Filler that glues the phrases of an outro together ("Und das war's …", "dann schreibt es …").
# Stripped between phrases so it cannot defeat a literal match.
_LEADING_FILLER = re.compile(r"^(?:und|ja|also|ok|okay|so|na|dann|aber|tja)\s+")

# Longest first, so "vielen dank furs zuhoren" (hard) wins over its own prefix "vielen dank" (weak).
_ARTEFACTS_BY_LENGTH = None  # built lazily below, after both tuples exist


def _fold(text: str) -> str:
    """Lowercase, drop accents/umlaut marks and every non-letter — so "Das war's für heute",
    "das wars fuer heute" and "Das war es für heute …" all fold to the same string."""
    text = text.lower().replace("ß", "ss")
    text = text.replace("ä", "a").replace("ö", "o").replace("ü", "u")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _ordered_artefacts() -> list[tuple[str, bool]]:
    """``(phrase, is_hard)`` sorted longest first, so the most specific phrase wins."""
    global _ARTEFACTS_BY_LENGTH
    if _ARTEFACTS_BY_LENGTH is None:
        pairs = [(p, True) for p in _HARD_ARTEFACTS] + [(p, False) for p in _WEAK_ARTEFACTS]
        _ARTEFACTS_BY_LENGTH = sorted(pairs, key=lambda pair: -len(pair[0]))
    return _ARTEFACTS_BY_LENGTH


def is_stock_phrase_only(text: str) -> bool:
    """True when ``text`` is nothing but Whisper outro boilerplate (D114).

    Eats known phrases off the front until nothing is left. Anything that is *not* an artefact
    means a person was speaking, and the whole utterance is kept — this never removes part of a
    sentence, only ever the entire thing. Punctuation is folded away first, so the unpunctuated
    transcripts Whisper produces ("das wars für heute tschüss") are judged the same as the
    punctuated ones.

    Then Tobi's rule: any hard artefact blocks on its own; weak pleasantries block only from the
    second one onwards, so a lone "Tschüss" still reaches the table.
    """
    rest = _fold(text)
    if not rest:
        return False
    hard = 0
    weak = 0
    while rest:
        rest = _LEADING_FILLER.sub("", rest).strip()
        if not rest or rest.isdigit():
            break  # a trailing year ("Untertitel im Auftrag des ZDF, 2021") is part of the artefact
        for phrase, is_hard in _ordered_artefacts():
            if rest == phrase or rest.startswith(phrase + " "):
                rest = rest[len(phrase):].strip()
                if is_hard:
                    hard += 1
                else:
                    weak += 1
                break
        else:
            return False  # something real in there — keep the whole utterance
    return hard > 0 or weak > 1


def confident_text(segments) -> tuple[str, list[tuple[str, float, float]]]:
    """Join the confident segments into one transcript.

    Returns ``(text, dropped)``: ``text`` is the space-joined, stripped transcript of the kept
    segments; ``dropped`` lists ``(text, no_speech_prob, avg_logprob)`` for each guarded-out
    segment (the caller logs them). Empty/whitespace-only segments are skipped silently.

    If what survives the confidence guard is nothing but outro boilerplate, the whole utterance is
    dropped and its segments are reported — the content guard has to judge the *joined* text,
    because "Das war's für heute." and "Tschüss!" arrive as two separate confident segments and
    neither is blockable on its own.
    """
    kept: list[str] = []
    kept_segs: list[tuple[str, float, float]] = []
    dropped: list[tuple[str, float, float]] = []
    for seg in segments:
        seg_text = seg.text.strip()
        if not seg_text:
            continue
        if seg.no_speech_prob > _NO_SPEECH_MAX or seg.avg_logprob < _LOGPROB_MIN:
            dropped.append((seg_text, seg.no_speech_prob, seg.avg_logprob))
            continue
        kept.append(seg_text)
        kept_segs.append((seg_text, seg.no_speech_prob, seg.avg_logprob))
    text = " ".join(kept).strip()
    if text and is_stock_phrase_only(text):
        return "", dropped + kept_segs
    return text, dropped
