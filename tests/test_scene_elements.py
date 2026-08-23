"""Stateful scene cards (ADR 043) — the schema/render/gate half, pure and Discord-free.

Element ids: ``opportunities_de``/``secrets_de`` entries are a plain string (derived positional
id) or ``{"id", "text_de"}``; ids unique per scene across both lists. The card render moves
resolved elements to „Bereits geschehen"/„Bekannt", joins dead NPCs as ``(tot)`` and hides gated
exits until unlocked. ``resolve_move`` rejects an unmet gate like an unknown target."""

from __future__ import annotations

import json
import logging

from dmbot.rag.adventure import Adventure, Scene


def _write_adventure(tmp_path, scenes: list[dict]):
    (tmp_path / "adventure.json").write_text(json.dumps({
        "id": "mini", "title": "Mini", "start_scene": scenes[0]["id"],
        "summary_de": "Der Bogen.", "scenes": scenes,
    }, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _scene_a(**overrides) -> dict:
    d = {
        "id": "a", "title_de": "Anfang", "part": 1, "description_de": "Es beginnt.",
        "npcs_here": ["Bob", "Alia"],
        "opportunities_de": ["Wahrnehmung: etwas sehen.", "Überreden: Wache umgehen."],
        "secrets_de": ["Bob ist der Täter."],
        "leads_to": ["b"],
    }
    d.update(overrides)
    return d


# -- schema: both entry forms, derived ids, collisions ---------------------------------------------

def test_plain_string_elements_get_derived_positional_ids(tmp_path) -> None:
    adv = Adventure.load(_write_adventure(tmp_path, [_scene_a(), {"id": "b", "title_de": "B"}]))
    scene = adv.get_scene("a")
    assert scene.opportunity_ids == ["opp-1", "opp-2"]
    assert scene.secret_ids == ["geh-1"]
    assert scene.opportunities_de == ["Wahrnehmung: etwas sehen.", "Überreden: Wache umgehen."]


def test_dict_elements_keep_explicit_id_and_text(tmp_path) -> None:
    adv = Adventure.load(_write_adventure(tmp_path, [_scene_a(
        opportunities_de=[{"id": "kiste", "text_de": "Die Kiste öffnen."}],
        secrets_de=[{"id": "taeter", "text_de": "Bob ist der Täter."}],
    ), {"id": "b", "title_de": "B"}]))
    scene = adv.get_scene("a")
    assert scene.opportunity_ids == ["kiste"] and scene.opportunities_de == ["Die Kiste öffnen."]
    assert scene.secret_ids == ["taeter"] and scene.secrets_de == ["Bob ist der Täter."]


def test_mixed_string_and_dict_forms_position_counts_the_whole_list(tmp_path) -> None:
    adv = Adventure.load(_write_adventure(tmp_path, [_scene_a(
        opportunities_de=[{"id": "kiste", "text_de": "Die Kiste."}, "Zweiter Eintrag."],
    ), {"id": "b", "title_de": "B"}]))
    scene = adv.get_scene("a")
    assert scene.opportunity_ids == ["kiste", "opp-2"]  # plain entry keeps its list position


def test_id_collision_across_both_lists_logs_and_stays_unique(tmp_path, caplog) -> None:
    with caplog.at_level(logging.ERROR):
        adv = Adventure.load(_write_adventure(tmp_path, [_scene_a(
            opportunities_de=["Etwas sehen."],
            secrets_de=[{"id": "opp-1", "text_de": "Kollidiert absichtlich."}],
        ), {"id": "b", "title_de": "B"}]))
    scene = adv.get_scene("a")
    assert scene is not None  # load survives (degrade, don't die)
    ids = scene.element_ids()
    assert len(ids) == len(set(ids))  # ids end up unique
    assert "opp-1" in caplog.text


def test_directly_constructed_scene_derives_ids() -> None:
    scene = Scene(id="a", title_de="A", opportunities_de=["x"], secrets_de=["y", "z"])
    assert scene.opportunity_ids == ["opp-1"]
    assert scene.secret_ids == ["geh-1", "geh-2"]
    assert scene.element_ids() == ["opp-1", "geh-1", "geh-2"]
    assert scene.element_text("geh-2") == "z"
    assert scene.element_text("nope") is None


def test_leads_to_dict_form_parses_ziel_and_requires(tmp_path) -> None:
    adv = Adventure.load(_write_adventure(tmp_path, [
        _scene_a(leads_to=["b", {"ziel": "c", "requires": "opp-1"}]),
        {"id": "b", "title_de": "B"}, {"id": "c", "title_de": "C"},
    ]))
    scene = adv.get_scene("a")
    assert scene.leads_to == ["b", "c"]  # unchanged shape for the membership test
    assert scene.exit_requires == {"c": "opp-1"}


def test_requires_naming_no_element_logs_and_fails_open(tmp_path, caplog) -> None:
    with caplog.at_level(logging.ERROR):
        adv = Adventure.load(_write_adventure(tmp_path, [
            _scene_a(leads_to=[{"ziel": "b", "requires": "tippfehler"}]),
            {"id": "b", "title_de": "B"},
        ]))
    scene = adv.get_scene("a")
    assert scene.exit_requires == {}  # gate dropped → exit stays reachable
    assert adv.resolve_move("a", "b", "verbunden") is not None
    assert "tippfehler" in caplog.text


# -- render: inline ids, Bereits geschehen / Bekannt, dead NPCs, hidden exits ----------------------

def _adv() -> Adventure:
    return Adventure(summary_de="Der Bogen.", scenes=[
        Scene(id="a", title_de="Anfang", part=1, description_de="Es beginnt.",
              npcs_here=["Bob", "Alia"],
              opportunities_de=["Etwas sehen.", "Wache umgehen."],
              secrets_de=["Bob ist der Täter."],
              leads_to=["b", "c"], exit_requires={"c": "opp-1"}),
        Scene(id="b", title_de="B"),
        Scene(id="c", title_de="C"),
    ])


def test_element_ids_render_inline() -> None:
    block = _adv().adventure_block_de("a")
    assert "- [opp-1] Etwas sehen." in block
    assert "- [opp-2] Wache umgehen." in block
    assert "- [geh-1] Bob ist der Täter." in block


def test_untouched_scene_has_no_new_sections() -> None:
    block = _adv().adventure_block_de("a")
    assert "Bereits geschehen" not in block
    assert "Bekannt (bereits enthüllt)" not in block


def test_resolved_opportunity_moves_to_bereits_geschehen() -> None:
    block = _adv().adventure_block_de("a", resolved_ids=["opp-1"])
    assert "Bereits geschehen:" in block
    moeglich = block.split("Möglichkeiten hier:")[1].split("Bereits geschehen:")[0]
    assert "Etwas sehen." not in moeglich  # gone from the open list …
    geschehen = block.split("Bereits geschehen:")[1].split("Geheimnisse")[0]
    assert "- [opp-1] Etwas sehen." in geschehen  # … but the DM still knows it happened
    assert "- [opp-2] Wache umgehen." in moeglich  # the other stays offered


def test_revealed_secret_moves_to_bekannt() -> None:
    block = _adv().adventure_block_de("a", resolved_ids=["geh-1"])
    assert "Geheimnisse (NIE aussprechen" not in block  # only secret revealed → block gone
    assert "Bekannt (bereits enthüllt):" in block
    assert "- [geh-1] Bob ist der Täter." in block.split("Bekannt (bereits enthüllt):")[1]


def test_dead_npc_renders_tot_case_insensitive() -> None:
    block = _adv().adventure_block_de("a", dead_npcs=["bob"])
    assert "Anwesende NSCs: Bob (tot), Alia" in block


def test_locked_exit_hidden_until_unlocked() -> None:
    adv = _adv()
    # Exits render as "id — title" since D107 (ADR 057 #6): a bare id gives the model nothing
    # to map a fictional direction onto.
    assert "Mögliche nächste Orte: b — B\n" in adv.adventure_block_de("a") + "\n"  # c is locked
    unlocked = adv.adventure_block_de("a", resolved_ids=["opp-1"])
    assert "Mögliche nächste Orte:" in unlocked and ", c — C" in unlocked


def test_all_exits_locked_omits_the_line() -> None:
    adv = Adventure(scenes=[
        Scene(id="a", title_de="A", opportunities_de=["x"],
              leads_to=["b"], exit_requires={"b": "opp-1"}),
        Scene(id="b", title_de="B"),
    ])
    assert "Mögliche nächste Orte" not in adv.adventure_block_de("a")


# -- gates: resolve_move ----------------------------------------------------------------------------

def test_gate_unmet_rejected_in_verbunden(caplog) -> None:
    with caplog.at_level(logging.INFO):
        assert _adv().resolve_move("a", "c", "verbunden") is None
    assert "opp-1" in caplog.text  # log names the missing condition


def test_gate_met_allows_move() -> None:
    moved = _adv().resolve_move("a", "c", "verbunden", resolved_ids=["opp-1"])
    assert moved is not None and moved.id == "c"


def test_frei_bypasses_gates() -> None:
    moved = _adv().resolve_move("a", "c", "frei")
    assert moved is not None and moved.id == "c"


def test_ungated_neighbour_still_moves() -> None:
    moved = _adv().resolve_move("a", "b", "verbunden")
    assert moved is not None and moved.id == "b"
