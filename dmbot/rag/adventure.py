"""Adventure compendium — the scene-tracker half of the 3-stage hybrid (Phase 10a, ADR 019).

A hand-curated ``data/adventures/<id>/adventure.json`` (German scene cards authored offline from
the bought PDF) plus ``npcs.json`` (statblocks for the dice engine). The cog keeps a code-owned
pointer (``WorldState.scene_id``) into the scene list and the orchestrator injects two things into
every prompt: the always-on adventure summary (stage 1) and the *current* scene card (stage 2) —
so "where are we in the plot" is deterministic state, not vector-similarity luck, and part-3
spoilers can't surface while the party is in part 1. Pure file-reading + formatting; no LLM.

D107 (ADR 057/059) widened both halves. The adventure now also ships its own clock —
``start_time_de``, ``deadlines``, ``clocks`` — plus ``briefing_de``, the spoken plain-language
opening; all four are read here and handed to the wiring untouched. And the scene card renders
what the model was missing on 2026-08-22: exits as ``id — title`` instead of a bare id, the
present NPCs with their role and manner from ``npcs.json``, the description labelled as
reference material rather than ready-made prose, and the scene's standing guidance only when
the caller asks for it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Scene-card labels. Constants, not inline literals: the wording is the whole point of B5/B2/A5
# (the card was recited verbatim, the NPCs had no manner, the guidance became a standing order).
MATERIAL_HINT_DE = (
    "Material zur Szene (Notizen für dich, keine fertige Erzählung — nicht vorlesen und nicht "
    "abschreiben; erzähle mit eigenen Worten, was die Gruppe jetzt wahrnimmt):"
)
NPC_HEADER_DE = (
    "Anwesende NSCs (jeder klingt anders — spiele die Spielweise, nicht nur den Namen):"
)
GUIDANCE_PREFIX_DE = "Regie-Impuls für diesen Zug (einmalig, kein Dauerauftrag): "


def _parse_elements(
    raw: list, prefix: str, *, scene_id: str = "", warn_missing_ids: bool = False,
) -> tuple[list[str], list[str]]:
    """``opportunities_de``/``secrets_de`` entries are a plain string (today's form) or
    ``{"id": ..., "text_de": ...}`` (ADR 043). Returns (texts, ids); a plain entry gets the
    deterministic positional id ``{prefix}-{n}`` — position counts across the whole list, so
    mixing both forms keeps derived ids stable.

    ``warn_missing_ids`` (opportunities only) is a **deliberate deviation from ADR 057 #3**,
    which asks the loader to treat an id-less opportunity as a load-time content error. It warns
    loudly instead: ``chemical_burn`` is unversioned local-only content with no ids anywhere, and
    a hard error would make it unloadable — golden rule "an unloadable adventure must not down
    the bot" outranks the enforcement here. The cost is that such a campaign silently loses the
    flag gate (``scene_flow.has_authored_opportunity_ids`` detects the positional fallback), so
    the warning names the scene and says what stops working."""
    texts: list[str] = []
    ids: list[str] = []
    missing: list[int] = []
    for i, entry in enumerate(raw or [], start=1):
        if isinstance(entry, dict):
            texts.append(str(entry.get("text_de", "") or ""))
            authored = str(entry.get("id", "") or "")
            ids.append(authored or f"{prefix}-{i}")
            if not authored:
                missing.append(i)
        else:
            texts.append(str(entry))
            ids.append(f"{prefix}-{i}")
            missing.append(i)
    if warn_missing_ids and missing:
        log.warning(
            "scene '%s': %d of %d opportunities without an id (positions %s) — using positional "
            "ids; the flag gate cannot advance this scene (ADR 057 #3)",
            scene_id, len(missing), len(texts), ", ".join(str(i) for i in missing),
        )
    return texts, ids


def _parse_mappings(raw: object, kind: str, adventure_id: str) -> list[dict]:
    """``deadlines``/``clocks`` from the adventure file (ADR 059 #1), passed through as plain
    dicts. Only non-mapping entries are dropped here (loudly) — the field-level rules live in
    ``WorldState.seed_time_from_adventure``, which already skips-and-logs a malformed entry, and
    duplicating them would give two places to disagree about what a valid clock is."""
    if raw is not None and not isinstance(raw, (list, tuple)):
        log.error("adventure '%s': %s field is not a list — ignored: %r", adventure_id, kind, raw)
        return []
    out: list[dict] = []
    for entry in raw or ():
        if isinstance(entry, Mapping):
            out.append(dict(entry))
        else:
            log.error("adventure '%s': %s entry is not an object — dropped: %r",
                      adventure_id, kind, entry)
    return out


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
        scene_id = str(d.get("id", "") or "")
        opportunities, opportunity_ids = _parse_elements(
            d.get("opportunities_de", []) or [], "opp",
            scene_id=scene_id, warn_missing_ids=True,
        )
        secrets, secret_ids = _parse_elements(d.get("secrets_de", []) or [], "geh")
        leads_to, exit_requires = _parse_exits(d.get("leads_to", []) or [])
        return cls(
            id=scene_id,
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
    # Gossip group (ADR 044): NPCs sharing a non-empty faction hear each other's important
    # memories as hearsay. Authored data — optional, absent statblocks simply don't gossip.
    faction: str = ""
    # Agenda goal (ADR 049): a non-empty goal makes this NPC an agenda NPC on registration —
    # it pursues the goal offscreen. Authored data; keep it to the few NPCs that drive the plot.
    goal_de: str = ""
    # Anonymous extra: this statblock's "name" is a role, not a person („Kettenbund-Schläger") —
    # a mook the DM may have shout in any scene. Such a name is kept out of
    # :meth:`Adventure.npc_names`, so the consistency guard (ADR 045) never presence-checks it.
    # A named individual stays False, however minor.
    generic: bool = False

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
            faction=str(d.get("faction", "") or ""),
            goal_de=str(d.get("goal_de", "") or ""),
            generic=bool(d.get("generic", False)),
        )


class Adventure:
    """A loaded compendium: scenes by id + NPC statblocks by (lowercased) name.

    Besides the scene chain it carries the campaign's own clock (ADR 059 #1), its spoken opening
    and its objective: ``start_time_de`` (``"Tag 1, 21:00"``), ``deadlines``/``clocks`` (dicts in
    the shape ``WorldState.seed_time_from_adventure`` consumes), ``briefing_de`` (the
    plain-language briefing read out before the atmosphere prose) and ``mission``
    (``{"title_de", "detail_de", "given_by"}``, seeded as the mission quest, ADR 058 #3). All are
    optional — an adventure without them behaves exactly as before, which is what keeps the
    older compendia loadable."""

    def __init__(
        self,
        *,
        id: str = "",
        title: str = "",
        start_scene: str = "",
        summary_de: str = "",
        scenes: list[Scene] | None = None,
        npcs: list[AdventureNpc] | None = None,
        start_time_de: str = "",
        deadlines: list[dict] | None = None,
        clocks: list[dict] | None = None,
        briefing_de: str = "",
        mission: dict | None = None,
    ) -> None:
        self.id = id
        self.title = title
        self.start_scene = start_scene
        self.summary_de = summary_de
        self.start_time_de = start_time_de
        self.deadlines: list[dict] = list(deadlines or [])
        self.clocks: list[dict] = list(clocks or [])
        self.briefing_de = briefing_de
        # The campaign's objective (ADR 058 #3): ``{"title_de", "detail_de", "given_by"}``, seeded
        # into the world state as the mission quest at session start so "what is our mission?"
        # has a hard answer in the prompt AND on the player panel. Optional — no field, no seed.
        self.mission: dict = dict(mission or {})
        self._scenes: dict[str, Scene] = {s.id: s for s in (scenes or []) if s.id}
        self._npcs: dict[str, AdventureNpc] = {n.name.lower(): n for n in (npcs or []) if n.name}

    # -- loading --------------------------------------------------------------------------

    @classmethod
    def load(cls, directory: Path) -> "Adventure | None":
        """Load ``adventure.json`` (+ optional ``npcs.json``) from ``directory``. ``None`` (with a
        loud log) when missing/broken — an unloadable adventure must not down the bot; the DM then
        simply runs without a scene tracker, like before Phase 10a.

        Content problems short of "broken" degrade the same way: an opportunity without an id
        warns and falls back to a positional id instead of failing the load (see
        ``_parse_elements`` for why this deviates from ADR 057 #3), and a malformed
        deadline/clock entry is dropped."""
        adv_path = directory / "adventure.json"
        if not adv_path.is_file():
            log.error("no adventure.json under %s — running without an adventure", directory)
            return None
        try:
            data = json.loads(adv_path.read_text(encoding="utf-8"))
            adventure_id = str(data.get("id", "") or directory.name)
            scenes = [Scene.from_dict(s) for s in data.get("scenes", []) or []]
            npcs: list[AdventureNpc] = []
            npc_path = directory / "npcs.json"
            if npc_path.is_file():
                npc_data = json.loads(npc_path.read_text(encoding="utf-8"))
                npcs = [AdventureNpc.from_dict(n) for n in npc_data.get("npcs", []) or []]
            return cls(
                id=adventure_id,
                title=str(data.get("title", "") or ""),
                start_scene=str(data.get("start_scene", "") or (scenes[0].id if scenes else "")),
                summary_de=str(data.get("summary_de", "") or ""),
                scenes=scenes,
                npcs=npcs,
                start_time_de=str(data.get("start_time_de", "") or ""),
                deadlines=_parse_mappings(data.get("deadlines"), "deadline", adventure_id),
                clocks=_parse_mappings(data.get("clocks"), "clock", adventure_id),
                briefing_de=str(data.get("briefing_de", "") or ""),
                mission=data.get("mission") if isinstance(data.get("mission"), dict) else None,
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

    def npc_names(self) -> set[str]:
        """Every *named* NPC this campaign authored — the statblocks plus every scene's
        ``npcs_here``, lowercased, minus every statblock flagged ``generic``.

        Used to scope the consistency guard's presence check (ADR 045 + D107): only a named
        campaign NPC can be "absent". Without it an incidental figure the DM invented once and
        the NPC-memory extractor then registered would violate in every other scene.

        Generic mook statblocks are excluded from *both* sources for the mirror-image reason: a
        role name doubles as an anonymous extra the DM may use anywhere („Der Schläger brüllt"),
        but ADR 045 only lets such a mention pass after an indefinite article („ein Schläger
        ruft"). Registering the mook on scene entry would otherwise make its name permanently
        „absent" in every later scene — one wasted regeneration per hit, mid-session."""
        generic = {name for name, npc in self._npcs.items() if npc.generic}
        names = set(self._npcs) - generic
        for scene in self._scenes.values():
            names.update(n for n in (m.strip().lower() for m in scene.npcs_here)
                         if n and n not in generic)
        return names

    def npc(self, name: str) -> AdventureNpc | None:
        """Statblock lookup by name, case-insensitive; underscores tolerated (Discord args can't
        carry spaces, so ``!npc add Raguel_der_Rote`` must match 'Raguel der Rote')."""
        key = (name or "").strip().lower()
        return self._npcs.get(key) or self._npcs.get(key.replace("_", " "))

    # -- prompt block (stages 1+2) ----------------------------------------------------------

    def _npc_lines_de(self, scene: Scene, dead: Collection[str]) -> list[str]:
        """The present NPCs (B2). Each statblock already carries a role and roleplaying notes and
        nothing in the repo read them — so on 2026-08-22 the model re-invented Kaad every turn and
        borrowed the only characterisation it had, the scene's guidance. Rendered as
        ``- Name — Rolle. Spielweise: …``; a name with no statblock keeps its bare line, and a
        scene whose NPCs are *all* unknown stays on the compact one-liner (nothing to add — don't
        grow the prompt)."""
        names = [f"{n} (tot)" if n.strip().lower() in dead else n for n in scene.npcs_here]
        blocks = [self.npc(n) for n in scene.npcs_here]
        if not any(b is not None and (b.role_de or b.roleplaying_de) for b in blocks):
            return ["Anwesende NSCs: " + ", ".join(names)]
        lines = [NPC_HEADER_DE]
        for name, block in zip(names, blocks):
            line = f"- {name}"
            if block is not None and block.role_de:
                line += f" — {block.role_de}."
            if block is not None and block.roleplaying_de:
                line += f" Spielweise: {block.roleplaying_de}"
            lines.append(line)
        return lines

    def adventure_block_de(
        self, scene_id: str,
        *, resolved_ids: Collection[str] = (), dead_npcs: Collection[str] = (),
        include_guidance: bool = False,
    ) -> str:
        """The German prompt block: the always-on summary (stage 1) + the current scene card
        (stage 2). An unknown/empty ``scene_id`` degrades to the summary alone.

        Stateful (ADR 043): ``resolved_ids`` (this scene's flags from ``WorldState.scene_flags``)
        move a resolved Gelegenheit to „Bereits geschehen" and a revealed Geheimnis to „Bekannt",
        and hide gated exits until unlocked; ``dead_npcs`` (lowercase-joined by name) render as
        ``(tot)``. Plain collections, not WorldState — keeps ``rag/`` decoupled from ``memory/``.
        Element ids render inline (``- [opp-1] …``) so the model can cite them in ``<<ERLEDIGT>>``.

        ``include_guidance`` is the D107 switch (A5/B6): the scene's standing GM guidance used to
        sit in *every* turn's prompt, and the starting scene's "keep the deadline in view" came
        back in eight of ten answers. It is off by default and the caller owns the cadence —
        occasionally, or when a scene has stalled. When on, it is labelled as a one-off impulse
        instead of a standing order."""
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
            if scene.description_de:
                # B5: unlabelled, the card read as finished prose and was recited word for word.
                lines.append(MATERIAL_HINT_DE)
                lines.append(scene.description_de)
            if scene.npcs_here:
                lines.extend(self._npc_lines_de(scene, dead))
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
            if include_guidance and scene.guidance_de:
                lines.append(GUIDANCE_PREFIX_DE + scene.guidance_de)
            # Which exits are open, and how one is written down, are both owned elsewhere:
            # ``rules.scene_flow`` decides (same gate as the mover), ``llm.scene_router`` renders
            # (ADR 057 #6 — "schrein" alone gave the model nothing to map "zum Hafen" onto).
            # Both imports are local because ``scene_flow`` imports :class:`Scene` from this
            # module; at module level that edge would be an import cycle.
            from ..llm.scene_router import exit_label
            from ..rules.scene_flow import reachable_exits
            exits = reachable_exits(scene, resolved)
            if exits:
                labelled = []
                for t in exits:
                    target = self.get_scene(t)
                    labelled.append(exit_label(t, target.title_de if target is not None else ""))
                lines.append("Mögliche nächste Orte: " + ", ".join(labelled))
        return "\n".join(line for line in lines if line is not None).strip()
