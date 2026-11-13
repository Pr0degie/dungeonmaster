"""Presence classifier for improvised NPCs (ADR 062).

A figure the DM improvises must become state, or the target picker offers only the people the
state already knows — and a hit lands on an NPC two scenes away.

After each narrated turn one stateless constrained-JSON call lists who appears in person at the
group's location and is not yet listed as present. Code validates every field and only then
registers or moves the NPC (golden rule #3: the model requests, code writes). Same seam, sampling
and failure posture as the scene and fact classifiers (ADR 057/058): optional, fail-open, loud in
the log, never blocking the table.

Everything here is pure except :func:`classify_present_npcs`, which takes the chat coroutine as an
argument — so the contract is testable without Discord and without a model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

log = logging.getLogger(__name__)

#: At most this many newcomers per turn — a crowd is not four hundred NPCs.
MAX_SIGHTINGS = 4

#: A label is a name or a short noun ("Hakenmann", "Vosk der Haken"), never a description.
LABEL_MAX = 40
LABEL_MAX_WORDS = 5
_LABEL_BAD = re.compile(r"[\"„“”»«‚‘’<>\[\]{}()*_`#.,;:!?\n]")

#: Shares the turn boundary with the scene and fact classifiers — must not outlive the answer.
NPC_ROUTER_TIMEOUT = 20.0

#: Pinned at the call site (``docs/lessons/sampling-defaults-leak-into-aux-calls.md``).
NPC_ROUTER_OPTIONS: dict[str, Any] = {
    "temperature": 0,
    "num_predict": 160,
    "repeat_penalty": 1.0,
    "repeat_last_n": 0,
}


class NpcFailure(str, Enum):
    """Why a turn produced no usable verdict. ``None`` covers both sightings and a clean ``[]``."""

    NO_INPUT = "no_input"
    EMPTY = "empty_answer"
    BAD_JSON = "bad_json"
    TIMEOUT = "timeout"
    CALL_FAILED = "call_failed"


@dataclass(frozen=True)
class Sighting:
    """A validated request to place a person in the current scene — never state itself.
    ``statblock`` is one of the offered roster names or empty."""

    label: str
    statblock: str = ""


@dataclass(frozen=True)
class NpcVerdict:
    sightings: tuple[Sighting, ...] = ()
    raw: str = ""
    failure: NpcFailure | None = None


class Candidate(NamedTuple):
    """A scene-card person the classifier is offered and code may merge a sighting into. A
    plain ``(name, role)`` tuple is accepted wherever candidates are."""

    name: str
    role: str = ""
    aliases: tuple[str, ...] = ()


ChatFn = Callable[..., Awaitable[str]]


def npc_schema(roster: Sequence[str] | None) -> dict:
    """Constrain the verdict: up to :data:`MAX_SIGHTINGS` entries, each a label plus a statblock
    from the adventure roster (empty = none fits)."""
    return {
        "type": "object",
        "properties": {
            "npcs": {
                "type": "array",
                "maxItems": MAX_SIGHTINGS,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "statblock": {"type": "string", "enum": [*(roster or []), ""]},
                    },
                    "required": ["label", "statblock"],
                },
            },
        },
        "required": ["npcs"],
    }


def npc_system(
    *, party: Sequence[str], roster: Sequence[str], present: Sequence[str],
    candidates: Sequence[tuple] = (),
) -> str:
    """The classifier's system prompt — German, stateless, no narration.

    ``candidates`` are the scene-card NPCs of the current scene and of the exits reachable from
    it (:class:`Candidate`), shown with role and short names: a bare name tells the model too
    little to recognise a figure described by her looks (ADR 062, amendment 2026-11-13)."""
    people = "".join(
        f"\n  · {c.name}" + (f" — {c.role}" if c.role else "")
        + (f" (auch: {', '.join(c.aliases)})" if c.aliases else "")
        for c in (Candidate(*entry) for entry in candidates)
    )
    known = (
        "- Figuren dieses Ortes und der Nachbarorte, mit Rolle:" + people + "\n"
        "  Passt eine Person der Antwort nach Rolle, Ort oder Beschreibung auf eine dieser "
        "Figuren, IST sie diese Figur: statblock = deren Name. Steht diese Figur schon unter "
        "den Anwesenden, ist die Person nicht neu.\n"
    ) if people else ""
    return (
        "Du liest eine Antwort der Spielleitung eines Rollenspiels und meldest, welche Personen "
        "darin LEIBHAFTIG am Ort der Spielergruppe auftreten und handeln oder sprechen.\n"
        "- NICHT melden: Spielfiguren (" + (", ".join(party) or "—") + "); Personen, die nur "
        "erwähnt werden oder woanders sind; Menschenmengen ohne Einzelne.\n"
        "- Schon anwesend sind: " + (", ".join(present) or "niemand") + ". Melde NUR Personen, "
        "die in dieser Antwort NEU dazukommen. Wer schon im Geschehen war und nur anders "
        "beschrieben wird („der Kerl“, „der Verwundete“, „er“), ist nicht neu.\n"
        "- label: der Name aus der Antwort, sonst eine kurze Bezeichnung im Nominativ Singular "
        "(z. B. „Hakenmann“). Mehrere Gleichartige einzeln, höchstens vier.\n"
        + known +
        "- statblock: nur wenn die Person eindeutig eine dieser Abenteuerfiguren ist: "
        + (", ".join(roster) or "—") + "; sonst leer.\n"
        "Niemand Neues: npcs = []. Antworte NUR mit JSON."
    )


def npc_user_msg(answer_text: str) -> str:
    return f"Antwort der Spielleitung:\n{answer_text.strip()}"


def _key(name: str) -> str:
    return " ".join(name.split()).casefold()


def _label(value: object) -> str | None:
    """The anti-free-text gate for a label: short, single line, no quotes or sentence marks."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > LABEL_MAX or len(text.split()) > LABEL_MAX_WORDS:
        return None
    if _LABEL_BAD.search(text):
        return None
    return text


