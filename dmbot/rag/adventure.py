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
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


def _parse_elements(raw: list, prefix: str) -> tuple[list[str], list[str]]:
    """``opportunities_de``/``secrets_de`` entries are a plain string (today's form) or
    ``{"id": ..., "text_de": ...}`` (ADR 043). Returns (texts, ids); a plain entry gets the
    deterministic positional id ``{prefix}-{n}`` — position counts across the whole list, so
    mixing both forms keeps derived ids stable."""
    texts: list[str] = []
    ids: list[str] = []
    for i, entry in enumerate(raw or [], start=1):
        if isinstance(entry, dict):
            texts.append(str(entry.get("text_de", "") or ""))
            ids.append(str(entry.get("id", "") or "") or f"{prefix}-{i}")
        else:
            texts.append(str(entry))
            ids.append(f"{prefix}-{i}")
    return texts, ids


def _parse_exits(raw: list) -> tuple[list[str], dict[str, str]]:
    """``leads_to`` entries are a plain scene-id string or ``{"ziel": ..., "requires": ...}``
    (ADR 043, gated exits). Returns (target ids in today's shape, target → required element id)."""
    targets: list[str] = []
    requires: dict[str, str] = {}
    for entry in raw or []:
        if isinstance(entry, dict):
            ziel = str(entry.get("ziel", "") or "")
            if not ziel:
                continue
            targets.append(ziel)
            req = str(entry.get("requires", "") or "")
            if req:
                requires[ziel] = req
        else:
            targets.append(str(entry))
    return targets, requires


