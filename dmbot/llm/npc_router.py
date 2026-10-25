"""Presence classifier for improvised NPCs (ADR 062).

On 2026-10-25 Opus invented the opposition on the spot — a "Kettenmann" at the shrine door, a
"Hakenmann", four chain-gang thugs. None of them became state, so when Fridolin's shot hit, the
target picker offered the people the state *did* know: Seneschal Kaad, two scenes away. Both hits
landed on the quest-giver.

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
from typing import Any

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


def npc_system(*, party: Sequence[str], roster: Sequence[str], present: Sequence[str]) -> str:
    """The classifier's system prompt — German, stateless, no narration."""
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


async def classify_present_npcs(
    chat: ChatFn,
    *,
    answer_text: str,
    party: Sequence[str],
    roster: Sequence[str],
    present: Sequence[str],
    timeout: float | None = NPC_ROUTER_TIMEOUT,
) -> NpcVerdict:
    """Ask who newly appears in person this turn and return a validated verdict. Never raises."""
    if not answer_text.strip():
        return NpcVerdict(failure=NpcFailure.NO_INPUT)
    coro = chat(
        npc_system(party=party, roster=roster, present=present),
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
