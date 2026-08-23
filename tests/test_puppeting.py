"""The DM may speak NSCs, never the player characters (D113).

On 2026-08-22 the DM put words in the players' mouths repeatedly — "Du drehst dich zu ihm um und
musterst ihn eingehend. 'Ich sehe hier keine illegalen Waffen', sagst du kühl." (turn 12), and the
whole intro gave each character a line. Two players said so out loud: "jetzt labert er schon
wieder, das ist ich" and "er redet einfach für dich oder was?".

D110 deferred this to a prompt fix plus measurement. Tobi overrode that: the rule is hard, so the
code enforces it.

Scope is exactly *speech*. A player character acting in the narration is not touched — the line
between narrating a consequence and steering someone's character is not sharp enough to cut with
a regex, and a filter that eats real narration costs more than the tic it removes.
"""

from __future__ import annotations

from dmbot.llm.sanitize import _drop_puppet_speech

PARTY = ["Fridolin Feuchtgebietheld", "Gellicus Schulz", "Rektalus Zerfickus", "Rene Redo", "Timo"]


# --- what must go -----------------------------------------------------------------------------

def test_a_named_player_character_may_not_speak() -> None:
    text = ('Kaad blickt auf. '
            'Fridolin Feuchtgebietheld flüstert: "Wir werden das Ossarium finden."')
    assert _drop_puppet_speech(text, PARTY) == "Kaad blickt auf."


def test_the_second_person_may_not_speak() -> None:
    """The exact shape from turn 12."""
    text = ('Du drehst dich zu ihm um und musterst ihn eingehend. '
            '"Ich sehe hier keine illegalen Waffen", sagst du kühl.')
    assert _drop_puppet_speech(text, PARTY) == "Du drehst dich zu ihm um und musterst ihn eingehend."


def test_a_trailing_attribution_to_a_character_goes() -> None:
    text = 'Der Kran quietscht. "Das gefällt mir nicht", sagt Gellicus Schulz leise.'
    assert _drop_puppet_speech(text, PARTY) == "Der Kran quietscht."


def test_the_plural_you_may_not_speak() -> None:
    text = 'Die Tür fällt zu. "Wir gehen weiter", sagt ihr entschlossen.'
    assert _drop_puppet_speech(text, PARTY) == "Die Tür fällt zu."


def test_a_player_display_name_counts_too() -> None:
    text = 'Nebel zieht auf. Timo ruft: "Hier entlang!"'
    assert _drop_puppet_speech(text, PARTY) == "Nebel zieht auf."


# --- what must stay ---------------------------------------------------------------------------

def test_an_npc_speaks_freely() -> None:
    text = 'Seneschall Kaad hebt die Hand. "Im Namen des Inquisitors", sagt er ernst.'
    assert _drop_puppet_speech(text, PARTY) == text


def test_a_player_character_may_still_act() -> None:
    """Narrating what a character does is the DM's job; only their voice is off limits."""
    text = "Rene Redo tritt an die Kiste und legt die Hand auf das Siegel."
    assert _drop_puppet_speech(text, PARTY) == text


def test_hearing_someone_else_speak_survives() -> None:
    text = 'Du hörst, wie jemand hinter den Kisten sagt: "Sie kommen."'
    assert _drop_puppet_speech(text, PARTY) == text


def test_an_inner_thought_without_speech_survives() -> None:
    text = "Du fragst dich, ob der Seneschall die Wahrheit sagt."
    assert _drop_puppet_speech(text, PARTY) == text


def test_a_character_named_in_narration_survives() -> None:
    text = 'Kaad mustert Gellicus Schulz lange. "Dich kenne ich", sagt er.'
    assert _drop_puppet_speech(text, PARTY) == text


def test_second_person_perception_survives() -> None:
    text = "Du siehst die Kette am Hals des Dockmeisters und riechst den Rauch."
    assert _drop_puppet_speech(text, PARTY) == text


# --- safety rails -----------------------------------------------------------------------------

def test_an_answer_that_is_nothing_but_puppeting_is_left_alone() -> None:
    """Never strip a turn down to nothing: silence is worse than a tic, and the same guard is
    what ``_strip_trailing_prompt`` already does in this module."""
    text = '"Wir werden das Ossarium finden", sagst du entschlossen.'
    assert _drop_puppet_speech(text, PARTY) == text


def test_without_a_known_party_nothing_is_touched() -> None:
    """Second-person speech is still caught — it needs no roster — but a bare name is not a
    player character unless the table says so."""
    text = 'Nebel zieht auf. Timo ruft: "Hier entlang!"'
    assert _drop_puppet_speech(text, []) == text


# --- the streaming path, which is the mode the table actually plays in -------------------------

def test_a_puppeted_sentence_is_never_spoken_while_streaming() -> None:
    """The batch path is not enough: the live sessions run in ``stream`` mode, where sentences go
    to TTS as they complete. A puppeted sentence must never reach the bridge in the first place —
    spoken audio cannot be retracted (docs/lessons/spoken-audio-cannot-be-retracted.md).
    """
    from dmbot.llm.stream_assembler import StreamAssembler

    deltas = [
        "Du drehst dich zu ihm um und musterst ihn eingehend. ",
        '"Ich sehe hier keine illegalen Waffen", sagst du kühl. ',
        "Kaad verschränkt die Arme und schweigt. ",
        'Draußen heult die Sirene ein zweites Mal auf.',
    ]
    assembler = StreamAssembler(PARTY, None)
    spoken: list[str] = []
    for delta in deltas:
        spoken.extend(assembler.feed(delta))
    result = assembler.finish()
    spoken.extend(result.remaining)

    everything = " ".join(spoken)
    assert "sagst du" not in everything
    assert "illegalen Waffen" not in everything
    # and the real narration around it survived, in order
    assert "Du drehst dich zu ihm um und musterst ihn eingehend." in everything
    assert "Kaad verschränkt die Arme und schweigt." in everything
    assert "Draußen heult die Sirene ein zweites Mal auf." in everything
    # the stored answer agrees with what was spoken (parity, ADR 017)
    assert "illegalen Waffen" not in result.answer
