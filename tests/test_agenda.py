"""NPC agendas (ADR 049): AgendaStep schema round-trip + FIFO cap, the one-step-per-NPC
clamp in apply_extraction, extractor input (goal + recent steps + in-game time), rendering
(present memory block vs. absent world-state line) and the !agenda/!agenden commands. Steps
are narrative-only — the LLM proposes, code clamps and stores (golden rule #3)."""

from __future__ import annotations

import asyncio

from dmbot.memory.npc_memory import (
    EXTRACT_SCHEMA,
    apply_extraction,
    build_extract_user,
    npc_memory_block_de,
)
from dmbot.memory.state import (
    AGENDA_LOG_CAP,
    AgendaStep,
    Combatant,
    WorldState,
    world_state_summary_de,
)
from dmbot.rag.adventure import AdventureNpc
from dmbot.runtime import SessionRuntime
from dmbot.voice.dicecog import DiceCog


def _agenda_npc(name: str = "Vex", goal: str = "Die Ware außer Reichweite schaffen") -> Combatant:
    return Combatant(name=name, wounds=10, max_wounds=10, is_npc=True,
                     attitude="wary", goal=goal)


# -- schema round-trip + cap -------------------------------------------------------------------


def test_agenda_step_round_trip_and_omit_when_empty() -> None:
    step = AgendaStep(ts_ingame="Tag 2, 14:30", text="Hat die Kisten verlegt.")
    assert AgendaStep.from_dict(step.to_dict()) == step
    bare = AgendaStep(ts_ingame="", text="Ohne Zeit.")
    assert bare.to_dict() == {"text": "Ohne Zeit."}
    assert AgendaStep.from_dict(bare.to_dict()) == bare


def test_combatant_goal_and_log_survive_state_round_trip(tmp_path) -> None:
    state = WorldState(session_id="t")
    npc = state.add_or_update_npc("Vex", attitude="wary", goal="Untertauchen")
    npc.add_agenda_step(AgendaStep(ts_ingame="Tag 1, 09:00", text="Bar geräumt."))
    path = tmp_path / "state.json"
    state.save(path)
    loaded = WorldState.load(path)
    got = loaded.npcs[0]
    assert got.goal == "Untertauchen"
    assert got.agenda_log == npc.agenda_log
    # Goal-less combatants keep a clean dict (omit-when-empty).
    bare = Combatant(name="X", wounds=1, max_wounds=1).to_dict()
    assert "goal" not in bare and "agenda_log" not in bare


def test_old_state_without_agenda_fields_loads_unchanged() -> None:
    state = WorldState.from_dict(
        {"session_id": "old", "npcs": [{"name": "Alecto", "wounds": 8, "max_wounds": 8}]}
    )
    assert state.npcs[0].goal == "" and state.npcs[0].agenda_log == []


def test_agenda_log_caps_fifo() -> None:
    npc = _agenda_npc()
    for i in range(AGENDA_LOG_CAP + 3):
        npc.add_agenda_step(AgendaStep(ts_ingame="", text=f"s{i}"))
    assert len(npc.agenda_log) == AGENDA_LOG_CAP
    assert npc.agenda_log[0].text == "s3"  # oldest aged out, newest kept
    assert npc.agenda_log[-1].text == f"s{AGENDA_LOG_CAP + 2}"


def test_adventure_npc_carries_goal_de() -> None:
    block = AdventureNpc.from_dict({"name": "Vex", "goal_de": "Untertauchen"})
    assert block.goal_de == "Untertauchen"
    assert AdventureNpc.from_dict({"name": "Ohne"}).goal_de == ""


# -- extractor input ---------------------------------------------------------------------------


def test_build_extract_user_renders_goal_recent_steps_and_time() -> None:
    npc = _agenda_npc()
    for i in range(4):
        npc.add_agenda_step(AgendaStep(ts_ingame=f"Tag 1, 0{i}:00", text=f"Schritt {i}"))
    text = build_extract_user([], [npc], "mud_gate", now_ingame="Tag 2, 14:30")
    assert "Aktuelle Ingame-Zeit: Tag 2, 14:30" in text
    assert "Ziel: Die Ware außer Reichweite schaffen" in text
    # Only the last AGENDA_INPUT_STEPS (2) ride along.
    assert "Schritt 3" in text and "Schritt 2" in text
    assert "Schritt 1" not in text


def test_build_extract_user_goalless_npc_has_no_ziel_line() -> None:
    npc = Combatant(name="Grubb", wounds=10, max_wounds=10, is_npc=True, attitude="neutral")
    text = build_extract_user([], [npc], "bar")
    assert "Ziel:" not in text and "Aktuelle Ingame-Zeit" not in text


def test_extract_schema_accepts_agenda_step() -> None:
    props = EXTRACT_SCHEMA["properties"]["npcs"]["items"]["properties"]
    assert props["agenda_step"] == {"type": "string"}


