"""Split a DM answer into TTS-safe chunks.

XTTS truncates the audio of any single chunk longer than ~253 chars for German (it warns "text
length exceeds the character limit"), which cut DM answers off mid-sentence. We split the text
into sub-limit chunks here, then the XTTS wrapper synthesises each and concatenates the WAVs.

Pure (no torch / no audio deps) so it stays unit-testable on its own.
"""

from __future__ import annotations

import re

# Stay safely under XTTS's 253-char German limit.
TTS_CHAR_LIMIT = 240

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")

# Split after terminal punctuation + any closing quote/bracket + whitespace. Used by the streaming
# assembler (ADR 017) to tell a *complete* sentence (it ends on a terminator) from a still-growing
# fragment — the single home for sentence-boundary logic, so the assembler doesn't re-roll its own.
_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?…])["»”’)\]]*\s+')
_ENDS_SENTENCE = re.compile(r'[.!?…]["»”’)\]]*$')


def split_completed(text: str) -> tuple[list[str], str]:
    """Split ``text`` into (completed sentences, trailing fragment).

    A *completed* sentence ends on terminal punctuation (optionally a closing quote/bracket); the
    trailing fragment is whatever follows the last terminator with no terminator of its own (the
    part still being generated mid-stream). ``("", "")``-safe: empty input → ``([], "")``.
    """
    text = text.strip()
    if not text:
        return [], ""
    parts = [p for p in _SENTENCE_BOUNDARY.split(text) if p]
    if not parts:
        return [], ""
    tail = "" if _ENDS_SENTENCE.search(parts[-1]) else parts.pop()
    return [p.strip() for p in parts if p.strip()], tail.strip()

# Glyphs XTTS reads out or stumbles over when spoken (players: "er liest die Interpunktion mit vor
# — Komma, Punkt, Ausrufezeichen … das ist Müll"): quotation marks of every flavour, brackets and
# stray symbols. Dropped before synthesis. We deliberately KEEP . , ! ? ; : (they carry the voice's
# intonation + pauses, which the players want — "durch die Betonung erkennt man es sowieso") and the
# word hyphen "-" (Hive-Stadt). Em/en dashes and the ellipsis get mapped to a pause separately.
_DROP_CHARS = "".join([
    '"', "'", "«", "»", "‹", "›", "„", "“", "”", "‚", "‘", "’",
    "*", "_", "#", "`", "~", "|", "<", ">", "(", ")", "[", "]", "{", "}",
    "/", "\\", "&", "%", "$", "@", "=", "+",
])
_TTS_DROP = str.maketrans("", "", _DROP_CHARS)


def normalize_for_tts(text: str) -> str:
    """Clean a DM answer for **speech only** (never the text posted to Discord): drop the glyphs
    XTTS verbalises or mangles — quotes, ellipses, em/en dashes, brackets, stray symbols — while
    keeping the prosody-bearing ``. , ! ? ; :`` and word hyphens. The fix for the players' "stop
    reading the punctuation aloud" wish. Falls back to the stripped original if cleaning empties it
    (an all-symbol answer is implausible, but never feed TTS an empty string)."""
    cleaned = text.replace("…", ".")                    # ellipsis → period (else read as dots)
    cleaned = re.sub(r"\s*[—–]\s*", ", ", cleaned)      # em/en dash as a pause → comma (keeps "-" in words)
    cleaned = cleaned.translate(_TTS_DROP)              # drop quotes / brackets / stray symbols
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)  # no space before punctuation (left by removed quotes)
    cleaned = re.sub(r"([.!?])\s*,", r"\1", cleaned)    # a comma stranded after a sentence-ender → drop
    cleaned = re.sub(r"([.!?,;:])\1+", r"\1", cleaned)  # collapse repeats: "!!"→"!", ",,"→","
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()   # tidy whitespace from removals
    return cleaned or text.strip()


def has_speakable_content(text: str) -> bool:
    """True if ``text`` has anything worth synthesising — at least one letter or digit. A turn that
    reduces to only punctuation / quotes / backticks (e.g. a marker-only answer the model wrapped in
    a code fence, after stripping) must NOT be spoken: XTTS would burn ~15 s of synth + playback on a
    lone quote (seen live 2026-06-10). The dice button still posts; just nothing is read aloud."""
    return any(ch.isalnum() for ch in text)


def chunk_text(text: str, limit: int = TTS_CHAR_LIMIT) -> list[str]:
    """Split ``text`` into chunks no longer than ``limit`` chars, breaking at sentence ends first,
    then at commas/spaces for any single sentence that is itself too long. Whole sentences are kept
    together where they fit, so prosody stays natural."""
    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        while len(sentence) > limit:
            cut = sentence.rfind(", ", 0, limit)
            if cut == -1:
                cut = sentence.rfind(" ", 0, limit)
            if cut == -1:
                cut = limit
            head, sentence = sentence[: cut + 1].strip(), sentence[cut + 1 :].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks or [text.strip()]
