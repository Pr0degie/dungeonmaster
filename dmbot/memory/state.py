"""World state — the 'hard facts' half of memory (architecture §7, golden rule #3).

Per-channel mutable game state in ``data/sessions/<channel_id>/state.json``: the party's current
wounds / conditions / inventory, the NPCs in play, open quests, the mission and the narrated
commitments that became hard facts (ADR 058 — a handed-over item, a standing promise), location,
in-game time, and the stored session recap. Advanced **deterministically by code** (e.g. HP after damage) — never
written from LLM free text. The one narrative field is ``recap``, produced by the wrap-up
summariser (LLM) but *stored* by code (memory split, golden rule #3).

Design (ADR 015 — "split"): the player **sheets** (characteristics, skills, ``max_wounds``,
aliases) stay in the read-only ``characters.json`` — the source transferred once from the sheets
(ADR 004). This ``state.json`` is the code-owned **mutable layer**, seeded once from that sheet on
the first join. Code only ever writes ``state.json``, so the sheet stays pristine and a session
resets by deleting ``state.json``.

Pure data + pure functions, unit-tested without Discord or the LLM. Combat *math* lives in
:mod:`dmbot.rules.engine`; this module only applies the resulting number and persists it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .gametime import (
    DAY_MINUTES,
    DEFAULT_START_MINUTES,
    parse_duration_de,
    render_time_de,
)

# The records WorldState is made of, moved to records (ADR 034) — re-exported so
# ``from dmbot.memory.state import Combatant`` keeps working.
from .records import (  # noqa: F401
    AGENDA_LOG_CAP,
    ATTITUDE_SCALE,
    CLOCK_SIZES,
    DOWNED_CONDITION,
    FACT_CAP,
    FACT_KINDS,
    FACT_STATUSES,
    FACT_TEXT_MAX,
    GROUP_HOLDER,
    NPC_MEMORY_CAP,
    AgendaStep,
    Clock,
    Combatant,
    Deadline,
    Fact,
    NpcMemory,
    Quest,
    _validated_fact_text,
    slugify_clock_id,
    step_attitude,
)

# German renderings of the world state, moved to state_text (ADR 034) — re-exported so
# ``from dmbot.memory.state import world_state_summary_de`` keeps working.
from .state_text import (  # noqa: F401
    _agenda_line_de,
    _combatant_line_de,
    clock_full_note_de,
    clock_line_de,
    clock_segments,
    clocks_panel_de,
    fact_line_de,
    mission_line_de,
    pressure_panel_de,
    world_state_summary_de,
)

if TYPE_CHECKING:
    from ..rules.characters import CharacterStore

log = logging.getLogger(__name__)

# -- in-game time that runs without the model (ADR 059) --------------------------------------
# Each narrated turn costs this much fictional time, each scene change the larger amount. Small
# on purpose: the clock must not overtake the narration, only stop standing still (ADR 059 #2).
# The <<ZEIT>> marker stays the accelerator on top of these (ADR 048 #4).
TURN_ADVANCE_MINUTES = 2
SCENE_CHANGE_ADVANCE_MINUTES = 15

_TIME_OF_DAY_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
# The exact form :func:`gametime.render_time_de` produces — adventure files state their start
# time the way the bot displays it, so author and log read the same string.
_CAMPAIGN_TIME_RE = re.compile(r"^Tag\s+(\d+)\s*,\s*([01]?\d|2[0-3]):([0-5]\d)$", re.IGNORECASE)


def parse_time_of_day(text: str) -> int | None:
    """``'21:00'`` → 1260 — minutes *within* a day. ``None`` for anything that is not HH:MM.

    The adventure files state their start time and deadlines the way a human writes them
    (ADR 059 #1); the accepted textual forms are closed, so a typo fails loudly instead of
    seeding a plausible wrong hour."""
    m = _TIME_OF_DAY_RE.match(str(text or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def parse_campaign_time_de(text: str) -> int | None:
    """``'Tag 1, 21:00'`` → 1260 — the read-back of :func:`gametime.render_time_de`, so an
    adventure can state its start time in the same form the bot prints. ``None`` otherwise."""
    m = _CAMPAIGN_TIME_RE.match(str(text or "").strip())
    if m is None:
        return None
    day = max(1, int(m.group(1)))
    return (day - 1) * DAY_MINUTES + int(m.group(2)) * 60 + int(m.group(3))


def absolute_minutes(value: object, *, day: int = 1) -> int | None:
    """Coerce one adventure-file time value to the counter's model (minutes since day 1, 00:00).

    Accepts an int/float (already counter minutes), a digit string, ``'Tag 1, 21:00'`` (the
    rendered form, which carries its own day) or a bare ``'HH:MM'`` — the latter offset by
    ``day`` (1 = the first day, so ``'00:00'`` on day 2 is the midnight *after* the evening the
    campaign starts on). ``None`` for anything else, including negatives: the loader then skips
    that entry rather than guessing."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    dated = parse_campaign_time_de(text)
    if dated is not None:
        return dated
    within = parse_time_of_day(text)
    if within is None:
        return None
    return max(0, int(day) - 1) * DAY_MINUTES + within


@dataclass
class WorldState:
    """The mutable world state for one session (one voice channel). Serialises to ``state.json``."""

    system: str = ""
    session_id: str = ""
    characters: list[Combatant] = field(default_factory=list)
    npcs: list[Combatant] = field(default_factory=list)
    quests: list[Quest] = field(default_factory=list)
    location: str = ""
    # In-game time (ADR 048): the minutes counter since day 1, 00:00 is the model; the string
    # is the code-rendered human-readable mirror ("Tag 2, 14:30") — never parsed back, never
    # written by the LLM. Fresh campaigns start day 1, 08:00.
    time_ingame: str = ""
    time_minutes: int = DEFAULT_START_MINUTES
    recap: str = ""
    # Scene pointer into the loaded adventure compendium (Phase 10a, ADR 019) — the code-owned
    # "where are we in the plot" the prompt's scene card is selected by. Empty = no adventure.
    scene_id: str = ""
    # Scene-element flags (ADR 043): scene_id → element ids resolved there (used Gelegenheiten,
    # revealed Geheimnisse). Code-owned like scene_id (golden rule #3) — the LLM only *requests*
    # a flag via <<ERLEDIGT>>; validation lives in session/scenes.py, this is dumb storage.
    scene_flags: dict[str, list[str]] = field(default_factory=dict)
    # Consequence clocks (ADR 047): code-owned pressure meters. The LLM only *requests* a tick
    # via <<UHR id>>; validation + the per-turn clamp live in the delivery pipeline.
    clocks: list[Clock] = field(default_factory=list)
    # Deadlines (ADR 048): human-created or seeded from the adventure (ADR 059 #1); they expire
    # against the code-owned time counter.
    deadlines: list[Deadline] = field(default_factory=list)
    # Hard facts from narrated commitments (ADR 058): handed-over items and standing promises.
    # Written only through the validating writers below — never parsed out of LLM free text.
    facts: list[Fact] = field(default_factory=list)
    # Latches once the adventure's start time / deadlines / clocks were seeded (ADR 059 #1), so
    # a re-join or a restart mid-session doesn't reset the clock or duplicate the deadlines.
    time_seeded: bool = False

    # -- (de)serialisation ----------------------------------------------------------------

    def to_dict(self) -> dict:
        d = {
            "session_id": self.session_id,
            "system": self.system,
            "characters": [c.to_dict() for c in self.characters],
            "npcs": [n.to_dict() for n in self.npcs],
            "quests": [q.to_dict() for q in self.quests],
            "location": self.location,
            "time_ingame": self.time_ingame,
            "time_minutes": self.time_minutes,
            "recap": self.recap,
            "scene_id": self.scene_id,
        }
        if self.scene_flags:  # omit-when-empty, like the Combatant extras
            d["scene_flags"] = {k: list(v) for k, v in self.scene_flags.items() if v}
        if self.clocks:  # omit-when-empty (ADR 047) — an old state.json shape stays untouched
            d["clocks"] = [c.to_dict() for c in self.clocks]
        if self.deadlines:  # omit-when-empty (ADR 048)
            d["deadlines"] = [dl.to_dict() for dl in self.deadlines]
        if self.facts:  # omit-when-empty (ADR 058)
            d["facts"] = [f.to_dict() for f in self.facts]
        if self.time_seeded:  # omit-when-empty (ADR 059)
            d["time_seeded"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WorldState":
        # Time migration (ADR 048 #2): a pre-048 state.json has no counter — start it at the
        # default (day 1, 08:00) and say so. A legacy free-text time_ingame is NOT parsed
        # (prose); it stays visible until the first advance re-renders it from the counter.
        raw_minutes = d.get("time_minutes")
        if raw_minutes is None:
            time_minutes = DEFAULT_START_MINUTES
            legacy = str(d.get("time_ingame", "") or "")
            if d:  # only a real loaded state is a migration; the {}-default path stays quiet
                log.info(
                    "state migration (ADR 048): no time_minutes — starting the clock at %s%s",
                    render_time_de(time_minutes),
                    f" (legacy time_ingame {legacy!r} left as display until the first advance)"
                    if legacy else "",
                )
        else:
            time_minutes = max(0, int(raw_minutes or 0))
        return cls(
            system=str(d.get("system", "") or ""),
            session_id=str(d.get("session_id", "") or ""),
            characters=[Combatant.from_dict(c) for c in d.get("characters", []) or []],
            npcs=[Combatant.from_dict(n, is_npc=True) for n in d.get("npcs", []) or []],
            quests=[Quest.from_dict(q) for q in d.get("quests", []) or []],
            location=str(d.get("location", "") or ""),
            time_ingame=str(d.get("time_ingame", "") or ""),
            time_minutes=time_minutes,
            recap=str(d.get("recap", "") or ""),
            scene_id=str(d.get("scene_id", "") or ""),
            scene_flags={
                str(k): [str(x) for x in (v or [])]
                for k, v in (d.get("scene_flags") or {}).items()
            },
            clocks=[Clock.from_dict(c) for c in d.get("clocks", []) or []],
            deadlines=[Deadline.from_dict(dl) for dl in d.get("deadlines", []) or []],
            # Fact/seed migration (ADR 058/059), the shape ADR 048's clock migration set: a
            # pre-058 file simply has neither key, so both default and nothing else changes.
            # Unknown fact kinds are dropped here, not stored — the enumeration is closed.
            facts=[
                f for f in (Fact.from_dict(x) for x in d.get("facts", []) or [])
                if f.kind in FACT_KINDS and f.text
            ],
            time_seeded=bool(d.get("time_seeded", False)),
        )

    @classmethod
    def load(cls, path: Path) -> "WorldState | None":
        """Load state from ``path``; ``None`` if it doesn't exist yet (the caller then seeds it)."""
        if not path.is_file():
            return None
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        """Write atomically (temp + ``os.replace``) so a crash mid-write can't corrupt the file —
        the gate is 'an HP change survives a restart', so this file must always be readable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)  # atomic on Windows + POSIX
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    @classmethod
    def seed_from_store(
        cls, store: "CharacterStore", *, system: str = "", session_id: str = ""
    ) -> "WorldState":
        """Build a fresh state from the read-only sheet (the once-only transfer, ADR 004): copy each
        character's current/max wounds, conditions and inventory into the mutable layer."""
        chars = [
            Combatant(
                name=c.name,
                wounds=c.wounds if c.wounds is not None else (c.max_wounds or 0),
                max_wounds=c.max_wounds if c.max_wounds is not None else (c.wounds or 0),
                conditions=list(c.conditions),
                inventory=list(c.inventory),
                fate_total=c.fate_total,
            )
            for c in store.characters()
        ]
        return cls(system=system, session_id=session_id, characters=chars)

    # -- lookup ---------------------------------------------------------------------------

    def find(self, name: str | None) -> Combatant | None:
        """Find a combatant (character first, then NPC) by name, case-insensitively."""
        if not name:
            return None
        key = name.strip().lower()
        for c in self.characters:
            if c.name.lower() == key:
                return c
        for n in self.npcs:
            if n.name.lower() == key:
                return n
        return None

    # -- scene-element flags (ADR 043) ------------------------------------------------------

    def resolved_ids(self, scene_id: str) -> list[str]:
        """The element ids flagged resolved for ``scene_id`` (order of resolution)."""
        return list(self.scene_flags.get(scene_id, []))

    def mark_resolved(self, scene_id: str, element_id: str) -> bool:
        """Flag ``element_id`` resolved for ``scene_id``; False if it already was (idempotent)."""
        flags = self.scene_flags.setdefault(scene_id, [])
        if element_id in flags:
            return False
        flags.append(element_id)
        return True

    def mark_open(self, scene_id: str, element_id: str) -> bool:
        """Un-flag ``element_id`` for ``scene_id``; False if it wasn't set. Drops an emptied
        scene key so ``to_dict``'s omit-when-empty stays clean."""
        flags = self.scene_flags.get(scene_id, [])
        if element_id not in flags:
            return False
        flags.remove(element_id)
        if not flags:
            self.scene_flags.pop(scene_id, None)
        return True

    # -- consequence clocks (ADR 047) --------------------------------------------------------

    def find_clock(self, clock_id: str | None) -> Clock | None:
        """Find a clock by id, case-insensitively (ids are lowercase slugs; a hand-edited
        state.json may differ in case — tolerate it like ``find`` does for names)."""
        if not clock_id:
            return None
        key = clock_id.strip().lower()
        return next((c for c in self.clocks if c.id.lower() == key), None)

    def add_clock(self, name: str, size: int, *, clock_id: str = "") -> Clock:
        """Create a clock with a slug id derived from ``name`` (deduped with a numeric suffix).
        ``size`` is the caller's job to validate against :data:`CLOCK_SIZES` (the command does).
        ``clock_id`` overrides the derived slug — the adventure file ships its own ids so its
        guidance text can cite them (ADR 059 #1); it is slugified and deduped just the same."""
        base = slugify_clock_id(clock_id or name)
        cid, n = base, 1
        while self.find_clock(cid) is not None:
            n += 1
            cid = f"{base}-{n}"
        clock = Clock(id=cid, name=name.strip(), size=size)
        self.clocks.append(clock)
        return clock

    def remove_clock(self, clock_id: str) -> Clock | None:
        """Remove a clock by id; returns it, or ``None`` if unknown."""
        clock = self.find_clock(clock_id)
        if clock is not None:
            self.clocks.remove(clock)
        return clock

    def tick_clock(self, clock_id: str) -> Clock | None:
        """Advance a clock one segment (never past ``size``). Returns the clock, or ``None``
        for an unknown id **or an already-full clock** — a full clock's consequence is due,
        not tickable. The caller decides what a fresh fill triggers (the GM-note injection)."""
        clock = self.find_clock(clock_id)
        if clock is None or clock.full:
            return None
        clock.filled += 1
        return clock

    def untick_clock(self, clock_id: str) -> Clock | None:
        """Take one segment back (never below 0). Returns the clock, or ``None`` if unknown."""
        clock = self.find_clock(clock_id)
        if clock is None:
            return None
        clock.filled = max(0, clock.filled - 1)
        return clock

    # -- in-game time + deadlines (ADR 048) --------------------------------------------------

    def advance_time(self, minutes: int) -> list[Deadline]:
        """Advance the code-owned clock by ``minutes`` (≤0 is a no-op) and re-render the
        human-readable mirror. Returns the deadlines that *newly* expired on this advance
        (crossed ``due_minutes`` and were not yet notified) — each is latched ``notified``
        here, so the expiry note fires exactly once (ADR 048 #8). The caller (runtime)
        queues the [Regie] notes and persists."""
        if minutes <= 0:
            return []
        self.time_minutes += minutes
        self.time_ingame = render_time_de(self.time_minutes)
        expired: list[Deadline] = []
        for dl in self.deadlines:
            if not dl.notified and dl.due_minutes <= self.time_minutes:
                dl.notified = True
                expired.append(dl)
        return expired

    def advance_turn(self, *, minutes: int = TURN_ADVANCE_MINUTES) -> list[Deadline]:
        """The clock's heartbeat (ADR 059 #2): one narrated turn costs a small fixed amount of
        in-game time, whether or not the model emits a ``<<ZEIT>>`` marker. Returns the newly expired
        deadlines, exactly like :meth:`advance_time`. ``minutes=0`` switches it off."""
        return self.advance_time(minutes)

    def advance_scene_change(
        self, *, minutes: int = SCENE_CHANGE_ADVANCE_MINUTES
    ) -> list[Deadline]:
        """The larger increment: getting somewhere else costs more than talking in one room
        (ADR 059 #2). Called by the scene-advancement path (ADR 057) on a confirmed move."""
        return self.advance_time(minutes)

    def seed_time_from_adventure(
        self,
        *,
        start_time: object = None,
        start_day: int = 1,
        deadlines: "Iterable[Mapping[str, object]]" = (),
        clocks: "Iterable[Mapping[str, object]]" = (),
        force: bool = False,
    ) -> bool:
        """Seed the campaign's own clock from the adventure file (ADR 059 #1) — start time,
        deadlines and consequence clocks, so a campaign built on a midnight siren can *state*
        that deadline instead of relying on the operator typing it at the table.

        Values are the simple ones a loader reads straight out of JSON. ``start_time`` is an int
        (counter minutes), ``'Tag 1, 21:00'`` or ``'HH:MM'`` with ``start_day``. Each deadline
        mapping needs a ``label`` plus one of ``due_in`` (a German duration, ``'+3h'``), ``at``
        (+ optional ``day``), ``due_minutes`` (absolute) or ``in_minutes``; each clock mapping a
        ``name`` plus optional ``size`` (one of :data:`CLOCK_SIZES`, default 6) and ``filled``.
        Both may carry their own ``id``, which the adventure's guidance text can then cite.

        Malformed entries are skipped and logged; the rest still seed. Latches
        :attr:`time_seeded`, so calling it again on a resumed session is a no-op returning
        ``False`` — ``force=True`` re-seeds (the operator's reset)."""
        if self.time_seeded and not force:
            log.debug("state: adventure time already seeded — skipping")
            return False
        self.time_seeded = True

        start = absolute_minutes(start_time, day=start_day) if start_time is not None else None
        if start is not None:
            self.time_minutes = start
            self.time_ingame = render_time_de(self.time_minutes)
        elif start_time is not None:
            log.warning("state: adventure start time %r is not HH:MM or minutes — keeping %s",
                        start_time, render_time_de(self.time_minutes))

        for entry in deadlines or ():
            label = str(entry.get("label", "") or "").strip()
            if not label:
                log.warning("state: adventure deadline without a label — skipped: %r", entry)
                continue
            if entry.get("due_in") is not None:  # "+3h" — the form the adventure file ships
                offset = parse_duration_de(str(entry.get("due_in") or ""))
                due = None if offset is None else self.time_minutes + offset
            elif entry.get("in_minutes") is not None:
                offset = absolute_minutes(entry.get("in_minutes"))
                due = None if offset is None else self.time_minutes + offset
            else:
                raw = entry.get("at", entry.get("due_minutes"))
                due = absolute_minutes(raw, day=int(entry.get("day", 1) or 1))
            if due is None:
                log.warning("state: adventure deadline %r has no usable time — skipped", label)
                continue
            self.add_deadline(label, due - self.time_minutes,
                              deadline_id=str(entry.get("id", "") or ""))

        for entry in clocks or ():
            name = str(entry.get("name", "") or "").strip()
            if not name:
                log.warning("state: adventure clock without a name — skipped: %r", entry)
                continue
            size = int(entry.get("size", 6) or 6)
            if size not in CLOCK_SIZES:
                log.warning("state: adventure clock %r has size %s (allowed: %s) — skipped",
                            name, size, CLOCK_SIZES)
                continue
            clock = self.add_clock(name, size, clock_id=str(entry.get("id", "") or ""))
            clock.filled = max(0, min(size, int(entry.get("filled", 0) or 0)))

        log.info("state: seeded adventure time — %s, %d Frist(en), %d Uhr(en)",
                 render_time_de(self.time_minutes), len(self.deadlines), len(self.clocks))
        return True

    def find_deadline(self, deadline_id: str | None) -> Deadline | None:
        """Find a deadline by id, case-insensitively (like :meth:`find_clock`)."""
        if not deadline_id:
            return None
        key = deadline_id.strip().lower()
        return next((dl for dl in self.deadlines if dl.id.lower() == key), None)

    def add_deadline(self, label: str, in_minutes: int, *, deadline_id: str = "") -> Deadline:
        """Create a deadline ``in_minutes`` from now, with a slug id derived from the label
        (deduped with a numeric suffix, the clock-id scheme). Human-created (ADR 048 #7) or
        seeded from the adventure (ADR 059 #1) — the latter passes its own ``deadline_id``."""
        base = slugify_clock_id(deadline_id or label, fallback="frist")
        did, n = base, 1
        while self.find_deadline(did) is not None:
            n += 1
            did = f"{base}-{n}"
        deadline = Deadline(id=did, label=label.strip(),
                            due_minutes=self.time_minutes + max(0, in_minutes))
        self.deadlines.append(deadline)
        return deadline

    def remove_deadline(self, deadline_id: str) -> Deadline | None:
        """Remove a deadline by id; returns it, or ``None`` if unknown."""
        deadline = self.find_deadline(deadline_id)
        if deadline is not None:
            self.deadlines.remove(deadline)
        return deadline

    # -- deterministic advancement (golden rule #3) ---------------------------------------

    def apply_damage(
        self, name: str, amount: int, *, downed_condition: str = DOWNED_CONDITION
    ) -> Combatant | None:
        """Subtract ``amount`` wounds (already soaked — the engine did the math), clamped at 0. At 0
        the combatant gains the downed condition. Returns the updated combatant, or ``None`` if the
        name is unknown."""
        c = self.find(name)
        if c is None:
            return None
        c.wounds = max(0, c.wounds - max(0, amount))
        if c.wounds == 0 and downed_condition and downed_condition not in c.conditions:
            c.conditions.append(downed_condition)
        return c

    def heal(
        self, name: str, amount: int, *, downed_condition: str = DOWNED_CONDITION
    ) -> Combatant | None:
        """Restore ``amount`` wounds, clamped at ``max_wounds``. Rising above 0 clears the downed
        condition. Returns the updated combatant, or ``None`` if unknown."""
        c = self.find(name)
        if c is None:
            return None
        c.wounds = min(c.max_wounds, c.wounds + max(0, amount))
        if c.wounds > 0 and downed_condition in c.conditions:
            c.conditions.remove(downed_condition)
        return c

    def add_condition(self, name: str, condition: str) -> Combatant | None:
        c = self.find(name)
        if c is not None and condition and condition not in c.conditions:
            c.conditions.append(condition)
        return c

    def remove_condition(self, name: str, condition: str) -> Combatant | None:
        c = self.find(name)
        if c is not None and condition in c.conditions:
            c.conditions.remove(condition)
        return c

    def add_or_update_npc(
        self,
        name: str,
        *,
        wounds: int | None = None,
        max_wounds: int | None = None,
        toughness_bonus: int = 0,
        armour: int = 0,
        attitude: str = "hostile",
        faction: str = "",
        goal: str = "",
    ) -> Combatant:
        """Register an NPC (an enemy the party can damage) or update an existing one."""
        existing = next((n for n in self.npcs if n.name.lower() == name.strip().lower()), None)
        max_w = max_wounds if max_wounds is not None else (wounds if wounds is not None else 10)
        if existing is None:
            npc = Combatant(
                name=name.strip(),
                wounds=wounds if wounds is not None else max_w,
                max_wounds=max_w,
                toughness_bonus=toughness_bonus,
                armour=armour,
                is_npc=True,
                attitude=attitude,
                faction=faction,
                goal=goal,
            )
            self.npcs.append(npc)
            return npc
        if wounds is not None:
            existing.wounds = wounds
        if max_wounds is not None:
            existing.max_wounds = max_wounds
        if toughness_bonus:
            existing.toughness_bonus = toughness_bonus
        if armour:
            existing.armour = armour
        if attitude:
            existing.attitude = attitude
        if faction:
            existing.faction = faction
        if goal:
            existing.goal = goal
        return existing

    def place_npc(
        self, name: str, scene_id: str, *, wounds: int, toughness_bonus: int = 0, armour: int = 0,
        faction: str = "", goal: str = "",
    ) -> tuple[Combatant, bool]:
        """Put an NPC the narration showed in person into ``scene_id`` (ADR 062): an unknown name
        is registered (neutral, the given numbers), a known one only moves. Returns ``(npc, new)``.
        Wounds of a known NPC are never touched — a sighting is not a heal."""
        known = next((n for n in self.npcs if n.name.lower() == name.strip().lower()), None)
        if known is not None:
            known.scene = scene_id
            return known, False
        npc = self.add_or_update_npc(
            name, wounds=wounds, toughness_bonus=toughness_bonus, armour=armour,
            attitude="neutral", faction=faction, goal=goal,
        )
        npc.scene = scene_id
        return npc, True

    def start_fate_session(self, *, default: int) -> None:
        """A new session (ADR 063): characters without a Fate total get the profile's ``default``,
        and every character recovers the Fate spent last session (IM p.220)."""
        for c in self.characters:
            if c.fate_total is None:
                c.fate_total = default
            c.fate_spent = 0

    def spend_fate(self, name: str) -> bool:
        """Spend one Fate of player character ``name``; False if none is left or no such PC."""
        c = next((x for x in self.characters if x.name.lower() == (name or "").strip().lower()), None)
        if c is None or c.fate_available <= 0:
            return False
        c.fate_spent += 1
        return True

    def present_npcs(self, scene_id: str, card_names: "Collection[str]" = ()) -> list[Combatant]:
        """The living NPCs present in ``scene_id`` (ADR 062): on the scene card or seen there."""
        card = {str(n).strip().lower() for n in card_names}
        return [n for n in self.npcs if n.wounds > 0
                and (n.name.strip().lower() in card or (scene_id and n.scene == scene_id))]

    # -- psyker / Warp Charge (ADR 022) ---------------------------------------------------

    def set_warp_charge(self, name: str, value: int) -> Combatant | None:
        """Set a combatant's Warp Charge to ``value`` (clamped ≥ 0). Returns the combatant or
        ``None`` if unknown. The engine computes the new total; this only stores it."""
        c = self.find(name)
        if c is not None:
            c.warp_charge = max(0, int(value))
        return c

    def reset_warp_charge(self, name: str) -> Combatant | None:
        """Reset Warp Charge to 0 and drop all Sustained powers — what Perils of the Warp does."""
        c = self.find(name)
        if c is not None:
            c.warp_charge = 0
            c.sustained_powers = []
        return c

    def sustain_power(self, name: str, power: str) -> Combatant | None:
        c = self.find(name)
        if c is not None and power and power not in c.sustained_powers:
            c.sustained_powers.append(power)
        return c

    def set_location(self, location: str) -> None:
        self.location = location.strip()

    def add_quest(
        self,
        title: str,
        *,
        status: str = "open",
        detail: str = "",
        given_by: str = "",
        at_minutes: int | None = None,
    ) -> Quest:
        """Record an accepted job. Re-adding a known title updates it in place (idempotent —
        the post-turn classifier may report the same acceptance twice) and only *fills* the
        optional provenance fields, so a later, vaguer verdict can't blank a detail."""
        existing = next((q for q in self.quests if q.title.lower() == title.strip().lower()), None)
        target = existing if existing is not None else Quest(title=title.strip())
        target.status = status
        if detail:
            target.detail = detail.strip()
        if given_by:
            target.given_by = given_by.strip()
        if at_minutes is not None:
            target.at_minutes = max(0, int(at_minutes))
        elif target.at_minutes is None:
            target.at_minutes = self.time_minutes
        if existing is None:
            self.quests.append(target)
        return target

    def set_quest_status(self, title: str, status: str) -> Quest | None:
        q = next((q for q in self.quests if q.title.lower() == title.strip().lower()), None)
        if q is not None:
            q.status = status
        return q

    # -- the mission as a hard fact (ADR 058 #3) --------------------------------------------

    def mission(self) -> Quest | None:
        """The adventure's own objective, or ``None`` before it is seeded. The player panel
        shows this as *the* goal; the prompt block names it on its own line."""
        return next((q for q in self.quests if q.is_mission), None)

    def set_mission(
        self,
        title: str,
        *,
        detail: str = "",
        given_by: str = "",
        at_minutes: int | None = None,
    ) -> Quest | None:
        """Seed the adventure's objective as a quest (ADR 058 #3) so it is state, not narration.

        There is exactly one mission per campaign: re-seeding with a different title *replaces*
        the old one rather than leaving a stale objective in the prompt. ``None`` for an
        empty/over-long title (nothing is written)."""
        clean = _validated_fact_text(title)
        if clean is None:
            log.info("state: rejected a mission — not a label: %r", title)
            return None
        previous = self.mission()
        if previous is not None and previous.title.lower() != clean.lower():
            self.quests.remove(previous)
        quest = self.add_quest(clean, detail=detail.strip(), given_by=given_by.strip(),
                               at_minutes=at_minutes)
        for q in self.quests:
            q.is_mission = q is quest
        return quest

    # -- hard facts from narrated commitments (ADR 058) -------------------------------------

    def open_facts(self, kind: str = "") -> list[Fact]:
        """The facts that still hold, optionally filtered to one ``kind``."""
        return [f for f in self.facts if f.status == "open" and (not kind or f.kind == kind)]

    def find_fact(self, text: str, *, kind: str = "", holder: str = "") -> Fact | None:
        """Find an *open* fact by its label, case-insensitively; optionally pinned to a kind
        and/or a holder. ``None`` if there is none."""
        key = str(text or "").strip().lower()
        if not key:
            return None
        hkey = holder.strip().lower()
        for f in self.open_facts(kind):
            if f.text.lower() == key and (not hkey or f.holder.lower() == hkey):
                return f
        return None

    def give_item(
        self,
        item: str,
        *,
        to: str = "",
        by: str = "",
        at_minutes: int | None = None,
    ) -> Fact | None:
        """Record that ``item`` changed hands (ADR 058). A ``to`` that names a character lands on that character's sheet
        *and* in the facts; anything else (empty, an NPC, a group phrase) is held by the party.

        Returns the fact, or ``None`` when the value isn't a label (empty, over-long, multi-line
        — i.e. the classifier returned prose): nothing is written in that case."""
        clean = _validated_fact_text(item)
        if clean is None:
            log.info("state: rejected an item fact — not a label: %r", item)
            return None
        holder = self._resolve_holder(to)
        existing = self.find_fact(clean, kind="item", holder=holder)
        if existing is not None:
            return existing
        fact = Fact(kind="item", text=clean, holder=holder, source=by.strip(),
                    at_minutes=self.time_minutes if at_minutes is None else max(0, int(at_minutes)))
        self._append_fact(fact)
        c = self.find(holder)
        if c is not None and clean not in c.inventory:
            c.inventory.append(clean)
        return fact

    def take_item(self, item: str, *, holder: str = "") -> Fact | None:
        """Take a handed-over item back: revoke the fact and drop it from the sheet again.
        ``None`` if no open item fact matches (nothing to undo)."""
        fact = self.find_fact(item, kind="item", holder=self._resolve_holder(holder) if holder else "")
        if fact is None:
            return None
        fact.status = "revoked"
        c = self.find(fact.holder)
        if c is not None and fact.text in c.inventory:
            c.inventory.remove(fact.text)
        return fact

    def record_promise(
        self,
        text: str,
        *,
        by: str = "",
        to: str = "",
        at_minutes: int | None = None,
    ) -> Fact | None:
        """Record a standing promise or condition an NPC gave (ADR 058 #1). Same label
        discipline as :meth:`give_item`; ``None`` (and no write) when it isn't one."""
        clean = _validated_fact_text(text)
        if clean is None:
            log.info("state: rejected a promise fact — not a label: %r", text)
            return None
        holder = self._resolve_holder(to)
        existing = self.find_fact(clean, kind="promise", holder=holder)
        if existing is not None:
            return existing
        fact = Fact(kind="promise", text=clean, holder=holder, source=by.strip(),
                    at_minutes=self.time_minutes if at_minutes is None else max(0, int(at_minutes)))
        self._append_fact(fact)
        return fact

    def revoke_fact(self, text: str, *, kind: str = "") -> Fact | None:
        """Mark a fact as no longer holding (a broken promise, an item confiscated). ``None``
        if no open fact matches. The operator-facing 'remove a wrong fact' path (ADR 058)."""
        fact = self.find_fact(text, kind=kind)
        if fact is None:
            return None
        if fact.kind == "item":
            return self.take_item(fact.text, holder=fact.holder)
        fact.status = "revoked"
        return fact

    def record_commitment(
        self,
        kind: str,
        *,
        text: str,
        to: str = "",
        by: str = "",
        detail: str = "",
        at_minutes: int | None = None,
    ) -> "Fact | Quest | None":
        """The single validated entry point for the post-turn fact classifier (ADR 058 #2):
        ``kind`` is a closed enumeration (``item`` / ``promise`` / ``quest``) and everything
        else is a label plus provenance. An unknown kind, an empty text or prose instead of a
        label returns ``None`` and changes nothing — the guard fails open, as optional layers
        must. The model never writes state; this is where code decides what its verdict means."""
        key = str(kind or "").strip().lower()
        if key == "item":
            return self.give_item(text, to=to, by=by, at_minutes=at_minutes)
        if key == "promise":
            return self.record_promise(text, by=by, to=to, at_minutes=at_minutes)
        if key == "quest":
            clean = _validated_fact_text(text)
            if clean is None:
                log.info("state: rejected a quest fact — not a label: %r", text)
                return None
            return self.add_quest(clean, detail=detail.strip(), given_by=by.strip(),
                                  at_minutes=at_minutes)
        log.info("state: rejected a commitment of unknown kind %r", kind)
        return None

    def _resolve_holder(self, to: str) -> str:
        """A recipient that names a known character resolves to that character's canonical
        name; everything else (empty, an NPC, 'die Gruppe') is the party."""
        c = self.find(to)
        return c.name if c is not None and not c.is_npc else GROUP_HOLDER

    def _append_fact(self, fact: Fact) -> None:
        """Append and enforce :data:`FACT_CAP` — revoked facts age out first (they no longer
        render), then the oldest open ones."""
        self.facts.append(fact)
        while len(self.facts) > FACT_CAP:
            victim = next((f for f in self.facts if f.status != "open"), self.facts[0])
            self.facts.remove(victim)

    def set_recap(self, text: str) -> None:
        self.recap = text.strip()
