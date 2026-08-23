"""Grouping a turn's buffered player lines per speaker (D111).

The roll-detection router classified only the *last* buffered line, so when several players
declared an action in one turn only the last speaker could ever be asked for a test — every
other declaration was silently dropped. These are the pure grouping rules behind the fix.
"""

from __future__ import annotations

from dmbot.llm.turn_actions import group_by_speaker


def test_a_single_speaker_is_one_action() -> None:
    assert group_by_speaker([("Timo", "Ich überrede ihn.")]) == [("Timo", "Ich überrede ihn.")]


def test_each_speaker_keeps_their_own_action() -> None:
    lines = [
        ("Timo", "Ich wende mich an Kaad und überrede ihn."),
        ("Sezgin", "Ich schaue mich in der Sakristei um."),
    ]
    assert group_by_speaker(lines) == [
        ("Timo", "Ich wende mich an Kaad und überrede ihn."),
        ("Sezgin", "Ich schaue mich in der Sakristei um."),
    ]


def test_several_lines_from_one_speaker_join_in_order() -> None:
    """A player who pauses mid-sentence produces several lines — one action, not three."""
    lines = [
        ("Timo", "Ich wende mich an Kaad"),
        ("Timo", "und versuche ihn zu überreden."),
    ]
    assert group_by_speaker(lines) == [("Timo", "Ich wende mich an Kaad und versuche ihn zu überreden.")]


def test_interleaved_speakers_keep_first_appearance_order() -> None:
    lines = [
        ("Timo", "Ich ziehe die Waffe."),
        ("Sezgin", "Ich rede auf ihn ein."),
        ("Timo", "Und ziele auf die Kiste."),
    ]
    assert group_by_speaker(lines) == [
        ("Timo", "Ich ziehe die Waffe. Und ziele auf die Kiste."),
        ("Sezgin", "Ich rede auf ihn ein."),
    ]


def test_blank_lines_and_whitespace_never_become_an_action() -> None:
    assert group_by_speaker([("Timo", "   "), ("Sezgin", "")]) == []
    assert group_by_speaker([("Timo", "  Ich horche.  ")]) == [("Timo", "Ich horche.")]


def test_no_lines_is_no_action() -> None:
    assert group_by_speaker([]) == []


def test_the_cap_keeps_the_last_speakers_not_the_first() -> None:
    """More distinct speakers than the cap: the most recent declarations win, because a stale
    one from the start of a long buffer is the least likely to still be what the table wants
    rolled. The cap bounds how many classifier calls one turn can spawn."""
    lines = [("A", "eins"), ("B", "zwei"), ("C", "drei"), ("D", "vier"), ("E", "fünf")]
    assert group_by_speaker(lines, cap=3) == [("C", "drei"), ("D", "vier"), ("E", "fünf")]


def test_the_cap_counts_speakers_not_lines() -> None:
    lines = [("A", "eins"), ("A", "noch eins"), ("A", "und eins"), ("B", "zwei")]
    assert group_by_speaker(lines, cap=2) == [("A", "eins noch eins und eins"), ("B", "zwei")]
