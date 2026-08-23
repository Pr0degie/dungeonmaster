"""World state (Phase 9, ADR 015): deterministic advancement + persistence (the code half of the
gate 'an HP change survives a restart') and the engine's combat-damage math. Pure — no Discord,
no LLM, seeded RNG where dice are involved.
"""

from __future__ import annotations

import json
import random

from dmbot.memory.state import (
    DOWNED_CONDITION,
    FACT_CAP,
    FACT_TEXT_MAX,
    GROUP_HOLDER,
    Fact,
    Quest,
    WorldState,
    world_state_summary_de,
)
from dmbot.rules import engine, profile as profile_mod
from dmbot.rules.characters import CharacterStore

_IM = profile_mod.load("imperium_maledictum")

_STORE = CharacterStore.from_dict(
    {
        "characters": [
            {
                "name": "Seskin",
                "characteristics": {"Tgh": 42},
                "skills": {"Nahkampf": 45},
                "wounds": 11, "max_wounds": 11,
                "inventory": ["Kettenschwert"],
            },
            {"name": "Mortn", "characteristics": {"Tgh": 32}, "skills": {}, "wounds": 9, "max_wounds": 9},
        ],
    }
)


# -- seeding ------------------------------------------------------------------------------

def test_seed_from_store_copies_wounds_and_inventory() -> None:
    s = WorldState.seed_from_store(_STORE, system="imperium_maledictum", session_id="42")
    assert {c.name for c in s.characters} == {"Seskin", "Mortn"}
    sk = s.find("Seskin")
    assert sk.wounds == 11 and sk.max_wounds == 11 and "Kettenschwert" in sk.inventory
    assert s.system == "imperium_maledictum" and s.session_id == "42"


# -- deterministic advancement ------------------------------------------------------------

def test_apply_damage_clamps_at_zero_and_downs() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.apply_damage("Seskin", 4)
    assert s.find("Seskin").wounds == 7
    s.apply_damage("Seskin", 100)  # over-kill clamps at 0
    sk = s.find("Seskin")
    assert sk.wounds == 0 and DOWNED_CONDITION in sk.conditions


def test_heal_clamps_at_max_and_clears_downed() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.apply_damage("Mortn", 100)
    assert DOWNED_CONDITION in s.find("Mortn").conditions
    s.heal("Mortn", 3)
    m = s.find("Mortn")
    assert m.wounds == 3 and DOWNED_CONDITION not in m.conditions
    s.heal("Mortn", 100)  # clamps at max_wounds
    assert s.find("Mortn").wounds == 9


def test_unknown_target_returns_none() -> None:
    s = WorldState.seed_from_store(_STORE)
    assert s.apply_damage("Niemand", 5) is None
    assert s.heal("Niemand", 5) is None


def test_find_is_case_insensitive_over_characters_then_npcs() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.add_or_update_npc("Kultist", wounds=10)
    assert s.find("seskin").name == "Seskin"
    assert s.find("KULTIST").name == "Kultist"
    assert s.find(None) is None


def test_npc_add_update_and_damage() -> None:
    s = WorldState.seed_from_store(_STORE)
    npc = s.add_or_update_npc("Kultist", wounds=10, toughness_bonus=3, armour=1, attitude="feindlich")
    assert npc.is_npc and npc.wounds == 10 and npc.toughness_bonus == 3
    s.apply_damage("Kultist", 4)
    assert s.find("Kultist").wounds == 6
    s.add_or_update_npc("Kultist", wounds=2)  # update existing, not duplicate
    assert len([n for n in s.npcs if n.name == "Kultist"]) == 1 and s.find("Kultist").wounds == 2


def test_quests_and_location() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.set_location("Hive Primus")
    s.add_quest("Finde den Häretiker")
    s.set_quest_status("Finde den Häretiker", "done")
    assert s.location == "Hive Primus" and s.quests[0].status == "done"


# -- persistence (the gate's code half) ---------------------------------------------------

def test_save_load_round_trip_survives(tmp_path) -> None:
    s = WorldState.seed_from_store(_STORE, system="imperium_maledictum", session_id="99")
    s.apply_damage("Seskin", 5)
    s.add_or_update_npc("Kultist", wounds=8, toughness_bonus=2)
    s.set_location("Unterstadt von Hive Primus")
    s.add_quest("Finde den Häretiker")
    s.set_recap("Die Gruppe stieg in die Unterstadt hinab.")
    path = tmp_path / "state.json"
    s.save(path)

    again = WorldState.load(path)
    assert again is not None
    assert again.find("Seskin").wounds == 6           # the HP change survived the reload
    assert again.find("Kultist").wounds == 8 and again.find("Kultist").toughness_bonus == 2
    assert again.location == "Unterstadt von Hive Primus"
    assert again.recap.startswith("Die Gruppe")
    assert again.quests[0].title == "Finde den Häretiker"


def test_load_missing_file_returns_none(tmp_path) -> None:
    assert WorldState.load(tmp_path / "does_not_exist.json") is None


