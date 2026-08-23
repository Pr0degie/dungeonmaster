"""Commitment classifier (ADR 058).

On 2026-08-22 the group won a social test and the seneschal handed over a customs warrant. Nine
turns later the same NPC refused to give them one — because the warrant was never a fact, only
prose in a history that gets truncated and summarised. Nothing in the world state ever recorded
that an item changed hands, that a quest was accepted, or that a promise was made.

This is the plot-side of the seam that already works for dice (golden rule #2 extended to #3): the
model *requests*, code validates and writes. After the turn is narrated, one stateless
constrained-JSON call reports what the answer committed to — an item handed over, a quest accepted,
a promise given — from a closed enumeration, with the recipient picked from the actual people at
the table. Code checks that verdict and only then calls
:meth:`dmbot.memory.state.WorldState.record_commitment`; free text never reaches hard state (the
label passes the same length/shape gate the writer applies, :data:`FACT_TEXT_MAX`).

Everything here is pure except :func:`classify_commitment`, which takes the chat coroutine as an
argument — so the contract is testable without Discord and without a running Ollama.

Failure posture: optional layer, fails open loudly (``docs/lessons/optional-layers-fail-open-...``).
A malformed, out-of-enum or empty verdict writes nothing, logs one line, and never blocks the table.
A false positive is the expensive direction here — a prompt-resident wrong fact is worse than a
forgotten right one (ADR 058) — so every doubtful case is discarded rather than repaired.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

# ``_validated_fact_text`` is the writer's own gate, imported instead of retyped so the two
# can't drift (``docs/lessons/parity-by-construction.md``). It is private only because it
# predates this second caller — see :func:`validated_label`.
from ..memory.state import FACT_TEXT_MAX, GROUP_HOLDER, _validated_fact_text

log = logging.getLogger(__name__)

#: The kinds a turn can commit to — the exact enumeration
#: :meth:`dmbot.memory.state.WorldState.record_commitment` dispatches on.
COMMITMENT_KINDS: tuple[str, ...] = ("item", "quest", "promise")

#: The classifier's "nothing was committed to" answer — part of the enum, not a failure.
NO_COMMITMENT = "nichts"

#: Seconds the post-turn call may take before it is abandoned. Shares the turn boundary with the
#: scene classifier (ADR 057/058), so it must not outlive the answer the table is listening to.
FACT_ROUTER_TIMEOUT = 20.0

#: Sampling pinned at the call site, never inherited from the client's narration defaults
#: (``docs/lessons/sampling-defaults-leak-into-aux-calls.md``): temperature 0 for a deterministic
#: verdict, penalties neutralised because the system prompt lists every kind and every name — a
#: repeat penalty would punish exactly the enum token the classifier must emit.
FACT_ROUTER_OPTIONS: dict[str, Any] = {
    "temperature": 0,
    "num_predict": 120,
    "repeat_penalty": 1.0,
    "repeat_last_n": 0,
}


class FactFailure(str, Enum):
    """Why a turn produced no usable commitment — for the operator line and the replay notes.
    ``None`` covers both a recorded commitment and a clean ``"nichts"``."""

    NO_INPUT = "no_input"                    # nothing was narrated this turn
    EMPTY = "empty_answer"                   # model returned nothing / a blank kind
    BAD_JSON = "bad_json"                    # unparseable or wrong-shaped verdict
    OFF_LIST = "off_list"                    # a kind outside the enumeration
    BAD_TEXT = "bad_text"                    # narration instead of a short label
    UNKNOWN_RECIPIENT = "unknown_recipient"  # a holder nobody at the table can be
    TIMEOUT = "timeout"
    CALL_FAILED = "call_failed"


@dataclass(frozen=True)
class Commitment:
    """A validated request for the world state — never state itself. ``kind`` is one of
    :data:`COMMITMENT_KINDS`, ``text`` a short label ("Zollvollmacht", never a sentence), ``to``
    the resolved holder (a character name or :data:`GROUP_HOLDER`) and ``by`` the NPC it came
    from (empty when unknown)."""

    kind: str
    text: str
    to: str = GROUP_HOLDER
    by: str = ""

    def record_kwargs(self) -> dict[str, str]:
        """The keyword arguments for the writer:
        ``state.record_commitment(c.kind, **c.record_kwargs())``."""
        return {"text": self.text, "to": self.to, "by": self.by}


@dataclass(frozen=True)
class FactVerdict:
    """What the classifier decided. ``commitment`` is ``None`` unless something was validated."""

    commitment: Commitment | None = None
    raw: str = ""
    failure: FactFailure | None = None


ChatFn = Callable[..., Awaitable[str]]


def recipient_choices(recipients: Sequence[str] | None) -> list[str]:
    """The people an item or promise can go to: the characters at the table plus the party itself,
    deduplicated, order preserved. The party is always offered — a promise made "to the group" is
    the common case and must not depend on a roster being loaded."""
    out: list[str] = []
    for name in [*(recipients or []), GROUP_HOLDER]:
        clean = str(name or "").strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def source_choices(givers: Sequence[str] | None) -> list[str]:
    """The NPCs a commitment can come from (the scene's cast); empty is always allowed."""
    out: list[str] = []
    for name in givers or []:
        clean = str(name or "").strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def _match(value: str, choices: Sequence[str]) -> str | None:
    for c in choices:
        if value.casefold() == c.casefold():
            return c
    return None


def validated_label(value: object) -> str | None:
    """The anti-free-text gate: a fact's text is a short single-line label or it is narration,
    and narration never becomes hard state (golden rule #3).

    One implementation, not two — this delegates to the gate the writer itself applies,
    :func:`dmbot.memory.state._validated_fact_text` (same criterion, same :data:`FACT_TEXT_MAX`).
    The ``isinstance`` check stays on this side and is deliberately not part of it: the value
    here comes straight out of model JSON, so a number or an object must be discarded rather
    than coerced into the label ``"42"``."""
    if not isinstance(value, str):
        return None
    return _validated_fact_text(value)


def fact_schema(recipients: Sequence[str] | None, givers: Sequence[str] | None) -> dict:
    """The constrained-output schema. Kind, recipient and source are closed enums; only the label
    is free-form, and it is length-gated by code afterwards."""
    return {
        "type": "object",
        "properties": {
            "art": {"type": "string", "enum": [*COMMITMENT_KINDS, NO_COMMITMENT]},
            "sache": {"type": "string"},
            "an": {"type": "string", "enum": [*recipient_choices(recipients), ""]},
            "von": {"type": "string", "enum": [*source_choices(givers), ""]},
        },
        "required": ["art", "sache", "an", "von"],
    }


def fact_system(recipients: Sequence[str] | None, givers: Sequence[str] | None) -> str:
    """The classifier's tiny, stateless German system prompt — one question about the turn that
    was just narrated, with the bar set at "actually happened", not "was offered"."""
    who = ", ".join(recipient_choices(recipients))
    npcs = ", ".join(source_choices(givers)) or "— (dann 'von' leer lassen)"
    return (
        "Du bist der Protokollant der Spielleitung eines Rollenspiels.\n"
        "Lies die eben erzählte Antwort der Spielleitung und melde NUR, was darin wirklich "
        "geschehen ist — nicht, was jemand vorhat, anbietet oder andeutet.\n"
        f"- '{COMMITMENT_KINDS[0]}': ein Gegenstand hat den Besitzer gewechselt; die Gruppe hat "
        "ihn jetzt in der Hand.\n"
        f"- '{COMMITMENT_KINDS[1]}': die Gruppe hat einen Auftrag angenommen.\n"
        f"- '{COMMITMENT_KINDS[2]}': eine Figur hat eine Zusage gegeben, die später gilt.\n"
        f"- '{NO_COMMITMENT}': alles andere — Angebote ohne Annahme, Verhandlungen, Drohungen, "
        "bloßes Erwähnen eines Gegenstands, reine Beschreibung.\n"
        f"'sache' ist ein kurzes Etikett von höchstens {FACT_TEXT_MAX} Zeichen, eine Zeile, keine "
        "Erzählung: 'Zollvollmacht', nicht 'Kaad schiebt ihm die Vollmacht über den Tisch'.\n"
        f"'an' nur aus dieser Liste: {who}.\n"
        f"'von' nur aus dieser Liste: {npcs}. Unklar: leer lassen.\n"
        f"Im Zweifel '{NO_COMMITMENT}'. Antworte NUR mit JSON."
    )


def fact_user_msg(answer_text: str) -> str:
    """The single user message: the answer that was just narrated."""
    return f"Antwort der Spielleitung:\n{answer_text.strip()}"


def to_fact_verdict(
    data: object,
    *,
    recipients: Sequence[str] | None,
    givers: Sequence[str] | None,
    raw: str = "",
) -> FactVerdict:
    """Validate the parsed verdict — this is where code decides what the model's answer means.

    Strict where a mistake would write the wrong hard state (unknown recipient, prose instead of a
    label, unknown kind all discard the whole verdict), lenient where it would only lose
    provenance: an off-list source is dropped and the fact is kept (clamp, don't reject —
    ``docs/lessons/llm-requests-code-validates.md``)."""
    if not isinstance(data, dict) or "art" not in data:
        log.info("fact-router: discarded a malformed verdict: %r", data)
        return FactVerdict(raw=raw, failure=FactFailure.BAD_JSON)
    art = data.get("art")
    if not isinstance(art, str):
        log.info("fact-router: discarded a non-string kind: %r", art)
        return FactVerdict(raw=raw, failure=FactFailure.BAD_JSON)
    kind = art.strip().casefold()
    if not kind:
        log.info("fact-router: discarded an empty kind")
        return FactVerdict(raw=raw, failure=FactFailure.EMPTY)
    if kind == NO_COMMITMENT.casefold():
        return FactVerdict(raw=raw)
    if kind not in COMMITMENT_KINDS:
        log.warning("fact-router: kind %r is outside the enumeration — discarded", art)
        return FactVerdict(raw=raw, failure=FactFailure.OFF_LIST)

    text = validated_label(data.get("sache"))
    if text is None:
        log.warning(
            "fact-router: %r is not a short label (narration or empty) — discarded",
            str(data.get("sache"))[:120],
        )
        return FactVerdict(raw=raw, failure=FactFailure.BAD_TEXT)

    choices = recipient_choices(recipients)
    to_raw = str(data.get("an") or "").strip()
    holder = GROUP_HOLDER if not to_raw else _match(to_raw, choices)
    if holder is None:
        log.warning(
            "fact-router: recipient %r is nobody at this table %s — discarded", to_raw, choices
        )
        return FactVerdict(raw=raw, failure=FactFailure.UNKNOWN_RECIPIENT)

    by_raw = str(data.get("von") or "").strip()
    source = _match(by_raw, source_choices(givers)) if by_raw else ""
    if by_raw and source is None:
        # Provenance only — it labels the line, it doesn't decide who holds what. Keep the fact.
        log.info("fact-router: source %r is not a known NPC — recorded without a source", by_raw)
        source = ""

    return FactVerdict(
        commitment=Commitment(kind=kind, text=text, to=holder, by=source), raw=raw
    )


async def classify_commitment(
    chat: ChatFn,
    *,
    answer_text: str,
    recipients: Sequence[str] | None = (),
    givers: Sequence[str] | None = (),
    timeout: float | None = FACT_ROUTER_TIMEOUT,
) -> FactVerdict:
    """Ask what the narrated turn committed to and return a validated verdict. Never raises.

    ``chat`` is :meth:`dmbot.llm.client.LLMClient.chat` (injected so the contract is testable
    without a model). The caller writes the result — and only the result — with
    ``state.record_commitment(v.commitment.kind, **v.commitment.record_kwargs())``.
    """
    if not answer_text.strip():
        log.debug("fact-router: skipped — nothing was narrated this turn")
        return FactVerdict(failure=FactFailure.NO_INPUT)
    schema = fact_schema(recipients, givers)
    system = fact_system(recipients, givers)
    coro = chat(
        system,
        [{"role": "user", "content": fact_user_msg(answer_text)}],
        options=dict(FACT_ROUTER_OPTIONS),
        format=schema,
    )
    try:
        raw = await (asyncio.wait_for(coro, timeout) if timeout else coro)
    except TimeoutError:  # asyncio.TimeoutError is this since 3.11; a real cancel stays uncaught
        log.warning("fact-router: no verdict within %ss — nothing recorded", timeout)
        return FactVerdict(failure=FactFailure.TIMEOUT)
    except Exception:
        log.exception("fact-router: classification call failed — nothing recorded")
        return FactVerdict(failure=FactFailure.CALL_FAILED)
    raw = raw or ""
    if not raw.strip():
        log.info("fact-router: empty answer — nothing recorded")
        return FactVerdict(raw=raw, failure=FactFailure.EMPTY)
    try:
        data = json.loads(raw)
    except Exception:
        log.warning("fact-router: unparseable verdict %r — nothing recorded", raw[:120])
        return FactVerdict(raw=raw, failure=FactFailure.BAD_JSON)
    return to_fact_verdict(data, recipients=recipients, givers=givers, raw=raw)