# -- apply: clamp + defensive processing -------------------------------------------------------


def test_apply_appends_one_agenda_step_with_ingame_ts() -> None:
    state = WorldState(session_id="t")
    state.npcs.append(_agenda_npc())
    payload = {"npcs": [{"name": "Vex", "agenda_step": "Hat die Kisten in den Unterschlupf verlegt."}]}
    apply_extraction(state, payload, scene_id="docks", now_ingame="Tag 2, 14:30")
    npc = state.npcs[0]
    assert len(npc.agenda_log) == 1
    assert npc.agenda_log[0].ts_ingame == "Tag 2, 14:30"
    assert npc.agenda_log[0].text.startswith("Hat die Kisten")


def test_apply_clamps_duplicate_entries_to_one_step() -> None:
    state = WorldState(session_id="t")
    state.npcs.append(_agenda_npc())
    payload = {"npcs": [
        {"name": "Vex", "agenda_step": "Erster Schritt."},
        {"name": "Vex", "agenda_step": "Zweiter Schritt (Duplikat)."},
    ]}
    apply_extraction(state, payload, scene_id="docks")
    assert len(state.npcs[0].agenda_log) == 1
    assert state.npcs[0].agenda_log[0].text == "Erster Schritt."


def test_apply_discards_step_for_goalless_and_dead_npcs() -> None:
    state = WorldState(session_id="t")
    state.npcs.append(Combatant(name="Grubb", wounds=10, max_wounds=10, is_npc=True))
    dead = _agenda_npc(name="Mort")
    dead.wounds = 0
    state.npcs.append(dead)
    payload = {"npcs": [
        {"name": "Grubb", "agenda_step": "Sollte verworfen werden."},
        {"name": "Mort", "agenda_step": "Tote schmieden keine Pläne."},
    ]}
    apply_extraction(state, payload, scene_id="docks")
    assert state.npcs[0].agenda_log == [] and state.npcs[1].agenda_log == []


def test_apply_without_agenda_step_is_fine_and_text_is_truncated() -> None:
    state = WorldState(session_id="t")
    state.npcs.append(_agenda_npc())
    # Missing key (older extractor output) → no step, no crash.
    apply_extraction(state, {"npcs": [{"name": "Vex"}]}, scene_id="docks")
    assert state.npcs[0].agenda_log == []
    # Overlong step text is truncated to the gist cap.
    apply_extraction(state, {"npcs": [{"name": "Vex", "agenda_step": "x" * 500}]}, scene_id="docks")
    assert len(state.npcs[0].agenda_log[0].text) <= 200


def test_apply_registration_copies_goal_from_statblock() -> None:
    state = WorldState(session_id="t")
    block = AdventureNpc(name="Vex", wounds=12, faction="Schmuggler", goal_de="Untertauchen")
    payload = {"npcs": [{"name": "Vex",
                         "memories": [{"about": ["party"], "gist": "Wurde bedroht."}],
                         "agenda_step": "Packt seine Sachen."}]}
    apply_extraction(state, payload, scene_id="bar", statblock=lambda n: block)
    npc = state.npcs[0]
    assert npc.goal == "Untertauchen"  # authored goal makes it an agenda NPC on registration
    assert len(npc.agenda_log) == 1


def test_apply_backfills_goal_onto_older_state() -> None:
    state = WorldState(session_id="t")
    state.npcs.append(Combatant(name="Vex", wounds=10, max_wounds=10, is_npc=True,
                                faction="Schmuggler"))  # pre-049 state: faction, no goal
    block = AdventureNpc(name="Vex", faction="Schmuggler", goal_de="Untertauchen")
    apply_extraction(state, {"npcs": [{"name": "Vex", "agenda_step": "Verschwindet."}]},
                     scene_id="bar", statblock=lambda n: block)
    assert state.npcs[0].goal == "Untertauchen"
    assert len(state.npcs[0].agenda_log) == 1


# -- rendering ---------------------------------------------------------------------------------


def test_memory_block_renders_goal_only_npc_and_recent_steps() -> None:
    npc = _agenda_npc()  # no memories at all
    for i in range(5):
        npc.add_agenda_step(AgendaStep(ts_ingame=f"Tag 1, 0{i}:00", text=f"Schritt {i}"))
    block = npc_memory_block_de([npc])
    assert "[NPC-Gedächtnis: Vex" in block
    assert "Ziel: Die Ware außer Reichweite schaffen" in block
    # Last AGENDA_RENDER_STEPS (3) only, marked offscreen with the in-game timestamp.
    assert "(offscreen, Tag 1, 04:00) Schritt 4" in block
    assert "Schritt 2" in block and "Schritt 1" not in block


