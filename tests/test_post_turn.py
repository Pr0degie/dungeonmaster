"""The combined post-turn classifier call (ADR 066, option B).

What is pinned here: the combined prompt is built from the separate classifiers' own question
texts (parity by construction), each part of a combined answer goes through its own validator and
journals its own part, a failed or malformed combined answer hands its questions back to the
separate calls in the same turn, and only the hook — never a call site — decides that a turn is
combined (Claude answering, ``DM_AUX_COMBINED=1``). Fake chat only; no model.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from dmbot.llm import post_turn_combined
from dmbot.llm.failover import FailoverClient
from dmbot.llm.fact_router import FactFailure, fact_question, fact_system
from dmbot.llm.npc_router import Candidate, NpcFailure, npc_question, npc_system
from dmbot.llm.post_turn import (
    CombinedFailure,
    classify_post_turn,
    combined_schema,
    combined_system,
    combined_user_msg,
)
from dmbot.llm.scene_router import SceneFailure, scene_question, scene_system

from fakes import FakeBrain, FakeLLMClient, make_config

ANSWER = "Fridolin tritt in den Schrein. Eine alte Schwester fährt herum."

SCENE = {"turn_text": ANSWER, "exits": {"schrein": "Schrein der Aschenheiligen"},
         "current_title": "Die Zoll-Sakristei", "context": "Fridolin: Geh rein!"}
FACT = {"answer_text": ANSWER, "recipients": ["Fridolin"], "givers": ["Seneschall Kaad"]}
NPC = {"answer_text": ANSWER, "party": ["Fridolin"], "roster": ["Schwester Vall"],
       "present": ["Seneschall Kaad"],
       "candidates": [Candidate("Schwester Vall", "Schreinschwester", ("Vall",))]}

FULL = {"ziel": "schrein", "art": "nichts", "sache": "", "an": "", "von": "",
        "npcs": [{"label": "Schreinschwester", "statblock": "Schwester Vall"}]}


class _Chat:
    """A chat coroutine with scripted answers (an exception is raised) and recorded calls."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    async def __call__(self, system, messages, *, options=None, format=None):
        self.calls.append({"system": system, "messages": messages, "options": options,
                           "format": format})
        answer = self.answers.pop(0) if self.answers else ""
        if isinstance(answer, BaseException):
            raise answer
        return answer


def _run(coro):
    return asyncio.run(coro)


# ---- one text per question ------------------------------------------------------------------


def test_the_separate_prompts_are_role_plus_the_shared_question_plus_the_json_line() -> None:
    assert scene_system(SCENE["exits"], current_title="Zoll") == (
        "Du bist der Regel-Assistent der Spielleitung eines Rollenspiels.\n"
        + scene_question(SCENE["exits"], current_title="Zoll")
        + 'Antworte NUR mit JSON: {"ziel": "<id>"} oder {"ziel": "nein"}.')
    assert fact_system(["Fridolin"], ["Kaad"]) == (
        "Du bist der Protokollant der Spielleitung eines Rollenspiels.\n"
        + fact_question(["Fridolin"], ["Kaad"]) + " Antworte NUR mit JSON.")
    kwargs = {k: NPC[k] for k in ("party", "roster", "present", "candidates")}
    assert npc_system(**kwargs) == npc_question(**kwargs) + " Antworte NUR mit JSON."


def test_the_combined_prompt_carries_each_question_verbatim_in_order() -> None:
    system = combined_system(scene=SCENE, fact=FACT, npc=NPC)
    texts = [
        scene_question(SCENE["exits"], current_title=SCENE["current_title"]).rstrip(),
        fact_question(FACT["recipients"], FACT["givers"]).rstrip(),
        npc_question(party=NPC["party"], roster=NPC["roster"], present=NPC["present"],
                     candidates=NPC["candidates"]).rstrip(),
    ]
    positions = [system.index(t) for t in texts]
    assert positions == sorted(positions)
    assert "Frage 1 — Ortswechsel" in system and "Frage 3 — neue Personen" in system
    assert system.endswith("(ziel, art, sache, an, von, npcs).")


def test_the_combined_schema_is_the_three_schemas_side_by_side() -> None:
    schema = combined_schema(scene=SCENE, fact=FACT, npc=NPC)
    # The [aux] line's fields= is the property names joined — its own value for this call.
    assert ",".join(schema["properties"]) == "ziel,art,sache,an,von,npcs"
    assert schema["required"] == ["ziel", "art", "sache", "an", "von", "npcs"]
    assert schema["properties"]["ziel"]["enum"] == ["schrein", "nein"]


