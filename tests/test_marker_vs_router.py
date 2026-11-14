"""Who decides the turn's test — the narration marker or the roll router (D140, amends D43/ADR 018).

On the Claude backend the narration model's inline ``<<TEST …>>`` marker decides (skill,
difficulty and target are what gets rolled); the router only decides when Opus emitted no
marker, or for an invalid one. On Ollama the router wins as before (D43) — except the safety
net on both backends: a marker repeated for the same character + skill with no roll in between
is honoured when the router posted nothing for that character (the "suspended moment" loop of
the 2026-11-14 evening). A Manifest request still covers the psyker's action: no double roll.
"""

from __future__ import annotations

import asyncio
import random
import types

from dmbot.llm.roll_router import MarkerRepeats, marker_decides
from dmbot.rules import profile as profile_mod
from dmbot.rules.characters import Character, CharacterStore, resolve_target
from dmbot.rules.marker import ManifestRequest, extract_tests
from dmbot.rules.marker import TestRequest as _Req
from dmbot.voice.dicecog import DiceCog

from fakes import make_brain, make_runtime

_IM = profile_mod.load("imperium_maledictum")
_CH = types.SimpleNamespace(guild=None)


def _party() -> CharacterStore:
    return CharacterStore([
        Character.from_dict({
            "name": "Fridolin",
            "characteristics": {"Fel": 40, "Wil": 45},
            "skills": {"Überreden": 42, "Nahkampf": 35, "Psi-Meisterschaft": 45},
            "psyker": True,
            "known_powers": ["Smite"],
        }),
        Character.from_dict({
            "name": "Rektalus",
            "characteristics": {"Per": 38},
            "skills": {"Wahrnehmung": 50, "Heimlichkeit": 30},
        }),
    ])


def _marker(text: str) -> _Req:
    _, reqs = extract_tests(text, _IM)
    return reqs[0]


class _Table:
    """A DiceCog on a fake runtime whose brain is scripted per turn; records every dice button."""

    def __init__(self, *, backend: str | None) -> None:
        self.markers: list[_Req] = []
        self.manifests: list[ManifestRequest] = []
        self.actions: list[tuple[str, str]] = []
        self.verdicts: dict[str, _Req | None] = {}
        self.classified: list[str] = []
        self.posted: list[_Req] = []
        self.manifest_posted: list[ManifestRequest] = []

        async def classify_test(*, action, character, skills):
            self.classified.append(character)
            return self.verdicts.get(character)

        stats = {"backend": backend} if backend else {"eval_count": 10}
        brain = make_brain(
            profile=_IM,
            take_pending_tests=lambda cid: self._take("markers"),
            take_pending_manifests=lambda cid: self._take("manifests"),
            last_actions=lambda cid: list(self.actions),
            classify_test=classify_test,
            last_llm_stats=stats,
            last_router=None,
        )
        rt = make_runtime(brain=brain, profile=_IM)
        rt._roll_router = True
        rt._characters = _party()
        rt._brain_channel = lambda channel: 1
        self.rt = rt
        self.cog = DiceCog(None, rt)

        async def _post(channel, req):
            self.posted.append(req)

        async def _post_manifest(channel, req):
            self.manifest_posted.append(req)

        self.cog._post_dice_button = _post
        self.cog._post_manifest_button = _post_manifest

    def _take(self, kind: str) -> list:
        items = getattr(self, kind)
        setattr(self, kind, [])
        return items

    def turn(self, *, markers=(), actions=(), verdicts=None, manifests=()) -> list[_Req]:
        self.markers = [_marker(m) for m in markers]
        self.manifests = list(manifests)
        self.actions = list(actions)
        self.verdicts = dict(verdicts or {})
        self.classified = []
        self.posted = []
        asyncio.run(self.cog._handle_dice(_CH))
        return self.posted


# -- the pure switch ------------------------------------------------------------------------

def test_marker_decides_only_when_claude_narrated_the_turn() -> None:
    assert marker_decides({"backend": "claude", "eval_count": 3})
    assert not marker_decides({"backend": "ollama"})  # fallback / !backend ollama: Nemo narrated
    assert not marker_decides({"eval_count": 3})      # Ollama alone: no failover, no backend key
    assert not marker_decides(None)


