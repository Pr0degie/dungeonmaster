"""The post-turn boundary of D107 — where the campaign is actually advanced (ADR 057/058/059).

On 2026-08-22 nothing here existed: the only mover of the scene pointer was an inline ``<<ORT>>``
marker the model emitted zero times in 22 turns, the in-game clock stood at 08:00 all evening, a
customs warrant handed over in turn 7 was gone by turn 16, and a refused move disappeared into a
``log.info`` line. ``SessionRuntime.close_turn`` is the seam that fixes all four, so these tests
drive the real runtime methods against a real :class:`WorldState` and a real :class:`Adventure`,
with only the LLM (the two classifiers), Discord and persistence faked.

The verdicts themselves are already covered by ``tests/test_scene_router.py`` /
``tests/test_fact_router.py``; what is under test here is the *wiring*: what the runtime does with
a verdict, in which order, and what each kill switch actually switches off.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from dmbot.llm import consistency as consistency_mod
from dmbot.llm.director_msgs import scene_rejected_note_de
from dmbot.llm.fact_router import Commitment, FactFailure, FactVerdict
from dmbot.llm.scene_router import SceneFailure, SceneVerdict
from dmbot.memory.state import Combatant, WorldState
from dmbot.rag.adventure import Adventure, AdventureNpc, Scene
from dmbot.rules.scene_flow import MoveRejection, MoveTrigger, capture_scene_undo
from dmbot.runtime import SessionRuntime


# ---- fixtures: a three-scene campaign with a gate ------------------------------------------

def _adventure() -> Adventure:
    """zollhaus → schrein → pier (the last one gated behind ``brief``), the shape of the debug
    campaign in miniature. Scene ids and gate semantics are what the wiring keys off."""
    return Adventure(
        id="mini",
        title="Mini",
        start_scene="zollhaus",
        scenes=[
            Scene(
                id="zollhaus", title_de="Die Zoll-Sakristei", part=1,
                npcs_here=["Seneschall Kaad"],
                opportunities_de=["Wissen (Routine): das Zeichen", "Überreden: die Vollmacht"],
                opportunity_ids=["zeichen", "vollmacht"],
                leads_to=["schrein"],
            ),
            Scene(
                id="schrein", title_de="Schrein der Aschenheiligen", part=1,
                npcs_here=["Schwester Vall"],
                opportunities_de=["Wahrnehmung: Stemmspuren"],
                opportunity_ids=["stemmspuren"],
                leads_to=["pier"],
                exit_requires={"pier": "stemmspuren"},
            ),
            Scene(id="pier", title_de="Pier Neun", part=2),
        ],
        npcs=[
            AdventureNpc(name="Seneschall Kaad", role_de="Zöllner", wounds=9,
                         toughness_bonus=3, armour=1, faction="inquisition", goal_de="Akten"),
            AdventureNpc(name="Schwester Vall", role_de="Schreinschwester"),
        ],
        start_time_de="Tag 1, 21:00",
        deadlines=[{"id": "sirene", "label": "Mitternachtssirene", "due_in": "+3h"}],
        clocks=[{"id": "wachsamkeit", "name": "Wachsamkeit", "size": 6, "filled": 0}],
        briefing_de="Kurz vorweg.",
        mission={"title_de": "Das Ossarium zurückholen", "detail_de": "ein Knochenkasten",
                 "given_by": "Kaad"},
    )


class _FakeBrain:
    """Records the GM notes and hands back canned classifier verdicts."""

    def __init__(self, *, scene: SceneVerdict | None = None,
                 fact: FactVerdict | None = None) -> None:
        self.notes: list[str] = []
        self.scene_calls: list[dict] = []
        self.fact_calls: list[dict] = []
        self._scene = scene
        self._fact = fact
        self.last_scene_router: dict | None = None
        self.last_facts: dict | None = None

    def add_gm_note(self, channel_id: int, note: str) -> None:
        self.notes.append(note)

    async def classify_scene_move(self, *, turn_text, exits, current_title=""):
        self.scene_calls.append({"turn_text": turn_text, "exits": dict(exits),
                                 "current_title": current_title})
        self.last_scene_router = {"raw": "{}", "verdict": "", "failure": None}
        return self._scene if self._scene is not None else SceneVerdict()

    async def classify_commitment(self, *, answer_text, recipients=(), givers=()):
        self.fact_calls.append({"answer_text": answer_text, "recipients": list(recipients),
                                "givers": list(givers)})
        self.last_facts = {"raw": "{}", "verdict": None, "failure": None}
        return self._fact if self._fact is not None else FactVerdict()


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.deleted = False
        self.edits: list[str] = []

    async def edit(self, *, content: str | None = None, view=None) -> None:
        if content is not None:
            self.content = content
            self.edits.append(content)

    async def delete(self) -> None:
        self.deleted = True


class _FakeChannel:
    def __init__(self, cid: int = 7) -> None:
        self.id = cid
        self.sent: list[str] = []
        self.messages: list[_FakeMessage] = []

    async def send(self, content=None, **kwargs) -> _FakeMessage:
        self.sent.append(content or "")
        msg = _FakeMessage(content or "")
        self.messages.append(msg)
        return msg


def _state(adv: Adventure, *, scene_id: str = "zollhaus") -> WorldState:
    state = WorldState(session_id="7", scene_id=scene_id)
    state.characters = [Combatant(name="Fridolin", wounds=12, max_wounds=12)]
    return state


def _runtime(adv: Adventure | None, state: WorldState | None, brain: _FakeBrain,
             channel: _FakeChannel, **over) -> SessionRuntime:
    """A SessionRuntime with ``__init__`` skipped, wired with exactly what the turn boundary
    touches. Persistence and the two other panels are recorded, never executed."""
    rt = SessionRuntime.__new__(SessionRuntime)
    rt._brain = brain
    rt._adventure = adv
    rt._adventure_dir = None
    rt._state = {channel.id: state} if state is not None else {}
    rt._active_vc_id = channel.id
    rt._text_channel = channel
    rt._characters = SimpleNamespace(character_names=lambda: ["Fridolin"], get=lambda n: None)
    rt._testplan = None
    rt._turn_order = {}
    rt._turn_index = {}
    rt._scene_turns = {}
    rt._char_by_user = {}
    rt._speaker_names = {}
    rt._bot_a_user_id = None
    rt._autosave = False
    rt._replay_notes = {}
    rt._npc_memory = False
    rt._consistency_guard = True
    rt._scene_router = True
    rt._fact_router = True
    rt._scene_flag_gate = True
    rt._turn_time_advance = 2
    rt._scene_time_advance = 30
    rt._scene_undo_seconds = 0        # no Discord view unless a test asks for one
    rt._guidance_every = 4
    rt._player_panel_enabled = True
    rt._player_panel = None
    rt._debug_panel = None
    rt._debug_channel_id = 0
    rt._debug_channel_warned = False
    rt.persist_calls: list[object] = []
    rt.mined: list[str] = []

    rt._persist_and_refresh = lambda ch: rt.persist_calls.append(ch)
    rt.schedule_npc_memory_extraction = lambda ch, sid: rt.mined.append(sid)

    async def _noop() -> None:
        return None

    rt.update_clock_panel = _noop
    rt.update_debug_overlay = _noop
    for key, value in over.items():
        setattr(rt, key, value)
    return rt


def _run(coro):
    return asyncio.run(coro)


# ---- the rejected-move note (pure) ----------------------------------------------------------

@pytest.mark.parametrize("reason,clause", [
    (MoveRejection.UNKNOWN_SCENE, "diesen Ort gibt es hier nicht"),
    (MoveRejection.NOT_CONNECTED, "von hier aus kommt die Gruppe dort nicht hin"),
    (MoveRejection.LOCKED, "dieser Weg ist noch versperrt"),
    (MoveRejection.SAME_SCENE, "dort ist die Gruppe bereits"),
])
def test_rejected_note_names_the_reason(reason, clause) -> None:
    note = scene_rejected_note_de("pier", reason)
    assert note.startswith("Die Gruppe ist NICHT nach „pier“ gelangt — " + clause + ".")
    assert "noch am selben Ort steht" in note


def test_rejected_note_lists_the_reachable_exits() -> None:
    note = scene_rejected_note_de("pier", MoveRejection.NOT_CONNECTED,
                                  ["schrein — Schrein der Aschenheiligen"])
    assert note.endswith("Von hier aus erreichbar sind nur: schrein — Schrein der Aschenheiligen.")


def test_rejected_note_without_exits_says_nothing_about_them() -> None:
    assert "erreichbar" not in scene_rejected_note_de("pier", MoveRejection.LOCKED, [])


def test_rejected_note_tolerates_an_unknown_reason_and_an_empty_target() -> None:
    note = scene_rejected_note_de("", "etwas-neues")
    assert "der genannte Ort" in note and "dieser Wechsel ist nicht möglich" in note


# ---- the consistency-guard trap (PRD block 3) -----------------------------------------------

def _speaking_state(npc_name: str) -> WorldState:
    state = WorldState()
    state.characters = [Combatant(name="Fridolin", wounds=12, max_wounds=12)]
    state.npcs = [Combatant(name=npc_name, wounds=9, max_wounds=9, is_npc=True)]
    return state


def test_absent_named_campaign_npc_still_violates() -> None:
    # The case ADR 045 was written for: a *named* NPC of the campaign speaking in a scene he is
    # not in. Scoping must not weaken this.
    adv = _adventure()
    state = _speaking_state("Seneschall Kaad")
    violations = consistency_mod.check(
        "Seneschall Kaad sagt etwas.", state, adv.get_scene("schrein"),
        named_only=adv.npc_names(),
    )
    assert [v.kind for v in violations] == ["absent"]


def test_an_incidental_extra_never_violates_once_registered() -> None:
    # The trap named in the PRD: the NPC-memory extractor registers whatever name it reads out of
    # a transcript, so one invented runner would otherwise be "absent" in every other scene and
    # cost a regeneration each time.
    adv = _adventure()
    state = _speaking_state("Kaads Laufbursche")
    assert consistency_mod.check(
        "Kaads Laufbursche ruft etwas herüber.", state, adv.get_scene("schrein"),
        named_only=adv.npc_names(),
    ) == []
    # …and without the scoping it WOULD have violated — that is what the parameter buys.
    assert consistency_mod.check(
        "Kaads Laufbursche ruft etwas herüber.", state, adv.get_scene("schrein"),
    ) != []


def test_the_dead_check_is_never_scoped() -> None:
    adv = _adventure()
    state = _speaking_state("Kaads Laufbursche")
    state.npcs[0].wounds = 0
    violations = consistency_mod.check(
        "Kaads Laufbursche ruft etwas herüber.", state, adv.get_scene("schrein"),
        named_only=adv.npc_names(),
    )
    assert [v.kind for v in violations] == ["dead"]


def test_consistency_checker_passes_the_campaign_names(monkeypatch) -> None:
    adv = _adventure()
    state = _speaking_state("Kaads Laufbursche")
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())
    seen: dict = {}

    def _check(text, world_state, scene, *, named_only=None):
        seen["named_only"] = named_only
        return []

    monkeypatch.setattr(consistency_mod, "check", _check)
    rt.consistency_checker(_FakeChannel())("egal")
    assert seen["named_only"] == adv.npc_names()


# ---- NPC registration on scene entry (PRD block 3, story 21) --------------------------------

def test_entering_a_scene_registers_its_npcs_with_statblock_values() -> None:
    adv = _adventure()
    state = _state(adv, scene_id="")
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())

    rt._set_scene(state, "zollhaus")

    kaad = state.find("Seneschall Kaad")
    assert kaad is not None and kaad.is_npc
    assert (kaad.wounds, kaad.armour, kaad.toughness_bonus) == (9, 1, 3)
    assert (kaad.attitude, kaad.faction, kaad.goal) == ("neutral", "inquisition", "Akten")


def test_re_entering_a_scene_keeps_drifted_attitude_and_wounds() -> None:
    adv = _adventure()
    state = _state(adv, scene_id="")
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())
    rt._set_scene(state, "zollhaus")
    kaad = state.find("Seneschall Kaad")
    kaad.attitude, kaad.wounds = "hostile", 4

    rt._set_scene(state, "schrein")
    rt._set_scene(state, "zollhaus")

    assert (kaad.attitude, kaad.wounds) == ("hostile", 4)  # registration is idempotent


def test_a_departed_npc_is_listed_as_not_here_in_the_prompt() -> None:
    # Registration makes the roster grow, so the state block has to say who is actually here —
    # otherwise it hands the model the seneschal from scene one as present in scene two, which
    # is the 2026-08-22 contradiction (the NPC who left in turn 4 leading the group in turn 21).
    from dmbot.memory.state import world_state_summary_de

    adv = _adventure()
    state = _state(adv, scene_id="")
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())
    rt._set_scene(state, "zollhaus")
    rt._set_scene(state, "schrein")

    summary = world_state_summary_de(state, present=adv.get_scene("schrein").npcs_here)

    assert "NSCs in der Szene: Schwester Vall" in summary
    assert "NSCs anderswo (NICHT anwesend" in summary and "Seneschall Kaad" in summary


def test_without_a_scene_the_roster_renders_as_before() -> None:
    from dmbot.memory.state import world_state_summary_de

    adv = _adventure()
    state = _state(adv, scene_id="")
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())
    rt._set_scene(state, "zollhaus")

    summary = world_state_summary_de(state)  # present=None → the pre-D107 rendering

    assert "NSCs in der Szene: Seneschall Kaad" in summary
    assert "anderswo" not in summary


def test_registration_never_touches_a_player_character() -> None:
    adv = _adventure()
    state = _state(adv, scene_id="")
    adv.get_scene("zollhaus").npcs_here.append("Fridolin")  # a PC name on the card
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())

    rt._set_scene(state, "zollhaus")

    assert [n.name for n in state.npcs] == ["Seneschall Kaad"]


# ---- the guidance impulse (PRD block 3 / finding A5) ----------------------------------------

def test_guidance_fires_on_entry_then_every_fourth_turn() -> None:
    rt = _runtime(None, None, _FakeBrain(), _FakeChannel())
    fired = []
    for turn in range(9):
        rt._scene_turns[7] = turn
        fired.append(rt._guidance_due(7))
    assert fired == [True, False, False, False, True, False, False, False, True]


def test_guidance_can_be_switched_off_and_back_to_every_turn() -> None:
    rt = _runtime(None, None, _FakeBrain(), _FakeChannel())
    rt._scene_turns[7] = 3
    rt._guidance_every = 0
    assert rt._guidance_due(7) is False
    rt._guidance_every = 1
    assert rt._guidance_due(7) is True


# ---- close_turn: the clock (ADR 059) --------------------------------------------------------

def test_a_narrated_turn_costs_in_game_minutes() -> None:
    adv = _adventure()
    state = _state(adv)
    state.time_minutes = 1260  # Tag 1, 21:00
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Kaad schiebt euch die Tafel hin."))

    assert state.time_minutes == 1262
    assert state.time_ingame == "Tag 1, 21:02"


def test_the_time_kill_switch_freezes_the_clock() -> None:
    adv = _adventure()
    state = _state(adv)
    state.time_minutes = 1260
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel(), _turn_time_advance=0)

    _run(rt.close_turn(_FakeChannel(), "Kaad schweigt."))

    assert state.time_minutes == 1260


def test_an_expiring_deadline_queues_its_director_note() -> None:
    adv = _adventure()
    state = _state(adv)
    state.time_minutes = 1260
    state.add_deadline("Mitternachtssirene", 1, deadline_id="sirene")
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Die Uhr tickt."))

    assert any("Mitternachtssirene" in n for n in brain.notes)


# ---- close_turn: both classifiers, one latency window (ADR 057 + 058) -----------------------

def test_both_classifiers_run_on_the_same_turn_and_see_the_narration() -> None:
    adv = _adventure()
    state = _state(adv)
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Ihr tretet in den Schrein."))

    assert len(brain.scene_calls) == 1 and len(brain.fact_calls) == 1
    assert brain.scene_calls[0]["turn_text"] == "Ihr tretet in den Schrein."
    assert brain.fact_calls[0]["answer_text"] == "Ihr tretet in den Schrein."


def test_the_scene_classifier_is_offered_exits_with_their_titles() -> None:
    adv = _adventure()
    state = _state(adv)
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Ihr geht los."))

    assert brain.scene_calls[0]["exits"] == {"schrein": "Schrein der Aschenheiligen"}
    assert brain.scene_calls[0]["current_title"] == "Die Zoll-Sakristei"


def test_a_locked_exit_is_not_offered_to_the_classifier() -> None:
    adv = _adventure()
    state = _state(adv, scene_id="schrein")
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Ihr seht euch um."))

    assert brain.scene_calls == []  # no reachable exit → no call at all


def test_the_fact_classifier_is_given_the_table_and_the_scene_npcs() -> None:
    adv = _adventure()
    state = _state(adv)
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Kaad reicht die Vollmacht."))

    assert brain.fact_calls[0]["recipients"] == ["Fridolin"]
    assert brain.fact_calls[0]["givers"] == ["Seneschall Kaad"]


def test_each_classifier_has_its_own_kill_switch() -> None:
    adv = _adventure()
    state = _state(adv)
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, _FakeChannel(), _scene_router=False, _fact_router=False)

    _run(rt.close_turn(_FakeChannel(), "Nichts passiert."))

    assert brain.scene_calls == [] and brain.fact_calls == []


def test_a_raising_classifier_does_not_break_the_turn(caplog) -> None:
    adv = _adventure()
    state = _state(adv)
    brain = _FakeBrain()

    async def _boom(**_kw):
        raise RuntimeError("ollama down")

    brain.classify_scene_move = _boom
    rt = _runtime(adv, state, brain, _FakeChannel())

    with caplog.at_level(logging.ERROR):
        _run(rt.close_turn(_FakeChannel(), "Ihr geht los."))

    assert state.scene_id == "zollhaus"          # nothing moved
    assert len(brain.fact_calls) == 1            # the sibling call still ran
    assert "classifier raised" in caplog.text


# ---- close_turn: the scene move (ADR 057) ---------------------------------------------------

def test_a_clean_classifier_verdict_moves_the_pointer_and_announces_it() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    brain = _FakeBrain(scene=SceneVerdict(target_id="schrein"))
    rt = _runtime(adv, state, brain, channel)

    _run(rt.close_turn(channel, "Ihr tretet in den Schrein."))

    assert state.scene_id == "schrein"
    assert state.location == "Schrein der Aschenheiligen"
    assert any("Szene gewechselt" in m and "Schrein der Aschenheiligen" in m
               for m in channel.sent)
    assert rt.mined == ["zollhaus"]              # the departed scene is mined (ADR 044)
    assert state.time_minutes == 480 + 2 + 30    # the turn, then the scene change (ADR 059 #2)


def test_a_scene_change_registers_the_new_scene_s_npcs() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(scene=SceneVerdict(target_id="schrein")), channel)

    _run(rt.close_turn(channel, "Ihr tretet in den Schrein."))

    assert state.find("Schwester Vall") is not None


def test_the_classifier_beats_the_flag_gate_when_both_would_fire() -> None:
    adv = _adventure()
    state = _state(adv)
    state.mark_resolved("zollhaus", "zeichen")
    state.mark_resolved("zollhaus", "vollmacht")   # exhausted → the gate would push to schrein
    channel = _FakeChannel()
    brain = _FakeBrain(scene=SceneVerdict(target_id="schrein"))
    rt = _runtime(adv, state, brain, channel, _autosave=True)  # replay notes need the journal on

    _run(rt.close_turn(channel, "Ihr tretet in den Schrein."))

    assert state.scene_id == "schrein"
    note = rt.take_replay_notes(channel).get("scene_move", {})
    assert note.get("trigger") == MoveTrigger.CLASSIFIER.value


def test_the_flag_gate_moves_without_asking_the_model() -> None:
    adv = _adventure()
    state = _state(adv)
    state.mark_resolved("zollhaus", "zeichen")
    state.mark_resolved("zollhaus", "vollmacht")
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel, _autosave=True)

    _run(rt.close_turn(channel, "Mehr ist hier nicht zu holen."))

    assert state.scene_id == "schrein"
    assert rt.take_replay_notes(channel)["scene_move"]["trigger"] == MoveTrigger.FLAG_GATE.value


def test_the_flag_gate_kill_switch_leaves_an_exhausted_scene_alone() -> None:
    adv = _adventure()
    state = _state(adv)
    state.mark_resolved("zollhaus", "zeichen")
    state.mark_resolved("zollhaus", "vollmacht")
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel(), _scene_flag_gate=False)

    _run(rt.close_turn(_FakeChannel(), "Mehr ist hier nicht zu holen."))

    assert state.scene_id == "zollhaus"


def test_an_unexhausted_scene_is_never_pushed_on() -> None:
    adv = _adventure()
    state = _state(adv)
    state.mark_resolved("zollhaus", "zeichen")  # one of two
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Ihr fragt weiter."))

    assert state.scene_id == "zollhaus"


def test_a_no_verdict_turn_changes_nothing() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(scene=SceneVerdict(failure=SceneFailure.TIMEOUT)),
                  channel)

    _run(rt.close_turn(channel, "Ihr redet weiter."))

    assert state.scene_id == "zollhaus"
    assert not any("Szene gewechselt" in m for m in channel.sent)


def test_a_verdict_is_dropped_when_the_pointer_moved_during_classification(caplog) -> None:
    """``docs/lessons/snapshot-state-at-event-time.md``: the classifier may take 20 s while the
    table keeps playing. If ``!ort``, the ``<<ORT>>`` button or an undo moves the pointer in that
    window, the verdict was built against the exits of a scene the group has already left —
    honouring it would reject the move and tell the model the group did NOT go where it just
    went. It is dropped silently instead."""
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()

    class _MovingBrain(_FakeBrain):
        async def classify_scene_move(self, **kwargs):
            state.scene_id = "schrein"      # the operator got there first
            return await super().classify_scene_move(**kwargs)

    brain = _MovingBrain(scene=SceneVerdict(target_id="schrein"))
    rt = _runtime(adv, state, brain, channel)
    operator = _with_operator_channel(rt)

    with caplog.at_level(logging.WARNING):
        _run(rt.close_turn(channel, "Ihr tretet in den Schrein."))

    assert state.scene_id == "schrein"      # the human's move stands, untouched
    assert brain.notes == []                # no "Die Gruppe ist NICHT ..." correction
    assert operator.sent == []
    assert "abgelehnt" not in caplog.text


def test_an_unmoved_pointer_still_lets_the_verdict_through() -> None:
    # The guard must only fire on a real concurrent move — the normal turn is unaffected.
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(scene=SceneVerdict(target_id="schrein")), channel)

    _run(rt.close_turn(channel, "Ihr tretet in den Schrein."))

    assert state.scene_id == "schrein"


# ---- a rejected move is loud (ADR 057 #5) ---------------------------------------------------

def _with_operator_channel(rt: SessionRuntime, cid: int = 42) -> _FakeChannel:
    """Give ``rt`` a resolvable DM_DEBUG_CHANNEL and hand it back — the only configuration in
    which an operator line is allowed to be posted anywhere."""
    operator = _FakeChannel(cid)
    rt._debug_channel_id = cid
    rt._text_channel.guild = SimpleNamespace(
        get_channel=lambda i: operator if i == cid else None)
    return operator


def test_a_locked_target_queues_a_director_note_and_an_operator_line(caplog) -> None:
    adv = _adventure()
    state = _state(adv, scene_id="schrein")
    channel = _FakeChannel()
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, channel)
    operator = _with_operator_channel(rt)

    with caplog.at_level(logging.WARNING):
        _run(rt.request_scene_move(channel, "pier", trigger=MoveTrigger.CLASSIFIER))

    assert state.scene_id == "schrein"
    assert any("dieser Weg ist noch versperrt" in n for n in brain.notes)
    assert any("abgelehnt" in m for m in operator.sent)
    assert "stemmspuren" in caplog.text          # the unlocking element: operator only


def test_the_rejection_line_needs_a_configured_operator_channel() -> None:
    # Without DM_DEBUG_CHANNEL (the .env.example default) the "operator" channel IS the game
    # channel, and the line names a scene the players must not hear about. Log + [Regie] note
    # carry it instead; the game channel stays silent.
    adv = _adventure()
    state = _state(adv, scene_id="schrein")
    channel = _FakeChannel()
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, channel)   # _debug_channel_id = 0

    _run(rt.request_scene_move(channel, "pier"))

    assert channel.sent == []
    assert any("dieser Weg ist noch versperrt" in n for n in brain.notes)


def test_the_rejection_line_names_the_scene_title_not_its_id() -> None:
    adv = _adventure()
    state = _state(adv, scene_id="schrein")
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)
    operator = _with_operator_channel(rt)

    _run(rt.request_scene_move(channel, "pier"))

    assert operator.sent == ["🚫 Szenenwechsel nach „Pier Neun“ abgelehnt — die Gruppe bleibt, "
                             "wo sie ist. (Grund im Log; die Spielleitung bekommt einen "
                             "Hinweis.)"]
    assert "pier" not in operator.sent[0]


def test_an_unknown_target_falls_back_to_the_bare_id() -> None:
    # Nothing to look a title up for — but an invented id is the model's, not the campaign's,
    # so naming it leaks nothing.
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)
    operator = _with_operator_channel(rt)

    _run(rt.request_scene_move(channel, "kanalisation"))

    assert any("„kanalisation“" in m for m in operator.sent)


def test_the_operator_line_never_names_the_unlocking_element() -> None:
    adv = _adventure()
    state = _state(adv, scene_id="schrein")
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)
    operator = _with_operator_channel(rt)

    _run(rt.request_scene_move(channel, "pier"))

    assert not any("stemmspuren" in m for m in operator.sent)   # spoiler discipline


def test_an_unknown_target_is_rejected_with_its_own_reason() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, channel)

    _run(rt.request_scene_move(channel, "kanalisation"))

    assert any("diesen Ort gibt es hier nicht" in n for n in brain.notes)
    assert state.scene_id == "zollhaus"


def test_a_permitted_move_queues_no_correction() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    brain = _FakeBrain()
    rt = _runtime(adv, state, brain, channel)

    _run(rt.request_scene_move(channel, "schrein"))

    assert brain.notes == []
    assert state.scene_id == "schrein"


# ---- the undo control (ADR 057 #4) ----------------------------------------------------------

class _FakeInteraction:
    def __init__(self) -> None:
        self.responses: list[str] = []

    async def edit_original_response(self, *, content: str) -> None:
        self.responses.append(content)


def test_undo_restores_the_pointer_and_the_in_game_time() -> None:
    adv = _adventure()
    state = _state(adv)
    state.time_minutes = 1260
    state.time_ingame = "Tag 1, 21:00"
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)
    undo = capture_scene_undo(state, "schrein", trigger=MoveTrigger.CLASSIFIER)

    _run(rt.move_scene(channel, "schrein", trigger=MoveTrigger.CLASSIFIER))
    assert state.scene_id == "schrein" and state.time_minutes == 1290

    interaction = _FakeInteraction()
    _run(rt._make_scene_undo(channel, undo)(interaction))

    assert state.scene_id == "zollhaus"
    assert (state.time_minutes, state.time_ingame) == (1260, "Tag 1, 21:00")
    assert any("zurückgenommen" in r for r in interaction.responses)


def test_a_second_undo_click_is_a_no_op() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)
    undo = capture_scene_undo(state, "schrein", trigger=MoveTrigger.CLASSIFIER)
    _run(rt.move_scene(channel, "schrein", trigger=MoveTrigger.CLASSIFIER))
    _run(rt._make_scene_undo(channel, undo)(_FakeInteraction()))

    interaction = _FakeInteraction()
    _run(rt._make_scene_undo(channel, undo)(interaction))

    assert state.scene_id == "zollhaus"                      # unchanged, nothing clobbered
    assert any("Nicht mehr aktuell" in r for r in interaction.responses)


def test_the_announcement_carries_an_undo_control_when_one_is_configured() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    sent: list[dict] = []

    async def _send(ch, content=None, *, view=None, embed=None):
        sent.append({"content": content, "view": view})
        return _FakeMessage(content or "")

    rt = _runtime(adv, state, _FakeBrain(), channel, _scene_undo_seconds=60)
    rt._send_with_retry = _send

    _run(rt.move_scene(channel, "schrein", trigger=MoveTrigger.FLAG_GATE))

    assert sent and sent[0]["view"] is not None
    assert sent[0]["view"].timeout == 60.0


def test_undo_seconds_zero_posts_the_line_without_a_control() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    sent: list[dict] = []

    async def _send(ch, content=None, *, view=None, embed=None):
        sent.append({"content": content, "view": view})
        return _FakeMessage(content or "")

    rt = _runtime(adv, state, _FakeBrain(), channel, _scene_undo_seconds=0)
    rt._send_with_retry = _send

    _run(rt.move_scene(channel, "schrein"))

    assert sent and sent[0]["view"] is None


# ---- hard facts (ADR 058) -------------------------------------------------------------------

def test_a_handed_over_item_becomes_a_world_state_fact() -> None:
    adv = _adventure()
    state = _state(adv)
    state.time_minutes = 1260
    verdict = FactVerdict(commitment=Commitment(kind="item", text="Zollvollmacht",
                                                to="Fridolin", by="Seneschall Kaad"))
    rt = _runtime(adv, state, _FakeBrain(fact=verdict), _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Kaad reicht dir die Zollvollmacht."))

    fact = state.find_fact("Zollvollmacht", kind="item")
    assert fact is not None and fact.holder == "Fridolin" and fact.source == "Seneschall Kaad"
    assert "Zollvollmacht" in state.find("Fridolin").inventory


def test_the_same_item_is_not_recorded_twice() -> None:
    adv = _adventure()
    state = _state(adv)
    verdict = FactVerdict(commitment=Commitment(kind="item", text="Zollvollmacht",
                                                to="Fridolin"))
    rt = _runtime(adv, state, _FakeBrain(fact=verdict), _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Kaad reicht dir die Zollvollmacht."))
    _run(rt.close_turn(_FakeChannel(), "Du hältst die Zollvollmacht hoch."))

    assert len(state.open_facts("item")) == 1


def test_a_failed_fact_verdict_writes_nothing() -> None:
    adv = _adventure()
    state = _state(adv)
    rt = _runtime(adv, state, _FakeBrain(fact=FactVerdict(failure=FactFailure.OFF_LIST)),
                  _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "Kaad sagt nichts zu."))

    assert state.facts == []


def test_prose_instead_of_a_label_is_refused_by_the_writer() -> None:
    # The classifier's own validation is tested in tests/test_fact_router.py; this pins that the
    # *writer* refuses too, so a bypassed or future caller can't push narration into hard state.
    adv = _adventure()
    state = _state(adv)
    long_text = "Kaad " + "x" * 200
    verdict = FactVerdict(commitment=Commitment(kind="item", text=long_text, to="Fridolin"))
    rt = _runtime(adv, state, _FakeBrain(fact=verdict), _FakeChannel())

    _run(rt.close_turn(_FakeChannel(), "irgendwas"))

    assert state.facts == []


# ---- session start: the adventure's own clock and objective (ADR 059 #1 / ADR 058 #3) -------

def test_session_start_seeds_time_deadline_clock_and_mission() -> None:
    adv = _adventure()
    state = _state(adv)
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())

    rt._seed_adventure_state(state)

    assert state.time_minutes == 1260 and state.time_ingame == "Tag 1, 21:00"
    assert [d.id for d in state.deadlines] == ["sirene"]
    assert state.deadlines[0].due_minutes == 1440       # +3h → midnight
    assert [c.id for c in state.clocks] == ["wachsamkeit"]
    mission = state.mission()
    assert mission is not None and mission.title == "Das Ossarium zurückholen"
    assert mission.detail == "ein Knochenkasten" and mission.given_by == "Kaad"


def test_seeding_twice_neither_resets_the_clock_nor_duplicates_anything() -> None:
    adv = _adventure()
    state = _state(adv)
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())
    rt._seed_adventure_state(state)
    state.advance_time(45)

    rt._seed_adventure_state(state)               # a re-join mid-session

    assert state.time_minutes == 1305
    assert len(state.deadlines) == 1 and len(state.clocks) == 1
    assert len([q for q in state.quests if q.is_mission]) == 1


def test_an_adventure_without_a_clock_keeps_the_default_start() -> None:
    adv = Adventure(id="bare", start_scene="a", scenes=[Scene(id="a", title_de="A")])
    state = WorldState()
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())

    rt._seed_adventure_state(state)

    assert state.time_minutes == 480 and state.deadlines == [] and state.mission() is None


# ---- identity: character name at the source (PRD "Identity", findings A4/B4) ----------------

def test_a_player_line_enters_the_prompt_under_the_character_name() -> None:
    lines: list[tuple[str, str]] = []
    rt = _runtime(None, None, _FakeBrain(), _FakeChannel())
    rt._brain.add_player_line = lambda cid, name, text: lines.append((name, text))
    rt._last_stt_ms = {}
    rt._char_by_user = {42: "Rektalus Zerfickus"}
    rt._speaker_names["SezBoss69"] = rt.character_name_for(42, "SezBoss69")

    rt._on_transcript("SezBoss69", "Ich frage nach der Vollmacht.", 1.0, 200.0, True)

    assert lines == [("Rektalus Zerfickus", "Ich frage nach der Vollmacht.")]


def test_a_renamed_player_is_still_resolved_by_user_id() -> None:
    rt = _runtime(None, None, _FakeBrain(), _FakeChannel())
    rt._char_by_user = {42: "Rektalus Zerfickus"}
    # The nickname changed mid-session; the alias map still holds the OLD display name only.
    rt._characters = SimpleNamespace(get=lambda n: None, character_names=lambda: [])
    assert rt.character_name_for(42, "SezBoss70") == "Rektalus Zerfickus"


def test_an_unknown_speaker_keeps_the_display_name() -> None:
    rt = _runtime(None, None, _FakeBrain(), _FakeChannel())
    rt._characters = SimpleNamespace(get=lambda n: None, character_names=lambda: [])
    assert rt.character_name_for(None, "Gast") == "Gast"
    assert rt.prompt_speaker_name("Gast") == "Gast"


def test_identities_are_seeded_from_the_voice_channel_members() -> None:
    rt = _runtime(None, None, _FakeBrain(), _FakeChannel())
    rt._characters = SimpleNamespace(
        get=lambda n: SimpleNamespace(name="Fridolin") if n == "Pr0degie" else None,
        character_names=lambda: ["Fridolin"],
    )
    members = [
        SimpleNamespace(id=1, display_name="Pr0degie", bot=False),
        SimpleNamespace(id=2, display_name="Gast", bot=False),
        SimpleNamespace(id=3, display_name="MusicBot", bot=True),
    ]
    rt._seed_speaker_identities(SimpleNamespace(members=members))

    assert rt._char_by_user == {1: "Fridolin"}
    assert rt.character_name_for(2, "Gast") == "Gast"


# ---- the player panel (PRD stories 14-17) ---------------------------------------------------

def test_the_panel_posts_once_and_is_edited_in_place() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)

    _run(rt.update_player_panel())
    first = rt._player_panel
    _run(rt.update_player_panel())

    assert len(channel.messages) == 1 and rt._player_panel is first
    assert first.edits  # the second call edited instead of posting again


def test_the_panel_is_re_anchored_after_a_turn() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)

    _run(rt.update_player_panel())
    old = rt._player_panel
    _run(rt.update_player_panel(reanchor=True))

    assert old.deleted and rt._player_panel is not old
    assert len(channel.messages) == 2


def test_the_panel_shows_place_goal_and_deadline() -> None:
    adv = _adventure()
    state = _state(adv)
    rt = _runtime(adv, state, _FakeBrain(), _FakeChannel())
    rt._seed_adventure_state(state)

    text = rt._panel_text()

    assert "📍 **Wo ihr seid:** Die Zoll-Sakristei" in text
    assert "🎯 **Was ihr wollt:** Das Ossarium zurückholen — ein Knochenkasten (von Kaad)" in text
    assert "🕐 **Wie spät es ist:** Tag 1, 21:00 (Abend)" in text
    assert "⏳ **Mitternachtssirene**" in text


def test_the_panel_kill_switch_posts_nothing() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel, _player_panel_enabled=False)

    _run(rt.update_player_panel())

    assert channel.messages == []


def test_a_scene_change_refreshes_the_panel() -> None:
    adv = _adventure()
    state = _state(adv)
    channel = _FakeChannel()
    rt = _runtime(adv, state, _FakeBrain(), channel)
    _run(rt.update_player_panel())
    panel = rt._player_panel

    _run(rt.move_scene(channel, "schrein", trigger=MoveTrigger.COMMAND, announce=False))

    assert any("Schrein der Aschenheiligen" in e for e in panel.edits)
