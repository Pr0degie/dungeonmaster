"""``DM_CLOCKS`` — the kill switch for consequence clocks (ADR 047/059).

Off means: the adventure's clocks are not created, no clock line reaches the prompt or a panel,
``<<UHR>>`` is still stripped from the spoken text but ticks nothing, and every ``!uhr`` command
answers with a hint. It is non-destructive — clocks already saved stay in the state file — and
deadlines and in-game time (ADR 048) keep running. The default path is pinned by the existing
clock tests, which this file does not touch. Stub runtime (init skipped, attrs injected), the
tests/test_clock_delivery.py pattern."""

from __future__ import annotations

import asyncio
import inspect
import logging
import types

import dmbot.config as config_mod
from dmbot.config import Config
from dmbot.discord_ui.panel import render_player_panel_de
from dmbot.memory.state import WorldState, pressure_panel_de, world_state_summary_de
from dmbot.rules.marker import ClockTickRequest, extract_uhr
from dmbot.runtime import SessionRuntime
from dmbot.voice.clockcog import CLOCKS_OFF_DE, ClockCog
from dmbot.voice.delivery import DeliveryPipeline


def _load(monkeypatch, **env) -> Config:
    """``Config.load()`` from exactly this environment (the developer's ``.env`` stays out)."""
    monkeypatch.setattr(config_mod, "load_dotenv", lambda: None)
    monkeypatch.delenv("DM_CLOCKS", raising=False)
    monkeypatch.setenv("DISCORD_TOKEN_DMBOT", "token")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Config.load()


def _adventure():
    return types.SimpleNamespace(
        start_time_de="Tag 1, 21:00",
        deadlines=[{"id": "sirene", "label": "Mitternachtssirene", "in_minutes": 180}],
        clocks=[{"id": "wachsamkeit", "name": "Wachsamkeit", "size": 6}],
        mission={},
    )


def _runtime(*, clocks: bool) -> SessionRuntime:
    rt = object.__new__(SessionRuntime)
    rt._clocks = clocks
    rt._adventure = _adventure()
    return rt


def _state_with_clock_and_deadline() -> WorldState:
    state = WorldState()
    state.add_clock("Wachsamkeit", 6).filled = 2
    state.add_deadline("Mitternachtssirene", 180)
    return state


# -- the knob is wired: env → Config → runtime ----------------------------------------------------

def test_the_switch_defaults_to_on(monkeypatch) -> None:
    assert _load(monkeypatch).clocks is True
    assert object.__new__(SessionRuntime).clocks_enabled is True  # a runtime built without init


def test_env_zero_reaches_the_runtime(monkeypatch) -> None:
    config = _load(monkeypatch, DM_CLOCKS="0")
    assert config.clocks is False
    # __init__ is too heavy to run here (it loads the models); pin the one line that carries the
    # value across, then follow the value through the runtime's own switch.
    assert "self._clocks = config.clocks" in inspect.getsource(SessionRuntime.__init__)
    rt = _runtime(clocks=config.clocks)
    assert rt.clocks_enabled is False
    state = WorldState()
    rt._seed_adventure_state(state)
    assert state.clocks == []


# -- 1. seeding ----------------------------------------------------------------------------------

def test_off_skips_the_adventures_clocks_but_seeds_time_and_deadlines() -> None:
    state = WorldState()
    _runtime(clocks=False)._seed_adventure_state(state)
    assert state.clocks == []
    assert state.time_minutes == 1260
    assert [d.id for d in state.deadlines] == ["sirene"]


def test_on_still_seeds_the_adventures_clocks() -> None:
    state = WorldState()
    _runtime(clocks=True)._seed_adventure_state(state)
    assert [c.id for c in state.clocks] == ["wachsamkeit"]


# -- 2. prompt and panels ------------------------------------------------------------------------

def test_off_leaves_the_clock_line_out_of_the_prompt_and_keeps_the_saved_clock(tmp_path) -> None:
    rt = _runtime(clocks=False)
    rt._adventure = None
    state = _state_with_clock_and_deadline()
    rt._state = {7: state}
    rt._brain_channel = lambda ch: 7
    rt._state_path = lambda cid: tmp_path / "state.json"
    rt.chekhov_list = lambda cid: types.SimpleNamespace(top_open=lambda: [])
    rt._psyker_block = lambda s: ""
    rt._augmetic_block = lambda: ""
    rt._npc_memory = False
    seen: dict = {}
    rt._brain = types.SimpleNamespace(set_context=lambda cid, **kw: seen.update(kw))

    rt._persist_and_refresh(object())

    assert "Uhren" not in seen["state_summary"] and "Wachsamkeit" not in seen["state_summary"]
    assert "Fristen:" in seen["state_summary"]  # deadlines are a separate mechanism (ADR 048)
    # Non-destructive: the clock is hidden, not deleted — it is still in the saved file.
    saved = WorldState.load(tmp_path / "state.json")
    assert [(c.id, c.filled) for c in saved.clocks] == [("wachsamkeit", 2)]