def test_marker_repeats_remembers_one_turn_and_forgets_on_a_roll() -> None:
    rep = MarkerRepeats()
    key = ("fridolin", "überreden")
    assert rep.turn(1, {key}) == set()        # first time: nothing repeated
    assert rep.turn(1, {key}) == {key}        # same marker the next turn: repeated
    rep.rolled(1)
    assert rep.turn(1, {key}) == set()        # a roll in between resets it
    assert rep.turn(2, {key}) == set()        # per channel
    assert rep.turn(1, set()) == set()
    assert rep.turn(1, {key}) == set()        # a turn without the marker breaks the chain


# -- Claude: the marker decides ----------------------------------------------------------------

def test_on_claude_the_marker_decides_skill_and_difficulty() -> None:
    t = _Table(backend="claude")
    posted = t.turn(
        markers=["<<TEST Überreden Leicht für Fridolin>>"],
        actions=[("Fridolin", "Ich rede ihm gut zu.")],
        verdicts={"Fridolin": _Req(skill="Überreden", difficulty="Herausfordernd",
                                          target_name="Fridolin")},
    )
    assert t.classified == []  # the router is not asked
    assert [(r.skill, r.difficulty, r.target_name) for r in posted] == [("Überreden", "Leicht", "Fridolin")]


def test_on_claude_without_a_marker_the_router_decides() -> None:
    t = _Table(backend="claude")
    posted = t.turn(
        actions=[("Rektalus", "Ich schleiche mich an.")],
        verdicts={"Rektalus": _Req(skill="Heimlichkeit", difficulty="Schwer",
                                          target_name="Rektalus")},
    )
    assert t.classified == ["Rektalus"]
    assert [(r.skill, r.difficulty) for r in posted] == [("Heimlichkeit", "Schwer")]


def test_on_claude_an_invalid_marker_falls_back_to_the_router() -> None:
    t = _Table(backend="claude")
    posted = t.turn(
        markers=["<<TEST Bestechen Leicht für Fridolin>>"],  # not on Fridolin's sheet
        actions=[("Fridolin", "Ich schiebe ihm Geld rüber.")],
        verdicts={"Fridolin": _Req(skill="Überreden", difficulty="Routine",
                                          target_name="Fridolin")},
    )
    assert t.classified == ["Fridolin"]
    assert [(r.skill, r.difficulty) for r in posted] == [("Überreden", "Routine")]


def test_on_claude_an_invalid_marker_does_not_override_a_valid_one() -> None:
    # One valid marker for Fridolin, one unknown-character marker: Fridolin's stays the
    # marker's, the router classifies only the speakers no valid marker covers.
    t = _Table(backend="claude")
    posted = t.turn(
        markers=["<<TEST Überreden Leicht für Fridolin>>", "<<TEST Wahrnehmung für Niemand>>"],
        actions=[("Fridolin", "Ich rede."), ("Rektalus", "Ich sehe mich um.")],
        verdicts={"Rektalus": _Req(skill="Wahrnehmung", target_name="Rektalus"),
                  "Fridolin": _Req(skill="Nahkampf", target_name="Fridolin")},
    )
    assert t.classified == ["Rektalus"]
    assert sorted((r.target_name, r.skill) for r in posted) == [
        ("Fridolin", "Überreden"), ("Rektalus", "Wahrnehmung")]


def test_on_claude_a_manifest_covers_the_psykers_marker() -> None:
    t = _Table(backend="claude")
    posted = t.turn(
        markers=["<<TEST Psi-Meisterschaft für Fridolin>>"],
        manifests=[ManifestRequest(power="Smite", target_name="Fridolin")],
        actions=[("Fridolin", "Ich schleudere den Warp auf ihn.")],
    )
    assert posted == []                       # no double roll
    assert [m.power for m in t.manifest_posted] == ["Smite"]
    assert t.classified == []


# -- Ollama: the router wins (D43), the repeat safety net ---------------------------------------

def test_on_ollama_the_router_wins_and_the_marker_is_discarded() -> None:
    t = _Table(backend=None)
    posted = t.turn(
        markers=["<<TEST Überreden Leicht für Fridolin>>"],
        actions=[("Fridolin", "Ich rede ihm gut zu.")],
        verdicts={"Fridolin": _Req(skill="Überreden", difficulty="Herausfordernd",
                                          target_name="Fridolin")},
    )
    assert [(r.skill, r.difficulty) for r in posted] == [("Überreden", "Herausfordernd")]