def test_the_context_rides_only_with_the_scene_question_and_is_marked_as_its_own() -> None:
    with_scene = combined_user_msg(ANSWER, "Fridolin: Geh rein!", with_scene=True)
    assert with_scene.index("Fridolin: Geh rein!") < with_scene.index(ANSWER)
    assert "nur zur Einordnung für Frage 1" in with_scene
    assert "Geh rein" not in combined_user_msg(ANSWER, "Fridolin: Geh rein!", with_scene=False)


# ---- the call ---------------------------------------------------------------------------------


def test_one_call_answers_all_three_and_each_verdict_journals_its_own_part() -> None:
    chat = _Chat(json.dumps(FULL))
    result = _run(classify_post_turn(chat, scene=SCENE, fact=FACT, npc=NPC))

    assert len(chat.calls) == 1 and result.failure is None and result.retry == ()
    call = chat.calls[0]
    assert call["options"]["num_predict"] == 40 + 120 + 160 and call["options"]["temperature"] == 0
    assert result.verdicts["scene"].target_id == "schrein"
    assert result.verdicts["fact"].commitment is None and result.verdicts["fact"].failure is None
    assert [s.statblock for s in result.verdicts["npc"].sightings] == ["Schwester Vall"]
    assert json.loads(result.verdicts["scene"].raw) == {"ziel": "schrein"}
    assert set(json.loads(result.verdicts["fact"].raw)) == {"art", "sache", "an", "von"}
    assert result.note() == {"raw": json.dumps(FULL), "asked": ["scene", "fact", "npc"],
                             "failure": None, "separate": []}


def test_a_missing_part_is_handed_back_alone() -> None:
    partial = {k: v for k, v in FULL.items() if k != "npcs"}
    result = _run(classify_post_turn(_Chat(json.dumps(partial)), scene=SCENE, fact=FACT, npc=NPC))
    assert result.retry == ("npc",) and result.failure is None
    assert set(result.verdicts) == {"scene", "fact"}


def test_an_off_list_exit_is_a_verdict_not_a_malformed_part() -> None:
    """The validator's own discard (an exit not offered) is what the separate call would do too
    — no second call for it."""
    answer = {**FULL, "ziel": "pier"}
    result = _run(classify_post_turn(_Chat(json.dumps(answer)), scene=SCENE, fact=FACT, npc=NPC))
    assert result.retry == () and result.verdicts["scene"].failure is SceneFailure.OFF_LIST


@pytest.mark.parametrize("answer,failure", [
    ("", CombinedFailure.EMPTY),
    ("{nicht json", CombinedFailure.BAD_JSON),
    ("[1, 2]", CombinedFailure.BAD_JSON),
])
def test_an_unusable_answer_hands_every_question_back(answer, failure) -> None:
    result = _run(classify_post_turn(_Chat(answer), scene=SCENE, fact=FACT, npc=NPC))
    assert result.failure is failure and result.retry == ("scene", "fact", "npc")
    assert result.verdicts == {}


def test_a_failed_call_is_not_retried_separately() -> None:
    # Review 2026-11-14: the separate calls would go to the same backend that just failed (a paused
    # client, or a cold Nemo under fallback) — the turn's verdicts are lost, as a failed separate
    # call loses its own.
    result = _run(classify_post_turn(_Chat(RuntimeError("cli died")), scene=SCENE, fact=FACT, npc=NPC))
    assert result.failure is CombinedFailure.CALL_FAILED and result.retry == ()
    assert result.verdicts == {} and result.asked == ("scene", "fact", "npc")


def test_a_timeout_is_not_retried_separately() -> None:
    # Review 2026-11-14: retrying after the combined timeout put the verdicts ~40 s behind the
    # narration (20 s + 20 s); a separate call that times out loses its verdict too.
    async def slow(*args, **kwargs):
        await asyncio.sleep(1)
        return "{}"

    result = _run(classify_post_turn(slow, fact=FACT, npc=NPC, timeout=0.01))
    assert result.failure is CombinedFailure.TIMEOUT and result.retry == ()
    assert result.verdicts == {}


def test_a_single_question_or_a_blank_answer_is_not_combined() -> None:
    chat = _Chat()
    single = _run(classify_post_turn(chat, fact=FACT))
    blank = _run(classify_post_turn(chat, fact={**FACT, "answer_text": " "},
                                    npc={**NPC, "answer_text": " "}))
    assert chat.calls == []
    assert single.failure is blank.failure is CombinedFailure.NOT_COMBINABLE
    assert single.retry == ("fact",) and blank.retry == ("fact", "npc")


