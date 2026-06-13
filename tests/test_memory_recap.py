"""Recap generation + memory context injection (Phase 9). The LLM is faked — we assert the prompt
wiring (recap + world-state block land in the system prompt) and that the recap round-trips through
the summariser, not the model's prose quality (that's the live gate).
"""

from __future__ import annotations

import asyncio

from dmbot.memory.recap import build_recap_user
from dmbot.orchestrator import DMBrain


class _CapClient:
    """Captures the system prompt DMBrain builds; returns a canned answer. No real Ollama."""

    def __init__(self, answer: str = "Eine Antwort.") -> None:
        self.answer = answer
        self.system: str | None = None

    async def chat(self, system, messages, options=None, format=None) -> str:
        self.system = system
        return self.answer

    async def aclose(self) -> None:
        pass


def test_set_context_injects_recap_and_state_into_system_prompt() -> None:
    client = _CapClient()
    brain = DMBrain(client)
    ch = 5
    brain.set_context(
        ch,
        recap="Die Gruppe stieg in die Unterstadt.",
        state_summary="## Weltzustand\nOrt: Hive Primus\nGruppe: Seskin 7/11 (verwundet)",
    )
    brain.add_player_line(ch, "Timo", "Wir gehen weiter.")
    asyncio.run(brain.respond(ch))

    assert "Was bisher geschah" in client.system
    assert "Die Gruppe stieg in die Unterstadt." in client.system
    assert "Hive Primus" in client.system and "Seskin 7/11" in client.system


def test_set_context_empty_clears_injection() -> None:
    client = _CapClient()
    brain = DMBrain(client)
    ch = 6
    brain.set_context(ch, recap="Etwas", state_summary="Irgendwas")
    brain.set_context(ch, recap="", state_summary="")  # clear
    brain.add_player_line(ch, "Timo", "Hallo.")
    asyncio.run(brain.respond(ch))
    assert "Was bisher geschah" not in client.system


def test_summarize_returns_recap_from_history() -> None:
    client = _CapClient(answer="Die Gruppe betrat die Kapelle und floh vor dem Kultisten.")
    brain = DMBrain(client)
    ch = 7
    brain.add_player_line(ch, "Timo", "Wir betreten die Kapelle.")
    asyncio.run(brain.respond(ch))  # populate history
    recap = asyncio.run(brain.summarize(ch))
    assert recap is not None and "Kapelle" in recap


def test_summarize_empty_history_returns_none() -> None:
    assert asyncio.run(DMBrain(_CapClient()).summarize(404)) is None


class _CapUserClient(_CapClient):
    """Also captures the user message (the rulebook context + question for !rules <frage>)."""

    def __init__(self, answer: str = "Eine Regelauskunft.") -> None:
        super().__init__(answer)
        self.user: str | None = None

    async def chat(self, system, messages, options=None, format=None) -> str:
        self.user = messages[-1]["content"] if messages else None
        return await super().chat(system, messages, options=options, format=format)


def test_answer_rules_grounds_prompt_in_context_and_question() -> None:
    client = _CapUserClient(answer="Du würfelst 1W100 unter deinem Wert.")
    brain = DMBrain(client)
    answer = asyncio.run(brain.answer_rules(
        "Wie würfle ich eine Probe?",
        "[TESTS]\nRoll 1d100 under your skill.",
        system_name="Imperium Maledictum",
    ))
    assert answer == "Du würfelst 1W100 unter deinem Wert."
    assert "Imperium Maledictum" in client.system        # system name reaches the prompt
    assert "erfinde keine regeln" in client.system.lower()  # the no-hallucination guard
    assert "Roll 1d100 under your skill." in client.user  # the retrieved chunk is the grounding
    assert "Wie würfle ich eine Probe?" in client.user


def test_answer_rules_strips_markdown_and_empty_is_none() -> None:
    assert asyncio.run(DMBrain(_CapUserClient(answer="  *Fett*  ")).answer_rules(
        "x", "ctx", system_name="IM")) == "Fett"
    assert asyncio.run(DMBrain(_CapUserClient(answer="   ")).answer_rules(
        "x", "ctx", system_name="IM")) is None


def test_build_recap_user_renders_history_and_skips_empty() -> None:
    history = [
        {"role": "user", "content": "Timo: Wir öffnen die Tür."},
        {"role": "assistant", "content": "Die Tür schwingt auf."},
        {"role": "user", "content": ""},  # empty → skipped
    ]
    out = build_recap_user(history)
    assert "Spieler: Timo: Wir öffnen die Tür." in out
    assert "Spielleitung: Die Tür schwingt auf." in out
