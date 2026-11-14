"""One combined post-turn classifier call on the Claude backend (ADR 066, option B).

After every narrated turn three stateless schema calls ask three questions about the same answer:
did the group enter a place (ADR 057), did the narration commit to an item, quest or promise
(ADR 058), who newly appears in person (ADR 062). On Claude each is its own CLI process with its
own overhead, and each sends the answer again; the evening of 2026-11-14 measured about 6,700
Haiku input tokens per turn for the three. This module asks all of them in **one** call.

What it does not change, by construction:

- **The questions.** Each part of the combined system prompt is the separate classifier's own
  question builder (:func:`~dmbot.llm.scene_router.scene_question`,
  :func:`~dmbot.llm.fact_router.fact_question`, :func:`~dmbot.llm.npc_router.npc_question`) —
  one text per question, used by both paths (``docs/lessons/parity-by-construction.md``).
- **The schema.** The combined schema is the three schemas' properties side by side; the field
  names do not collide (``ziel``; ``art, sache, an, von``; ``npcs``), so the ``[aux]`` line's
  ``fields=`` names a combined call by itself.
- **The validators.** Each part of the answer goes through its own pure validator
  (``to_scene_verdict``, ``to_fact_verdict``, ``to_npc_verdict``) exactly as a separate answer
  would; each verdict's ``raw`` is its own part of the answer (the journal shape of ADR 066).

Only the caller decides whether a turn is combined — never this module, and never by naming a
backend: the brain asks the hook :func:`dmbot.llm.post_turn_combined` (ADR 061, tier rule). Ollama
keeps the three separate calls unchanged.

Failure posture: a combined answer that cannot be used is never repaired. A failed, timed-out,
empty or unparseable call hands **every** question back for a separate call; a part whose fields
are missing or wrong-shaped hands back that part. :attr:`CombinedResult.retry` names them, and the
caller asks them through the separate path in the same turn. Never raises.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .fact_router import (
    FACT_ROUTER_OPTIONS,
    FactFailure,
    fact_question,
    fact_schema,
    to_fact_verdict,
)
from .npc_router import NPC_ROUTER_OPTIONS, NpcFailure, npc_question, npc_schema, to_npc_verdict
from .scene_router import (
    SCENE_ROUTER_OPTIONS,
    SceneFailure,
    SceneVerdict,
    normalize_exits,
    scene_question,
    scene_schema,
    to_scene_verdict,
)

log = logging.getLogger(__name__)

#: The three post-turn questions, in prompt order. The scene question comes first because it is
#: the only one the context (previous narration, player lines) is for.
POST_TURN_KINDS: tuple[str, ...] = ("scene", "fact", "npc")

#: Each question's top-level schema fields — the part of a combined answer its validator gets.
FIELDS: dict[str, tuple[str, ...]] = {
    "scene": ("ziel",),
    "fact": ("art", "sache", "an", "von"),
    "npc": ("npcs",),
}

_HEADINGS = {
    "scene": "Ortswechsel",
    "fact": "Festlegungen",
    "npc": "neue Personen",
}

#: One deadline for the one call, as each separate call has (ADR 066 A/B). It runs behind the DM's
#: voice like the three did; on a timeout the separate calls follow in the same turn.
COMBINED_TIMEOUT = 20.0

#: A validator failure that means "this part of the answer is not there or has the wrong shape" —
#: asked again separately. Every other failure (an off-list exit, prose instead of a label, an
#: unknown recipient) is the model's verdict, discarded by code exactly as a separate answer is.
_MALFORMED = {
    "scene": {SceneFailure.BAD_JSON, SceneFailure.EMPTY},
    "fact": {FactFailure.BAD_JSON, FactFailure.EMPTY},
    "npc": {NpcFailure.BAD_JSON, NpcFailure.EMPTY},
}

_OPTIONS = {"scene": SCENE_ROUTER_OPTIONS, "fact": FACT_ROUTER_OPTIONS, "npc": NPC_ROUTER_OPTIONS}

ChatFn = Callable[..., Awaitable[str]]


class CombinedFailure(str, Enum):
    """Why the combined call as a whole gave nothing usable — every asked question goes back to
    its separate call. ``None`` on a result whose call was answered (some parts may still be
    handed back, see :attr:`CombinedResult.retry`)."""

    NOT_COMBINABLE = "not_combinable"  # fewer than two questions to ask, or different answers
    EMPTY = "empty_answer"
    BAD_JSON = "bad_json"
    TIMEOUT = "timeout"
    CALL_FAILED = "call_failed"


@dataclass(frozen=True)
class CombinedResult:
    """``verdicts`` holds the questions the combined call (or a check before it) decided;
    ``retry`` the ones the caller still has to ask separately; ``asked`` the ones the call
    carried. ``raw`` is the whole answer, for the journal's ``post_turn`` note."""

    verdicts: dict[str, Any] = field(default_factory=dict)
    retry: tuple[str, ...] = ()
    asked: tuple[str, ...] = ()
    raw: str = ""
    failure: CombinedFailure | None = None

    def note(self) -> dict:
        """The journal's ``post_turn`` note (ADR 066): the full answer once, next to the three
        per-question notes that keep their shape."""
        return {
            "raw": self.raw,
            "asked": list(self.asked),
            "failure": self.failure.value if self.failure else None,
            "separate": list(self.retry),
        }