def test_a_scene_without_exits_is_decided_before_the_call() -> None:
    chat = _Chat(json.dumps({k: v for k, v in FULL.items() if k != "ziel"}))
    result = _run(classify_post_turn(chat, scene={**SCENE, "exits": {}}, fact=FACT, npc=NPC))
    assert result.verdicts["scene"].failure is SceneFailure.NO_EXITS
    assert "ziel" not in chat.calls[0]["format"]["properties"]
    assert result.asked == ("fact", "npc")


# ---- the brain: fallback and journal ----------------------------------------------------------


def test_the_brain_asks_a_malformed_part_separately_in_the_same_turn(caplog) -> None:
    partial = {k: v for k, v in FULL.items() if k != "npcs"}
    client = FakeLLMClient([json.dumps(partial), '{"npcs": []}'])
    brain = FakeBrain(client=client, combine_post_turn=lambda: True)

    with caplog.at_level("INFO"):
        out = _run(brain.classify_post_turn(scene=SCENE, fact=FACT, npc=NPC))

    assert len(client.calls) == 2
    assert list(client.calls[1]["format"]["properties"]) == ["npcs"]  # the separate presence call
    assert out["scene"].target_id == "schrein" and out["npc"].sightings == ()
    assert brain.last_post_turn["separate"] == ["npc"]
    assert brain.last_npcs == {"raw": '{"npcs": []}', "verdict": [], "failure": None}
    assert brain.last_scene_router["raw"] == '{"ziel": "schrein"}'
    assert "separate calls this turn" in caplog.text
    assert "[classifier] post-turn" in caplog.text


def test_the_brain_falls_back_to_all_three_when_the_call_fails() -> None:
    client = FakeLLMClient(["", '{"ziel": "nein"}', '{"art": "nichts", "sache": "", "an": "", '
                                                    '"von": ""}', '{"npcs": []}'])
    brain = FakeBrain(client=client, combine_post_turn=lambda: True)
    out = _run(brain.classify_post_turn(scene=SCENE, fact=FACT, npc=NPC))
    assert len(client.calls) == 4
    assert out["scene"].target_id == "" and out["scene"].failure is None
    assert out["fact"].failure is None and out["npc"].failure is None
    assert brain.last_post_turn["failure"] == "empty_answer"


def test_without_a_hook_the_brain_never_combines_and_a_broken_hook_means_separate() -> None:
    assert FakeBrain().combines_post_turn() is False

    def broken() -> bool:
        raise RuntimeError("boom")

    assert FakeBrain(combine_post_turn=broken).combines_post_turn() is False
    assert FakeBrain(combine_post_turn=lambda: True).combines_post_turn() is True


# ---- the hook ---------------------------------------------------------------------------------


def test_the_hook_combines_only_on_claude_with_the_flag_and_while_claude_answers() -> None:
    pair = FailoverClient(FakeLLMClient(), FakeLLMClient())
    assert post_turn_combined(make_config(llm_backend="ollama", aux_combined=True), pair) is None
    assert post_turn_combined(make_config(llm_backend="claude", aux_combined=False), pair) is None

    hook = post_turn_combined(make_config(llm_backend="claude", aux_combined=True), pair)
    assert hook() is True
    pair.force("fallback")  # `!backend ollama`: Nemo keeps the separate calls
    assert hook() is False
    pair.force("auto")
    assert hook() is True


def test_the_flag_is_read_from_the_environment(monkeypatch) -> None:
    from dmbot import config as config_mod
    from dmbot.config import Config

    monkeypatch.setattr(config_mod, "load_dotenv", lambda: None)
    monkeypatch.setenv("DISCORD_TOKEN_DMBOT", "token")
    monkeypatch.delenv("DM_AUX_COMBINED", raising=False)
    default = Config.load().aux_combined
    monkeypatch.setenv("DM_AUX_COMBINED", "1")
    assert Config.load().aux_combined is True
    monkeypatch.setenv("DM_AUX_COMBINED", "0")
    assert Config.load().aux_combined is False
    assert isinstance(default, bool)


def test_npc_failure_set_is_what_the_validator_can_report() -> None:
    """``to_npc_verdict`` reports BAD_JSON for a missing list; the fallback keys off it."""
    from dmbot.llm.npc_router import to_npc_verdict
    from dmbot.llm.fact_router import to_fact_verdict

    assert to_npc_verdict({}, party=[], roster=[], present=[]).failure is NpcFailure.BAD_JSON
    assert to_fact_verdict({}, recipients=[], givers=[]).failure is FactFailure.BAD_JSON
