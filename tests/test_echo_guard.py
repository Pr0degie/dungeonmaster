"""Echo guard + roll-feedback directive (D43 / ADR 018).

The live failure (2026-06-12): on a post-roll turn the model answered with the *next player line*
("Pr0degie: Ich greife den Kultisten an.") instead of narrating; the leading-label strip left a
clean-looking echo that was spoken and stored, and three turns later the DM answered every input
with the same parroted sentence. Deterministic countermeasures, all unit-testable:

- ``is_echo`` flags an answer that merely parrots a player line of this turn's user_msg;
- ``respond``/``respond_streaming`` retry once with a corrective nudge, then suppress the turn
  entirely (nothing spoken, the pair stays out of history — an echo in history self-reinforces);
- a results-only ``[Würfel]`` turn carries an explicit "narrate the consequence" directive;
- ``restore_history`` skips empty answers so persisted junk turns aren't re-taught on restore.
"""

from __future__ import annotations

import asyncio

from dmbot.orchestrator import DMBrain, _ECHO_NUDGE, _ROLL_DIRECTIVE, is_echo


# --- is_echo: the pure detector ------------------------------------------------------------------

def test_exact_echo_of_a_player_line_is_flagged() -> None:
    user_msg = "Pr0degie: Ich greife den Kultisten an."
    assert is_echo("Ich greife den Kultisten an.", user_msg)


def test_echo_is_case_and_punctuation_insensitive() -> None:
    user_msg = "Timo: Ich öffne die schwere Tür!"
    assert is_echo("ich öffne die schwere Tür…", user_msg)


def test_fragment_of_a_player_line_is_flagged() -> None:
    user_msg = "Timo: Ich greife den Kultisten an, indem ich ihm mein Schwert in die Augen steche."
    assert is_echo("Ich greife den Kultisten an.", user_msg)


def test_line_covering_almost_the_whole_answer_is_flagged() -> None:
    # the echo plus a token of decoration is still an echo (≥90% coverage)
    user_msg = "Pr0degie: Ich greife den Kultisten an."
    assert is_echo("Ich greife den Kultisten an. Ja.", user_msg)


def test_real_consequence_narration_is_not_flagged() -> None:
    user_msg = "Pr0degie: Ich greife den Kultisten an."
    assert not is_echo(
        "Du greifst den Kultisten an und dein Kettenschwert reißt ihm die Schulter auf.", user_msg
    )


def test_echo_plus_substantial_narration_is_not_flagged() -> None:
    # quoting the action inside a longer narration is legitimate (coverage < 90%)
    user_msg = "Pr0degie: Ich greife den Kultisten an."
    assert not is_echo(
        "Ich greife den Kultisten an, zischt Garran — und der Kultist weicht mit gezogenem "
        "Messer in den Schatten der Kapelle zurück.", user_msg,
    )


def test_too_short_lines_never_count_as_echo() -> None:
    assert not is_echo("Ja.", "Timo: Ja.")  # under 10 normalized chars: too short to call
    assert not is_echo("Gut.", "Timo: Gut")


def test_empty_answer_is_not_an_echo() -> None:
    assert not is_echo("", "Timo: Ich greife den Kultisten an.")


# --- respond(): retry once, then suppress ---------------------------------------------------------