# -- prompt summary -----------------------------------------------------------------------

def test_summary_lists_the_hard_facts() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.apply_damage("Seskin", 4)
    s.set_location("Hive Primus")
    s.add_or_update_npc("Kultist", wounds=10, attitude="feindlich")
    out = world_state_summary_de(s)
    assert "Weltzustand" in out
    assert "Hive Primus" in out
    assert "Seskin 7/11" in out and "verwundet" in out
    assert "Kultist" in out


def test_summary_empty_state_still_carries_the_time() -> None:
    # Since ADR 048 the in-game time is always a hard fact — an otherwise empty state renders
    # exactly the header + the time line (day 1, 08:00, morning) and nothing else.
    out = world_state_summary_de(WorldState())
    assert "Zeit: Tag 1, 08:00 (Morgen)" in out
    assert len(out.splitlines()) == 2  # header + time — no other sections appear


def test_summary_hides_dead_npcs() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.add_or_update_npc("Kultist", wounds=4)
    s.apply_damage("Kultist", 99)  # → 0, downed
    assert "Kultist" not in world_state_summary_de(s)  # dead NPCs drop out of the scene block


# -- engine combat math (seeded) ----------------------------------------------------------

def test_resolve_damage_is_weapon_plus_sl_minus_soak() -> None:
    wr = engine.roll("1d10+5", random.Random(1))
    dmg = engine.resolve_damage(wr, success_level=2, soak=3)
    assert dmg.applied == max(0, wr.total + 2 - 3)
    assert dmg.weapon_roll.total == wr.total and dmg.soak == 3


def test_resolve_damage_never_negative() -> None:
    wr = engine.roll("1", random.Random(1))  # constant 1
    assert engine.resolve_damage(wr, success_level=0, soak=10).applied == 0


def test_describe_damage_de_mentions_who_what_and_target() -> None:
    wr = engine.roll("1d10+5", random.Random(1))
    dmg = engine.resolve_damage(wr, success_level=2, soak=3)
    line = engine.describe_damage_de(
        dmg, attacker="Vask", target="Kultist", weapon="Kettenschwert",
        new_wounds=3, max_wounds=10, downed=False,
    )
    assert "💥" in line and "Vask" in line and "Kultist" in line and "Kettenschwert" in line


# -- profile combat accessors -------------------------------------------------------------

def test_profile_combat_accessors() -> None:
    assert _IM.combat_enabled()
    assert _IM.is_attack_skill("Nahkampf") and _IM.is_attack_skill("fernkampf")
    assert not _IM.is_attack_skill("Wahrnehmung")
    assert _IM.weapon_damage("Kettenschwert") == "1d10+5"
    assert _IM.weapon_damage("kettenschwert") == "1d10+5"  # case-insensitive
    assert _IM.weapon_damage("Unbekannt") is None
    assert _IM.default_damage() == "1d10"
    assert _IM.soak_characteristic() == "Tgh" and _IM.soak_mode() == "tens"


# -- hard facts: handed-over items, promises, the mission (ADR 058) ------------------------

def test_give_item_lands_on_the_sheet_and_becomes_a_dated_fact() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.time_minutes = 21 * 60 + 10
    f = s.give_item("Zollvollmacht", to="seskin", by="Seneschall Kaad")
    assert f is not None
    assert (f.kind, f.text, f.holder, f.source, f.status) == (
        "item", "Zollvollmacht", "Seskin", "Seneschall Kaad", "open"
    )
    assert f.at_minutes == 21 * 60 + 10                    # "when" comes from the code-owned clock
    assert "Zollvollmacht" in s.find("Seskin").inventory   # extends the existing inventory


def test_give_item_without_a_known_recipient_goes_to_the_group() -> None:
    s = WorldState.seed_from_store(_STORE)
    assert s.give_item("Ladeliste").holder == GROUP_HOLDER
    assert s.give_item("Frachtbrief", to="Ein Kurier").holder == GROUP_HOLDER


def test_give_item_is_idempotent_per_holder() -> None:
    s = WorldState.seed_from_store(_STORE)
    first = s.give_item("Zollvollmacht", to="Seskin", by="Kaad")
    again = s.give_item("zollvollmacht", to="Seskin", by="Kaad")
    assert again is first
    assert len(s.facts) == 1
    assert s.find("Seskin").inventory.count("Zollvollmacht") == 1


def test_take_item_revokes_the_fact_and_clears_the_sheet() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.give_item("Zollvollmacht", to="Seskin")
    f = s.take_item("Zollvollmacht", holder="Seskin")
    assert f is not None and f.status == "revoked"
    assert "Zollvollmacht" not in s.find("Seskin").inventory
    assert s.open_facts("item") == []
    assert s.take_item("Zollvollmacht", holder="Seskin") is None  # already revoked


