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

import pytest

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


# --- D107: exits with titles, NPC roleplaying notes, guidance as an impulse, new fields --------
# Rendering + parsing only (ADR 057 #6, ADR 059 #1). No LLM, no new state — the same pure
# file-reading + formatting contract as the tests above.

DEBUG_KAMPAGNE = REPO / "data" / "adventures" / "debug-kampagne"


def _npc_adventure(tmp_path: Path) -> Path:
    """A compendium whose scene NPCs actually resolve to statblocks — the shape the real
    campaign has and the mini fixture above deliberately does not."""
    (tmp_path / "adventure.json").write_text(json.dumps({
        "id": "npcs", "title": "NSCs", "start_scene": "a", "summary_de": "Der Bogen.",
        "scenes": [
            {"id": "a", "title_de": "Anfang", "part": 1, "description_de": "Es beginnt.",
             "npcs_here": ["Seneschall Kaad", "Bree Marlok", "Laufbursche"],
             "opportunities_de": [{"id": "sehen", "text_de": "Etwas sehen."}],
             "leads_to": ["b"], "guidance_de": "Die Frist beiläufig ins Bild holen."},
            {"id": "b", "title_de": "Der Hafen"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "npcs.json").write_text(json.dumps({
        "npcs": [
            {"name": "Seneschall Kaad", "role_de": "Stimme des Inquisitors",
             "roleplaying_de": "Spricht leise und in Fristen."},
            {"name": "Bree Marlok", "role_de": "Hehlerin", "roleplaying_de": "Vergisst nie."},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _timed_adventure(tmp_path: Path, **extra) -> Path:
    payload = {"id": "t", "title": "T", "start_scene": "a", "summary_de": "S",
               "scenes": [{"id": "a", "title_de": "A"}]}
    payload.update(extra)
    (tmp_path / "adventure.json").write_text(json.dumps(payload, ensure_ascii=False),
                                             encoding="utf-8")
    return tmp_path


# -- exits with titles (B1/A7/A8, ADR 057 #6) --------------------------------------------------

def test_exits_render_with_their_titles(tmp_path) -> None:
    """A bare id ('schrein') gives the model nothing to map 'zum Hafen' onto."""
    adv = Adventure.load(_mini_adventure(tmp_path))
    assert "Mögliche nächste Orte: b — Ende" in adv.adventure_block_de("a")


def test_exit_without_a_known_title_stays_a_bare_id() -> None:
    from dmbot.rag.adventure import Scene

    adv = Adventure(scenes=[Scene(id="a", title_de="A", leads_to=["nirgendwo", "b"]),
                            Scene(id="b", title_de="")])
    line = [ln for ln in adv.adventure_block_de("a").splitlines()
            if ln.startswith("Mögliche nächste Orte")][0]
    assert line == "Mögliche nächste Orte: nirgendwo, b"


def test_the_scene_card_renders_an_exit_with_the_shared_label_function() -> None:
    """The card must not own a second copy of "id — Titel" (parity-by-construction): the string
    comes from ``scene_router.exit_label``, the open-exit set from ``scene_flow``."""
    from dmbot.llm.scene_router import exit_label

    assert exit_label("pier-neun", "Pier Neun") == "pier-neun — Pier Neun"
    assert exit_label("pier-neun", "") == "pier-neun"


def test_a_gated_exit_stays_hidden_exactly_as_scene_flow_decides() -> None:
    """Same gate as the mover: an exit whose required element isn't resolved is not offered."""
    from dmbot.rag.adventure import Scene
    from dmbot.rules.scene_flow import reachable_exits

    scene = Scene(id="a", title_de="A", leads_to=["b", "c"], exit_requires={"c": "opp-x"},
                  opportunities_de=["Das Manifest lesen."], opportunity_ids=["opp-x"])
    adv = Adventure(scenes=[scene, Scene(id="b", title_de="B"), Scene(id="c", title_de="C")])
    line = [ln for ln in adv.adventure_block_de("a").splitlines()
            if ln.startswith("Mögliche nächste Orte")][0]
    assert line == "Mögliche nächste Orte: b — B"
    assert reachable_exits(scene, ()) == ("b",)
    unlocked = [ln for ln in adv.adventure_block_de("a", resolved_ids=["opp-x"]).splitlines()
                if ln.startswith("Mögliche nächste Orte")][0]
    assert unlocked == "Mögliche nächste Orte: b — B, c — C"
    assert reachable_exits(scene, ["opp-x"]) == ("b", "c")


# -- NPCs with role and manner (B2) ------------------------------------------------------------

def test_present_npcs_render_role_and_manner(tmp_path) -> None:
    """roleplaying_de had no reader in the whole repo — so the model invented Kaad every turn."""
    block = Adventure.load(_npc_adventure(tmp_path)).adventure_block_de("a")
    assert ("- Seneschall Kaad — Stimme des Inquisitors. "
            "Spielweise: Spricht leise und in Fristen.") in block
    assert "- Bree Marlok — Hehlerin. Spielweise: Vergisst nie." in block
    assert "- Laufbursche" in block  # no statblock → the bare name, never dropped


def test_dead_npc_keeps_its_marker_in_the_detailed_block(tmp_path) -> None:
    block = Adventure.load(_npc_adventure(tmp_path)).adventure_block_de(
        "a", dead_npcs=["seneschall kaad"])
    assert "- Seneschall Kaad (tot) — Stimme des Inquisitors." in block


def test_npcs_without_any_statblock_stay_one_compact_line(tmp_path) -> None:
    """Nothing to add → don't grow the prompt; the legacy one-liner is kept."""
    block = Adventure.load(_mini_adventure(tmp_path)).adventure_block_de("a")
    assert "Anwesende NSCs: Bob" in block


# -- the campaign's named NPCs (scopes the consistency guard, ADR 045 + D107) ------------------

def test_npc_names_holds_statblocks_and_scene_casts_but_never_a_generic_mook() -> None:
    """A mook statblock's "name" is a role the DM may use as an anonymous extra anywhere. It must
    stay out of the guard's presence check — otherwise „Der Schläger brüllt" is a violation in
    every scene the squad isn't standing in."""
    from dmbot.rag.adventure import AdventureNpc, Scene

    adv = Adventure(
        scenes=[Scene(id="lager", title_de="Lager",
                      npcs_here=["Vosk der Haken", "Kettenbund-Schläger", "Alter Fenk"])],
        npcs=[AdventureNpc(name="Vosk der Haken"),
              AdventureNpc(name="Kettenbund-Schläger", generic=True)],
    )
    # statblock + a name that only ever appears in npcs_here; the mook from neither source
    assert adv.npc_names() == {"vosk der haken", "alter fenk"}
    assert adv.npc("Kettenbund-Schläger").generic is True  # still a usable statblock for combat


def test_the_debug_campaign_flags_its_thug_squad_and_nobody_else() -> None:
    adv = Adventure.load(REPO / "data" / "adventures" / "debug-kampagne")
    assert adv is not None
    assert adv.npc("Kettenbund-Schläger").generic is True
    assert [n for n in ("Arno Kessel", "Vosk der Haken", "Alter Fenk", "Bree Marlok",
                        "Lastenservitor Ohm-3", "Seneschall Bramwell Kaad",
                        "Schwester Cassia Vall") if adv.npc(n).generic] == []
    assert "kettenbund-schläger" not in adv.npc_names()
    assert "vosk der haken" in adv.npc_names()


# -- guidance is an impulse, not a standing order (A5, B6) -------------------------------------

def test_guidance_is_omitted_by_default(tmp_path) -> None:
    block = Adventure.load(_npc_adventure(tmp_path)).adventure_block_de("a")
    assert "Die Frist beiläufig ins Bild holen." not in block
    assert "Regie-Impuls" not in block


def test_guidance_is_opt_in_and_marked_as_a_one_off(tmp_path) -> None:
    block = Adventure.load(_npc_adventure(tmp_path)).adventure_block_de(
        "a", include_guidance=True)
    assert ("Regie-Impuls für diesen Zug (einmalig, kein Dauerauftrag): "
            "Die Frist beiläufig ins Bild holen.") in block


# -- the description is reference material, not a script (B5) ----------------------------------

def test_description_is_labelled_as_reference_material(tmp_path) -> None:
    block = Adventure.load(_mini_adventure(tmp_path)).adventure_block_de("a")
    material = block.split("## Aktuelle Szene")[1]
    label, body = material.splitlines()[1], material.splitlines()[2]
    assert "nicht vorlesen" in label and "eigenen Worten" in label
    assert body == "Es beginnt."


# -- new adventure-level fields (ADR 059 #1, briefing A1/A9/A11) -------------------------------

def test_start_time_deadlines_clocks_and_briefing_are_parsed(tmp_path) -> None:
    adv = Adventure.load(_timed_adventure(
        tmp_path,
        start_time_de="Tag 1, 21:00",
        deadlines=[{"id": "sirene", "label": "Mitternachtssirene", "due_in": "+3h"}],
        clocks=[{"id": "wachsamkeit", "name": "Wachsamkeit", "size": 6, "filled": 0}],
        briefing_de="Kurz vorweg, damit alle wissen, worum es geht.",
    ))
    assert adv.start_time_de == "Tag 1, 21:00"
    assert adv.deadlines == [{"id": "sirene", "label": "Mitternachtssirene", "due_in": "+3h"}]
    assert adv.clocks == [{"id": "wachsamkeit", "name": "Wachsamkeit", "size": 6, "filled": 0}]
    assert adv.briefing_de == "Kurz vorweg, damit alle wissen, worum es geht."


def test_adventure_without_the_new_fields_defaults_empty(tmp_path) -> None:
    adv = Adventure.load(_timed_adventure(tmp_path))
    assert adv.start_time_de == "" and adv.briefing_de == ""
    assert adv.deadlines == [] and adv.clocks == []


def test_non_mapping_time_entries_are_dropped_loudly(tmp_path, caplog) -> None:
    with caplog.at_level("ERROR"):
        adv = Adventure.load(_timed_adventure(
            tmp_path, deadlines=["+3h"], clocks=[{"id": "c", "name": "C"}, 7]))
    assert adv.deadlines == []
    assert adv.clocks == [{"id": "c", "name": "C"}]
    assert "deadline" in caplog.text and "clock" in caplog.text


# -- opportunity ids: warn, never fail the load (deliberate ADR 057 #3 deviation) ---------------

def test_opportunity_without_an_id_warns_but_still_loads(tmp_path, caplog) -> None:
    """chemical_burn is local-only and carries no ids — a hard error would make it unplayable."""
    with caplog.at_level("WARNING"):
        adv = Adventure.load(_mini_adventure(tmp_path))
    assert adv is not None and adv.get_scene("a").opportunity_ids == ["opp-1"]
    assert "without an id" in caplog.text and "'a'" in caplog.text


def test_authored_opportunity_ids_load_without_a_warning(tmp_path, caplog) -> None:
    with caplog.at_level("WARNING"):
        adv = Adventure.load(_npc_adventure(tmp_path))
    assert adv.get_scene("a").opportunity_ids == ["sehen"]
    assert "without an id" not in caplog.text


def test_secrets_keep_positional_ids_without_warning(tmp_path, caplog) -> None:
    """Only opportunities feed the flag gate; secrets are still authored as plain strings."""
    with caplog.at_level("WARNING"):
        Adventure.load(_timed_adventure(tmp_path, scenes=[
            {"id": "a", "title_de": "A", "secrets_de": ["Bob war es."]}]))
    assert "without an id" not in caplog.text


# -- the real committed campaign ---------------------------------------------------------------

def test_debug_kampagne_ships_its_clock_and_ids(caplog) -> None:
    """The committed gate-run campaign: every opportunity carries an authored id (so the flag
    gate can count), and the adventure ships start time, deadline, clocks and the spoken
    briefing."""
    with caplog.at_level("WARNING"):
        adv = Adventure.load(DEBUG_KAMPAGNE)
    assert adv is not None
    assert "without an id" not in caplog.text
    assert adv.start_time_de == "Tag 1, 21:00"
    assert [d["id"] for d in adv.deadlines] == ["mitternachtssirene"]
    assert [c["id"] for c in adv.clocks] == ["wachsamkeit", "verladung"]
    assert adv.briefing_de.strip() and "<<" not in adv.briefing_de