def _answer_of(kind: str, question: Mapping[str, Any]) -> str:
    return str(question.get("turn_text" if kind == "scene" else "answer_text") or "")


def combined_schema(*, scene: Mapping | None = None, fact: Mapping | None = None,
                    npc: Mapping | None = None) -> dict:
    """The asked questions' schemas, side by side in one object."""
    parts = []
    if scene is not None:
        parts.append(scene_schema(scene.get("exits")))
    if fact is not None:
        parts.append(fact_schema(fact.get("recipients"), fact.get("givers")))
    if npc is not None:
        parts.append(npc_schema(npc.get("roster")))
    properties: dict[str, Any] = {}
    required: list[str] = []
    for part in parts:
        properties.update(part["properties"])
        required.extend(part["required"])
    return {"type": "object", "properties": properties, "required": required}


def combined_system(*, scene: Mapping | None = None, fact: Mapping | None = None,
                    npc: Mapping | None = None) -> str:
    """One German system prompt with each asked question in full, under its own heading, in
    :data:`POST_TURN_KINDS` order. The texts are the separate calls' own builders."""
    blocks: list[tuple[str, str]] = []
    if scene is not None:
        blocks.append(("scene", scene_question(scene.get("exits"),
                                               current_title=scene.get("current_title") or "")))
    if fact is not None:
        blocks.append(("fact", fact_question(fact.get("recipients"), fact.get("givers"))))
    if npc is not None:
        blocks.append(("npc", npc_question(
            party=npc.get("party") or (), roster=npc.get("roster") or (),
            present=npc.get("present") or (), candidates=npc.get("candidates") or (),
        )))
    body = ""
    for number, (kind, text) in enumerate(blocks, start=1):
        names = ", ".join(f"'{f}'" for f in FIELDS[kind])
        label = "Feld" if len(FIELDS[kind]) == 1 else "Felder"
        body += f"\nFrage {number} — {_HEADINGS[kind]} ({label} {names}):\n{text.rstrip()}\n"
    fields = ", ".join(f for kind, _ in blocks for f in FIELDS[kind])
    return (
        "Du bist der Assistent der Spielleitung eines Rollenspiels. Du liest die zuletzt "
        f"erzählte Antwort der Spielleitung und beantwortest dazu {len(blocks)} voneinander "
        "unabhängige Fragen. Jede Frage hat ihre eigenen Regeln und ihre eigenen Felder: "
        "entscheide jede für sich, allein nach ihren Regeln.\n"
        + body
        + f"\nAntworte NUR mit JSON: ein Objekt mit allen Feldern ({fields})."
    )


def combined_user_msg(answer_text: str, context: str = "", *, with_scene: bool = False) -> str:
    """The one user message: the narrated answer, after the scene question's context when the
    scene is asked. The context is marked as the scene question's alone — the main risk of a
    combined call is a commitment or a person from the previous turn reported again (ADR 066)."""
    head = (
        "Davor (nur zur Einordnung für Frage 1, welcher Ort gemeint ist — ob die Gruppe ihn "
        "betritt, entscheidet allein der zuletzt erzählte Zug; die anderen Fragen beziehen sich "
        f"NUR auf den zuletzt erzählten Zug, nicht hierauf):\n{context.strip()}\n\n"
        if with_scene and context.strip() else ""
    )
    return (f"{head}Zuletzt erzählter Zug — die Antwort der Spielleitung:\n"
            f"{answer_text.strip()}")


def combined_options(kinds: tuple[str, ...]) -> dict[str, Any]:
    """Sampling pinned at the call site like each separate call's
    (``docs/lessons/sampling-defaults-leak-into-aux-calls.md``); the output cap is the asked
    questions' caps added up — the same verdict text is written either way."""
    return {
        "temperature": 0,
        "num_predict": sum(int(_OPTIONS[k]["num_predict"]) for k in kinds),
        "repeat_penalty": 1.0,
        "repeat_last_n": 0,
    }


def split_answer(data: dict, kind: str) -> dict:
    """The part of a combined answer one validator gets: its own fields, nothing else."""
    return {f: data[f] for f in FIELDS[kind] if f in data}


