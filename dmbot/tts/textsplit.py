"""Split a DM answer into TTS-safe chunks.

XTTS truncates the audio of any single chunk longer than ~253 chars for German (it warns "text
length exceeds the character limit"), which cut DM answers off mid-sentence. We split the text
into sub-limit chunks here, then the XTTS wrapper synthesises each and concatenates the WAVs.

Pure (no torch / no audio deps) so it stays unit-testable on its own.
"""

from __future__ import annotations

import re
import unicodedata

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

# What the voice may SAY: the prosody-bearing punctuation we keep (intonation + pauses the players
# want — "durch die Betonung erkennt man es sowieso") plus the word hyphen "-" (Hive-Stadt).
# Everything else non-alphanumeric is dropped before synthesis — a whitelist, so emojis, arrows,
# bullets, the middle dot "·", quotes, brackets and any future stray symbol never reach XTTS, which
# otherwise verbalises them as noise/gibberish (players: "er liest die Interpunktion mit vor … das
# ist Müll", and lone symbols make XTTS hallucinate). Em/en/figure/minus dashes + the ellipsis are
# mapped to a spoken pause first so they don't just vanish.
_KEEP_PUNCT = frozenset(".,!?;:-")
_WS_RE = re.compile(r"[\xa0  ​‌‍﻿]")  # NBSP / narrow / zero-width / BOM
_DASH_RE = re.compile(r"\s*[—–―‒‑−]\s*")  # dash & minus variants → pause; ASCII "-" stays in words
_APOSTROPHE_RE = re.compile(r"[’‘ʼ']")    # drop apostrophes outright so names/contractions don't split


def normalize_for_tts(text: str) -> str:
    """Clean a DM answer for **speech only** (never the text posted to Discord): keep letters,
    digits, whitespace and the prosody-bearing ``. , ! ? ; :`` + word hyphen; drop everything else
    (emojis, arrows, bullets, ``·``, quotes, brackets, stray symbols) — a whitelist so nothing new
    can leak through to XTTS as gibberish. Dashes/ellipsis become a spoken pause first. May return
    ``""`` when there's nothing speakable left (the caller/chunker guards against synthesising it)."""
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = _WS_RE.sub(" ", cleaned)                 # exotic whitespace → normal space
    cleaned = _APOSTROPHE_RE.sub("", cleaned)          # drop apostrophes (no word split)
    cleaned = cleaned.replace("…", ".")                # ellipsis → period (else read as dots)
    cleaned = _DASH_RE.sub(", ", cleaned)              # dashes as a pause → comma (keeps "-" in words)
    cleaned = "".join(                                 # whitelist: drop any other non-speakable glyph
        ch if (ch.isalnum() or ch.isspace() or ch in _KEEP_PUNCT) else " " for ch in cleaned
    )
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)  # no space before punctuation (left by removals)
    cleaned = re.sub(r"([.!?])\s*,", r"\1", cleaned)    # a comma stranded after a sentence-ender → drop
    cleaned = re.sub(r"([.,!?;:])\1+", r"\1", cleaned)  # collapse repeats: "!!"→"!", ",,"→","
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()   # tidy whitespace from removals
    return cleaned


def strip_speech_punctuation(text: str) -> str:
    """Drop **all** punctuation/symbols from speech text — keep only letters, digits and whitespace.

    `!intro test` only (ADR 031): XTTS sometimes loops/babbles **on** punctuation (D55), so this path
    feeds it punctuation-free sentences and restores the sentence breaks via the short pause between
    separately-spoken sentences. A whitelist (letters/digits/space), so *nothing* — sentence marks,
    the word hyphen, quotes, dashes, emojis — reaches the synth as a symbol (Tobi: "nimm alle
    satzzeichen raus"). Whitespace is tidied; may return ``""`` (the caller guards with
    :func:`has_speakable_content`)."""
    kept = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in text)
    return re.sub(r"\s{2,}", " ", kept).strip()


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
    # Drop chunks that carry nothing speakable (e.g. a lone "." split off a sentence) — XTTS reads a
    # bare punctuation chunk for ~15 s or hallucinates. Empty list = nothing to synthesise.
    return [c for c in chunks if has_speakable_content(c)]
