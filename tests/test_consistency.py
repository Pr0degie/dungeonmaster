"""Consistency guard (ADR 045): the pure check + the regenerate-once wiring in DMBrain.

The check must be conservative — a false positive costs a full regeneration of latency, so the
suite pins both directions: dead/absent NPCs with a speech attribution HIT; mere mention,
past tense (memories), quoted recounting, indefinite references („ein Kultist ruft") and
ambiguous name tokens DON'T. The DMBrain wiring is pinned on: exactly one retry, fail-open on a
still-violating retry, first answer kept when the retry is empty, marker hygiene.
"""

from __future__ import annotations

import asyncio

from dmbot.llm.consistency import Violation, check, retry_nudge_de
from dmbot.memory.state import Combatant, WorldState
from dmbot.orchestrator import DMBrain
from dmbot.rag.adventure import Scene
from dmbot.rules import profile as profile_mod

_IM = profile_mod.load("imperium_maledictum")


def _npc(name: str, wounds: int = 10) -> Combatant:
    return Combatant(name=name, wounds=wounds, max_wounds=10, is_npc=True)


def _state(*npcs: Combatant, characters: list[Combatant] | None = None) -> WorldState:
    return WorldState(npcs=list(npcs), characters=characters or [])


def _scene(*here: str) -> Scene:
    return Scene(id="s1", title_de="Testszene", npcs_here=list(here))


# --- dead NPC speaks ------------------------------------------------------------------------


def test_dead_npc_name_then_verb_hits() -> None:
    state = _state(_npc("Grendel", wounds=0))
    v = check("Grendel sagt: Verschwindet von hier.", state, None)
    assert [x.kind for x in v] == ["dead"] and v[0].npc == "Grendel"


def test_dead_npc_verb_then_name_hits() -> None:
    state = _state(_npc("Grendel", wounds=0))
    assert check("„Verschwindet!“, ruft Grendel euch entgegen.", state, None)


def test_dead_npc_script_style_hits() -> None:
    state = _state(_npc("Grendel", wounds=0))
    assert check("Grendel: „Ihr hättet nicht kommen dürfen.“", state, None)


def test_dead_npc_gap_words_before_verb_hit() -> None:
    # up to two lowercase words between name and verb („nickt und sagt") still attribute speech
    state = _state(_npc("Grendel", wounds=0))
    assert check("Grendel nickt und sagt: Na gut.", state, None)


def test_mere_mention_of_dead_npc_is_allowed() -> None:
    state = _state(_npc("Grendel", wounds=0))
    text = "Ihr findet Grendels Leiche hinter der Theke. Der Anblick von Grendel schmerzt."
    assert check(text, state, None) == []


def test_past_tense_speech_is_allowed() -> None:
    # memories/recaps are narrated in Präteritum — exactly the allowed mention case
    state = _state(_npc("Grendel", wounds=0))
    assert check("Grendel sagte damals: Vertraue niemandem.", state, None) == []


def test_quoted_recounting_is_allowed() -> None:
    # a living NPC quoting the dead one — the attribution inside the quotes must not count
    state = _state(_npc("Grendel", wounds=0), _npc("Janelle"))
    assert check("„Grendel sagt so was nie“, grinst Janelle.", state, None) == []


def test_guillemet_quotes_are_stripped_too() -> None:
    state = _state(_npc("Grendel", wounds=0))
    assert check("Janelle erinnert sich: »Grendel ruft immer nach Hilfe.«", state, None) == []


def test_bare_name_colon_line_does_not_hit() -> None:
    # script style needs the opening quote — a bare "Name: …" list line is no attribution
    state = _state(_npc("Grendel", wounds=0))
    assert check("Grendel: tot aufgefunden im Lagerraum.", state, None) == []


def test_umlaut_name_hits_and_respects_boundaries() -> None:
    state = _state(_npc("Käthe", wounds=0))
    assert check("Käthe flüstert dir etwas zu.", state, None)
    # the genitive form is a different word — mere mention, no hit (word boundary holds)
    assert check("Käthes Schwert liegt noch da.", state, None) == []


def test_indefinite_reference_does_not_hit() -> None:
    # generic statblock names double as anonymous extras: „ein Kultist" is not THE Kultist
    state = _state(_npc("Ganger", wounds=0))
    assert check("Ein Ganger ruft nach Verstärkung.", state, None) == []
    assert check("Mehrere Ganger schreien durcheinander.", state, None) == []
    # a definite reference still hits
    assert check("Der Ganger ruft nach Verstärkung.", state, None)


