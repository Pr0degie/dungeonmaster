"""System profile loader — the *data* half of the generic rules engine (ADR 005).

A profile (``data/systems/<name>.json``) declares one ruleset's core mechanic: dice,
resolution kind, where the target comes from, how degrees of success are computed, the
difficulty ladder, and the character schema. The engine (:mod:`dmbot.rules.engine`) reads
these and stays game-agnostic — IM is just the first profile, nothing is hardcoded.

Pure data + a thin typed wrapper, so it unit-tests without Discord or the LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Repo data dir: this file is dmbot/rules/profile.py → parents[2] is the repo root.
_DATA_SYSTEMS = Path(__file__).resolve().parents[2] / "data" / "systems"

_REQUIRED = ("name", "dice", "resolution")


class ProfileError(ValueError):
    """A system profile is missing or malformed — raised with a human-readable reason."""


@dataclass(frozen=True, slots=True)
class SystemProfile:
    """One ruleset's declarative mechanic. Build via :meth:`from_dict` / :func:`load`."""

    name: str
    dice: str
    resolution: str
    display_name: str = ""
    target_source: str = "skill_value"
    degrees: str = "tens_difference"
    default_difficulty: str = ""
    difficulty_ladder: dict[str, int] = field(default_factory=dict)
    difficulty_aliases: dict[str, str] = field(default_factory=dict)
    crit: str = ""
    auto_success_max: int = 0   # rolls <= this always succeed (0 = no band). IM: 5.
    auto_fail_min: int = 0      # rolls >= this always fail (0 = no band). IM: 96.
    damage: "str | dict" = ""   # free-text ("weapon_damage + SL") or structured, per architecture §9
    character_schema: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)  # full source dict, for forward-compat reads

    @classmethod
    def from_dict(cls, data: dict) -> "SystemProfile":
        missing = [k for k in _REQUIRED if not data.get(k)]
        if missing:
            raise ProfileError(f"profile is missing required key(s): {', '.join(missing)}")
        ladder = data.get("difficulty_ladder", {}) or {}
        if not all(isinstance(v, int) for v in ladder.values()):
            raise ProfileError("difficulty_ladder values must all be integers")
        return cls(
            name=data["name"],
            dice=data["dice"],
            resolution=data["resolution"],
            display_name=data.get("display_name", data["name"]),
            target_source=data.get("target_source", "skill_value"),
            degrees=data.get("degrees", "tens_difference"),
            default_difficulty=data.get("default_difficulty", ""),
            difficulty_ladder=dict(ladder),
            difficulty_aliases={k.lower(): v for k, v in (data.get("difficulty_aliases", {}) or {}).items()},
            crit=data.get("crit", ""),
            auto_success_max=int(data.get("auto_success_max", 0)),
            auto_fail_min=int(data.get("auto_fail_min", 0)),
            damage=data.get("damage", "") or "",
            character_schema=dict(data.get("character_schema", {}) or {}),
            raw=dict(data),
        )

    def difficulty_modifier(self, name: str | None) -> int | None:
        """Map a difficulty name to its modifier via the profile ladder (case-insensitive,
        aliases honoured). ``None`` input → the default difficulty. Returns ``None`` for an
        unknown word so the caller can fall back to the default."""
        if name is None:
            name = self.default_difficulty
        if not name:
            return None
        key = name.strip()
        # exact (case-insensitive) ladder hit
        for label, mod in self.difficulty_ladder.items():
            if label.lower() == key.lower():
                return mod
        # alias → canonical label
        canon = self.difficulty_aliases.get(key.lower())
        if canon is not None:
            for label, mod in self.difficulty_ladder.items():
                if label.lower() == canon.lower():
                    return mod
        return None

    def canonical_difficulty(self, name: str | None) -> str | None:
        """The canonical ladder label for ``name`` (resolving aliases/case), or ``None``."""
        if name is None:
            name = self.default_difficulty
        if not name:
            return None
        key = name.strip()
        for label in self.difficulty_ladder:
            if label.lower() == key.lower():
                return label
        canon = self.difficulty_aliases.get(key.lower())
        if canon is not None:
            for label in self.difficulty_ladder:
                if label.lower() == canon.lower():
                    return label
        return None

    def difficulty_names(self) -> list[str]:
        """Canonical ladder labels, hardest first only by declaration order — for the prompt."""
        return list(self.difficulty_ladder)


def systems_dir() -> Path:
    return _DATA_SYSTEMS


def load(name: str, *, systems_root: Path | None = None) -> SystemProfile:
    """Load and validate the profile ``data/systems/<name>.json``.

    Raises :class:`ProfileError` if the file is absent or malformed, with a reason the
    caller can surface (the cog logs it and runs rules-less rather than crashing).
    """
    root = systems_root or _DATA_SYSTEMS
    path = root / f"{name}.json"
    if not path.is_file():
        raise ProfileError(f"no system profile at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"could not read profile {path}: {exc}") from exc
    return SystemProfile.from_dict(data)
