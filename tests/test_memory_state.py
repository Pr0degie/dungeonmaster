"""World state (Phase 9, ADR 015): deterministic advancement + persistence (the code half of the
gate 'an HP change survives a restart') and the engine's combat-damage math. Pure — no Discord,
no LLM, seeded RNG where dice are involved.
"""

from __future__ import annotations

import random

from dmbot.memory.state import DOWNED_CONDITION, WorldState, world_state_summary_de
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


def test_summary_empty_state_is_empty() -> None:
    assert world_state_summary_de(WorldState()) == ""


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