# --- absent NPC speaks ----------------------------------------------------------------------


def test_absent_npc_speaking_hits() -> None:
    state = _state(_npc("Janelle"), _npc("Nedabeus"))
    scene = _scene("Nedabeus")
    v = check("Janelle antwortet: Das weiß ich nicht.", state, scene)
    assert [x.kind for x in v] == ["absent"] and v[0].npc == "Janelle"


def test_present_npc_speaking_is_fine() -> None:
    state = _state(_npc("Janelle"))
    assert check("Janelle antwortet: Das weiß ich nicht.", state, _scene("Janelle")) == []


def test_absent_check_needs_a_scene() -> None:
    # without a scene card there is no notion of "here" — only the dead check runs
    state = _state(_npc("Janelle"))
    assert check("Janelle antwortet dir leise.", state, None) == []


def test_absent_mention_is_allowed() -> None:
    state = _state(_npc("Janelle"))
    scene = _scene("Nedabeus")
    assert check("Ihr fragt euch, wo Janelle wohl steckt.", state, scene) == []


def test_npcs_here_matching_is_case_insensitive() -> None:
    state = _state(_npc("Janelle"))
    assert check("Janelle sagt: Hallo.", state, _scene("janelle ")) == []


# --- names: tokens, ambiguity, titles --------------------------------------------------------


def test_multiword_name_matches_per_token() -> None:
    state = _state(_npc("Vidame Gullar", wounds=0))
    assert check("Gullar spricht mit brüchiger Stimme.", state, None)
    assert check("Vidame Gullar spricht mit brüchiger Stimme.", state, None)


def test_title_token_alone_does_not_hit() -> None:
    # "Lord" is a title, not an alias — another lord speaking must not flag Lord Kaltos
    state = _state(_npc("Lord Kaltos", wounds=0))
    assert check("Der Lord sagt: Tretet ein.", state, None) == []
    assert check("Kaltos sagt: Tretet ein.", state, None)


def test_token_shared_between_npcs_is_ambiguous() -> None:
    # "Kultist" appears in two registered names → the bare token never flags either
    state = _state(_npc("Kultist", wounds=0), _npc("Verfluchter Kultist", wounds=0))
    assert check("Der Kultist ruft ein Gebet.", state, None) == []
    # the unambiguous full name still flags
    v = check("Verfluchter Kultist ruft ein Gebet.", state, None)
    assert [x.npc for x in v] == ["Verfluchter Kultist"]


def test_token_colliding_with_party_name_is_dropped() -> None:
    state = _state(
        _npc("Lord Fridolin", wounds=0),
        characters=[Combatant(name="Fridolin", wounds=12, max_wounds=12)],
    )
    # "Fridolin" alone is the PC — never attribute it to the dead NPC
    assert check("Fridolin sagt: Ich übernehme das.", state, None) == []


def test_dead_wins_over_absent() -> None:
    # a dead NPC speaking in a scene he's also absent from reports the dead violation only
    state = _state(_npc("Grendel", wounds=0))
    v = check("Grendel sagt: Hallo.", state, _scene("Janelle"))
    assert [x.kind for x in v] == ["dead"]


def test_empty_inputs_are_safe() -> None:
    assert check("", _state(_npc("X")), None) == []
    assert check("Text.", None, None) == []
    assert check("Text.", _state(), None) == []


def test_retry_nudge_contains_the_concrete_hint() -> None:
    v = Violation(kind="dead", npc="Grendel", hint_de="Grendel ist tot und kann nicht sprechen.")
    nudge = retry_nudge_de([v])
    assert "KORREKTUR" in nudge and "Grendel ist tot" in nudge


# --- DMBrain wiring: regenerate once, fail-open ----------------------------------------------


