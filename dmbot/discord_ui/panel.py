"""The player panel — the message the table reads while playing (D107, PRD
``docs/plans/coherent-campaign-run.md``, user stories 14-17).

The 2026-08-22 debug run failed Tobi's actual wish ("im Chat steht, was getestet werden soll")
twice over: the 🧪 overlay is refreshed only on a scene change — and no scene change ever
happened — so the table saw exactly one message that scrolled away, and what it said was
operator jargon (gate codes and command lines), not something a player can act on.

This module is the answer's pure half: **one render function, no Discord, no state, no
network, no clock of its own.** It takes the world state, the current scene and the current
scene's gate labels and returns the panel text in players' German. Posting it, editing it in
place and deciding when to refresh belongs to the runtime (see ``render_player_panel_de``'s
docstring for the call contract).

Two invariants hold the panel together:

* **Spoiler discipline.** The panel is channel-visible, so it renders only what players may
  know: the scene *title* (never its GM description or guidance), and for each unresolved
  opportunity only its *invitation* — the skill and difficulty in front of the colon, never
  the outcome behind it and never a ``secrets_de`` line. See :func:`opportunity_teaser_de`.
* **No operator jargon.** A gate label like ``"G4 Scene-Card-Gate"`` is translated into a
  sentence the table can act on, or dropped. Nothing raw is passed through, so a cheat sheet
  can never leak into the channel. See :func:`gate_hints_de`.

Deliberately *not* imported here: the sidecar loader behind those gate labels. The caller
hands over a plain list of strings, which keeps this module free of the sidecar entirely —
the LLM-invisibility invariant of ADR 052 is a structural one, and a panel renderer is the
wrong place to widen its reach.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from ..memory.gametime import remaining_de, render_time_phase_de
from ..memory.state import Quest, WorldState
from ..rag.adventure import Scene

# --- the fixed German lines (asserted verbatim by tests/test_panel.py) ------------------------

NO_SCENE_DE = "📍 **Wo ihr seid:** noch nirgends — die Sitzung hat noch keine Szene."
NO_MISSION_DE = "🎯 **Was ihr wollt:** noch unklar — fragt nach, wer euch beauftragt hat."
NO_DEADLINE_DE = "⏳ Keine laufende Frist."
ALL_DONE_DE = "✅ **Hier ist nichts mehr offen — zieht weiter.**"
OPEN_HEADER_DE = "🔎 **Hier ist noch etwas zu holen:**"
TEST_HEADER_DE = "🧪 **Testet in dieser Szene:**"
UNNAMED_OPPORTUNITY_DE = "noch etwas Unentdecktes"

# --- gate label → one sentence a player can act on -------------------------------------------

# Keyed by the gate code of `docs/live-run-script.md`. The code alone is the fallback; a few
# labels reuse a code for two different things (G8 covers both the fight and the restart), so
# the keyword table below wins when it matches.
_GATE_HINTS_DE: dict[str, str] = {
    "G1": "Fragt laut nach einer Regel — die Spielleitung darf im Regelbuch nachschlagen.",
    "G2": "Macht etwas Lautes oder Auffälliges — die Gegenseite soll darauf aufmerksam werden.",
    "G3": "Redet über die Zeit: Wie spät ist es, und wie lange bleibt euch noch?",
    "G4": "Versucht weiterzuziehen, bevor ihr hier alles gefunden habt.",
    "G5": "Erzählt jemandem hier etwas über euch — ruhig etwas, das nicht stimmt.",
    "G6": "Sprecht jemanden an, der eigentlich gar nicht mehr hier sein kann.",
    "G7": "Zieht weiter und fragt später nach, was die anderen inzwischen getrieben haben.",
    "G8": "Legt eine Pause ein; wenn die Spielleitung zurück ist, lasst euch erzählen, "
          "was bisher geschah.",
    "G9": "Merkt euch eine Kleinigkeit am Rand, ohne ihr nachzugehen — sie kommt später wieder.",
    "G10": "Fragt in einer späteren Sitzung in eigenen Worten nach etwas, das ihr heute "
           "erlebt habt.",
}

# Checked in order against the lowercased label, before the code table.
_KEYWORD_HINTS_DE: tuple[tuple[str, str], ...] = (
    ("kampf", "Sucht die Auseinandersetzung und würfelt einen Angriff — jemand soll wirklich "
              "Schaden nehmen."),
    ("wunden", "Sucht die Auseinandersetzung und würfelt einen Angriff — jemand soll wirklich "
               "Schaden nehmen."),
)

_GATE_CODE_RE = re.compile(r"^\s*(G\d{1,2})\b", re.IGNORECASE)

# The invitation of an opportunity card: "Wahrnehmung (Routine): …" / "Disziplin (Psi)
# (Herausfordernd): …". Everything behind the colon is the outcome — GM-side by definition.
_TEASER_MAX = 60


def gate_hints_de(gates: Iterable[str]) -> list[str]:
    """Translate the current scene's gate labels into sentences the table can act on.

    Operator labels ("G5 NPC-Gedächtnis (Saat: Lüge)") are never passed through: each is
    mapped to one player-language line, and an unknown label is dropped rather than shown —
    the panel is for the players, and a cheat sheet in the channel is the very failure this
    replaces. Duplicates collapse (two G3 gates in one scene are still one instruction) while
    the authored order is kept.
    """
    hints: list[str] = []
    for gate in gates:
        hint = _gate_hint_de(str(gate or ""))
        if hint and hint not in hints:
            hints.append(hint)
    return hints


def _gate_hint_de(gate: str) -> str:
    """One gate label → its player-language line, or '' when nothing sensible maps."""
    low = gate.lower()
    for keyword, hint in _KEYWORD_HINTS_DE:
        if keyword in low:
            return hint
    m = _GATE_CODE_RE.match(gate)
    if not m:
        return ""
    return _GATE_HINTS_DE.get(m.group(1).upper(), "")


def opportunity_teaser_de(text: str) -> str:
    """The channel-safe half of an opportunity card: the invitation in front of the colon.

    ``"Wahrnehmung (Routine): Vosks Gürteltasche birgt den Verladebrief — Pier Neun."`` →
    ``"Wahrnehmung (Routine)"``. What stands *behind* the colon is what a successful test
    reveals — the very thing the players are supposed to earn — so it never leaves this
    function. An opportunity written without that prefix yields ``''``; the caller then
    renders :data:`UNNAMED_OPPORTUNITY_DE` instead of guessing which half is safe.
    """
    head = (text or "").split(":", 1)[0].strip()
    if not head or head == (text or "").strip():  # no colon at all → nothing safe to show
        return ""
    if len(head) > _TEASER_MAX or "\n" in head:
        return ""
    return head


def render_player_panel_de(
    state: WorldState,
    scene: Scene | None = None,
    gates: Sequence[str] = (),
    *,
    active_player: str = "",
) -> str:
    """Render the player panel: where we are, what we want, what time it is, how long we have,
    who is up, what is still open here and what this scene is meant to exercise.

    Pure and total — every argument is optional data, no branch raises, and the same inputs
    always give the same string (the panel is edited in place, so a jitter would show as a
    flickering message).

    :param state: the session's :class:`~dmbot.memory.state.WorldState` — mission, in-game
        time, deadlines and the scene's resolved flags are read from it, nothing is written.
    :param scene: the current :class:`~dmbot.rag.adventure.Scene`, or ``None`` before a
        session has one. Only its ``title_de`` and its unresolved opportunities are rendered.
    :param gates: the current scene's gate labels, as the runtime has them (empty for a normal
        campaign); translated by :func:`gate_hints_de`. Empty → the 🧪 block disappears.
    :param active_player: whoever is up, if the turn order knows — empty omits the line.
    """
    lines: list[str] = []

    # 1. Where the group is. The scene *title* only: description and guidance are GM material.
    lines.append(NO_SCENE_DE if scene is None
                 else f"📍 **Wo ihr seid:** {scene.title_de or scene.id}")

    # 2. What the group wants — the mission as a hard fact (ADR 058 #3), not as narration.
    mission = state.mission()
    lines.append(_mission_line_de(mission) if mission else NO_MISSION_DE)

    # 3. What time it is and how much of the deadline is left (ADR 059): the pressure the run
    #    of 2026-08-22 only ever heard as an NPC's catchphrase.
    lines.append(f"🕐 **Wie spät es ist:** {render_time_phase_de(state.time_minutes)}")
    deadlines = sorted(state.deadlines, key=lambda dl: dl.due_minutes)
    if deadlines:
        lines.extend(
            f"⏳ **{dl.label}** — {remaining_de(dl.due_minutes, state.time_minutes)}"
            for dl in deadlines
        )
    else:
        lines.append(NO_DEADLINE_DE)

    # 4. Whose turn it is, when the turn order knows.
    if active_player.strip():
        lines.append(f"🗣 **Am Zug:** {active_player.strip()}")

    # 5. What is still open here — an incentive, never the answer.
    if scene is not None:
        lines.extend(_open_lines_de(state, scene))

    # 6. What this scene is meant to exercise, in players' language.
    hints = gate_hints_de(gates)
    if hints:
        lines.append(TEST_HEADER_DE)
        lines.extend(f"• {h}" for h in hints)

    return "\n".join(lines)


def _mission_line_de(quest: Quest) -> str:
    """The panel's goal line. Deliberately not
    :func:`~dmbot.memory.state.mission_line_de` — that one renders the same quest for the
    *prompt*; this one is read by the table and carries the panel's label and emoji."""
    line = f"🎯 **Was ihr wollt:** {quest.title}"
    if quest.detail:
        line += f" — {quest.detail}"
    if quest.given_by:
        line += f" (von {quest.given_by})"
    if quest.status != "open":
        line += f" [{quest.status}]"
    return line


def _open_lines_de(state: WorldState, scene: Scene) -> list[str]:
    """The 'still to be had here' block: one bullet per unresolved *opportunity* (secrets are
    never counted, resolved or not), or the move-on line when the scene is played out."""
    resolved = set(state.resolved_ids(scene.id))
    teasers = [
        opportunity_teaser_de(text)
        for eid, text in zip(scene.opportunity_ids, scene.opportunities_de)
        if eid not in resolved
    ]
    if not teasers:
        return [ALL_DONE_DE]
    return [OPEN_HEADER_DE] + [
        f"• eine Probe auf {t}" if t else f"• {UNNAMED_OPPORTUNITY_DE}" for t in teasers
    ]