class _EchoThenGoodClient:
    """First call parrots the player line, the retry narrates. Records each call's messages."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, system, messages, options=None):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return "Pr0degie: Ich greife den Kultisten an."
        return "Der Kultist weicht zurück und zieht ein Messer."

    async def aclose(self) -> None:
        pass


class _AlwaysEchoClient:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, system, messages, options=None):
        self.calls += 1
        return "Ich greife den Kultisten an."

    async def aclose(self) -> None:
        pass


def test_respond_retries_an_echo_with_the_nudge_and_stores_the_clean_answer() -> None:
    client = _EchoThenGoodClient()
    brain = DMBrain(client)
    ch = 1
    brain.add_player_line(ch, "Pr0degie", "Ich greife den Kultisten an.")
    answer = asyncio.run(brain.respond(ch))
    assert answer == "Der Kultist weicht zurück und zieht ein Messer."
    # the retry call carried the corrective nudge…
    assert _ECHO_NUDGE in client.calls[1][-1]["content"]
    # …but history stores the ORIGINAL user_msg with the clean answer
    history = brain._history[ch]
    assert _ECHO_NUDGE not in history[-2]["content"]
    assert history[-1]["content"] == answer


def test_respond_suppresses_a_double_echo_and_keeps_history_clean() -> None:
    client = _AlwaysEchoClient()
    brain = DMBrain(client)
    ch = 1
    brain.add_player_line(ch, "Pr0degie", "Ich greife den Kultisten an.")
    answer = asyncio.run(brain.respond(ch))
    assert answer == ""  # content-less to the cog: nothing posted/spoken
    assert client.calls == 2  # exactly one retry
    assert brain._history.get(ch, []) == []  # the poison pair never enters history


# --- respond_streaming(): same guard at finish() ---------------------------------------------------

class _EchoStreamClient:
    """Streams an echo; the (batch) retry narrates — or echoes again when ``always_echo``."""

    def __init__(self, always_echo: bool = False) -> None:
        self.always_echo = always_echo
        self.chat_calls = 0

    async def chat_stream(self, system, messages, options=None):
        for delta in ["Ich greife ", "den Kultisten an."]:
            yield delta

    async def chat(self, system, messages, options=None):
        self.chat_calls += 1
        if self.always_echo:
            return "Ich greife den Kultisten an."
        return "Die Klinge des Kultisten blitzt auf, als er zurückweicht."

    async def aclose(self) -> None:
        pass


def test_streaming_echo_is_retried_and_the_clean_answer_spoken_and_stored() -> None:
    client = _EchoStreamClient()
    brain = DMBrain(client)
    ch = 1
    spoken: list[str] = []

    async def on_sentence(s: str) -> None:
        spoken.append(s)

    brain.add_player_line(ch, "Pr0degie", "Ich greife den Kultisten an.")
    answer = asyncio.run(brain.respond_streaming(ch, on_sentence=on_sentence))
    assert answer == "Die Klinge des Kultisten blitzt auf, als er zurückweicht."
    assert spoken == [answer]  # the echo was never spoken; the retry was
    assert brain._history[ch][-1]["content"] == answer


def test_streaming_double_echo_is_suppressed_nothing_spoken_or_stored() -> None:
    client = _EchoStreamClient(always_echo=True)
    brain = DMBrain(client)
    ch = 1
    spoken: list[str] = []

    async def on_sentence(s: str) -> None:
        spoken.append(s)

    brain.add_player_line(ch, "Pr0degie", "Ich greife den Kultisten an.")
    answer = asyncio.run(brain.respond_streaming(ch, on_sentence=on_sentence))
    assert answer == ""
    assert spoken == []
    assert brain._history.get(ch, []) == []


# --- results-only turns carry the narrate-the-consequence directive -------------------------------

class _CaptureClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] | None = None

    async def chat(self, system, messages, options=None):
        self.messages = messages
        return "Der Kultist taumelt getroffen zurück."

    async def aclose(self) -> None:
        pass


def test_results_only_turn_appends_the_roll_directive() -> None:
    client = _CaptureClient()
    brain = DMBrain(client)
    ch = 1
    brain.add_test_result(ch, "🎲 Mortn auf Nahkampf, Herausfordernd (Ziel 45): 12 — Erfolg, 3 EG.")
    asyncio.run(brain.respond(ch))
    user_msg = client.messages[-1]["content"]
    assert user_msg.startswith("[Würfel]")
    assert user_msg.endswith(_ROLL_DIRECTIVE)


def test_turn_with_player_lines_has_no_roll_directive() -> None:
    client = _CaptureClient()
    brain = DMBrain(client)
    ch = 1
    brain.add_test_result(ch, "🎲 Nahkampf: 12 — Erfolg.")
    brain.add_player_line(ch, "Timo", "Ich ducke mich hinter die Kiste.")
    asyncio.run(brain.respond(ch))
    assert _ROLL_DIRECTIVE not in client.messages[-1]["content"]


# --- restore filter: persisted junk turns aren't re-taught -----------------------------------------

def test_restore_history_skips_empty_answers() -> None:
    brain = DMBrain(object())
    restored = brain.restore_history(7, [
        ("Pr0degie: Ich greife an.", ""),  # marker-only/suppressed turn — must not be re-taught
        ("Timo: Ich schaue mich um.", "Der Gang liegt still vor euch."),
    ])
    assert restored == 1
    history = brain._history[7]
    assert len(history) == 2
    assert history[0]["content"] == "Timo: Ich schaue mich um."
