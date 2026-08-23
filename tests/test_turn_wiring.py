"""Where the D107 turn boundary is hooked into the cogs (delivery, scenes, identity hint).

``tests/test_turn_boundary.py`` covers what the runtime *does* after a turn. This file covers the
three seams that decide whether it runs at all: the delivery pipeline spawning it beside the dice
button, the demoted ``<<ORT>>`` marker reporting its rejection instead of swallowing it, and the
``!automatik`` kill switches. Discord and the LLM are faked throughout.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from dmbot.rules.characters import CharacterStore
from dmbot.voice.delivery import DeliveryPipeline
from dmbot.voice.scenecog import SceneCog


class _Ctx:
    def __init__(self) -> None:
        self.channel = types.SimpleNamespace(id=7)
        self.sent: list[str] = []

    async def send(self, content: str, **_kw) -> None:
        self.sent.append(content)


def _run(coro):
    return asyncio.run(coro)


# ---- the delivery pipeline spawns the turn boundary -----------------------------------------

def _pipeline(rt) -> DeliveryPipeline:
    async def _post_deliver(*_a, **_kw):
        return None

    return DeliveryPipeline(rt, post_deliver=_post_deliver)


def _delivery_runtime(**over):
    """Enough runtime for ``_marker_proposal_tasks``: every marker handler bails out early
    (no adventure, no pending markers), so only the new turn-boundary entry does work."""
    brain = types.SimpleNamespace(
        take_pending_scenes=lambda cid: [],
        take_pending_erledigt=lambda cid: [],
        take_pending_uhr=lambda cid: [],
        take_pending_zeit=lambda cid: [],
    )
    rt = types.SimpleNamespace(
        _brain=brain, _adventure=None, _state={}, _brain_channel=lambda ch: 7,
    )
    for key, value in over.items():
        setattr(rt, key, value)
    return rt


def test_a_narrated_turn_spawns_the_turn_boundary_beside_the_markers() -> None:
    seen: list[str] = []

    async def _close(channel, answer):
        seen.append(answer)

    rt = _delivery_runtime(close_turn=_close)

    async def _drive():
        tasks = _pipeline(rt)._marker_proposal_tasks(types.SimpleNamespace(id=7), "Ihr geht los.")
        assert [label for _, label in tasks][-1] == "turn boundary"
        for task, _ in tasks:
            await task

    _run(_drive())
    assert seen == ["Ihr geht los."]


def test_a_content_less_turn_does_not_classify_anything() -> None:
    # A marker-only turn has nothing to classify — asking the model about an empty narration
    # would be two calls for a guaranteed "nein".
    seen: list[str] = []

    async def _close(channel, answer):
        seen.append(answer)

    rt = _delivery_runtime(close_turn=_close)

    async def _drive():
        tasks = _pipeline(rt)._marker_proposal_tasks(types.SimpleNamespace(id=7), "   ")
        assert all(label != "turn boundary" for _, label in tasks)
        for task, _ in tasks:
            await task

    _run(_drive())
    assert seen == []


def test_a_runtime_without_the_boundary_keeps_the_old_marker_list() -> None:
    rt = _delivery_runtime()  # no close_turn at all (the stub runtimes of the older tests)

    async def _drive():
        tasks = _pipeline(rt)._marker_proposal_tasks(types.SimpleNamespace(id=7), "Text")
        assert len(tasks) == 4
        for task, _ in tasks:
            await task

    _run(_drive())


# ---- the demoted <<ORT>> marker reports its rejection (ADR 057 #5) ---------------------------

class _Req:
    def __init__(self, scene_id: str) -> None:
        self.scene_id = scene_id
        self.raw = scene_id
        self.parsed = True


def test_a_rejected_ort_marker_reaches_the_runtime_instead_of_a_log_line() -> None:
    from dmbot.rag.adventure import Adventure, Scene

    adv = Adventure(
        id="mini", start_scene="a",
        scenes=[Scene(id="a", title_de="A", leads_to=["b"]), Scene(id="b", title_de="B")],
    )
    reported: list[object] = []

    async def _report(channel, verdict):
        reported.append(verdict)

    state = types.SimpleNamespace(scene_id="a", resolved_ids=lambda sid: [])
    rt = types.SimpleNamespace(
        _brain=types.SimpleNamespace(take_pending_scenes=lambda cid: [_Req("kanalisation")]),
        _adventure=adv, _scene_mode="verbunden", _state={7: state},
        _brain_channel=lambda ch: 7, report_rejected_move=_report,
        replay_note=lambda ch, k, v: None,
    )

    _run(_pipeline(rt)._handle_scene(types.SimpleNamespace(id=7)))

    assert len(reported) == 1
    assert reported[0].permitted is False
    assert reported[0].target_id == "kanalisation"


# ---- !automatik: the kill switches (PRD "Kill switches") -------------------------------------

def _switch_runtime():
    return types.SimpleNamespace(
        _scene_router=True, _scene_flag_gate=True, _fact_router=True,
        _turn_time_advance=2, _player_panel_enabled=True,
    )


def _scene_cog(rt) -> SceneCog:
    cog = SceneCog.__new__(SceneCog)
    cog._rt = rt
    return cog


@pytest.mark.parametrize("name,attr", [
    ("szene", "_scene_router"),
    ("flaggen", "_scene_flag_gate"),
    ("fakten", "_fact_router"),
    ("panel", "_player_panel_enabled"),
])
def test_each_block_can_be_switched_off_at_the_table(name, attr) -> None:
    rt, ctx = _switch_runtime(), _Ctx()
    _run(SceneCog.automatik.callback(_scene_cog(rt), ctx, args=f"{name} aus"))
    assert getattr(rt, attr) is False
    _run(SceneCog.automatik.callback(_scene_cog(rt), ctx, args=f"{name} an"))
    assert getattr(rt, attr) is True


def test_the_time_switch_restores_the_configured_default_when_switched_back_on() -> None:
    from dmbot.memory.state import TURN_ADVANCE_MINUTES

    rt, ctx = _switch_runtime(), _Ctx()
    _run(SceneCog.automatik.callback(_scene_cog(rt), ctx, args="zeit aus"))
    assert rt._turn_time_advance == 0
    _run(SceneCog.automatik.callback(_scene_cog(rt), ctx, args="zeit an"))
    assert rt._turn_time_advance == TURN_ADVANCE_MINUTES


def test_several_switches_flip_together() -> None:
    rt, ctx = _switch_runtime(), _Ctx()
    _run(SceneCog.automatik.callback(_scene_cog(rt), ctx, args="szene fakten aus"))
    assert rt._scene_router is False and rt._fact_router is False
    assert rt._scene_flag_gate is True


def test_a_bare_call_shows_the_state_and_changes_nothing() -> None:
    rt, ctx = _switch_runtime(), _Ctx()
    _run(SceneCog.automatik.callback(_scene_cog(rt), ctx, args=""))
    assert rt._scene_router is True and rt._turn_time_advance == 2
    assert any("szene **an**" in m for m in ctx.sent)


def test_an_unknown_switch_name_is_named_back() -> None:
    rt, ctx = _switch_runtime(), _Ctx()
    _run(SceneCog.automatik.callback(_scene_cog(rt), ctx, args="quatsch aus"))
    assert rt._scene_router is True
    assert any("Unbekannt" in m and "quatsch" in m for m in ctx.sent)


# ---- the prompt no longer teaches the model the display names (findings A4/B4) ---------------

_STORE = CharacterStore.from_dict({
    "characters": [{"name": "Rektalus Zerfickus"}, {"name": "Fridolin Feuchtgebietheld"}],
    "aliases": {"SezBoss69": "Rektalus Zerfickus", "Pr0degie": "Fridolin Feuchtgebietheld"},
})


def test_the_default_hint_still_maps_display_names() -> None:
    hint = _STORE.alias_hint_de()
    assert "SezBoss69 spielt Rektalus Zerfickus" in hint


def test_without_the_mapping_no_discord_name_reaches_the_prompt() -> None:
    hint = _STORE.alias_hint_de(with_mapping=False)
    assert "SezBoss69" not in hint and "Pr0degie" not in hint
    assert "Rektalus Zerfickus" in hint and "Fridolin Feuchtgebietheld" in hint


def test_the_party_boundary_survives_either_way() -> None:
    for hint in (_STORE.alias_hint_de(), _STORE.alias_hint_de(with_mapping=False)):
        assert "gehören allein den Spielenden" in hint
        assert "sprichst, denkst und handelst NIE für sie" in hint


def test_an_empty_store_still_yields_no_hint() -> None:
    assert CharacterStore().alias_hint_de(with_mapping=False) == ""
