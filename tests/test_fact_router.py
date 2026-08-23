"""Commitment classifier (ADR 058) — the contract of the post-turn call that turns what the
narration promised into a *validated* request for the world state.

The model never writes state (golden rule #3): it picks from a closed enumeration, and everything
here asserts that code is what decides. The write itself is
``WorldState.record_commitment(kind, **commitment.record_kwargs())`` — not under test, its input is.
Degenerate answers (off-enum kind, prose instead of a label, unknown recipient, empty, broken JSON,
timeout, transport error) must all leave the state untouched without raising.
"""

import asyncio

from dmbot.llm.fact_router import (
    COMMITMENT_KINDS,
    FACT_ROUTER_OPTIONS,
    NO_COMMITMENT,
    Commitment,
    FactFailure,
    classify_commitment,
    fact_schema,
    fact_system,
    to_fact_verdict,
)
from dmbot.memory.state import FACT_TEXT_MAX, GROUP_HOLDER

WHO = ["Seskin", "Fridolin", GROUP_HOLDER]
NPCS = ["Seneschall Kaad", "Vall"]


class _Chat:
    """Stand-in for ``LLMClient.chat``: records the call, returns a canned answer or raises."""

    def __init__(self, answer: str = "", raises: BaseException | None = None, delay: float = 0.0):
        self.answer, self.raises, self.delay = answer, raises, delay
        self.calls: list[dict] = []

    async def __call__(self, system, messages, *, options=None, format=None):
        self.calls.append(
            {"system": system, "messages": messages, "options": options, "format": format}
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        return self.answer


def _v(art="item", sache="Zollvollmacht", an="Seskin", von="Seneschall Kaad"):
    return {"art": art, "sache": sache, "an": an, "von": von}


# --- pure helpers -----------------------------------------------------------------------------

def test_schema_closes_kind_recipient_and_source():
    s = fact_schema(WHO, NPCS)
    assert s["properties"]["art"]["enum"] == [*COMMITMENT_KINDS, NO_COMMITMENT]
    assert s["properties"]["an"]["enum"] == [*WHO, ""]
    assert s["properties"]["von"]["enum"] == [*NPCS, ""]
    assert set(s["required"]) == {"art", "sache", "an", "von"}


def test_system_prompt_names_the_kinds_the_people_and_the_label_limit():
    sys = fact_system(WHO, NPCS)
    for kind in (*COMMITMENT_KINDS, NO_COMMITMENT):
        assert kind in sys
    assert "Seskin" in sys and "Seneschall Kaad" in sys
    assert str(FACT_TEXT_MAX) in sys and "JSON" in sys


def test_a_handed_over_item_becomes_a_validated_commitment():
    v = to_fact_verdict(_v(), recipients=WHO, givers=NPCS)
    assert v.failure is None
    assert v.commitment == Commitment(kind="item", text="Zollvollmacht", to="Seskin",
                                      by="Seneschall Kaad")
    assert v.commitment.record_kwargs() == {
        "text": "Zollvollmacht", "to": "Seskin", "by": "Seneschall Kaad"
    }


def test_quest_and_promise_are_the_other_two_kinds():
    q = to_fact_verdict(_v(art="quest", sache="Ossarium zurückholen", an="", von="Seneschall Kaad"),
                        recipients=WHO, givers=NPCS)
    assert q.commitment is not None and q.commitment.kind == "quest"
    p = to_fact_verdict(_v(art="promise", sache="Freies Geleit am Kai", an=GROUP_HOLDER, von="Vall"),
                        recipients=WHO, givers=NPCS)
    assert p.commitment is not None and p.commitment.kind == "promise"
    assert p.commitment.to == GROUP_HOLDER


def test_nothing_happened_is_a_clean_verdict_not_a_failure():
    v = to_fact_verdict(_v(art=NO_COMMITMENT, sache="", an="", von=""),
                        recipients=WHO, givers=NPCS)
    assert v.commitment is None and v.failure is None


def test_a_missing_recipient_falls_back_to_the_party():
    v = to_fact_verdict(_v(an=""), recipients=WHO, givers=NPCS)
    assert v.commitment is not None and v.commitment.to == GROUP_HOLDER


def test_case_and_whitespace_resolve_to_the_canonical_names():
    v = to_fact_verdict(_v(an="  seskin ", von="seneschall kaad"), recipients=WHO, givers=NPCS)
    assert v.commitment is not None
    assert v.commitment.to == "Seskin" and v.commitment.by == "Seneschall Kaad"


def test_an_unknown_recipient_rejects_the_whole_verdict():
    v = to_fact_verdict(_v(an="Ein Laufbursche"), recipients=WHO, givers=NPCS)
    assert v.commitment is None and v.failure is FactFailure.UNKNOWN_RECIPIENT


def test_an_unknown_source_is_dropped_but_keeps_the_fact():
    # the giver is provenance only — clamp, don't reject (docs/lessons/llm-requests-code-validates)
    v = to_fact_verdict(_v(von="Irgendwer"), recipients=WHO, givers=NPCS)
    assert v.commitment is not None and v.commitment.by == "" and v.failure is None


def test_prose_instead_of_a_label_changes_nothing():
    prose = "Kaad reicht ihm mit spitzen Fingern die Vollmacht,\nals wäre sie ansteckend."
    assert to_fact_verdict(_v(sache=prose), recipients=WHO,
                           givers=NPCS).failure is FactFailure.BAD_TEXT
    assert to_fact_verdict(_v(sache="x" * (FACT_TEXT_MAX + 1)), recipients=WHO,
                           givers=NPCS).failure is FactFailure.BAD_TEXT
    assert to_fact_verdict(_v(sache="   "), recipients=WHO,
                           givers=NPCS).failure is FactFailure.BAD_TEXT


def test_the_label_gate_is_the_writers_own_gate(monkeypatch):
    """One implementation, not two (docs/lessons/parity-by-construction.md): the classifier's
    gate delegates to ``memory.state._validated_fact_text``, so a change to the writer's limit
    can't leave a second copy behind."""
    import dmbot.llm.fact_router as fr

    seen: list[str] = []

    def _gate(value: str) -> str | None:
        seen.append(value)
        return "GEPRÜFT"

    monkeypatch.setattr(fr, "_validated_fact_text", _gate)
    assert fr.validated_label("  Zollvollmacht  ") == "GEPRÜFT"
    assert seen == ["  Zollvollmacht  "]
    # a non-string out of the model JSON is discarded here, never coerced into a label
    assert fr.validated_label(42) is None and fr.validated_label(None) is None
    assert seen == ["  Zollvollmacht  "]


def test_a_kind_outside_the_enumeration_changes_nothing():
    for art in ("gold", "npc_tot", "quest_completed", "Gegenstand"):
        v = to_fact_verdict(_v(art=art), recipients=WHO, givers=NPCS)
        assert v.commitment is None and v.failure is FactFailure.OFF_LIST
    # …but harmless whitespace/casing around a valid kind is not an off-list answer
    assert to_fact_verdict(_v(art=" Item "), recipients=WHO, givers=NPCS).failure is None


def test_empty_and_malformed_verdicts_change_nothing():
    assert to_fact_verdict(_v(art=""), recipients=WHO, givers=NPCS).failure is FactFailure.EMPTY
    assert to_fact_verdict({}, recipients=WHO, givers=NPCS).failure is FactFailure.BAD_JSON
    assert to_fact_verdict("item", recipients=WHO, givers=NPCS).failure is FactFailure.BAD_JSON
    assert to_fact_verdict(None, recipients=WHO, givers=NPCS).failure is FactFailure.BAD_JSON
    assert to_fact_verdict({"art": ["item"]}, recipients=WHO,
                           givers=NPCS).failure is FactFailure.BAD_JSON


# --- the call ---------------------------------------------------------------------------------

def test_call_pins_its_own_sampling_and_the_constrained_schema():
    chat = _Chat('{"art":"item","sache":"Zollvollmacht","an":"Seskin","von":"Seneschall Kaad"}')
    v = asyncio.run(classify_commitment(
        chat, answer_text="Kaad schiebt Seskin die Zollvollmacht über den Tisch.",
        recipients=WHO, givers=NPCS,
    ))
    assert v.commitment is not None and v.commitment.text == "Zollvollmacht"
    assert v.raw == chat.answer
    call = chat.calls[0]
    assert call["format"] == fact_schema(WHO, NPCS)
    # sampling pinned at the call site, never inherited (docs/lessons/sampling-defaults-...)
    assert call["options"] == FACT_ROUTER_OPTIONS
    assert call["options"]["temperature"] == 0
    assert call["options"]["repeat_penalty"] == 1.0 and call["options"]["repeat_last_n"] == 0
    assert "Zollvollmacht über den Tisch" in call["messages"][0]["content"]


def test_broken_json_changes_nothing_and_keeps_the_raw_answer():
    chat = _Chat('{"art":"item","sache":')
    v = asyncio.run(classify_commitment(chat, answer_text="egal", recipients=WHO, givers=NPCS))
    assert v.commitment is None and v.failure is FactFailure.BAD_JSON and v.raw == chat.answer


def test_an_empty_answer_changes_nothing():
    v = asyncio.run(classify_commitment(_Chat(" "), answer_text="egal",
                                        recipients=WHO, givers=NPCS))
    assert v.commitment is None and v.failure is FactFailure.EMPTY


def test_a_timeout_never_reaches_the_table():
    chat = _Chat("", raises=TimeoutError())
    v = asyncio.run(classify_commitment(chat, answer_text="egal", recipients=WHO, givers=NPCS))
    assert v.commitment is None and v.failure is FactFailure.TIMEOUT


def test_a_slow_model_is_cut_off_by_the_deadline():
    chat = _Chat('{"art":"item","sache":"Zollvollmacht","an":"Seskin","von":""}', delay=5.0)
    v = asyncio.run(classify_commitment(chat, answer_text="egal", recipients=WHO, givers=NPCS,
                                        timeout=0.01))
    assert v.commitment is None and v.failure is FactFailure.TIMEOUT


def test_a_transport_error_changes_nothing():
    chat = _Chat("", raises=RuntimeError("ollama down"))
    v = asyncio.run(classify_commitment(chat, answer_text="egal", recipients=WHO, givers=NPCS))
    assert v.commitment is None and v.failure is FactFailure.CALL_FAILED


def test_no_answer_text_skips_the_call_entirely():
    chat = _Chat('{"art":"item","sache":"Zollvollmacht","an":"Seskin","von":""}')
    v = asyncio.run(classify_commitment(chat, answer_text="  ", recipients=WHO, givers=NPCS))
    assert v.failure is FactFailure.NO_INPUT and not chat.calls


def test_the_party_is_always_a_valid_recipient_even_with_an_empty_roster():
    chat = _Chat('{"art":"promise","sache":"Freies Geleit","an":"Gruppe","von":""}')
    v = asyncio.run(classify_commitment(chat, answer_text="Vall verspricht freies Geleit.",
                                        recipients=[], givers=[]))
    assert v.commitment is not None and v.commitment.to == GROUP_HOLDER
    assert chat.calls[0]["format"]["properties"]["an"]["enum"] == [GROUP_HOLDER, ""]
