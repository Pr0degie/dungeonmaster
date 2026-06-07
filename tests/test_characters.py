"""Character store + target resolution (ADR 004) — alias map (open item F) and 'roll FOR the
player' (open item K): target = skill value (JSON) + difficulty modifier (profile ladder)."""

from __future__ import annotations

from dmbot.rules import profile as profile_mod
from dmbot.rules.characters import CharacterStore, resolve_target

_IM = profile_mod.load("imperium_maledictum")

_STORE = CharacterStore.from_dict(
    {
        "characters": [
            {
                "name": "Seskin",
                "characteristics": {"WS": 40, "Per": 48},
                "skills": {"Wahrnehmung": 48, "Heimlichkeit": 52},
                "wounds": 11, "max_wounds": 11,
            },
            {"name": "Mortn", "characteristics": {"Int": 52}, "skills": {"Wahrnehmung": 44}},
        ],
        "aliases": {"SezBoss69": "Seskin", "Tobi": "Mortn"},
    }
)


def test_lookup_by_name_and_alias() -> None:
    assert _STORE.get("Seskin").name == "Seskin"
    assert _STORE.get("sezboss69").name == "Seskin"   # alias, case-insensitive
    assert _STORE.get("Tobi").name == "Mortn"
    assert _STORE.get("Unbekannt") is None


def test_skill_value_with_characteristic_fallback() -> None:
    seskin = _STORE.get("Seskin")
    assert _STORE.skill_value(seskin, "Wahrnehmung") == 48
    assert _STORE.skill_value(seskin, "wahrnehmung") == 48      # case-insensitive
    assert _STORE.skill_value(seskin, "WS") == 40               # characteristic fallback
    assert _STORE.skill_value(seskin, "Kochen") is None         # unknown


def test_resolve_target_applies_difficulty_from_the_ladder() -> None:
    # Tobi → Mortn, Wahrnehmung 44, Schwer −20 → target 24. The number comes from code.
    rt = resolve_target(_IM, _STORE, skill="Wahrnehmung", target_name="Tobi", difficulty="Schwer")
    assert rt.character.name == "Mortn"
    assert rt.base == 44 and rt.modifier == -20 and rt.target == 24
    assert rt.difficulty == "Schwer"


def test_resolve_target_explicit_modifier_overrides_ladder() -> None:
    rt = resolve_target(_IM, _STORE, skill="Heimlichkeit", target_name="Seskin", modifier=10)
    assert rt.base == 52 and rt.modifier == 10 and rt.target == 62 and rt.difficulty is None


def test_resolve_target_unknown_difficulty_falls_back_to_default() -> None:
    rt = resolve_target(_IM, _STORE, skill="Wahrnehmung", target_name="Seskin", difficulty="Banane")
    assert rt.modifier == 0 and rt.difficulty == "Herausfordernd"  # default ladder rung


def test_resolve_target_without_character_has_no_target() -> None:
    rt = resolve_target(_IM, _STORE, skill="Wahrnehmung", target_name=None, difficulty="Schwer")
    assert rt.character is None and rt.base is None and rt.target is None


def test_alias_hint_lists_who_plays_whom() -> None:
    hint = _STORE.alias_hint_de()
    assert "spielt" in hint and "Seskin" in hint and "Mortn" in hint