def test_fallback_narration_on_claude_config_is_treated_as_ollama() -> None:
    t = _Table(backend="ollama")
    posted = t.turn(markers=["<<TEST Überreden Leicht für Fridolin>>"],
                    actions=[("Fridolin", "Ich rede.")], verdicts={"Fridolin": None})
    assert posted == [] and t.classified == ["Fridolin"]


def test_safety_net_honours_a_repeated_marker_the_router_keeps_refusing() -> None:
    t = _Table(backend=None)
    marker = "<<TEST Überreden Schwierig für Fridolin>>"
    first = t.turn(markers=[marker], actions=[("Fridolin", "Ich rede weiter.")],
                   verdicts={"Fridolin": None})
    assert first == []                        # once: the router's "no test" stands
    second = t.turn(markers=[marker], actions=[("Fridolin", "Na komm schon.")],
                    verdicts={"Fridolin": None})
    assert [(r.skill, r.difficulty, r.target_name) for r in second] == [
        ("Überreden", "Schwierig", "Fridolin")]


def test_safety_net_needs_the_same_skill_and_character() -> None:
    t = _Table(backend=None)
    t.turn(markers=["<<TEST Überreden für Fridolin>>"], actions=[("Fridolin", "x")],
           verdicts={"Fridolin": None})
    assert t.turn(markers=["<<TEST Nahkampf für Fridolin>>"], actions=[("Fridolin", "y")],
                  verdicts={"Fridolin": None}) == []
    assert t.turn(markers=["<<TEST Wahrnehmung für Rektalus>>"], actions=[("Fridolin", "z")],
                  verdicts={"Fridolin": None}) == []


def test_safety_net_resets_after_a_roll() -> None:
    t = _Table(backend=None)
    marker = "<<TEST Überreden für Fridolin>>"
    t.turn(markers=[marker], actions=[("Fridolin", "x")], verdicts={"Fridolin": None})
    t.cog._repeats.rolled(1)                  # what the dice-button callbacks call
    assert t.turn(markers=[marker], actions=[("Fridolin", "y")], verdicts={"Fridolin": None}) == []


def test_safety_net_stays_out_when_the_router_posted_for_that_character() -> None:
    t = _Table(backend=None)
    marker = "<<TEST Überreden für Fridolin>>"
    t.turn(markers=[marker], actions=[("Fridolin", "x")], verdicts={"Fridolin": None})
    posted = t.turn(markers=[marker], actions=[("Fridolin", "Ich zahle.")],
                    verdicts={"Fridolin": _Req(skill="Nahkampf", target_name="Fridolin")})
    assert [r.skill for r in posted] == ["Nahkampf"]  # one button per action, the router's


def test_safety_net_respects_a_manifest() -> None:
    t = _Table(backend=None)
    marker = "<<TEST Überreden für Fridolin>>"
    t.turn(markers=[marker], actions=[("Fridolin", "x")], verdicts={"Fridolin": None})
    posted = t.turn(markers=[marker], actions=[("Fridolin", "y")], verdicts={"Fridolin": None},
                    manifests=[ManifestRequest(power="Smite", target_name="Fridolin")])
    assert posted == []


def test_a_dice_button_press_clears_the_repeat_memory() -> None:
    t = _Table(backend=None)
    t.rt._rng = random.Random(3)
    marker = "<<TEST Überreden für Fridolin>>"
    t.turn(markers=[marker], actions=[("Fridolin", "x")], verdicts={"Fridolin": None})

    async def _quiet(*args, **kwargs):
        return None

    t.cog._show_result = _quiet
    t.cog._finish_roll = _quiet
    t.cog._dice_animation_on = lambda: False
    t.cog._fate_holder = lambda channel, who: None
    other = _marker("<<TEST Wahrnehmung für Rektalus>>")
    resolved = resolve_target(_IM, t.rt._characters, skill="Wahrnehmung", target_name="Rektalus")
    roll = t.cog._make_dice_roll(_CH, other, resolved)
    asyncio.run(roll(types.SimpleNamespace(message=None)))
    assert t.turn(markers=[marker], actions=[("Fridolin", "y")], verdicts={"Fridolin": None}) == []
