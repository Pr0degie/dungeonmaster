"""🧪 debug overlay (ADR 052): `SessionRuntime.update_debug_overlay` renders the current
scene's testplan entry edit-in-place (the clock-panel pattern), is fully dormant without a
loaded testplan, honours DM_DEBUG_CHANNEL, and — the core invariant — never enters any
prompt path: no prompt-building module may even mention the testplan."""

from __future__ import annotations

import asyncio
import inspect
import types
from pathlib import Path

import dmbot
from dmbot.memory.state import WorldState
from dmbot.rag.testplan import Testplan, TestplanEntry
from dmbot.runtime import SessionRuntime
from dmbot.voice.delivery import DeliveryPipeline


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content
        self.edits: list[str] = []

    async def edit(self, content: str = "") -> None:
        self.content = content
        self.edits.append(content)


class _Channel:
    def __init__(self) -> None:
        self.sent: list[_Msg] = []

    async def send(self, content: str = "", **kwargs) -> _Msg:
        msg = _Msg(content)
        self.sent.append(msg)
        return msg


def _plan() -> Testplan:
    return Testplan({"s1": TestplanEntry(
        gates=["G4 Gated Exit"], hint_de="Die Tür ohne Schlüssel öffnen.")})


def _runtime(*, testplan, scene_id: str = "s1"):
    rt = object.__new__(SessionRuntime)
    rt._testplan = testplan
    rt._debug_panel = None
    rt._debug_channel_id = 0
    rt._debug_channel_warned = False
    rt._active_vc_id = 7
    state = WorldState()
    state.scene_id = scene_id
    rt._state = {7: state}
    scene = types.SimpleNamespace(id="s1", title_de="Die Docks", part=1)
    rt._adventure = types.SimpleNamespace(get_scene=lambda sid: scene if sid == "s1" else None)
    rt._text_channel = _Channel()
    return rt


# --- dormancy -------------------------------------------------------------------------------

def test_dormant_without_testplan() -> None:
    rt = _runtime(testplan=None)
    asyncio.run(SessionRuntime.update_debug_overlay(rt))
    assert rt._text_channel.sent == []


def test_stub_runtime_without_attrs_is_dormant() -> None:
    # The delivery/cog call sites run against stub runtimes in tests — the getattr guard
    # keeps a bare SessionRuntime shell quiet instead of raising.
    rt = object.__new__(SessionRuntime)
    asyncio.run(SessionRuntime.update_debug_overlay(rt))


def test_dormant_without_active_session() -> None:
    rt = _runtime(testplan=_plan())
    rt._active_vc_id = None
    asyncio.run(SessionRuntime.update_debug_overlay(rt))
    assert rt._text_channel.sent == []


# --- rendering + edit-in-place ---------------------------------------------------------------

def test_posts_overlay_for_current_scene() -> None:
    rt = _runtime(testplan=_plan())
    asyncio.run(SessionRuntime.update_debug_overlay(rt))
    assert len(rt._text_channel.sent) == 1
    msg = rt._text_channel.sent[0]
    assert msg.content.startswith("🧪")
    assert "Die Docks" in msg.content and "G4 Gated Exit" in msg.content
    assert "Die Tür ohne Schlüssel öffnen." in msg.content


def test_second_update_edits_in_place() -> None:
    rt = _runtime(testplan=_plan())
    asyncio.run(SessionRuntime.update_debug_overlay(rt))
    rt._state[7].scene_id = "s2"  # a scene the plan has no entry for
    asyncio.run(SessionRuntime.update_debug_overlay(rt))
    assert len(rt._text_channel.sent) == 1  # edited, not re-posted
    msg = rt._text_channel.sent[0]
    assert msg.edits and "keine Gates" in msg.content and "`s2`" in msg.content


# --- DM_DEBUG_CHANNEL ------------------------------------------------------------------------

def test_debug_channel_override_posts_there() -> None:
    rt = _runtime(testplan=_plan())
    debug_ch = _Channel()
    rt._debug_channel_id = 42
    rt._text_channel.guild = types.SimpleNamespace(
        get_channel=lambda i: debug_ch if i == 42 else None)
    asyncio.run(SessionRuntime.update_debug_overlay(rt))
    assert len(debug_ch.sent) == 1 and rt._text_channel.sent == []


def test_unresolvable_debug_channel_falls_back_loudly() -> None:
    rt = _runtime(testplan=_plan())
    rt._debug_channel_id = 99
    rt._text_channel.guild = types.SimpleNamespace(get_channel=lambda i: None)
    asyncio.run(SessionRuntime.update_debug_overlay(rt))
    assert len(rt._text_channel.sent) == 1  # game-channel fallback
    assert rt._debug_channel_warned is True  # warned once, not per scene change


# --- the scene-change call sites -------------------------------------------------------------

def test_scene_confirm_refreshes_the_overlay() -> None:
    # The <<ORT>> confirm click (ADR 026) ends with an overlay refresh, like !ort does.
    flags = {}
    scene = types.SimpleNamespace(id="s2", title_de="Die Brücke", part=2)

    async def _advance(ch):
        return 30

    async def _overlay():
        flags["overlay"] = True

    rt = types.SimpleNamespace(
        _brain_channel=lambda ch: 7,
        _state={7: types.SimpleNamespace(scene_id="s1")},
        _set_scene=lambda st, sid: scene,
        _persist_and_refresh=lambda ch: None,
        schedule_npc_memory_extraction=lambda ch, sid: None,
        advance_scene_time=_advance,
        update_debug_overlay=_overlay,
    )
    dp = object.__new__(DeliveryPipeline)
    dp._rt = rt

    class _Interaction:
        async def edit_original_response(self, content: str = "") -> None:
            flags["edited"] = content

    confirm = DeliveryPipeline._make_scene_confirm(dp, object(), scene)
    asyncio.run(confirm(_Interaction()))
    assert flags.get("overlay") is True
    assert "Die Brücke" in flags.get("edited", "")


# --- LLM-invisibility (the core invariant) ---------------------------------------------------

def test_prompt_paths_never_touch_the_testplan() -> None:
    # ADR 052: nothing about the testplan may reach a prompt, persona or RAG path. Pinned
    # structurally: no prompt-building module (nor the adventure loader, whose blocks feed
    # the prompt) may even mention it.
    import dmbot.orchestrator as orchestrator
    from dmbot.llm import director_msgs, prompt_assembly
    from dmbot.rag import adventure

    for mod in (orchestrator, prompt_assembly, director_msgs, adventure):
        assert "testplan" not in inspect.getsource(mod).lower(), mod.__name__


def test_testplan_is_only_reachable_from_the_runtime() -> None:
    # The stronger structural pin: within dmbot/, ONLY runtime.py (the loader + overlay
    # renderer) may even mention the testplan. Any other module reaching for it — a prompt
    # builder, memory, consistency, delivery — is a leak toward the LLM by definition.
    root = Path(dmbot.__file__).parent
    allowed = ("testplan.py", "runtime.py", "config.py")  # config only documents the env knobs
    offenders = [
        str(p.relative_to(root)) for p in sorted(root.rglob("*.py"))
        if p.name not in allowed
        and "testplan" in p.read_text(encoding="utf-8").lower()
    ]
    assert offenders == []
