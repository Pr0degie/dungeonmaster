"""TTS chunking: keep every chunk under XTTS's German char limit so audio isn't truncated."""

from __future__ import annotations

from dmbot.tts.textsplit import (
    TTS_CHAR_LIMIT,
    chunk_text,
    has_speakable_content,
    normalize_for_tts,
)


def test_has_speakable_content() -> None:
    # real narration is speakable; a content-less answer (a marker-only turn after stripping, a
    # lone quote/backtick) is NOT — it must not be synthesised (XTTS would read it for ~15 s).
    assert has_speakable_content("Du öffnest die Tür.")
    assert has_speakable_content("Ja")
    assert not has_speakable_content("``")
    assert not has_speakable_content('"')
    assert not has_speakable_content("  .,!? ")
    assert not has_speakable_content("")


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
    assert normalize_for_tts('"..."') == "."  # quotes drop, the dots collapse to one period
    assert normalize_for_tts("   ") == ""


def test_normalize_strips_emojis_and_symbols() -> None:
    # the live bug: emojis + Unicode symbols XTTS turns into gibberish — now dropped (whitelist).
    assert normalize_for_tts("Der Kult weicht zurück 🎲") == "Der Kult weicht zurück"
    assert normalize_for_tts("er weicht → zurück") == "er weicht zurück"   # arrow → space, no word merge
    assert normalize_for_tts("Treffer 💥 am Arm") == "Treffer am Arm"
    assert normalize_for_tts("1 EG · Warp") == "1 EG Warp"                 # middle dot gone
    assert normalize_for_tts("• Erster Punkt") == "Erster Punkt"           # bullet gone
    assert normalize_for_tts("Bann 🜏 Ende") == "Bann Ende"


def test_normalize_keeps_german_letters_digits_and_nbsp() -> None:
    assert normalize_for_tts("Schädel, Würfel 2 von 4!") == "Schädel, Würfel 2 von 4!"
    assert normalize_for_tts("Wort\xa0Wort") == "Wort Wort"                # NBSP → normal space


def test_chunk_drops_unspeakable_chunks() -> None:
    # a turn that cleans down to nothing speakable must yield no chunks (XTTS never sees junk)
    assert chunk_text(normalize_for_tts("🎲🌀🜏")) == []
    assert chunk_text("") == []
    # every chunk of a real (emoji-laced) answer is speakable
    chunks = chunk_text(normalize_for_tts("Du öffnest die Tür. 🎲 Was tut ihr?"))
    assert chunks and all(has_speakable_content(c) for c in chunks)
