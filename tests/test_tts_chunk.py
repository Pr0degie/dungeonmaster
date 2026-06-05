"""TTS chunking: keep every chunk under XTTS's German char limit so audio isn't truncated."""

from __future__ import annotations

from dmbot.tts.textsplit import TTS_CHAR_LIMIT, chunk_text


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Du siehst eine Tür. Was tut ihr?") == ["Du siehst eine Tür. Was tut ihr?"]


def test_every_chunk_under_limit() -> None:
    # a single long sentence (like the DM occasionally emits) must be split, all chunks <= limit
    long = (
        "Als die Gardisten skeptisch auf deine Kooperationsbereitschaft reagieren und Tobi "
        "misstrauisch mustern, der sich abseits halten will, tritt der Anführer einen Schritt vor "
        "und sagt mit ernster Miene, dass euer Angebot zweifelhaft sei, ihr aber dennoch mitkommen "
        "und euch bewähren müsst, bevor man euch traut."
    )
    chunks = chunk_text(long)
    assert len(chunks) >= 2
    assert all(len(c) <= TTS_CHAR_LIMIT for c in chunks)
    # nothing is lost: every word survives the split
    assert set(long.split()) == set(" ".join(chunks).split())


def test_sentences_kept_together_when_they_fit() -> None:
    text = "Der Mann knurrt. Er zieht einen Dolch. Was tut ihr?"
    assert chunk_text(text) == [text]  # all three short sentences fit one chunk


def test_packs_multiple_sentences_up_to_limit() -> None:
    s = "Ein Satz von mittlerer Länge, der etwas Raum braucht, aber nicht zu viel."  # ~73 chars
    chunks = chunk_text(" ".join([s] * 6))  # ~440 chars → must become >1 chunk, each <= limit
    assert len(chunks) >= 2
    assert all(len(c) <= TTS_CHAR_LIMIT for c in chunks)