def test_writers_reject_free_text_and_empty_values() -> None:
    s = WorldState.seed_from_store(_STORE)
    assert s.give_item("") is None
    assert s.give_item("   ") is None
    assert s.give_item("x" * (FACT_TEXT_MAX + 1)) is None
    assert s.give_item("Er reicht ihr die Vollmacht.\nSie nimmt sie entgegen.") is None
    assert s.record_promise("") is None
    assert s.record_commitment("geruecht", text="irgendwas") is None
    assert s.record_commitment("item", text="") is None
    assert s.facts == [] and s.quests == []  # a rejected verdict never touches state


def test_record_commitment_routes_the_classifier_verdict_by_kind() -> None:
    s = WorldState.seed_from_store(_STORE)
    q = s.record_commitment("quest", text="Das Ossarium zurückholen", by="Seneschall Kaad")
    assert isinstance(q, Quest) and q.status == "open" and q.given_by == "Seneschall Kaad"
    i = s.record_commitment("item", text="Zollvollmacht", to="Seskin", by="Kaad")
    assert isinstance(i, Fact) and i.kind == "item"
    p = s.record_commitment("promise", text="Freie Durchfahrt bis Mitternacht", by="Kaad")
    assert isinstance(p, Fact) and p.kind == "promise" and p.source == "Kaad"


def test_facts_are_capped_and_drop_the_revoked_ones_first() -> None:
    s = WorldState()
    s.give_item("Alter Krempel")
    s.take_item("Alter Krempel")
    for n in range(FACT_CAP):
        s.give_item(f"Gegenstand {n}")
    assert len(s.facts) == FACT_CAP
    assert all(f.status == "open" for f in s.facts)


def test_mission_is_a_hard_fact_and_the_only_one() -> None:
    s = WorldState()
    m = s.set_mission("Das Ossarium zurückholen",
                      detail="ein handtellergroßer Schrein aus Knochen und Messing",
                      given_by="Seneschall Kaad")
    assert m.is_mission and m.status == "open"
    again = s.set_mission("Das Ossarium doch nicht zurückholen")
    assert len(s.quests) == 1 and s.mission() is again  # one mission per campaign, replaced


def test_summary_names_the_mission_the_items_and_the_promises() -> None:
    s = WorldState.seed_from_store(_STORE)
    s.time_minutes = 21 * 60 + 10
    s.set_mission("Das Ossarium zurückholen", detail="ein Schrein aus Knochen und Messing")
    s.give_item("Zollvollmacht", to="Seskin", by="Seneschall Kaad")
    s.record_promise("Freie Durchfahrt bis Mitternacht", by="Kaad", to=GROUP_HOLDER)
    s.add_quest("Die Ladeliste beschaffen")
    out = world_state_summary_de(s)
    assert "Auftrag: Das Ossarium zurückholen — ein Schrein aus Knochen und Messing" in out
    assert "Zollvollmacht" in out and "Seneschall Kaad" in out and "Tag 1, 21:10" in out
    assert "Freie Durchfahrt bis Mitternacht" in out
    assert "Die Ladeliste beschaffen" in out
    # the mission does not double as a plain open quest
    assert out.count("Das Ossarium zurückholen") == 1


def test_summary_omits_the_new_sections_when_there_is_nothing_to_say() -> None:
    out = world_state_summary_de(WorldState())
    assert "Auftrag:" not in out and "Übergeben" not in out and "Zusagen" not in out


def test_facts_and_mission_survive_the_round_trip(tmp_path) -> None:
    s = WorldState.seed_from_store(_STORE, session_id="7")
    s.set_mission("Das Ossarium zurückholen", detail="ein Schrein", given_by="Kaad")
    s.give_item("Zollvollmacht", to="Seskin", by="Kaad")
    s.record_promise("Freie Durchfahrt", by="Kaad")
    path = tmp_path / "state.json"
    s.save(path)

    again = WorldState.load(path)
    assert again is not None
    m = again.mission()
    assert m is not None and m.detail == "ein Schrein" and m.given_by == "Kaad"
    item = again.find_fact("Zollvollmacht", kind="item")
    assert item is not None and item.holder == "Seskin" and item.source == "Kaad"
    assert [f.kind for f in again.open_facts()] == ["item", "promise"]


def test_a_pre_058_state_file_defaults_the_new_fields(tmp_path) -> None:
    # An older session file knows neither facts, nor the mission fields, nor the seed flag.
    legacy = {
        "session_id": "old", "system": "imperium_maledictum",
        "characters": [{"name": "Seskin", "wounds": 5, "max_wounds": 11}],
        "quests": [{"title": "Finde den Häretiker", "status": "open"}],
        "location": "Hive Primus", "time_minutes": 600, "recap": "",
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    s = WorldState.load(path)
    assert s is not None
    assert s.facts == [] and s.time_seeded is False
    q = s.quests[0]
    assert q.detail == "" and q.given_by == "" and q.at_minutes is None and q.is_mission is False
    assert s.mission() is None
    assert "Übergeben" not in world_state_summary_de(s)
    s.save(path)  # and the migrated file round-trips cleanly
    assert WorldState.load(path).facts == []
