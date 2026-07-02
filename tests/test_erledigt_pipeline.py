"""<<ERLEDIGT>> through the DMBrain (ADR 043): requests are queued per channel under the same
post-roll guard as <<ORT>> (only turns that answered a player action), drained exactly once, and
cleared on redo — no Discord, fake LLM client."""

from __future__ import annotations

import asyncio

from dmbot.orchestrator import DMBrain


class _C:
    """Fake Ollama client: returns a scripted answer per call."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)

    async def chat(self, system, messages, options=None):
        return self._answers.pop(0)

    async def aclose(self) -> None:
        pass


def test_erledigt_requests_are_queued_and_drained_once() -> None:
    brain = DMBrain(_C(["Ihr öffnet die Kiste. <<ERLEDIGT opp-1>> <<ERLEDIGT geh-1>>"]))
    ch = 1
    brain.add_player_line(ch, "Timo", "Wir öffnen die Kiste.")
    answer = asyncio.run(brain.respond(ch))
    assert "<<" not in answer
    reqs = brain.take_pending_erledigt(ch)
    assert [r.element_id for r in reqs] == ["opp-1", "geh-1"]  # ALL markers, order preserved
    assert brain.take_pending_erledigt(ch) == []  # drained exactly once


def test_erledigt_suppressed_on_results_only_turn() -> None:
    # A post-roll consequence turn (no player action) must not queue flags — same guard as <<ORT>>.
    brain = DMBrain(_C(["Der Schlag sitzt. <<ERLEDIGT opp-1>>"]))
    ch = 1
    brain.add_test_result(ch, "Timo: Kampf → Erfolg (SL 2)")
    answer = asyncio.run(brain.respond(ch))
    assert "<<" not in answer  # still stripped from the spoken text …
    assert brain.take_pending_erledigt(ch) == []  # … but never queued


def test_redo_clears_pending_erledigt() -> None:
    brain = DMBrain(_C([
        "Ihr schafft es. <<ERLEDIGT opp-1>>",
        "Nochmal anders erzählt.",
    ]))
    ch = 1
    brain.add_player_line(ch, "Timo", "Wir versuchen es.")
    asyncio.run(brain.respond(ch))
    asyncio.run(brain.redo(ch))  # the redo supersedes the old turn's markers
    assert brain.take_pending_erledigt(ch) == []