def _party_keys(party: Sequence[str]) -> set[str]:
    """Every spelling that names a player character: the full name and its first token."""
    keys: set[str] = set()
    for name in party:
        if name and name.strip():
            keys.add(_key(name))
            keys.add(_key(name.split()[0]))
    return keys


def to_npc_verdict(
    data: object, *, party: Sequence[str], roster: Sequence[str], present: Sequence[str],
    raw: str = "",
) -> NpcVerdict:
    """Validate the parsed JSON entry by entry; a bad entry is dropped, never repaired."""
    if not isinstance(data, dict) or not isinstance(data.get("npcs"), list):
        return NpcVerdict(raw=raw, failure=NpcFailure.BAD_JSON)
    blocked = _party_keys(party) | {_key(p) for p in present if p}
    roster_by_key = {_key(r): r for r in roster if r}
    out: list[Sighting] = []
    for entry in data["npcs"][:MAX_SIGHTINGS]:
        if not isinstance(entry, dict):
            continue
        label = _label(entry.get("label"))
        if label is None or _key(label) in blocked:
            continue
        block = entry.get("statblock") or ""
        if not isinstance(block, str):
            continue
        # An off-roster statblock is a guess: keep the person, fall back to the default numbers.
        statblock = roster_by_key.get(_key(block), "") if block.strip() else ""
        blocked.add(_key(label))
        out.append(Sighting(label=label, statblock=statblock))
    return NpcVerdict(sightings=tuple(out), raw=raw)


def _words(text: str) -> list[str]:
    return [w for w in (t.strip(".,;:!?()„“\"'").casefold() for t in text.split()) if w]


def card_person(sighting: Sighting, candidates: Sequence[tuple]) -> str:
    """Which scene-card NPC a sighting *is* — her name, or ``""`` for somebody else (ADR 062,
    amendment 2026-11-13 #8). Code decides identity; the verdict only names people.

    In order: the statblock names a candidate; the label is a candidate's name; the label is
    exactly one of a candidate's authored aliases ("Fenk"); the label is a candidate's role or
    its leading words ("Schreinschwester" for "Schreinschwester der Aschenheiligen"). An alias
    or a role that fits two candidates identifies nobody. Names are never matched by their
    parts."""
    people = [Candidate(*entry) for entry in candidates]
    by_name = {_key(c.name): c.name for c in people if c.name}
    for probe in (sighting.statblock, sighting.label):
        if probe and _key(probe) in by_name:
            return by_name[_key(probe)]
    called = _key(sighting.label)
    hits = {c.name for c in people if any(_key(alias) == called for alias in c.aliases)}
    if hits:
        return hits.pop() if len(hits) == 1 else ""
    label = _words(sighting.label)
    hits = {c.name for c in people if label and _words(c.role)[:len(label)] == label}
    return hits.pop() if len(hits) == 1 else ""


async def classify_present_npcs(
    chat: ChatFn,
    *,
    answer_text: str,
    party: Sequence[str],
    roster: Sequence[str],
    present: Sequence[str],
    candidates: Sequence[tuple] = (),
    timeout: float | None = NPC_ROUTER_TIMEOUT,
) -> NpcVerdict:
    """Ask who newly appears in person this turn and return a validated verdict. Never raises."""
    if not answer_text.strip():
        return NpcVerdict(failure=NpcFailure.NO_INPUT)
    coro = chat(
        npc_system(party=party, roster=roster, present=present, candidates=candidates),
        [{"role": "user", "content": npc_user_msg(answer_text)}],
        options=dict(NPC_ROUTER_OPTIONS),
        format=npc_schema(roster),
    )
    try:
        raw = await (asyncio.wait_for(coro, timeout) if timeout else coro)
    except TimeoutError:
        log.warning("npc-router: no verdict within %ss — nobody registered", timeout)
        return NpcVerdict(failure=NpcFailure.TIMEOUT)
    except Exception:
        log.exception("npc-router: classification call failed — nobody registered")
        return NpcVerdict(failure=NpcFailure.CALL_FAILED)
    raw = raw or ""
    if not raw.strip():
        return NpcVerdict(raw=raw, failure=NpcFailure.EMPTY)
    try:
        data = json.loads(raw)
    except Exception:
        log.warning("npc-router: unparseable verdict %r — nobody registered", raw[:120])
        return NpcVerdict(raw=raw, failure=NpcFailure.BAD_JSON)
    return to_npc_verdict(data, party=party, roster=roster, present=present, raw=raw)
