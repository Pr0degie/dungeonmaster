"""German renderings of the world state — the prompt block and the Discord panels.

Moved out of :mod:`dmbot.memory.state` (no behaviour change); ``state`` re-exports every name
here, so existing importers keep working (ADR 034). Pure functions over the records; nothing in
this module writes state (golden rule #3).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from .gametime import (
    day_phase_de,
    deadline_line_de,
    remaining_de,
    render_time_de,
    render_time_phase_de,
)
from .records import Clock, Combatant, Fact, Quest

if TYPE_CHECKING:
    from .state import WorldState


def _combatant_line_de(c: Combatant) -> str:
    """'Seskin 8/11 (verwundet)' / 'Mortn 0/9 (kampfunfähig)' — compact per-combatant status."""
    tags: list[str] = []
    if c.wounds <= 0:
        pass  # the downed condition already conveys it; avoid "(0/9, kampfunfähig)" noise
    elif c.wounds < c.max_wounds:
        tags.append("verwundet")
    tags.extend(c.conditions)
    if not c.is_npc and c.fate_total is not None:
        tags.append(f"Schicksal {c.fate_available}/{c.fate_total}")
    if c.warp_charge or c.sustained_powers:
        warp = f"Warp {c.warp_charge}"
        if c.sustained_powers:
            warp += f", hält: {', '.join(c.sustained_powers)}"
        tags.append(warp)
    suffix = f" ({', '.join(tags)})" if tags else ""
    head = f"{c.name} {c.wounds}/{c.max_wounds}"
    if c.is_npc and c.attitude:
        head = f"{c.name} [{c.attitude}] {c.wounds}/{c.max_wounds}"
    return head + suffix


def _agenda_line_de(n: Combatant) -> str:
    """'Vex → will die Ware außer Reichweite schaffen (zuletzt: …)' — one compact line per
    agenda NPC (ADR 049) for the world-state block."""
    line = f"{n.name} → {n.goal}"
    if n.agenda_log:
        line += f" (zuletzt: {n.agenda_log[-1].text})"
    return line


def mission_line_de(quest: Quest) -> str:
    """'Auftrag: Das Ossarium zurückholen — ein handtellergroßer Schrein (von Kaad)' — the
    mission on its own prompt line (ADR 058 #3), so "was ist eigentlich unsere Mission?" has a
    concrete answer instead of a tautology."""
    line = f"Auftrag: {quest.title}"
    if quest.detail:
        line += f" — {quest.detail}"
    if quest.given_by:
        line += f" (von {quest.given_by})"
    if quest.status != "open":
        line += f" [{quest.status}]"
    return line


def fact_line_de(fact: Fact) -> str:
    """'Zollvollmacht → Seskin (von Seneschall Kaad, Tag 1, 21:10)' — one handed-over item or
    standing promise, with recipient, source and the in-game time it happened (ADR 058)."""
    line = f"{fact.text} → {fact.holder}"
    marks = []
    if fact.source:
        marks.append(f"von {fact.source}")
    if fact.at_minutes is not None:
        marks.append(render_time_de(fact.at_minutes))
    if marks:
        line += f" ({', '.join(marks)})"
    return line


def clock_segments(clock: Clock) -> str:
    """'◉◉◉○○○' — the filled/empty segment string for panel + command replies (ADR 047)."""
    return "◉" * min(clock.filled, clock.size) + "○" * max(0, clock.size - clock.filled)


def clock_line_de(clock: Clock) -> str:
    """'[arbites] Arbites-Ermittlung 3/6' (+ ' — VOLL') — the compact prompt rendering: the id in
    brackets so the model can cite it in ``<<UHR id>>``, exactly like scene-element ids (ADR 043)."""
    line = f"[{clock.id}] {clock.name} {clock.filled}/{clock.size}"
    return f"{line} — VOLL" if clock.full else line


def clock_full_note_de(clock: Clock) -> str:
    """The one-shot ``[Regie]`` directive queued when a clock fills (ADR 047). The clock name is
    wrapped in „…“ — ``discard_gm_notes(containing='„<name>“')`` relies on exactly this framing
    to retract the note when ``!uhr zurück`` undoes an accidental fill."""
    return (
        f"Die Uhr „{clock.name}“ ist voll — die angekündigte Konsequenz tritt JETZT ein. "
        "Erzähle sie in deinem nächsten Beitrag als Ereignis in der Szene."
    )


def clocks_panel_de(clocks: list[Clock]) -> str:
    """The Discord clock panel body (ADR 047): one line per clock, filled/empty segments.
    Visible-to-all first cut — ``visible`` is deliberately ignored here (ADR 047 #4)."""
    lines = ["⏱ **Uhren**"]
    for c in clocks:
        head = "⌛" if c.full else "⏱"
        line = f"{head} {clock_segments(c)} **{c.name}** (`{c.id}`) {c.filled}/{c.size}"
        if c.full:
            line += " — **VOLL**"
        lines.append(line)
    return "\n".join(lines)


def pressure_panel_de(state: WorldState, *, clocks: bool = True) -> str:
    """The combined pressure-panel body (ADR 048 #11): current time + day phase on top, then
    open deadlines, then the clocks — one edit-in-place panel instead of a second one. The
    caller shows it whenever clocks OR deadlines exist. ``clocks=False`` (``DM_CLOCKS=0``)
    leaves the clocks out; time and deadlines stay."""
    lines = [f"🕐 **{render_time_de(state.time_minutes)}** ({day_phase_de(state.time_minutes)})"]
    for dl in state.deadlines:
        line = f"⏳ **{dl.label}** (`{dl.id}`) — {remaining_de(dl.due_minutes, state.time_minutes)}"
        lines.append(line)
    if clocks and state.clocks:
        lines.append(clocks_panel_de(state.clocks))
    return "\n".join(lines)


def world_state_summary_de(
    state: WorldState, *, present: "Collection[str] | None" = None, clocks: bool = True
) -> str:
    """A compact, *structured* German block for the prompt (docs/conventions.md: 'state as structured data,
    don't boil it into prose'). Only non-empty sections appear. Empty state → ''.

    ``present`` (D107) are the names the current scene card lists as here — everything else
    registered is rendered under its own "not here" heading instead. Scene NPCs are registered on
    entry, so an unscoped "NSCs in der Szene" line would tell the model that the seneschal from
    scene one is standing in scene four (ADR 057). ``None`` keeps the unscoped rendering.

    ``clocks=False`` (``DM_CLOCKS=0``) leaves the clock line out; the clocks stay in the state."""
    lines: list[str] = []
    if state.location:
        lines.append(f"Ort: {state.location}")
    # Time renders from the counter (ADR 048) — always present, phase included so the DM can
    # play it (nachts ist der Wirt nicht da). The legacy time_ingame string is display-only.
    lines.append(f"Zeit: {render_time_phase_de(state.time_minutes)}")
    if state.deadlines:
        lines.append("Fristen: " + "; ".join(
            deadline_line_de(dl.id, dl.label, dl.due_minutes, state.time_minutes)
            for dl in state.deadlines
        ))
    if state.characters:
        lines.append("Gruppe: " + "; ".join(_combatant_line_de(c) for c in state.characters))
    # The gear each player character carries (sheet inventory + equipment + weapons, then advanced
    # by code) — without it the DM cannot answer "Was habe ich dabei?" from the sheet.
    carried = [c for c in state.characters if c.inventory]
    if carried:
        lines.append(
            "Ausrüstung (tragen die Spielfiguren bei sich — Fragen danach beantwortest du hieraus): "
            + "; ".join(f"{c.name}: {', '.join(c.inventory)}" for c in carried)
        )
    living_npcs = [n for n in state.npcs if n.wounds > 0]
    here, elsewhere = living_npcs, []
    if present is not None:
        keys = {str(n).strip().lower() for n in present}
        here = [n for n in living_npcs if n.name.strip().lower() in keys]
        elsewhere = [n for n in living_npcs if n.name.strip().lower() not in keys]
    if here:
        lines.append("NSCs in der Szene: " + "; ".join(_combatant_line_de(n) for n in here))
    if elsewhere:
        lines.append(
            "NSCs anderswo (NICHT anwesend — sie sprechen und handeln in dieser Szene nicht): "
            + "; ".join(n.name for n in elsewhere)
        )
    # Agenda NPCs (ADR 049): one compact line each, so offscreen movement is felt even when the
    # NPC is elsewhere — the DM surfaces it as rumours and traces, never as hard facts.
    agenda_npcs = [n for n in living_npcs if n.goal]
    if agenda_npcs:
        lines.append(
            "Agenden (diese NSCs handeln offscreen weiter — deute ihre Bewegungen über "
            "Gerüchte und Spuren an, wenn sie nicht anwesend sind): "
            + "; ".join(_agenda_line_de(n) for n in agenda_npcs)
        )
    # The mission first (ADR 058 #3) — it is the campaign's spine, not one job among many.
    mission = state.mission()
    if mission is not None:
        lines.append(mission_line_de(mission))
    open_quests = [q.title for q in state.quests if q.status == "open" and not q.is_mission]
    if open_quests:
        lines.append("Offene Aufträge: " + "; ".join(open_quests))
    # Handed-over items and standing promises (ADR 058): prompt-resident, so a warrant given in
    # turn 7 cannot be refused again in turn 16 without contradicting the model's own context.
    items = state.open_facts("item")
    if items:
        lines.append(
            "Übergeben (liegt vor — nimm es nicht zurück und lass es dir nicht neu geben): "
            + "; ".join(fact_line_de(f) for f in items)
        )
    promises = state.open_facts("promise")
    if promises:
        lines.append("Zusagen (gelten weiterhin): "
                     + "; ".join(fact_line_de(f) for f in promises))
    if clocks and state.clocks:  # ADR 047 — visible-to-all first cut: every clock rides in the prompt
        lines.append("Uhren (Druck/Fortschritt): " + "; ".join(clock_line_de(c) for c in state.clocks))
    if not lines:
        return ""
    return "## Weltzustand (harte Fakten — verlass dich darauf, erfinde keine abweichenden Werte)\n" + "\n".join(lines)
