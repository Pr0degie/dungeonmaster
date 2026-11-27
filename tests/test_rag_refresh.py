"""Retrieval before a narration call (``DMBrain._refresh_rag``): a turn with a player line is
looked up and timed, a turn without one is not, and the embedder stays loaded between turns."""

from __future__ import annotations

import asyncio
import logging

from dmbot.rag.retrieve import EMBED_KEEP_ALIVE, RulebookRetriever
from dmbot.turn_timing import _TurnTiming

from tests.fakes import FakeLLMClient, make_brain

_CID = 1


class _Retriever:
    """Records each lookup and answers with the next scripted block."""

    def __init__(self, *blocks: str) -> None:
        self.blocks = list(blocks)
        self.queries: list[tuple[str, int | None]] = []

    async def fetch_block(self, query: str, *, channel_id: int | None = None) -> str:
        self.queries.append((query, channel_id))
        return self.blocks.pop(0) if self.blocks else ""


def _brain(retriever: _Retriever, *replies: str):
    return make_brain(client=FakeLLMClient(replies), _retriever=retriever)


def test_a_player_line_is_looked_up_and_timed() -> None:
    retriever = _Retriever("## Regelwerk\n[Quelle: Tests]\nRoll under the target.")
    brain = _brain(retriever, "Die Wache sieht nicht auf.")
    brain.add_player_line(_CID, "Castor", "Wie funktioniert eine Probe auf Heimlichkeit?")

    asyncio.run(brain.respond(_CID))

    assert retriever.queries == [("Castor: Wie funktioniert eine Probe auf Heimlichkeit?", _CID)]
    assert "## Regelwerk" in brain._client.calls[0]["system"]
    assert isinstance(brain.last_rag_ms, int)


def test_a_dice_result_alone_is_not_looked_up_and_drops_the_block_of_the_turn_before() -> None:
    retriever = _Retriever("## Regelwerk\n[Quelle: Tests]\nRoll under the target.")
    brain = _brain(retriever, "Die Wache sieht nicht auf.", "Du gleitest an ihr vorbei.")
    brain.add_player_line(_CID, "Castor", "Ich schleiche an der Wache vorbei.")
    asyncio.run(brain.respond(_CID))

    brain.add_test_result(_CID, "🎲 Castor auf Heimlichkeit (Ziel 45): 23 — Erfolg, 2 EG.")
    asyncio.run(brain.respond(_CID))

    assert len(retriever.queries) == 1  # the player turn only
    assert "## Regelwerk" not in brain._client.calls[1]["system"]
    assert brain.last_rag_ms is None


def test_a_dice_result_next_to_a_player_line_is_looked_up() -> None:
    retriever = _Retriever()
    brain = _brain(retriever, "Die Tür gibt nach.")
    brain.add_test_result(_CID, "🎲 Castor auf Athletik (Ziel 40): 12 — Erfolg, 3 EG.")
    brain.add_player_line(_CID, "Mortn", "Ich folge ihm durch die Tür.")

    asyncio.run(brain.respond(_CID))

    assert len(retriever.queries) == 1
    assert "Mortn: Ich folge ihm durch die Tür." in retriever.queries[0][0]


def test_a_redo_looks_the_player_line_up_again() -> None:
    retriever = _Retriever()
    brain = _brain(retriever, "Die Wache sieht nicht auf.", "Die Wache hebt den Kopf.")
    brain.add_player_line(_CID, "Castor", "Ich schleiche an der Wache vorbei.")
    asyncio.run(brain.respond(_CID))

    asyncio.run(brain.redo(_CID))

    assert [query for query, _ in retriever.queries] == ["Castor: Ich schleiche an der Wache vorbei."] * 2


def _line(timing: _TurnTiming, caplog) -> str:
    with caplog.at_level(logging.INFO, logger="dmbot.turn_timing"):
        timing.log_line()
    return caplog.records[0].getMessage()


def test_the_latency_line_names_the_lookup_before_the_llm_stage(caplog) -> None:
    timing = _TurnTiming(turn=3, trigger=10.0, llm_done=12.5, end=20.0, queued_ms=40)
    timing.take_llm_stats({"prompt_eval_count": 9000, "eval_count": 180}, rag_ms=85)

    assert "queued=40ms rag=85ms trigger→llm_done=2500ms" in _line(timing, caplog)


def test_the_latency_line_of_a_turn_without_a_lookup_is_unchanged(caplog) -> None:
    timing = _TurnTiming(turn=3, trigger=10.0, llm_done=12.5, end=20.0)
    timing.take_llm_stats({"prompt_eval_count": 9000, "eval_count": 180})

    assert "rag=" not in _line(timing, caplog)


def test_the_embed_call_keeps_the_embedder_loaded(tmp_path) -> None:
    sent: list[dict] = []

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"embeddings": [[1.0, 0.0]]}

    class _Client:
        async def post(self, url: str, *, json: dict) -> _Response:
            sent.append(json)
            return _Response()

    retriever = RulebookRetriever(tmp_path / "rag.db", "http://unused")
    retriever._client = _Client()  # type: ignore[assignment]
    retriever._model = "bge-m3"  # skip the meta-table read: there is no store here

    assert asyncio.run(retriever._embed_query("Wie funktioniert eine Probe?")) == [1.0, 0.0]
    assert sent == [{"model": "bge-m3", "input": ["Wie funktioniert eine Probe?"],
                     "keep_alive": EMBED_KEEP_ALIVE}]