def test_the_pure_renderers_take_the_switch() -> None:
    state = _state_with_clock_and_deadline()
    assert "Uhren" in world_state_summary_de(state)
    assert "Uhren" not in world_state_summary_de(state, clocks=False)
    assert "Uhren" in pressure_panel_de(state)
    off = pressure_panel_de(state, clocks=False)
    assert "Uhren" not in off and "Wachsamkeit" not in off and "Mitternachtssirene" in off


class _PanelMsg:
    def __init__(self, content: str) -> None:
        self.content = content

    async def edit(self, content: str):
        self.content = content

    async def delete(self):
        pass


class _PanelChannel:
    def __init__(self) -> None:
        self.posted: list[_PanelMsg] = []

    async def send(self, content: str):
        self.posted.append(_PanelMsg(content))
        return self.posted[-1]


def _panel_runtime(state: WorldState) -> SessionRuntime:
    rt = _runtime(clocks=False)
    rt._active_vc_id = 7
    rt._state = {7: state}
    rt._text_channel = _PanelChannel()
    rt._clock_panel = None
    return rt


def test_off_posts_no_pressure_panel_for_clocks_alone() -> None:
    state = WorldState()
    state.add_clock("Wachsamkeit", 6)
    rt = _panel_runtime(state)
    asyncio.run(rt.update_clock_panel())
    assert rt._text_channel.posted == [] and rt._clock_panel is None


def test_off_keeps_the_pressure_panel_for_deadlines_without_the_clocks() -> None:
    rt = _panel_runtime(_state_with_clock_and_deadline())
    asyncio.run(rt.update_clock_panel())
    assert len(rt._text_channel.posted) == 1
    body = rt._text_channel.posted[0].content
    assert "Mitternachtssirene" in body and "Uhren" not in body and "Wachsamkeit" not in body


def test_the_player_panel_shows_no_clock() -> None:
    body = render_player_panel_de(_state_with_clock_and_deadline())
    assert "Wachsamkeit" not in body and "Uhren" not in body


# -- 3. <<UHR>>: stripped, then ignored ------------------------------------------------------------

class _Channel:
    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, content: str, view=None):
        self.sent.append((content, view))


def test_off_still_strips_the_marker_and_ticks_nothing(caplog) -> None:
    clean, reqs = extract_uhr("Die Wachen werden unruhig. <<UHR wachsamkeit>>")
    assert clean == "Die Wachen werden unruhig." and len(reqs) == 1

    for confirm in (True, False):
        rt = _runtime(clocks=False)
        pending = [ClockTickRequest(clock_id="wachsamkeit", raw="<<UHR wachsamkeit>>", parsed=True)]
        rt._brain = types.SimpleNamespace(
            take_pending_uhr=lambda cid, _p=pending: [_p.pop() for _ in range(len(_p))]
        )
        rt._brain_channel = lambda ch: 7
        rt._state = {7: _state_with_clock_and_deadline()}
        rt._flag_confirm = confirm
        persisted: list = []
        rt._persist_and_refresh = lambda channel, _l=persisted: _l.append(channel)
        channel = _Channel()
        pipeline = DeliveryPipeline(rt, post_deliver=lambda *a, **k: None)

        with caplog.at_level(logging.INFO, logger="dmbot.voice.delivery"):
            asyncio.run(pipeline._handle_uhr(channel))

        assert pending == []                                  # drained, never carried over
        assert channel.sent == [] and persisted == []         # no button, no write
        assert rt._state[7].find_clock("wachsamkeit").filled == 2
    assert "ignoriert" in caplog.text and "DM_CLOCKS=0" in caplog.text


# -- 4. the commands answer with the hint ----------------------------------------------------------

class _Ctx:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.channel = object()

    async def send(self, content: str = "", **kwargs) -> None:
        self.sent.append(content)


def test_off_every_clock_command_answers_with_the_hint_and_changes_nothing() -> None:
    rt = _runtime(clocks=False)
    rt._brain_channel = lambda ch: 7
    rt._state = {7: _state_with_clock_and_deadline()}
    cog = object.__new__(ClockCog)
    cog._rt = rt
    calls = [
        (ClockCog.uhr, ()),
        (ClockCog.neu, ("Alarm", 4)),
        (ClockCog.tick, ("wachsamkeit",)),
        (ClockCog.zurueck, ("wachsamkeit",)),
        (ClockCog.weg, ("wachsamkeit",)),
        (ClockCog.uhren, ()),
    ]
    for command, args in calls:
        ctx = _Ctx()
        asyncio.run(command.callback(cog, ctx, *args))
        assert ctx.sent == [CLOCKS_OFF_DE], command.name
    assert "DM_CLOCKS" in CLOCKS_OFF_DE
    state = rt._state[7]
    assert [(c.id, c.filled) for c in state.clocks] == [("wachsamkeit", 2)]