def _validate(kind: str, part: dict, question: Mapping[str, Any], raw: str):
    if kind == "scene":
        return to_scene_verdict(part, exits=question.get("exits"), raw=raw)
    if kind == "fact":
        return to_fact_verdict(part, recipients=question.get("recipients"),
                               givers=question.get("givers"), raw=raw)
    return to_npc_verdict(part, party=question.get("party") or (),
                          roster=question.get("roster") or (),
                          present=question.get("present") or (), raw=raw)


def split_verdicts(data: object, questions: Mapping[str, Mapping[str, Any]],
                   ) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Validate each asked part of a parsed combined answer with its own validator. Returns the
    usable verdicts and the kinds whose part was missing or wrong-shaped (to be asked again)."""
    if not isinstance(data, dict):
        return {}, tuple(questions)
    verdicts: dict[str, Any] = {}
    retry: list[str] = []
    for kind, question in questions.items():
        part = split_answer(data, kind)
        verdict = _validate(kind, part, question, json.dumps(part, ensure_ascii=False))
        if verdict.failure in _MALFORMED[kind]:
            retry.append(kind)
        else:
            verdicts[kind] = verdict
    return verdicts, tuple(retry)


async def classify_post_turn(
    chat: ChatFn,
    *,
    scene: Mapping[str, Any] | None = None,
    fact: Mapping[str, Any] | None = None,
    npc: Mapping[str, Any] | None = None,
    timeout: float | None = COMBINED_TIMEOUT,
) -> CombinedResult:
    """Ask the given questions in one call. Never raises.

    Each question is the keyword set its separate classifier takes (``classify_scene_move``,
    ``classify_commitment``, ``classify_present_npcs``), so the caller builds one set per
    question and hands the same set to either path. A scene question without a reachable exit is
    decided here as the separate call would (``no_exits``). Fewer than two questions left, or
    questions about different answers, are not combined: they come back in ``retry``."""
    given = {k: q for k, q in (("scene", scene), ("fact", fact), ("npc", npc)) if q is not None}
    decided: dict[str, Any] = {}
    if "scene" in given and not normalize_exits(given["scene"].get("exits")):
        decided["scene"] = SceneVerdict(failure=SceneFailure.NO_EXITS)
        del given["scene"]
    answers = {_answer_of(k, q).strip() for k, q in given.items()}
    if len(given) < 2 or len(answers) != 1:
        return CombinedResult(verdicts=decided, retry=tuple(given),
                              failure=CombinedFailure.NOT_COMBINABLE)
    answer = answers.pop()
    kinds = tuple(given)
    if not answer:
        # Nothing narrated: each separate call would skip without asking — so do they.
        return CombinedResult(verdicts=decided, retry=kinds,
                              failure=CombinedFailure.NOT_COMBINABLE)
    context = str(given["scene"].get("context") or "") if "scene" in given else ""
    coro = chat(
        combined_system(**given),
        [{"role": "user",
          "content": combined_user_msg(answer, context, with_scene="scene" in given)}],
        options=combined_options(kinds),
        format=combined_schema(**given),
    )
    try:
        raw = await (asyncio.wait_for(coro, timeout) if timeout else coro)
    except TimeoutError:  # a real cancel stays uncaught
        log.warning("post-turn: no combined verdict within %ss — asking %s separately",
                    timeout, ", ".join(kinds))
        return CombinedResult(verdicts=decided, retry=kinds, asked=kinds,
                              failure=CombinedFailure.TIMEOUT)
    except Exception:
        log.exception("post-turn: combined call failed — asking %s separately", ", ".join(kinds))
        return CombinedResult(verdicts=decided, retry=kinds, asked=kinds,
                              failure=CombinedFailure.CALL_FAILED)
    raw = raw or ""
    if not raw.strip():
        log.warning("post-turn: empty combined answer — asking %s separately", ", ".join(kinds))
        return CombinedResult(verdicts=decided, retry=kinds, asked=kinds, raw=raw,
                              failure=CombinedFailure.EMPTY)
    try:
        data = json.loads(raw)
    except Exception:
        data = None
    if not isinstance(data, dict):
        log.warning("post-turn: unusable combined answer %r — asking %s separately",
                    raw[:120], ", ".join(kinds))
        return CombinedResult(verdicts=decided, retry=kinds, asked=kinds, raw=raw,
                              failure=CombinedFailure.BAD_JSON)
    verdicts, retry = split_verdicts(data, given)
    if retry:
        log.warning("post-turn: the combined answer has no usable %s part — asked separately",
                    ", ".join(retry))
    return CombinedResult(verdicts={**decided, **verdicts}, retry=retry, asked=kinds, raw=raw)
