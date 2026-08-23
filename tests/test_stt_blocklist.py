"""Whisper's YouTube-outro hallucinations, blocked by content rather than by confidence (D114).

The threshold guard in ``segments`` drops segments the model itself is unsure about. It cannot
help with these: a fluently generated stock phrase scores *high* confidence, which is exactly why
"Das war's für heute. Tschüss!" reached the table as a player utterance on 2026-08-22 — six times
in one evening, twice routed straight at the DM.

Tobi set the rule at the table: block the combination, not the individual phrase. "Tschüss" on its
own is something a person says; "Das war's für heute, tschüss" is a subtitle track. Phrases that
are *only* ever outro boilerplate ("Ich hoffe, dass euch das Video gefallen hat") are blocked even
alone.

The negative cases are the point of this file: whatever a player really says must survive, even
when it starts with a pleasantry.
"""

from __future__ import annotations

from dmbot.stt.segments import confident_text, is_stock_phrase_only


class _Seg:
    """The faster-whisper Segment duck-type, with confident values by default."""

    def __init__(self, text: str, no_speech_prob: float = 0.1, avg_logprob: float = -0.2) -> None:
        self.text = text
        self.no_speech_prob = no_speech_prob
        self.avg_logprob = avg_logprob


# --- what must be blocked ---------------------------------------------------------------------

def test_the_combination_from_the_live_run_is_blocked() -> None:
    """Tobi's exact instruction: the two-phrase form, not the halves."""
    assert is_stock_phrase_only("Das war's für heute, tschüss!")
    assert is_stock_phrase_only("Das war's für heute. Tschüss!")
    assert is_stock_phrase_only("Das war's für heute, bis zum nächsten Mal!")


def test_a_pure_outro_phrase_is_blocked_even_alone() -> None:
    assert is_stock_phrase_only("Vielen Dank für's Zuhören!")
    assert is_stock_phrase_only("Vielen Dank fürs Zuhören.")
    assert is_stock_phrase_only("Untertitel im Auftrag des ZDF, 2021")


def test_the_full_youtube_outro_is_blocked() -> None:
    text = ("Und das war's für heute. Ich hoffe, dass euch das Video gefallen hat. "
            "Und wenn ihr meinen Kanal abonnieren wollt, dann schreibt es in die Kommentare.")
    assert is_stock_phrase_only(text)


def test_punctuation_and_apostrophes_do_not_help_it_through() -> None:
    assert is_stock_phrase_only("das wars für heute tschüss")
    assert is_stock_phrase_only("Das war es für heute – tschüss ...")


# --- what must survive ------------------------------------------------------------------------

def test_a_single_pleasantry_survives() -> None:
    """Explicitly per Tobi: do not block these on their own."""
    assert not is_stock_phrase_only("Das war's für heute.")
    assert not is_stock_phrase_only("Tschüss!")
    assert not is_stock_phrase_only("Vielen Dank.")
    assert not is_stock_phrase_only("Auf Wiedersehen.")


def test_real_speech_starting_with_a_pleasantry_survives() -> None:
    assert not is_stock_phrase_only("Vielen Dank, das nehme ich mit.")
    assert not is_stock_phrase_only("Tschüss, sagt Kaad, und dreht sich um.")


def test_ordinary_table_talk_survives() -> None:
    for line in [
        "Ich wende mich an Kaad und versuche ihn zu überreden.",
        "Ja Bro, worauf willst du denn warten?",
        "Wir teilen uns auf und schauen uns in den Gebäuden am Hafen um.",
        "Was ist eigentlich unsere Mission?",
    ]:
        assert not is_stock_phrase_only(line), line


def test_empty_input_is_not_a_hallucination() -> None:
    assert not is_stock_phrase_only("")
    assert not is_stock_phrase_only("   ")


# --- the seam the transcriber actually calls ---------------------------------------------------

def test_a_confident_hallucination_is_dropped_by_content() -> None:
    """The whole point: these segments are *confident*, so the thresholds never see them."""
    segments = [_Seg("Das war's für heute."), _Seg(" Tschüss!")]
    text, dropped = confident_text(segments)
    assert text == ""
    assert [d[0] for d in dropped] == ["Das war's für heute.", "Tschüss!"]


def test_real_speech_still_comes_through_whole() -> None:
    segments = [_Seg("Ich trete vor"), _Seg(" und frage ihn nach dem Ossarium.")]
    text, dropped = confident_text(segments)
    assert text == "Ich trete vor und frage ihn nach dem Ossarium."
    assert dropped == []


def test_the_threshold_guard_still_works() -> None:
    segments = [_Seg("Ich horche."), _Seg("Rauschen", no_speech_prob=0.95)]
    text, dropped = confident_text(segments)
    assert text == "Ich horche."
    assert [d[0] for d in dropped] == ["Rauschen"]


def test_one_surviving_pleasantry_is_not_swallowed_by_the_blocklist() -> None:
    segments = [_Seg("Tschüss!")]
    text, _ = confident_text(segments)
    assert text == "Tschüss!"
