"""Deterministic removal of assistant-register and stage-direction sentences (D112).

The live run of 2026-08-22 read three kinds of non-fiction aloud to the table:

* an assistant apologising in the formal register — "Es tut mir leid, aber ich kann Ihre Frage
  nicht verstehen. Könnten Sie bitte etwas genauer erklären, was Sie meinen?" (turn 3, and it was
  the *whole* answer), plus "Ich entschuldige mich für das Missverständnis. Ich werde in Zukunft
  darauf achten …" (turn 18);
* a director frame in a word order the existing preamble strip does not catch — "In diesem Fall
  würde ich als Spielleitung antworten: …" (turn 4);
* a handover stage direction closing almost every answer — "Damit übergibt Kaad die Verantwortung
  wieder an die Gruppe.", "Damit endet dein Zug und die Szene ist wieder offen für die nächste
  Aktion." (turns 4, 8, 9, 10, 15, 16).

The prompt forbids all three and nemo writes them anyway, which is what
``docs/lessons/deterministic-guards-over-persona-hopes.md`` says to expect: code owns removal.

The negative cases matter as much as the positive ones. An NPC may apologise, and a scene may
legitimately end something — those must survive untouched, or the filter eats the game.
"""

from __future__ import annotations

from dmbot.llm.sanitize import META_FALLBACK_DE, _sanitize
from dmbot.llm.stream_assembler import finalize_answer_markers


# --- stage directions -----------------------------------------------------------------------

def test_the_handover_stage_direction_goes() -> None:
    text = ('Kaad nickt ernst. "Gut. Ihr wisst, was zu tun ist." '
            "Damit übergibt Kaad die Verantwortung wieder an die Gruppe.")
    assert _sanitize(text) == 'Kaad nickt ernst. "Gut. Ihr wisst, was zu tun ist."'


def test_every_handover_wording_from_the_live_run_goes() -> None:
    tail_variants = [
        "Damit übergibt er wieder die Verantwortung an die Gruppe und wartet auf ihren nächsten Zug.",
        "Damit übergebe ich wieder an die Gruppe und warte auf ihren nächsten Zug.",
        "Damit endet dein Zug und die Szene ist wieder offen für die nächste Aktion.",
        "Damit gibst du wieder den Ball zurück an die Gruppe und wartest auf ihren nächsten Zug.",
        "Damit übergibt er wieder das Wort an die Gruppe und wartet auf ihren nächsten Zug.",
        "Ich warte darauf, wie die Gruppe reagiert.",
    ]
    for tail in tail_variants:
        assert _sanitize(f"Der Nebel zieht über den Kai. {tail}") == "Der Nebel zieht über den Kai.", tail


def test_a_scene_that_legitimately_ends_something_survives() -> None:
    """"Damit endet …" is only a stage direction when it hands play back."""
    text = "Der letzte Kran verstummt. Damit endet die Schicht im Hafenbecken."
    assert _sanitize(text) == text


def test_an_npc_waiting_is_not_a_stage_direction() -> None:
    text = 'Kessel lehnt sich zurück. "Ich warte darauf, dass ihr endlich bietet."'
    assert _sanitize(text) == text


# --- director frame -------------------------------------------------------------------------

def test_the_would_answer_director_frame_goes() -> None:
    text = ('In diesem Fall würde ich als Spielleitung antworten: '
            'Kaad nickt ernst und reicht euch die Karte.')
    assert _sanitize(text) == "Kaad nickt ernst und reicht euch die Karte."


def test_the_bare_would_answer_frame_goes_too() -> None:
    assert _sanitize("Würde ich als Spielleitung antworten: Der Raum ist leer.") == "Der Raum ist leer."


# --- assistant register ---------------------------------------------------------------------

def test_an_assistant_apology_sentence_goes_but_the_narration_stays() -> None:
    text = ("Ich entschuldige mich für das Missverständnis. "
            "Der Regen trommelt auf die Verladerampe.")
    assert _sanitize(text) == "Der Regen trommelt auf die Verladerampe."


def test_a_whole_assistant_answer_leaves_nothing() -> None:
    text = ("Es tut mir leid, aber ich kann Ihre Frage nicht verstehen. "
            "Könnten Sie bitte etwas genauer erklären, was Sie meinen?")
    assert _sanitize(text) == ""


def test_the_future_promise_goes() -> None:
    text = ("Ich werde in Zukunft darauf achten, jeden Spielenden direkt mit seinem "
            "Charakternamen anzusprechen.")
    assert _sanitize(text) == ""


def test_an_npc_may_apologise_in_dialogue() -> None:
    """A quoted sentence is never assistant register — it is someone speaking in the fiction."""
    text = 'Der Schreiber senkt den Blick. "Es tut mir leid, ich kann Ihre Frage nicht beantworten."'
    assert _sanitize(text) == text


def test_narration_that_merely_mentions_an_apology_survives() -> None:
    text = "Der Seneschall entschuldigt sich für die Verspätung und winkt euch durch."
    assert _sanitize(text) == text


# --- the collapse case, at the seam that decides what gets spoken -----------------------------

def test_an_all_meta_answer_collapses_to_a_gm_line_instead_of_silence() -> None:
    """Stripping everything must not leave the table in silence after they pressed the mic.

    The intent (I did not understand you) is kept, the chatbot register is dropped.
    """
    raw = ("Es tut mir leid, aber ich kann Ihre Frage nicht verstehen. "
           "Könnten Sie bitte etwas genauer erklären, was Sie meinen?")
    answer, _ = finalize_answer_markers(raw, [], None)
    assert answer == META_FALLBACK_DE
    assert "Sie " not in answer  # the fallback speaks to the table the way the DM always does


def test_a_marker_only_answer_is_not_treated_as_meta() -> None:
    """An answer that is empty because a marker was stripped is a different thing entirely —
    it must stay empty, not be replaced by the did-not-understand line."""
    answer, _ = finalize_answer_markers("<<ERLEDIGT zollvollmacht>>", [], None)
    assert answer == ""


def test_a_normal_answer_is_untouched_at_the_seam() -> None:
    raw = "Der Nebel liegt über dem Ladebecken, und die Sirene heult ein zweites Mal."
    answer, _ = finalize_answer_markers(raw, [], None)
    assert answer == raw