class _SeqClient:
    """Returns the queued answers in order and records every prompt it was asked."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.calls: list[str] = []

    async def chat(self, system, messages, options=None):
        self.calls.append(messages[-1]["content"])
        return self.answers.pop(0) if self.answers else "Es bleibt still."

    async def aclose(self) -> None:
        pass


def _checker_for(state: WorldState):
    return lambda text: check(text, state, None)


def test_violation_regenerates_once_with_korrektur_nudge() -> None:
    state = _state(_npc("Grendel", wounds=0))
    client = _SeqClient(["Grendel sagt: Hallo.", "Grendels Leiche liegt still da."])
    brain = DMBrain(client, profile=_IM)
    brain.add_player_line(1, "Timo", "Ich sehe mich um.")
    answer = asyncio.run(brain.respond(1, check=_checker_for(state)))
    assert answer == "Grendels Leiche liegt still da."
    assert len(client.calls) == 2 and "KORREKTUR" in client.calls[1]
    # only the kept answer lands in history, paired with the ORIGINAL user message
    hist = brain._history[1]
    assert hist[-1]["content"] == answer and "KORREKTUR" not in hist[-2]["content"]


def test_still_violating_retry_is_delivered_anyway() -> None:
    # fail-open: max ONE retry — a second violation is delivered, never regenerated again
    state = _state(_npc("Grendel", wounds=0))
    client = _SeqClient(["Grendel sagt: Hallo.", "Grendel ruft: Immer noch hier!"])
    brain = DMBrain(client, profile=_IM)
    brain.add_player_line(1, "Timo", "Ich sehe mich um.")
    answer = asyncio.run(brain.respond(1, check=_checker_for(state)))
    assert answer == "Grendel ruft: Immer noch hier!"
    assert len(client.calls) == 2  # exactly one regenerate, not a loop


def test_clean_answer_is_not_regenerated() -> None:
    state = _state(_npc("Grendel", wounds=0))
    client = _SeqClient(["Die Halle liegt verlassen da."])
    brain = DMBrain(client, profile=_IM)
    brain.add_player_line(1, "Timo", "Ich sehe mich um.")
    answer = asyncio.run(brain.respond(1, check=_checker_for(state)))
    assert answer == "Die Halle liegt verlassen da." and len(client.calls) == 1


def test_raising_checker_fails_open() -> None:
    client = _SeqClient(["Die Halle liegt verlassen da."])
    brain = DMBrain(client, profile=_IM)
    brain.add_player_line(1, "Timo", "Ich sehe mich um.")

    def _boom(text: str):
        raise RuntimeError("guard bug")

    answer = asyncio.run(brain.respond(1, check=_boom))
    assert answer == "Die Halle liegt verlassen da." and len(client.calls) == 1


def test_empty_retry_keeps_first_answer_and_its_markers() -> None:
    # the retry echoing the player line gets suppressed (None) → keep the first answer AND
    # restore the dice marker it queued (marker hygiene, ADR 045)
    state = _state(_npc("Grendel", wounds=0))
    first = "Grendel sagt: Zieh! <<TEST Kampf für Timo>>"
    # the consistency retry echoes the player line twice — the echo guard's OWN retry also
    # misfires, so _generate returns None and the guard keeps the first answer
    client = _SeqClient([first, "Ich sehe mich um.", "Ich sehe mich um."])
    brain = DMBrain(client, profile=_IM)
    brain.add_player_line(1, "Timo", "Ich sehe mich um.")
    answer = asyncio.run(brain.respond(1, check=_checker_for(state)))
    assert "Grendel sagt: Zieh!" in answer
    tests = brain.take_pending_tests(1)
    assert len(tests) == 1 and tests[0].skill == "Kampf"


def test_regenerate_replaces_first_answers_markers() -> None:
    # the discarded first answer's dice request must NOT survive its replacement
    state = _state(_npc("Grendel", wounds=0))
    client = _SeqClient([
        "Grendel sagt: Zieh! <<TEST Kampf für Timo>>",
        "Die Leiche rührt sich nicht. <<TEST Wahrnehmung für Timo>>",
    ])
    brain = DMBrain(client, profile=_IM)
    brain.add_player_line(1, "Timo", "Ich sehe mich um.")
    asyncio.run(brain.respond(1, check=_checker_for(state)))
    tests = brain.take_pending_tests(1)
    assert [t.skill for t in tests] == ["Wahrnehmung"]


def test_redo_also_runs_the_guard() -> None:
    state = _state(_npc("Grendel", wounds=0))
    client = _SeqClient([
        "Die Halle ist leer.",              # first turn, clean
        "Grendel sagt: Hallo.",             # redo, violating
        "Nur Staub und Stille.",            # redo retry, clean
    ])
    brain = DMBrain(client, profile=_IM)
    brain.add_player_line(1, "Timo", "Ich sehe mich um.")
    asyncio.run(brain.respond(1, check=_checker_for(state)))
    answer = asyncio.run(brain.redo(1, check=_checker_for(state)))
    assert answer == "Nur Staub und Stille." and len(client.calls) == 3
