"""Character store — lean structured JSON the engine rolls against (ADR 004 + D12).

Characters live as ``data/sessions/<channel>/characters.json``: the player sheets transferred
**once** into JSON (sheets never go into RAG). The *shape* follows the active system profile
(§9). This gives two things Phase 8 needs:

1. **Stat-aware target resolution** — the GM rolls *for* the player: target = skill value
   (from here) ± difficulty modifier (from the profile ladder). Neither number comes from the
   LLM (golden rule #2 / open item K).
2. **Display-name → character alias map** — fixes the model confusing "SezBoss69" with the
   character "Seskin" (open item F); injected as a light hint into the prompt.

Pure data + pure functions, unit-tested without Discord or the LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .profile import SystemProfile


@dataclass(frozen=True, slots=True)
class Character:
    """One player character. Stat fields follow the active profile's schema."""

    name: str
    characteristics: dict[str, int] = field(default_factory=dict)
    skills: dict[str, int] = field(default_factory=dict)
    wounds: int | None = None
    max_wounds: int | None = None
    inventory: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        return cls(
            name=data["name"],
            characteristics={k: int(v) for k, v in (data.get("characteristics", {}) or {}).items()},
            skills={k: int(v) for k, v in (data.get("skills", {}) or {}).items()},
            wounds=data.get("wounds"),
            max_wounds=data.get("max_wounds"),
            inventory=tuple(data.get("inventory", []) or []),
            conditions=tuple(data.get("conditions", []) or []),
            raw=dict(data),
        )


@dataclass(frozen=True, slots=True)
class ResolvedTest:
    """A test request resolved against a character + profile, ready for the engine.

    ``target`` is ``None`` when the skill value is unknown (no character/skill match) — the
    caller still rolls the die but can't compute SL, so it asks the player to compare manually.
    """

    skill: str
    character: Character | None
    base: int | None              # the skill (or characteristic) value, before difficulty
    modifier: int                 # the difficulty modifier applied
    difficulty: str | None        # canonical difficulty label, for display
    target: int | None            # base + modifier (None if base is None)


class CharacterStore:
    """Characters + a display-name→character alias map for one session."""

    def __init__(
        self, characters: list[Character] | None = None, aliases: dict[str, str] | None = None
    ) -> None:
        self._by_name: dict[str, Character] = {c.name.lower(): c for c in (characters or [])}
        # alias (display name) → character name, lower-cased keys for case-insensitive lookup …
        self._aliases: dict[str, str] = {k.lower(): v for k, v in (aliases or {}).items()}
        # … but keep the original-case display names for the prompt hint.
        self._alias_pairs: list[tuple[str, str]] = list((aliases or {}).items())

    # -- construction ---------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterStore":
        chars = [Character.from_dict(c) for c in data.get("characters", [])]
        return cls(chars, data.get("aliases", {}))

    @classmethod
    def load(cls, path: Path) -> "CharacterStore":
        """Load a characters JSON. A missing file yields an empty store (no characters yet)."""
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # -- lookup ---------------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._by_name)

    def characters(self) -> list[Character]:
        """All loaded characters (insertion order). Used to seed the mutable world state (§7)."""
        return list(self._by_name.values())

    def get(self, name: str | None) -> Character | None:
        """Find a character by character name or by a player's display-name alias."""
        if not name:
            return None
        key = name.lower()
        if key in self._by_name:
            return self._by_name[key]
        alias = self._aliases.get(key)
        if alias and alias.lower() in self._by_name:
            return self._by_name[alias.lower()]
        return None

    def skill_value(self, character: Character | None, skill: str) -> int | None:
        """Skill value for ``skill`` (case-insensitive). Falls back to a same-named
        characteristic (the IM governing characteristic is often what a 'test' names), else
        ``None``."""
        if character is None or not skill:
            return None
        key = skill.strip().lower()
        for name, value in character.skills.items():
            if name.lower() == key:
                return value
        for name, value in character.characteristics.items():
            if name.lower() == key:
                return value
        return None

    def alias_hint_de(self) -> str:
        """A short 'who plays whom' line for the prompt (open item F). Empty if no aliases."""
        if not self._alias_pairs:
            return ""
        pairs = [f"{display} spielt {char}" for display, char in self._alias_pairs]
        return "Am Tisch: " + "; ".join(pairs) + "."


def resolve_target(
    profile: SystemProfile,
    store: CharacterStore | None,
    *,
    skill: str,
    target_name: str | None = None,
    difficulty: str | None = None,
    modifier: int | None = None,
) -> ResolvedTest:
    """Resolve a parsed test into a numeric target — the 'dice = code' core (open item K).

    target = skill value (from the character JSON) + difficulty modifier (explicit ``±N``
    override, else the profile difficulty ladder). The LLM supplies neither number.
    """
    character = store.get(target_name) if store is not None else None
    base = store.skill_value(character, skill) if store is not None else None

    if modifier is not None:
        mod, label = modifier, None  # explicit ±N override from the marker
    else:
        mod = profile.difficulty_modifier(difficulty)
        if mod is None:  # unknown word → fall back to the profile default
            mod = profile.difficulty_modifier(None) or 0
            label = profile.canonical_difficulty(None)
        else:
            label = profile.canonical_difficulty(difficulty)

    target = base + mod if base is not None else None
    return ResolvedTest(
        skill=skill, character=character, base=base, modifier=mod, difficulty=label, target=target
    )
