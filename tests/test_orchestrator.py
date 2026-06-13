"""Orchestrator tuning (player input → DM answer): meta-preamble stripping + buffer cap.

Two playability levers, both deterministic and unit-testable:
- ``_sanitize`` strips the "Als Spielleitung beschreibe ich: …" preamble nemo prepends despite
  the persona forbidding it (it would be read aloud verbatim), without eating real narration.
- ``DMBrain`` only forwards the most recent ``max_buffer_lines`` to the LLM, so continuous-
  transcription table-talk between !dm presses doesn't drown the latest action.
"""

from __future__ import annotations

import asyncio

from dmbot.orchestrator import (
    DMBrain,
    _ROLE_LABELS,
    _sanitize,
    _strip_leading_label,
    finalize_answer,
)
from dmbot.rules import profile as profile_mod

_IM = profile_mod.load("imperium_maledictum")


def test_strip_leading_player_label() -> None:
    # the model answering AS a player — leading "Name:" must go, narration must stay
    labels = ["SezBoss69", "Timo", "Spielleitung", "DM"]
    assert _strip_leading_label("SezBoss69: Das wäre cool.", labels) == "Das wäre cool."
    assert _strip_leading_label("timo: Ich renne.", labels) == "Ich renne."  # case-insensitive
    # a name not in this turn's labels, or a colon mid-narration, is left untouched
    assert _strip_leading_label("Marko: Bleib stehen.", labels) == "Marko: Bleib stehen."
    assert _strip_leading_label("Du siehst: Rost und Asche.", labels) == "Du siehst: Rost und Asche."


def test_sanitize_strips_meta_preamble() -> None:
    assert _sanitize("Als Spielleitung beschreibe ich: Du siehst eine Tür.") == "Du siehst eine Tür."
    assert _sanitize("Als die Spielleitung beschreibe ich euch: Test.") == "Test."
    assert _sanitize("Spielleitung: Der Rover rollt.") == "Der Rover rollt."


def test_sanitize_strips_code_fence_backticks() -> None:
    # nemo wraps output / a bare marker in `code fences`; backticks would be read aloud — strip them
    assert _sanitize("`Du öffnest die Tür.`") == "Du öffnest die Tür."
    assert _sanitize("```\nEs ist dunkel.\n```") == "Es ist dunkel."


def test_finalize_marker_only_in_backticks_is_empty() -> None:
    # the live failure: the model emits ONLY a marker wrapped in backticks → nothing to speak, but
    # the dice request still surfaces (the cog then posts the button and stays silent).
    raw = "`<<TEST Kampf Schwer für Mortn>>`"
    answer, tests, _manifests, _scenes = finalize_answer(raw, ["Mortn", *_ROLE_LABELS], _IM)
    assert answer == ""
    assert tests and tests[0].skill == "Kampf"


def test_results_only_turn_suppresses_inline_marker() -> None:
    # a post-roll consequence narration must NOT request a new roll, or the dice loop never ends.
    class _C:
        async def chat(self, system, messages, options=None):
            return "Der Kultist weicht zurück. <<TEST Kampf für Mortn>>"

        async def aclose(self) -> None:
            pass

    brain = DMBrain(_C(), profile=_IM)
    ch = 1
    brain.add_test_result(ch, "🎲 Kampf: 28")  # results-only: a dice result, no player line
    answer = asyncio.run(brain.respond(ch))
    assert "<<" not in answer  # marker stripped from the spoken text
    assert brain.take_pending_tests(ch) == []  # but NO new dice button — the loop is broken


def test_player_action_turn_keeps_inline_marker() -> None:
    class _C:
        async def chat(self, system, messages, options=None):
            return "Du schleichst zur Tür. <<TEST Heimlichkeit für Timo>>"

        async def aclose(self) -> None:
            pass

    brain = DMBrain(_C(), profile=_IM)
    ch = 1
    brain.add_player_line(ch, "Timo", "Ich schleiche zur Tür.")
    asyncio.run(brain.respond(ch))
    tests = brain.take_pending_tests(ch)
    assert len(tests) == 1 and tests[0].skill == "Heimlichkeit"  # real player action → marker honoured


def test_sanitize_keeps_real_narration() -> None:
    # "Als der Inquisitor …" is narration, not a role-preamble — must survive untouched.
    text = "Als der Inquisitor eintrifft, wird es still."
    assert _sanitize(text) == text
    assert _sanitize("Du öffnest die schwere Eisentür.") == "Du öffnest die schwere Eisentür."


def test_sanitize_strips_trailing_meta_disclaimer() -> None:
    # nemo's read-aloud disclaimer at the end of a turn must go.
    assert (
        _sanitize("Der Tech-Priester weicht zurück. (Bitte beachte, dass ich keine Repliken "
                  "der Spielenden erfinde.)")
        == "Der Tech-Priester weicht zurück."
    )
    assert (
        _sanitize("Was tut ihr? (Die Spielleitung spricht die Spielenden mit Namen an.)")
        == "Was tut ihr?"
    )


def test_sanitize_keeps_in_fiction_parenthetical() -> None:
    # a genuine in-fiction aside has no meta-language — keep it.
    text = "Du öffnest die Tür (ein Schuss fällt)."
    assert _sanitize(text) == text


