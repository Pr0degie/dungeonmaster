"""Streaming pipeline (ADR 017): the sentence accumulator/emitter + the brain's streaming turn.

The whole point is to verify, without Discord or Ollama, that streaming a turn produces the *same*
stored answer as the batch path (history parity) while never speaking the bits the sanitizers drop
(leading meta-preamble, a trailing 'Was tut ihr?', dice markers, a puppeted speaker label, a
mid-sentence num_predict cut). Plus the tiny NDJSON line parser and the degrade-on-error path.
"""

from __future__ import annotations

import asyncio

import httpx

from dmbot.llm.client import _parse_stream_line
from dmbot.orchestrator import (
    DMBrain,
    StreamAssembler,
    _ROLE_LABELS,
    finalize_answer,
)
from dmbot.rules import profile as profile_mod

_IM = profile_mod.load("imperium_maledictum")
LABELS = ["Timo", "Seskin", "Pr0degie", *_ROLE_LABELS]


def _norm(text: str) -> str:
    return " ".join(text.split())


def _run(deltas, labels=LABELS, profile=None):
    """Feed ``deltas`` to a StreamAssembler; return (spoken sentences, finish result, assembler)."""
    a = StreamAssembler(labels, profile)
    spoken: list[str] = []
    for d in deltas:
        spoken.extend(a.feed(d))
        if a.stopped:
            break
    res = a.finish()
    spoken.extend(res.remaining)
    return spoken, res, a


# --- the NDJSON line parser ---------------------------------------------------------------------

def test_parse_stream_line_delta():
    delta, final = _parse_stream_line('{"message":{"content":"Hallo"},"done":false}')
    assert delta == "Hallo" and final is None


def test_parse_stream_line_final_carries_counts():
    delta, final = _parse_stream_line(
        '{"message":{"content":""},"done":true,"prompt_eval_count":120,"eval_count":42}'
    )
    assert delta == ""
    assert final == {"prompt_eval_count": 120, "eval_count": 42}


def test_parse_stream_line_blank_or_garbage():
    assert _parse_stream_line("") == ("", None)
    assert _parse_stream_line("   ") == ("", None)
    assert _parse_stream_line("not json") == ("", None)


# --- the assembler's hold-back rules ------------------------------------------------------------

def test_meta_preamble_in_first_chunk_is_never_spoken():
    deltas = [
        "Als Spielleitung beschreibe ich: Die Gasse ist dunkel.",
        " Ein Schatten regt sich.",
        " Es ist kalt.",
    ]
    spoken, res, _ = _run(deltas)
    joined = " ".join(spoken)
    assert "Als Spielleitung" not in joined
    assert "Als Spielleitung" not in res.answer
    assert spoken[0].startswith("Die Gasse ist dunkel")


def test_trailing_prompt_split_across_last_deltas_is_held_and_stripped():
    deltas = ["Die Tür ist verschlossen. Es zieht kalt.", " Was tut", " ihr?"]
    spoken, res, _ = _run(deltas)
    joined = " ".join(spoken)
    assert "Was tut ihr" not in joined  # held back, then stripped — never spoken
    assert "Was tut ihr" not in res.answer


def test_marker_split_across_a_boundary_is_extracted_not_spoken():
    deltas = ["Du schleichst zur Tür. <<TEST Heim", "lichkeit Schwer für Timo>> Der Gang ist still."]
    spoken, res, _ = _run(deltas, profile=_IM)
    joined = " ".join(spoken)
    assert "<<" not in joined and "TEST" not in joined  # no partial/whole marker ever spoken
    assert "<<" not in res.answer
    assert res.tests and res.tests[0].skill == "Heimlichkeit"
    assert res.tests[0].target_name == "Timo"


def test_stop_label_mid_stream_truncates_and_signals_stop():
    deltas = ["Du schlägst zu.", "\nSeskin: Ich helfe dir!"]
    spoken, res, assembler = _run(deltas)
    joined = " ".join(spoken)
    assert assembler.stopped is True
    assert "Seskin" not in joined and "Ich helfe" not in joined
    assert "Ich helfe" not in res.answer


def test_stream_ending_mid_sentence_drops_the_dangling_fragment():
    deltas = ["Der Raum ist groß. Eine Lampe flackert. Plötzlich"]
    spoken, res, _ = _run(deltas)
    joined = " ".join(spoken)
    assert "Plötzlich" not in joined
    assert res.answer.endswith("flackert.")


def test_history_parity_with_the_batch_sanitizer_chain():
    cases = [
        ["Als Spielleitung beschreibe ich: Die Gasse ist dunkel.", " Ein Schatten regt sich.", " Es ist kalt."],
        ["Die Tür ist verschlossen. Es zieht kalt.", " Was tut", " ihr?"],
        ["Du schleichst zur Tür. <<TEST Heim", "lichkeit Schwer für Timo>> Der Gang ist still."],
        ["Der Raum ist groß. Eine Lampe flackert. Plötzlich"],
        ["Du schlägst zu.", "\nSeskin: Ich helfe dir!"],
    ]
    for deltas in cases:
        spoken, res, _ = _run(deltas, profile=_IM)
        raw = "".join(deltas)
        expected, _tests = finalize_answer(raw, LABELS, _IM)
        # the stored answer is byte-identical to the batch path on the same raw text
        assert res.answer == expected
        # and the concatenation of what was spoken equals the stored answer (modulo whitespace)
        assert _norm(" ".join(spoken)) == _norm(res.answer)


