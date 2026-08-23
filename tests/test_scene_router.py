"""Scene-move classifier (ADR 057) — the contract of the post-turn call that decides whether the
group actually entered one of the current scene's reachable exits.

Same shape as ``tests/test_roll_router.py``: the model is never called here. What is locked is the
constrained schema, the German prompt, and — the part that decides whether the table keeps
playing — that every degenerate answer (off-list, empty, broken JSON, timeout, transport error)
changes nothing and never raises. Optional layers fail open
(``docs/lessons/optional-layers-fail-open-core-fails-loud.md``).
"""

import asyncio

from dmbot.llm.scene_router import (
    NO_MOVE,
    SCENE_ROUTER_OPTIONS,
    SceneExit,
    SceneFailure,
    classify_scene_move,
    normalize_exits,
    scene_schema,
    scene_system,
    to_scene_verdict,
)

EXITS = {"schrein": "Schrein der Aschenheiligen", "pfandhalle": "Bree's Pfandhalle"}


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


# --- pure helpers -----------------------------------------------------------------------------

def test_normalize_accepts_ids_pairs_and_mappings_and_dedupes():
    assert normalize_exits(["schrein"]) == (SceneExit("schrein", ""),)
    assert normalize_exits({"schrein": "Schrein"}) == (SceneExit("schrein", "Schrein"),)
    assert normalize_exits([("schrein", "Schrein")]) == (SceneExit("schrein", "Schrein"),)
    # empties dropped, order kept, first title wins on a duplicate id
    assert normalize_exits(["", "b", "a", "b"]) == (SceneExit("b", ""), SceneExit("a", ""))
    assert normalize_exits(None) == ()


def test_schema_is_exactly_the_reachable_exits_plus_no():
    s = scene_schema(EXITS)
    assert s["properties"]["ziel"]["enum"] == ["schrein", "pfandhalle", NO_MOVE]
    assert s["required"] == ["ziel"]


def test_system_prompt_names_the_exits_with_titles_and_demands_json():
    sys = scene_system(EXITS, current_title="Zollhaus am Kettenkai")
    assert "schrein — Schrein der Aschenheiligen" in sys
    assert "pfandhalle — Bree's Pfandhalle" in sys
    assert "Zollhaus am Kettenkai" in sys
    assert NO_MOVE in sys and "JSON" in sys


def test_a_reachable_target_is_accepted():
    v = to_scene_verdict({"ziel": "schrein"}, exits=EXITS)
    assert v.target_id == "schrein" and v.moved and v.failure is None


def test_no_is_a_clean_verdict_not_a_failure():
    v = to_scene_verdict({"ziel": NO_MOVE}, exits=EXITS)
    assert v.target_id == "" and not v.moved and v.failure is None


def test_whitespace_and_case_resolve_to_the_canonical_id():
    v = to_scene_verdict({"ziel": '  "Schrein" '}, exits=EXITS)
    assert v.target_id == "schrein" and v.failure is None


def test_a_target_outside_the_choice_changes_nothing():
    for answer in ({"ziel": "pier_neun"}, {"ziel": "der hafen"}, {"ziel": "schrein — Schrein"}):
        v = to_scene_verdict(answer, exits=EXITS)
        assert v.target_id == "" and v.failure is SceneFailure.OFF_LIST


def test_empty_and_malformed_verdicts_change_nothing():
    assert to_scene_verdict({"ziel": ""}, exits=EXITS).failure is SceneFailure.EMPTY
    assert to_scene_verdict({"ziel": "   "}, exits=EXITS).failure is SceneFailure.EMPTY
    assert to_scene_verdict({}, exits=EXITS).failure is SceneFailure.BAD_JSON
    assert to_scene_verdict("nein", exits=EXITS).failure is SceneFailure.BAD_JSON
    assert to_scene_verdict(None, exits=EXITS).failure is SceneFailure.BAD_JSON
    assert to_scene_verdict({"ziel": ["schrein"]}, exits=EXITS).failure is SceneFailure.BAD_JSON


# --- the call ---------------------------------------------------------------------------------

def test_call_pins_its_own_sampling_and_the_constrained_schema():
    chat = _Chat('{"ziel": "schrein"}')
    v = asyncio.run(classify_scene_move(chat, turn_text="Ihr tretet in den Schrein.", exits=EXITS))
    assert v.target_id == "schrein" and v.failure is None and v.raw == '{"ziel": "schrein"}'
    call = chat.calls[0]
    assert call["format"] == scene_schema(EXITS)
    # sampling is pinned at the call site, never inherited (docs/lessons/sampling-defaults-...)
    assert call["options"]["temperature"] == 0
    assert call["options"]["repeat_penalty"] == 1.0 and call["options"]["repeat_last_n"] == 0
    assert call["options"] == SCENE_ROUTER_OPTIONS
    assert "Ihr tretet in den Schrein." in call["messages"][0]["content"]


def test_call_returns_no_move_on_a_negative_verdict():
    chat = _Chat('{"ziel": "nein"}')
    v = asyncio.run(classify_scene_move(chat, turn_text="Ihr redet weiter.", exits=EXITS))
    assert not v.moved and v.failure is None


def test_broken_json_changes_nothing_and_keeps_the_raw_answer():
    chat = _Chat('{"ziel": "schr')
    v = asyncio.run(classify_scene_move(chat, turn_text="egal", exits=EXITS))
    assert not v.moved and v.failure is SceneFailure.BAD_JSON and v.raw == '{"ziel": "schr'


def test_an_empty_answer_changes_nothing():
    v = asyncio.run(classify_scene_move(_Chat("   "), turn_text="egal", exits=EXITS))
    assert not v.moved and v.failure is SceneFailure.EMPTY


def test_a_timeout_never_reaches_the_table():
    chat = _Chat("", raises=TimeoutError())
    v = asyncio.run(classify_scene_move(chat, turn_text="egal", exits=EXITS))
    assert not v.moved and v.failure is SceneFailure.TIMEOUT


def test_a_slow_model_is_cut_off_by_the_deadline():
    chat = _Chat('{"ziel": "schrein"}', delay=5.0)
    v = asyncio.run(classify_scene_move(chat, turn_text="egal", exits=EXITS, timeout=0.01))
    assert not v.moved and v.failure is SceneFailure.TIMEOUT


def test_a_transport_error_changes_nothing():
    chat = _Chat("", raises=RuntimeError("ollama down"))
    v = asyncio.run(classify_scene_move(chat, turn_text="egal", exits=EXITS))
    assert not v.moved and v.failure is SceneFailure.CALL_FAILED


def test_no_exits_and_no_turn_text_skip_the_call_entirely():
    chat = _Chat('{"ziel": "schrein"}')
    v = asyncio.run(classify_scene_move(chat, turn_text="Ihr tretet ein.", exits=[]))
    assert v.failure is SceneFailure.NO_EXITS and not chat.calls
    v = asyncio.run(classify_scene_move(chat, turn_text="  ", exits=EXITS))
    assert v.failure is SceneFailure.NO_INPUT and not chat.calls