def test_memory_block_still_skips_npc_without_memories_or_goal() -> None:
    npc = Combatant(name="Grubb", wounds=10, max_wounds=10, is_npc=True)
    assert npc_memory_block_de([npc]) == ""


def test_world_state_summary_lists_living_agenda_npcs_with_latest_step() -> None:
    state = WorldState(session_id="t")
    vex = _agenda_npc()
    vex.add_agenda_step(AgendaStep(ts_ingame="Tag 1, 09:00", text="Bar geräumt."))
    state.npcs.append(vex)
    dead = _agenda_npc(name="Mort", goal="Rache")
    dead.wounds = 0
    state.npcs.append(dead)
    summary = world_state_summary_de(state)
    assert "Agenden" in summary
    assert "Vex → Die Ware außer Reichweite schaffen (zuletzt: Bar geräumt.)" in summary
    assert "Mort" not in summary.split("Agenden")[1].split("\n")[0]  # dead NPCs don't act


def test_world_state_summary_without_agenda_npcs_has_no_agenda_line() -> None:
    state = WorldState(session_id="t")
    state.npcs.append(Combatant(name="Grubb", wounds=10, max_wounds=10, is_npc=True))
    assert "Agenden" not in world_state_summary_de(state)


# -- commands (stub runtime, callback pattern like test_clock_commands) -------------------------


class _Ctx:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.channel = object()

    async def send(self, content: str = "", **kwargs) -> None:
        if content:
            self.sent.append(content)


def _runtime():
    rt = object.__new__(SessionRuntime)
    rt._brain_channel = lambda ch: 7
    rt._state = {7: WorldState()}
    rt._persisted = []
    rt._persist_and_refresh = lambda ch: rt._persisted.append(ch)

    async def _send(channel, content):
        rt._sent_long = getattr(rt, "_sent_long", [])
        rt._sent_long.append(content)
    rt._send_with_retry = _send
    return rt


def _cog(rt) -> DiceCog:
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    return cog


def test_agenda_sets_and_changes_goal() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state[7].npcs.append(Combatant(name="Vex", wounds=10, max_wounds=10, is_npc=True))
    asyncio.run(DiceCog.agenda.callback(_cog(rt), ctx, "Vex", goal='"Untertauchen"'))
    assert rt._state[7].npcs[0].goal == "Untertauchen"  # surrounding quotes stripped
    assert len(rt._persisted) == 1
    assert any("Vex" in m and "Untertauchen" in m for m in ctx.sent)


def test_agenda_weg_removes_goal_but_keeps_log() -> None:
    rt, ctx = _runtime(), _Ctx()
    npc = _agenda_npc()
    npc.add_agenda_step(AgendaStep(ts_ingame="", text="Bar geräumt."))
    rt._state[7].npcs.append(npc)
    asyncio.run(DiceCog.agenda.callback(_cog(rt), ctx, "Vex", goal="weg"))
    assert npc.goal == "" and len(npc.agenda_log) == 1
    assert any("entfernt" in m for m in ctx.sent)


def test_agenda_unknown_npc_and_usage_reply() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(DiceCog.agenda.callback(_cog(rt), ctx, "Niemand", goal="Ziel"))
    assert any("Unbekannter NSC" in m for m in ctx.sent)
    ctx2 = _Ctx()
    asyncio.run(DiceCog.agenda.callback(_cog(rt), ctx2))
    assert any("Nutzung" in m for m in ctx2.sent)


def test_agenda_warns_past_five_agenda_npcs() -> None:
    rt, ctx = _runtime(), _Ctx()
    for i in range(5):
        rt._state[7].npcs.append(_agenda_npc(name=f"N{i}", goal="Ziel"))
    rt._state[7].npcs.append(Combatant(name="Vex", wounds=10, max_wounds=10, is_npc=True))
    asyncio.run(DiceCog.agenda.callback(_cog(rt), ctx, "Vex", goal="Sechstes Ziel"))
    assert any("⚠️" in m and "6" in m for m in ctx.sent)


def test_agenden_lists_goals_and_recent_steps() -> None:
    rt, ctx = _runtime(), _Ctx()
    npc = _agenda_npc()
    for i in range(4):
        npc.add_agenda_step(AgendaStep(ts_ingame=f"Tag 1, 0{i}:00", text=f"Schritt {i}"))
    rt._state[7].npcs.append(npc)
    asyncio.run(DiceCog.agenden.callback(_cog(rt), ctx))
    out = "\n".join(rt._sent_long)
    assert "Vex" in out and "Die Ware außer Reichweite schaffen" in out
    assert "Schritt 3" in out and "Schritt 0" not in out  # last 3 only


def test_agenden_empty_replies_hint() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(DiceCog.agenden.callback(_cog(rt), ctx))
    assert any("Keine Agenda-NSCs" in m for m in ctx.sent)
