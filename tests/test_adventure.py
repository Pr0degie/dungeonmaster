"""Adventure compendium (Phase 10a, ADR 019): loader, scene cards, prompt block, NPC statblocks,
scene pointer round-trip, and the W4 self-repetition guard.

The scene tracker is the deterministic half of the hybrid — "where are we in the plot" must be
code state (golden rule #3), so it's unit-tested like the rules engine: pure file-reading +
formatting, no LLM anywhere.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dmbot.memory.state import WorldState
from dmbot.orchestrator import DMBrain, _REPEAT_NUDGE, is_self_repetition
from dmbot.rag.adventure import Adventure

REPO = Path(__file__).resolve().parents[1]
CHEMICAL_BURN = REPO / "data" / "adventures" / "chemical_burn"


def _mini_adventure(tmp_path: Path) -> Path:
    (tmp_path / "adventure.json").write_text(json.dumps({
        "id": "mini", "title": "Mini", "start_scene": "a",
        "summary_de": "Der Bogen.",
        "scenes": [
            {"id": "a", "title_de": "Anfang", "part": 1, "description_de": "Es beginnt.",
             "npcs_here": ["Bob"], "opportunities_de": ["Wahrnehmung (Schwer): etwas sehen."],
             "secrets_de": ["Bob ist der Täter."], "leads_to": ["b"], "guidance_de": "Ruhig anspielen."},
            {"id": "b", "title_de": "Ende", "part": 2, "description_de": "Es endet."},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "npcs.json").write_text(json.dumps({
        "npcs": [{"name": "Bob der Böse", "wounds": 9, "toughness_bonus": 3, "armour": 2,
                  "roleplaying_de": "Fies."}],
    }, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_load_and_scene_lookup(tmp_path) -> None:
    adv = Adventure.load(_mini_adventure(tmp_path))
    assert adv is not None and adv.start_scene == "a"
    assert adv.get_scene("a").title_de == "Anfang"
    assert adv.get_scene("nope") is None
    assert [(p, i) for p, i, _ in adv.scene_overview()] == [(1, "a"), (2, "b")]


def test_missing_or_broken_compendium_yields_none(tmp_path) -> None:
    assert Adventure.load(tmp_path / "nowhere") is None
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "adventure.json").write_text("{not json", encoding="utf-8")
    assert Adventure.load(bad) is None


def test_adventure_block_carries_summary_scene_and_secrets(tmp_path) -> None:
    adv = Adventure.load(_mini_adventure(tmp_path))
    block = adv.adventure_block_de("a")
    assert "## Abenteuer" in block and "Der Bogen." in block
    assert "## Aktuelle Szene: Anfang (Teil 1)" in block
    assert "Bob ist der Täter." in block  # secrets reach the DM …
    assert "NIE aussprechen" in block      # … flagged as never-say
    assert "Mögliche nächste Orte: b" in block
    # unknown scene degrades to the summary alone
    assert "Aktuelle Szene" not in adv.adventure_block_de("nope")


def test_npc_lookup_is_case_insensitive_and_underscore_tolerant(tmp_path) -> None:
    adv = Adventure.load(_mini_adventure(tmp_path))
    assert adv.npc("bob der böse").wounds == 9
    assert adv.npc("Bob_der_Böse").armour == 2  # Discord args can't carry spaces
    assert adv.npc("Unbekannt") is None


def test_scene_id_survives_a_state_round_trip(tmp_path) -> None:
    state = WorldState(session_id="t", scene_id="mud_gate")
    path = tmp_path / "state.json"
    state.save(path)
    loaded = WorldState.load(path)
    assert loaded is not None and loaded.scene_id == "mud_gate"  # plot position survives restarts


def test_adventure_block_lands_in_the_system_prompt() -> None:
    captured: dict = {}

    class _C:
        async def chat(self, system, messages, options=None):
            captured["system"] = system
            return "Es regnet Asche."

        async def aclose(self) -> None:
            pass

    brain = DMBrain(_C())
    ch = 1
    brain.set_context(ch, recap="Bisher.", state_summary="## Weltzustand\nx",
                      adventure_block="## Abenteuer\nBogen.\n\n## Aktuelle Szene: Anfang (Teil 1)")
    brain.add_player_line(ch, "Timo", "Was sehe ich?")
    asyncio.run(brain.respond(ch))
    system = captured["system"]
    assert "## Abenteuer" in system
    # order: recap → adventure → hard state (CLAUDE.md prompt order, extended by ADR 019)
    assert system.index("Bisher.") < system.index("## Abenteuer") < system.index("## Weltzustand")


import pytest


@pytest.mark.skipif(not (CHEMICAL_BURN / "adventure.json").is_file(),
                    reason="local-only content (public repo: data/adventures/ stays untracked, "
                           "like the PDFs it derives from)")
def test_chemical_burn_compendium_is_loadable_and_complete() -> None:
    """The real authored compendium: every leads_to points at an existing scene, the start scene
    exists, and every scene NPC with a statblock requirement resolves."""
    adv = Adventure.load(CHEMICAL_BURN)
    assert adv is not None and adv.get_scene(adv.start_scene) is not None
    ids = {sid for _, sid, _ in adv.scene_overview()}
    for _, sid, _ in adv.scene_overview():
        scene = adv.get_scene(sid)
        for target in scene.leads_to:
            assert target in ids, f"{sid} → unknown scene {target!r}"
    # the finale's key NPCs have engine-ready statblocks
    for name in ("Tourmaline", "Kultist", "Raguel der Rote", "Alecto"):
        npc = adv.npc(name)
        assert npc is not None and npc.wounds > 0


# --- W4: self-repetition guard ---------------------------------------------------------------

_SCENE = ("Ihr steht inmitten des pulsierenden Herzens der Hive-Stadt. Der Lärm unzähliger "
          "Arbeitsgeräusche umgibt euch, während der beißende Geruch von Weihrauch und "
          "Maschinenöl eure Sinne betäubt.")
# the live failure: same description re-told with pronoun swaps ("wir/uns" POV slip included)
_SCENE_AGAIN = ("Wir befinden uns inmitten des pulsierenden Herzens der Hive-Stadt. Der Lärm "
                "unzähliger Arbeitsgeräusche umgibt uns, während der beißende Geruch von "
                "Weihrauch und Maschinenöl unsere Sinne betäubt.")


def test_self_repetition_detects_the_live_pronoun_swap_case() -> None:
    assert is_self_repetition(_SCENE_AGAIN, _SCENE)


def test_fresh_narration_is_not_self_repetition() -> None:
    fresh = ("Petronilla bahnt sich mit gezogenem Schock-Knüppel einen Weg durch die Menge, "
             "ihre Stimme schneidet durch den Lärm des Hafens.")
    assert not is_self_repetition(fresh, _SCENE)


def test_short_answers_are_exempt_from_the_repetition_check() -> None:
    assert not is_self_repetition("Du triffst.", "Du triffst.")


def test_repetition_is_retried_with_the_repeat_nudge() -> None:
    class _C:
        def __init__(self) -> None:
            self.calls: list[list[dict[str, str]]] = []

        async def chat(self, system, messages, options=None):
            self.calls.append(messages)
            if len(self.calls) == 1:
                return _SCENE_AGAIN
            return "Petronilla mustert euch scharf und verlangt eure Papiere."

        async def aclose(self) -> None:
            pass

    client = _C()
    brain = DMBrain(client)
    ch = 1
    # seed history so there IS a previous answer to repeat
    brain.restore_history(ch, [("Timo: Wo sind wir?", _SCENE)])
    brain.add_player_line(ch, "Timo", "Warum sind wir hier?")
    answer = asyncio.run(brain.respond(ch))
    assert answer == "Petronilla mustert euch scharf und verlangt eure Papiere."
    assert _REPEAT_NUDGE in client.calls[1][-1]["content"]  # the retry carried the W4 nudge
