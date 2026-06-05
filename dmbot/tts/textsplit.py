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