def test_sanitize_strips_meta_preamble_with_and_without_colon() -> None:
    # nemo opens with "Als Spielleitung beschreibe ich …" in several shapes — all must go.
    assert _sanitize("Als Spielleitung beschreibe ich: Du siehst eine Tür.") == "Du siehst eine Tür."
    assert (
        _sanitize("Als Spielleitung beschreibe ich eine dunkle Gasse, in der ihr steht.")
        == "Eine dunkle Gasse, in der ihr steht."
    )
    out = _sanitize("Als Spielleitung beschreibe ich die Szene, wie der Mann näher kommt.")
    assert "Als Spielleitung" not in out and out[0].isupper()
    # "… beschreibe ich die Szene so:" must strip fully, not leave a stray "So:" (seen live).
    assert (
        _sanitize("Als Spielleitung beschreibe ich die Szene so:\n\nDu betrittst die Halle.")
        == "Du betrittst die Halle."
    )


def test_sanitize_strips_trailing_action_prompt() -> None:
    # nemo ends almost every turn with "Was tut ihr?"/"Was tust du?" despite the persona — strip it.
    assert _sanitize("Du bemerkst einen Tech-Priester.\n\nWas tust du?") == "Du bemerkst einen Tech-Priester."
    assert _sanitize("Die Tür fällt zu. Was tut ihr jetzt?") == "Die Tür fällt zu."
    # a real mid-scene question and an NPC's question survive — only the generic closer goes
    assert _sanitize("Ihr hört einen Schrei. Was war das? Was tut ihr?") == "Ihr hört einen Schrei. Was war das?"
    assert _sanitize('Der Wächter fragt: "Wer seid ihr?"') == 'Der Wächter fragt: "Wer seid ihr?"'


def test_redo_reruns_last_turn_without_stacking_history() -> None:
    class _SeqClient:
        def __init__(self) -> None:
            self.n = 0

        async def chat(self, system, messages, options=None) -> str:
            self.n += 1
            return f"Antwort {self.n}"

        async def aclose(self) -> None:
            pass

    brain = DMBrain(_SeqClient())
    ch = 1
    brain.add_player_line(ch, "Timo", "Ich öffne die Tür.")
    assert asyncio.run(brain.respond(ch)) == "Antwort 1"
    hist_len = len(brain._history[ch])

    assert asyncio.run(brain.redo(ch)) == "Antwort 2"  # fresh generation, same input
    assert len(brain._history[ch]) == hist_len  # replaced the last turn, not stacked
    assert brain._history[ch][-2]["content"] == "Timo: Ich öffne die Tür."
    assert brain._history[ch][-1]["content"] == "Antwort 2"


def test_redo_without_prior_turn_returns_none() -> None:
    assert asyncio.run(DMBrain(_FakeClient()).redo(999)) is None


class _FakeClient:
    """Captures the messages DMBrain forwards, returns a canned answer; no real Ollama call."""

    def __init__(self) -> None:
        self.last_user_content: str | None = None

    async def chat(self, system, messages, options=None) -> str:
        self.last_user_content = messages[-1]["content"]
        return "Eine knappe Antwort."

    async def aclose(self) -> None:
        pass


def test_buffer_cap_keeps_only_recent_lines() -> None:
    client = _FakeClient()
    brain = DMBrain(client, max_buffer_lines=3)
    ch = 123
    for i in range(5):
        brain.add_player_line(ch, f"P{i}", f"Zeile {i}")

    asyncio.run(brain.respond(ch))

    sent = client.last_user_content
    # only the last 3 of 5 lines reach the model
    assert "Zeile 2" in sent and "Zeile 3" in sent and "Zeile 4" in sent
    assert "Zeile 0" not in sent and "Zeile 1" not in sent


def test_buffer_unbounded_when_cap_zero() -> None:
    client = _FakeClient()
    brain = DMBrain(client, max_buffer_lines=0)  # 0 = keep everything
    ch = 7
    for i in range(5):
        brain.add_player_line(ch, f"P{i}", f"Zeile {i}")

    asyncio.run(brain.respond(ch))

    sent = client.last_user_content
    assert all(f"Zeile {i}" in sent for i in range(5))


def test_sanitize_strips_meta_selfcorrection() -> None:
    # nemo breaks the fiction to "correct itself" out loud (admits to being a Sprachmodell) — only
    # the real narration after "Hier ist die korrekte Antwort:" must survive.
    raw = (
        "Du öffnest die Tür. Nein, warte kurz. Das ist ein Meta-Kommentar von mir als "
        "Sprachmodell. Hier ist die korrekte Antwort: Die Tür knarrt rostig auf."
    )
    assert _sanitize(raw) == "Die Tür knarrt rostig auf."


class _CapClient:
    """Returns a puppeted multi-party script and captures the options DMBrain passes."""

    def __init__(self) -> None:
        self.options: dict | None = None

    async def chat(self, system, messages, options=None) -> str:
        self.options = options
        return "Du schlägst zu. Seskin: Ich helfe dir! Pr0degie: Ich auch!"

    async def aclose(self) -> None:
        pass


def test_known_speakers_truncate_puppeted_party_script() -> None:
    client = _CapClient()
    brain = DMBrain(client)
    ch = 42
    brain.set_known_speakers(ch, ["Seskin", "Vask", "Pr0degie"])
    brain.add_player_line(ch, "Timo", "Ich greife an.")

    answer = asyncio.run(brain.respond(ch))

    # the appended "Seskin: …/Pr0degie: …" puppet script is cut even though neither spoke this turn
    assert answer == "Du schlägst zu."
    # and the table's names also became Ollama stop sequences
    assert "\nSeskin:" in client.options["stop"] and "\nPr0degie:" in client.options["stop"]
