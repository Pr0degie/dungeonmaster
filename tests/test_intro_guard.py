"""The deterministic !intro weakness check (ADR 041 follow-up).

The opening monologue on a 12B model is high-variance; the director brief + pinned temperature
can't guarantee a strong turn. ``is_weak_intro`` decides — purely — when the batch ``!intro`` path
should regenerate once: a too-short/generic turn, or one that silently skips a player figure.
"""

from __future__ import annotations

from dmbot.llm.intro_guard import INTRO_RETRY_NUDGE, is_weak_intro

_ROSTER = ["Fridolin Feuchtgebietheld", "Seskin"]

# A strong opening: long, multi-beat, names every figure (by first name, as the DM would address them).
_GOOD = (
    "Der Rost-Regen trommelt auf die Plastahl-Dächer von Rokarth, als ihr durch das Schmugglertor "
    "tretet. Wochenlang seid ihr der Spur des Ketzers gefolgt, und nun endet sie hier, in dieser "
    "ersaufenden Hive-Tiefe. Fridolin, du spürst die vertraute Kälte im Warp-Sinn aufsteigen, ein "
    "Flüstern hinter den Mauern. Und du, Seskin, prüfst beiläufig den Sitz deiner Klinge, während "
    "die Menge sich teilt. Vor euch öffnet sich der Markt der Verlorenen. Welche Spur verfolgt ihr "
    "zuerst, das geflüsterte Gerücht oder die Blutspur am Boden?"
)


def test_strong_opening_is_not_weak() -> None:
    assert is_weak_intro(_GOOD, _ROSTER) is False


def test_short_generic_opening_is_weak() -> None:
    assert is_weak_intro("Ihr steht in Rokarth. Was tut ihr?", _ROSTER) is True


def test_opening_that_skips_a_figure_is_weak() -> None:
    # Long enough, but Seskin is never named — exactly the "skips a character" failure mode.
    only_fridolin = _GOOD.replace("Seskin", "die Gestalt neben dir")
    assert is_weak_intro(only_fridolin, _ROSTER) is True


def test_genitive_possessive_form_counts_as_present() -> None:
    # German names a figure as often in the possessive ("Seskins Hand") as bare — that must not
    # trigger a needless regeneration. Only the genitive 's' is tolerated, not arbitrary suffixes.
    text = _GOOD.replace("Seskin", "Seskins")
    assert is_weak_intro(text, _ROSTER) is False


def test_first_name_match_is_word_bounded() -> None:
    # "Sera" must not be considered present just because "Serania" appears.
    text = "Serania erstreckt sich endlos. " * 12  # long, but no real "Sera"
    assert is_weak_intro(text, ["Sera"]) is True


def test_empty_roster_reduces_to_length_check() -> None:
    assert is_weak_intro(_GOOD, []) is False
    assert is_weak_intro("zu kurz", []) is True


def test_retry_nudge_is_a_director_instruction() -> None:
    assert INTRO_RETRY_NUDGE.startswith("[Regie]")