@dataclass
class Scene:
    """One scene/location card — everything the DM needs to run the current beat.

    ``opportunity_ids``/``secret_ids`` run parallel to their ``*_de`` text lists (ADR 043) —
    they are backfilled positionally when not provided, so directly-constructed Scenes and
    legacy plain-string JSON both satisfy ``len(ids) == len(texts)``. ``exit_requires`` maps a
    ``leads_to`` target to the element id (of THIS scene) that must be resolved first."""

    id: str
    title_de: str
    part: int = 0
    description_de: str = ""
    npcs_here: list[str] = field(default_factory=list)
    opportunities_de: list[str] = field(default_factory=list)
    secrets_de: list[str] = field(default_factory=list)
    leads_to: list[str] = field(default_factory=list)
    guidance_de: str = ""
    opportunity_ids: list[str] = field(default_factory=list)
    secret_ids: list[str] = field(default_factory=list)
    exit_requires: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Backfill missing/mismatched ids positionally (direct construction, legacy callers).
        if len(self.opportunity_ids) != len(self.opportunities_de):
            self.opportunity_ids = [f"opp-{i}" for i in range(1, len(self.opportunities_de) + 1)]
        if len(self.secret_ids) != len(self.secrets_de):
            self.secret_ids = [f"geh-{i}" for i in range(1, len(self.secrets_de) + 1)]
        # Ids must be unique within the scene across BOTH lists — loud log + positional fallback
        # on collision (degrade, don't die: the card must keep rendering).
        seen: set[str] = set()
        for ids, prefix in ((self.opportunity_ids, "opp"), (self.secret_ids, "geh")):
            for i, eid in enumerate(ids):
                if eid in seen:
                    fallback = f"{prefix}-{i + 1}"
                    n = 2
                    while fallback in seen:
                        fallback = f"{prefix}-{i + 1}-{n}"
                        n += 1
                    log.error(
                        "scene '%s': duplicate element id '%s' — using '%s' instead",
                        self.id, eid, fallback,
                    )
                    ids[i] = fallback
                seen.add(ids[i])
        # A gate must point at an element of THIS scene; a typo'd requirement would lock the
        # exit forever, so it fails open (gate dropped, loud log).
        for ziel, req in list(self.exit_requires.items()):
            if req not in seen:
                log.error(
                    "scene '%s': exit '%s' requires unknown element '%s' — dropping the gate",
                    self.id, ziel, req,
                )
                del self.exit_requires[ziel]

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        opportunities, opportunity_ids = _parse_elements(d.get("opportunities_de", []) or [], "opp")
        secrets, secret_ids = _parse_elements(d.get("secrets_de", []) or [], "geh")
        leads_to, exit_requires = _parse_exits(d.get("leads_to", []) or [])
        return cls(
            id=str(d.get("id", "") or ""),
            title_de=str(d.get("title_de", "") or ""),
            part=int(d.get("part", 0) or 0),
            description_de=str(d.get("description_de", "") or ""),
            npcs_here=[str(n) for n in d.get("npcs_here", []) or []],
            opportunities_de=opportunities,
            secrets_de=secrets,
            leads_to=leads_to,
            guidance_de=str(d.get("guidance_de", "") or ""),
            opportunity_ids=opportunity_ids,
            secret_ids=secret_ids,
            exit_requires=exit_requires,
        )

    def element_ids(self) -> list[str]:
        """All flaggable element ids of this scene (opportunities first, then secrets)."""
        return [*self.opportunity_ids, *self.secret_ids]

    def element_text(self, element_id: str) -> str | None:
        """The German text behind ``element_id``, or None for a foreign/unknown id."""
        for ids, texts in ((self.opportunity_ids, self.opportunities_de),
                           (self.secret_ids, self.secrets_de)):
            for eid, text in zip(ids, texts):
                if eid == element_id:
                    return text
        return None


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

    def resolve_move(
        self, current_scene_id: str, target_id: str, mode: str,
        *, resolved_ids: Collection[str] = (),
    ) -> Scene | None:
        """Validate an automatic scene-transition request (ADR 026) and return the target Scene, or
        None if the move is rejected. Pure + deterministic (unit-tested without Discord). Rejects:
        an unknown ``target_id``; a move to the current scene (no-op); and — in ``verbunden`` mode —
        any target not listed in the current scene's ``leads_to`` or whose gate (``exit_requires``,
        ADR 043) isn't met by ``resolved_ids``. ``frei`` accepts any known scene (and thereby
        bypasses gates — it never consults the current scene). The unmet-gate hint goes to the
        console/log only, never to the channel (spoiler discipline)."""
        target_id = (target_id or "").strip()
        if not target_id or target_id == (current_scene_id or "").strip():
            return None
        target = self.get_scene(target_id)
        if target is None:
            return None
        if mode == "verbunden":
            current = self.get_scene(current_scene_id)
            if current is None or target.id not in current.leads_to:
                return None
            required = current.exit_requires.get(target.id)
            if required and required not in set(resolved_ids):
                log.info(
                    "🚫 Ausgang '%s' → '%s' verriegelt — Bedingung '%s' nicht erledigt",
                    current.id, target.id, required,
                )
                return None
        return target

    def npc_count(self) -> int:
        return len(self._npcs)

    def npc(self, name: str) -> AdventureNpc | None:
        """Statblock lookup by name, case-insensitive; underscores tolerated (Discord args can't
        carry spaces, so ``!npc add Raguel_der_Rote`` must match 'Raguel der Rote')."""
        key = (name or "").strip().lower()
        return self._npcs.get(key) or self._npcs.get(key.replace("_", " "))

    # -- prompt block (stages 1+2) ----------------------------------------------------------

    def adventure_block_de(
        self, scene_id: str,
        *, resolved_ids: Collection[str] = (), dead_npcs: Collection[str] = (),
    ) -> str:
        """The German prompt block: the always-on summary (stage 1) + the current scene card
        (stage 2). An unknown/empty ``scene_id`` degrades to the summary alone.

        Stateful (ADR 043): ``resolved_ids`` (this scene's flags from ``WorldState.scene_flags``)
        move a resolved Gelegenheit to „Bereits geschehen" and a revealed Geheimnis to „Bekannt",
        and hide gated exits until unlocked; ``dead_npcs`` (lowercase-joined by name) render as
        ``(tot)``. Plain collections, not WorldState — keeps ``rag/`` decoupled from ``memory/``.
        Element ids render inline (``- [opp-1] …``) so the model can cite them in ``<<ERLEDIGT>>``."""
        lines = [
            "## Abenteuer (nur für dich als Spielleitung — niemals wörtlich vorlesen)",
            self.summary_de,
        ]
        scene = self.get_scene(scene_id)
        if scene is not None:
            resolved = {str(r) for r in resolved_ids}
            dead = {str(n).strip().lower() for n in dead_npcs}
            opportunities = list(zip(scene.opportunity_ids, scene.opportunities_de))
            secrets = list(zip(scene.secret_ids, scene.secrets_de))
            open_opps = [(eid, t) for eid, t in opportunities if eid not in resolved]
            done_opps = [(eid, t) for eid, t in opportunities if eid in resolved]
            open_secrets = [(eid, t) for eid, t in secrets if eid not in resolved]
            known_secrets = [(eid, t) for eid, t in secrets if eid in resolved]
            lines.append("")
            lines.append(f"## Aktuelle Szene: {scene.title_de} (Teil {scene.part})")
            lines.append(scene.description_de)
            if scene.npcs_here:
                names = [f"{n} (tot)" if n.strip().lower() in dead else n for n in scene.npcs_here]
                lines.append("Anwesende NSCs: " + ", ".join(names))
            if open_opps:
                lines.append("Möglichkeiten hier:")
                lines.extend(f"- [{eid}] {t}" for eid, t in open_opps)
            if done_opps:
                lines.append("Bereits geschehen:")
                lines.extend(f"- [{eid}] {t}" for eid, t in done_opps)
            if open_secrets:
                lines.append("Geheimnisse (NIE aussprechen, höchstens andeuten):")
                lines.extend(f"- [{eid}] {t}" for eid, t in open_secrets)
            if known_secrets:
                lines.append("Bekannt (bereits enthüllt):")
                lines.extend(f"- [{eid}] {t}" for eid, t in known_secrets)
            if scene.guidance_de:
                lines.append(f"Spielleitungs-Hinweis: {scene.guidance_de}")
            exits = [t for t in scene.leads_to
                     if scene.exit_requires.get(t) is None or scene.exit_requires[t] in resolved]
            if exits:
                lines.append("Mögliche nächste Orte: " + ", ".join(exits))
        return "\n".join(line for line in lines if line is not None).strip()
