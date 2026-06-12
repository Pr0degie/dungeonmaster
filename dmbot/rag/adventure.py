"""Adventure compendium — the scene-tracker half of the 3-stage hybrid (Phase 10a, ADR 019).

A hand-curated ``data/adventures/<id>/adventure.json`` (German scene cards authored offline from
the bought PDF) plus ``npcs.json`` (statblocks for the dice engine). The cog keeps a code-owned
pointer (``WorldState.scene_id``) into the scene list and the orchestrator injects two things into
every prompt: the always-on adventure summary (stage 1) and the *current* scene card (stage 2) —
so "where are we in the plot" is deterministic state, not vector-similarity luck, and part-3
spoilers can't surface while the party is in part 1. Pure file-reading + formatting; no LLM.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Scene:
    """One scene/location card — everything the DM needs to run the current beat."""

    id: str
    title_de: str
    part: int = 0
    description_de: str = ""
    npcs_here: list[str] = field(default_factory=list)
    opportunities_de: list[str] = field(default_factory=list)
    secrets_de: list[str] = field(default_factory=list)
    leads_to: list[str] = field(default_factory=list)
    guidance_de: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(
            id=str(d.get("id", "") or ""),
            title_de=str(d.get("title_de", "") or ""),
            part=int(d.get("part", 0) or 0),
            description_de=str(d.get("description_de", "") or ""),
            npcs_here=[str(n) for n in d.get("npcs_here", []) or []],
            opportunities_de=[str(o) for o in d.get("opportunities_de", []) or []],
            secrets_de=[str(s) for s in d.get("secrets_de", []) or []],
            leads_to=[str(x) for x in d.get("leads_to", []) or []],
            guidance_de=str(d.get("guidance_de", "") or ""),
        )


@dataclass
class AdventureNpc:
    """A statblock from ``npcs.json`` — feeds ``!npc add`` (wounds/TB/armour for the engine) and
    gives the DM the roleplaying notes. ``attack_*`` fields are informational (NPC→PC damage is
    narrated / GM-overridden; the engine computes PC→NPC damage)."""

    name: str
    role_de: str = ""
    wounds: int = 10
    toughness_bonus: int = 0
    armour: int = 0
    roleplaying_de: str = ""
    attack_skill: str | None = None
    attack_value: int | None = None
    weapon: str | None = None
    damage: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "AdventureNpc":
        return cls(
            name=str(d.get("name", "") or ""),
            role_de=str(d.get("role_de", "") or ""),
            wounds=int(d.get("wounds", 10) or 10),
            toughness_bonus=int(d.get("toughness_bonus", 0) or 0),
            armour=int(d.get("armour", 0) or 0),
            roleplaying_de=str(d.get("roleplaying_de", "") or ""),
            attack_skill=d.get("attack_skill"),
            attack_value=d.get("attack_value"),
            weapon=d.get("weapon"),
            damage=d.get("damage"),
        )


class Adventure:
    """A loaded compendium: scenes by id + NPC statblocks by (lowercased) name."""

    def __init__(
        self,
        *,
        id: str = "",
        title: str = "",
        start_scene: str = "",
        summary_de: str = "",
        scenes: list[Scene] | None = None,
        npcs: list[AdventureNpc] | None = None,
    ) -> None:
        self.id = id
        self.title = title
        self.start_scene = start_scene
        self.summary_de = summary_de
        self._scenes: dict[str, Scene] = {s.id: s for s in (scenes or []) if s.id}
        self._npcs: dict[str, AdventureNpc] = {n.name.lower(): n for n in (npcs or []) if n.name}

    # -- loading --------------------------------------------------------------------------

    @classmethod
    def load(cls, directory: Path) -> "Adventure | None":
        """Load ``adventure.json`` (+ optional ``npcs.json``) from ``directory``. ``None`` (with a
        loud log) when missing/broken — an unloadable adventure must not down the bot; the DM then
        simply runs without a scene tracker, like before Phase 10a."""
        adv_path = directory / "adventure.json"
        if not adv_path.is_file():
            log.error("no adventure.json under %s — running without an adventure", directory)
            return None
        try:
            data = json.loads(adv_path.read_text(encoding="utf-8"))
            scenes = [Scene.from_dict(s) for s in data.get("scenes", []) or []]
            npcs: list[AdventureNpc] = []
            npc_path = directory / "npcs.json"
            if npc_path.is_file():
                npc_data = json.loads(npc_path.read_text(encoding="utf-8"))
                npcs = [AdventureNpc.from_dict(n) for n in npc_data.get("npcs", []) or []]
            return cls(
                id=str(data.get("id", "") or directory.name),
                title=str(data.get("title", "") or ""),
                start_scene=str(data.get("start_scene", "") or (scenes[0].id if scenes else "")),
                summary_de=str(data.get("summary_de", "") or ""),
                scenes=scenes,
                npcs=npcs,
            )
        except (OSError, ValueError, KeyError):
            log.exception("broken adventure compendium under %s — running without it", directory)
            return None

    # -- lookups --------------------------------------------------------------------------

    def get_scene(self, scene_id: str) -> Scene | None:
        return self._scenes.get((scene_id or "").strip())

    def scene_overview(self) -> list[tuple[int, str, str]]:
        """``(part, id, title_de)`` per scene, in file order — for ``!szenen``."""
        return [(s.part, s.id, s.title_de) for s in self._scenes.values()]

    def npc_count(self) -> int:
        return len(self._npcs)

    def npc(self, name: str) -> AdventureNpc | None:
        """Statblock lookup by name, case-insensitive; underscores tolerated (Discord args can't
        carry spaces, so ``!npc add Raguel_der_Rote`` must match 'Raguel der Rote')."""
        key = (name or "").strip().lower()
        return self._npcs.get(key) or self._npcs.get(key.replace("_", " "))

    # -- prompt block (stages 1+2) ----------------------------------------------------------

    def adventure_block_de(self, scene_id: str) -> str:
        """The German prompt block: the always-on summary (stage 1) + the current scene card
        (stage 2). An unknown/empty ``scene_id`` degrades to the summary alone."""
        lines = [
            "## Abenteuer (nur für dich als Spielleitung — niemals wörtlich vorlesen)",
            self.summary_de,
        ]
        scene = self.get_scene(scene_id)
        if scene is not None:
            lines.append("")
            lines.append(f"## Aktuelle Szene: {scene.title_de} (Teil {scene.part})")
            lines.append(scene.description_de)
            if scene.npcs_here:
                lines.append("Anwesende NSCs: " + ", ".join(scene.npcs_here))
            if scene.opportunities_de:
                lines.append("Möglichkeiten hier:")
                lines.extend(f"- {o}" for o in scene.opportunities_de)
            if scene.secrets_de:
                lines.append("Geheimnisse (NIE aussprechen, höchstens andeuten):")
                lines.extend(f"- {s}" for s in scene.secrets_de)
            if scene.guidance_de:
                lines.append(f"Spielleitungs-Hinweis: {scene.guidance_de}")
            if scene.leads_to:
                lines.append("Mögliche nächste Orte: " + ", ".join(scene.leads_to))
        return "\n".join(line for line in lines if line is not None).strip()