# --- the brain's streaming turn -----------------------------------------------------------------

class _FakeStreamClient:
    """An OllamaClient stand-in whose chat_stream yields the given deltas (chat returns the join)."""

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas
        self.last_stats = {"prompt_eval_count": 10, "eval_count": 5, "num_ctx": 8192}

    async def chat_stream(self, system, messages, *, options=None):
        for d in self._deltas:
            yield d

    async def chat(self, system, messages, *, options=None, format=None):
        return "".join(self._deltas)

    async def aclose(self) -> None:
        pass


def test_respond_streaming_stores_the_canonical_answer_and_speaks_it():
    deltas = ["Du öffnest die Tür. ", "Es ist dunkel. ", "Ein Geräusch. Was tut ihr?"]
    brain = DMBrain(_FakeStreamClient(deltas))
    ch = 1
    brain.add_player_line(ch, "Timo", "Ich öffne die Tür.")
    spoken: list[str] = []

    async def on_s(s):
        spoken.append(s)

    answer = asyncio.run(brain.respond_streaming(ch, on_sentence=on_s))
    raw = "".join(deltas)
    expected, _ = finalize_answer(raw, ["Timo", *_ROLE_LABELS], None)
    assert answer == expected  # the trailing "Was tut ihr?" is stripped
    assert brain._history[ch][-1]["content"] == answer  # stored == returned
    assert _norm(" ".join(spoken)) == _norm(answer)  # spoken == stored
    assert brain.last_llm_stats == {"prompt_eval_count": 10, "eval_count": 5, "num_ctx": 8192}


def test_streaming_marker_only_turn_speaks_nothing_but_requests_a_test():
    # the live failure (2026-06-10): the model streamed ONLY a backticked marker. Nothing speakable
    # must be emitted (no 15 s lone-quote), but the dice request still surfaces.
    brain = DMBrain(_FakeStreamClient(["`<<TEST Kampf für Timo>>`"]), profile=_IM)
    ch = 1
    brain.add_player_line(ch, "Timo", "Ich greife den Kultisten an.")
    spoken: list[str] = []

    async def on_s(s):
        spoken.append(s)

    answer = asyncio.run(brain.respond_streaming(ch, on_sentence=on_s))
    assert answer == ""  # nothing speakable left after stripping the fenced marker
    assert spoken == []  # and nothing was handed to TTS
    tests = brain.take_pending_tests(ch)
    assert tests and tests[0].skill == "Kampf"  # the dice button still gets posted by the cog


class _SeqStreamClient:
    """Yields a different one-sentence answer on each chat_stream call (for the redo test)."""

    def __init__(self) -> None:
        self._calls = 0
        self.last_stats = None

    async def chat_stream(self, system, messages, *, options=None):
        self._calls += 1
        yield f"Antwort {self._calls}."

    async def aclose(self) -> None:
        pass


def test_redo_streaming_replaces_the_last_turn_without_stacking():
    brain = DMBrain(_SeqStreamClient())
    ch = 1
    brain.add_player_line(ch, "Timo", "Ich öffne die Tür.")

    async def noop(s):
        pass

    a1 = asyncio.run(brain.respond_streaming(ch, on_sentence=noop))
    n = len(brain._history[ch])
    a2 = asyncio.run(brain.redo_streaming(ch, on_sentence=noop))
    assert a1 == "Antwort 1." and a2 == "Antwort 2."
    assert len(brain._history[ch]) == n  # replaced, not stacked
    assert brain._history[ch][-1]["content"] == "Antwort 2."
    assert brain._history[ch][-2]["content"] == "Timo: Ich öffne die Tür."


class _DyingStreamClient:
    """Yields two sentences then raises mid-stream (a dropped Ollama connection)."""

    def __init__(self) -> None:
        self.last_stats = None

    async def chat_stream(self, system, messages, *, options=None):
        yield "Du öffnest die Tür. "
        yield "Es ist dunkel. "
        raise httpx.ConnectError("boom")

    async def aclose(self) -> None:
        pass


def test_stream_dies_mid_turn_keeps_partial_and_notes_history():
    brain = DMBrain(_DyingStreamClient())
    ch = 1
    brain.add_player_line(ch, "Timo", "Ich öffne die Tür.")
    spoken: list[str] = []

    async def on_s(s):
        spoken.append(s)

    answer = asyncio.run(brain.respond_streaming(ch, on_sentence=on_s))  # must NOT raise
    assert "Du öffnest die Tür" in answer
    stored = brain._history[ch][-1]["content"]
    assert "[Antwort unterbrochen]" in stored  # the marker note lives in history, not the spoken text
    assert "[Antwort unterbrochen]" not in " ".join(spoken)
