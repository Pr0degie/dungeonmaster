"""TTS chunking: keep every chunk under XTTS's German char limit so audio isn't truncated."""

from __future__ import annotations

from dmbot.tts.textsplit import TTS_CHAR_LIMIT, chunk_text, normalize_for_tts


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


def test_normalize_drops_quotes_but_keeps_words_and_prosody() -> None:
    # NPC dialogue full of quotes (the likely culprit XTTS read aloud) → quotes gone, words + the
    # sentence-ending punctuation kept (the voice still phrases it as a question/exclamation).
    assert normalize_for_tts('Er zischt: "Wer wagt es?"') == "Er zischt: Wer wagt es?"
    assert normalize_for_tts('„Bleib weg!", zischt er.') == "Bleib weg! zischt er."
    # straight + curly quotes, asterisks, brackets all go
    assert normalize_for_tts("Ein *dunkler* (alter) Gang.") == "Ein dunkler alter Gang."


def test_normalize_maps_ellipsis_and_dashes_to_pauses() -> None:
    assert normalize_for_tts("Ich… ich weiß nicht.") == "Ich. ich weiß nicht."
    # em/en dash used as a parenthetical pause → comma; the word hyphen in "Hive-Stadt" survives
    assert normalize_for_tts("Der Raum — düster — schweigt.") == "Der Raum, düster, schweigt."
    assert normalize_for_tts("Die Hive-Stadt ist riesig.") == "Die Hive-Stadt ist riesig."


def test_normalize_never_returns_empty() -> None:
    assert normalize_for_tts('"..."') == "."  # all-symbol → falls back rather than feed TTS ""
    assert normalize_for_tts("   ") == ""
