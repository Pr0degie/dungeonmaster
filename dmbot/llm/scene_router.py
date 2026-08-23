"""Scene-move classifier (ADR 057).

The scene pointer decides whether the evening happens: overlay, in-game clock, deadlines, NPC
agendas, recap, NPC memory and Chekhov threads all hang off a scene change. On 2026-08-22 that
pointer never moved in 22 turns, because its only real mover was an inline ``<<ORT>>`` marker the
narration model has to emit at the very end of its answer — exactly where the token ceiling and the
stop-label cut destroy it.

So movement gets what the roll router got (ADR 014, the one LLM-driven decision with a live track
record): its own stateless constrained-JSON call, asked one question after each turn — *did the
group actually enter one of these places?* The answer space is exactly the current scene's
reachable exits plus ``"nein"``; anything else is a failure that changes nothing
(``docs/lessons/mandatory-decisions-need-a-separate-classifier.md``).

Everything here is pure except :func:`classify_scene_move`, and that takes the chat coroutine as an
argument — so the whole contract is testable without Discord and without a running Ollama. What the
verdict is then *allowed* to do is not decided here: the caller feeds ``target_id`` through
:func:`dmbot.rules.scene_flow.resolve_exit` and writes the pointer.

Failure posture: optional layer, fails open loudly (``docs/lessons/optional-layers-fail-open-...``).
Every degenerate answer returns a verdict with a machine-readable ``failure`` and a log line; the
table is never blocked and nothing is raised at the caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)

#: The classifier's "the group stayed where it was" answer — part of the enum, not a failure.
NO_MOVE = "nein"

#: Seconds the post-turn call may take before it is abandoned. It runs on the turn boundary next to
#: the fact classifier (ADR 058), where the players are already listening to the answer, so a slow
#: verdict is worth nothing: better no move than a late one.
SCENE_ROUTER_TIMEOUT = 20.0

#: Sampling pinned at the call site, never inherited from the client's narration defaults
#: (``docs/lessons/sampling-defaults-leak-into-aux-calls.md``): temperature 0 for a deterministic
#: verdict, and the anti-repetition penalties neutralised because the system prompt lists every
#: exit id — a repeat penalty would punish the very token the router has to emit.
SCENE_ROUTER_OPTIONS: dict[str, Any] = {
    "temperature": 0,
    "num_predict": 40,
    "repeat_penalty": 1.0,
    "repeat_last_n": 0,
}


class SceneFailure(str, Enum):
    """Why a turn produced no usable verdict — for the operator line and the replay notes.

    ``None`` (no failure) covers both a clean move and a clean ``"nein"``; these are the cases
    where the layer degraded instead."""

    NO_EXITS = "no_exits"          # current scene has no reachable exit — nothing to ask about
    NO_INPUT = "no_input"          # nothing was narrated this turn
    EMPTY = "empty_answer"         # model returned nothing / a blank target
    BAD_JSON = "bad_json"          # unparseable or wrong-shaped verdict
    OFF_LIST = "off_list"          # a target outside the offered choice — invented, so discarded
    TIMEOUT = "timeout"            # the deadline hit first
    CALL_FAILED = "call_failed"    # transport/HTTP error


def exit_label(scene_id: str, title: str = "") -> str:
    """Render one offered exit: ``"pier-neun — Pier Neun"``, or the bare id when no title is known.

    The single owner of that string. It had three copies — this module's :class:`SceneExit`, the
    scene card in :meth:`dmbot.rag.adventure.Adventure.adventure_block_de` and the rejection note
    in ``SessionRuntime.report_rejected_move`` — and the same value written in three places
    desyncs (``docs/lessons/parity-by-construction.md``). Call it from all of them; the signature
    (id first, title second, both plain strings, one line back) stays put."""
    sid = str(scene_id or "").strip()
    name = str(title or "").strip()
    return f"{sid} — {name}" if sid and name else sid


@dataclass(frozen=True)
class SceneExit:
    """One offered destination: the scene id the pointer would move to, plus its title for the
    prompt (ADR 057 #6 — a bare id gives the model nothing to map "zum Hafen" onto)."""

    id: str
    title: str = ""

    def label(self) -> str:
        return exit_label(self.id, self.title)


@dataclass(frozen=True)
class SceneVerdict:
    """What the classifier decided. ``target_id`` is empty unless a *reachable* exit was named."""

    target_id: str = ""
    raw: str = ""
    failure: SceneFailure | None = None

    @property
    def moved(self) -> bool:
        return bool(self.target_id)


ChatFn = Callable[..., Awaitable[str]]

ExitsArg = Mapping[str, str] | Sequence[Any] | None


def normalize_exits(exits: ExitsArg) -> tuple[SceneExit, ...]:
    """Accept the shapes the call sites actually have — ``{id: title}``, ``[(id, title)]``, plain
    ids (what :func:`dmbot.rules.scene_flow.reachable_exits` returns) or ready
    :class:`SceneExit`\\ s — and return a deduplicated, order-preserving tuple. Empty ids are
    dropped rather than offered as a choice the model could pick."""
    if not exits:
        return ()
    items: list[SceneExit] = []
    if isinstance(exits, Mapping):
        raw_items = [(str(k), str(v or "")) for k, v in exits.items()]
    else:
        raw_items = []
        for entry in exits:
            if isinstance(entry, SceneExit):
                raw_items.append((entry.id, entry.title))
            elif isinstance(entry, str):
                raw_items.append((entry, ""))
            elif isinstance(entry, Sequence) and len(entry) >= 2:
                raw_items.append((str(entry[0]), str(entry[1] or "")))
            else:  # unknown shape — ignore rather than offer a broken choice
                log.warning("scene-router: ignoring an exit of unexpected shape %r", entry)
    seen: set[str] = set()
    for eid, title in raw_items:
        key = eid.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(SceneExit(key, title.strip()))
    return tuple(items)


def scene_schema(exits: ExitsArg) -> dict:
    """The constrained-output schema: one field whose enum is exactly the reachable exits plus
    ``"nein"``. The model cannot name a place it may not move to — an invented target is a
    schema violation, not a rejected move."""
    ids = [e.id for e in normalize_exits(exits)]
    return {
        "type": "object",
        "properties": {"ziel": {"type": "string", "enum": [*ids, NO_MOVE]}},
        "required": ["ziel"],
    }


def scene_system(exits: ExitsArg, *, current_title: str = "") -> str:
    """The classifier's tiny, stateless German system prompt — no narration, no history, one
    question. The bar is deliberately high: only an *arrival* counts, because a false move tears
    the table out of a conversation while a missed one is caught by the flag gate next turn."""
    lines = [f"- {e.label()}" for e in normalize_exits(exits)]
    here = f"Die Gruppe war zuletzt hier: {current_title}.\n" if current_title.strip() else ""
    return (
        "Du bist der Regel-Assistent der Spielleitung eines Rollenspiels.\n"
        f"{here}"
        "Frage: Hat die Gruppe im zuletzt erzählten Zug tatsächlich einen dieser Orte BETRETEN?\n"
        + "\n".join(lines)
        + "\n"
        f"- Antworte mit der id des Ortes NUR, wenn die Gruppe dort ankommt oder eintritt.\n"
        f"- Absicht, Vorschlag, Aufbruch, ein Blick in die Richtung oder das bloße Erwähnen eines "
        f"Ortes ist KEIN Betreten: dann '{NO_MOVE}'.\n"
        f"- Bleibt die Gruppe, wo sie ist, oder passt nichts davon: '{NO_MOVE}'.\n"
        f"- Im Zweifel '{NO_MOVE}'.\n"
        'Antworte NUR mit JSON: {"ziel": "<id>"} oder {"ziel": "' + NO_MOVE + '"}.'
    )


def scene_user_msg(turn_text: str) -> str:
    """The single user message: the turn that was just narrated."""
    return f"Zuletzt erzählter Zug:\n{turn_text.strip()}"


def to_scene_verdict(data: object, *, exits: ExitsArg, raw: str = "") -> SceneVerdict:
    """Validate the parsed verdict against the offered choice — this is where code decides, not
    the model. Matching is case-insensitive and tolerates stray quotes/whitespace, but never
    matches partially: ``"schrein — Schrein"`` is off-list, because guessing which half was meant
    is how a wrong pointer gets written."""
    if not isinstance(data, dict) or "ziel" not in data:
        log.info("scene-router: discarded a malformed verdict: %r", data)
        return SceneVerdict(raw=raw, failure=SceneFailure.BAD_JSON)
    value = data.get("ziel")
    if not isinstance(value, str):
        log.info("scene-router: discarded a non-string target: %r", value)
        return SceneVerdict(raw=raw, failure=SceneFailure.BAD_JSON)
    target = value.strip().strip('"').strip("'").strip()
    if not target:
        log.info("scene-router: discarded an empty target")
        return SceneVerdict(raw=raw, failure=SceneFailure.EMPTY)
    if target.casefold() == NO_MOVE.casefold():
        return SceneVerdict(raw=raw)
    for e in normalize_exits(exits):
        if target.casefold() == e.id.casefold():
            return SceneVerdict(target_id=e.id, raw=raw)
    log.warning(
        "scene-router: target %r is not one of the reachable exits %s — discarded",
        target, [e.id for e in normalize_exits(exits)],
    )
    return SceneVerdict(raw=raw, failure=SceneFailure.OFF_LIST)


async def classify_scene_move(
    chat: ChatFn,
    *,
    turn_text: str,
    exits: ExitsArg,
    current_title: str = "",
    timeout: float | None = SCENE_ROUTER_TIMEOUT,
) -> SceneVerdict:
    """Ask the one question and return a validated verdict. Never raises.

    ``chat`` is :meth:`dmbot.llm.client.LLMClient.chat` (injected so the contract is testable
    without a model). ``turn_text`` is the answer that was just narrated — the DM's own words are
    the authority on where the group is; the caller may prefix the player lines.
    """
    offered = normalize_exits(exits)
    if not offered:
        log.debug("scene-router: skipped — the current scene has no reachable exit")
        return SceneVerdict(failure=SceneFailure.NO_EXITS)
    if not turn_text.strip():
        log.debug("scene-router: skipped — nothing was narrated this turn")
        return SceneVerdict(failure=SceneFailure.NO_INPUT)
    schema = scene_schema(offered)
    system = scene_system(offered, current_title=current_title)
    coro = chat(
        system,
        [{"role": "user", "content": scene_user_msg(turn_text)}],
        options=dict(SCENE_ROUTER_OPTIONS),
        format=schema,
    )
    try:
        raw = await (asyncio.wait_for(coro, timeout) if timeout else coro)
    except TimeoutError:  # asyncio.TimeoutError is this since 3.11; a real cancel stays uncaught
        log.warning("scene-router: no verdict within %ss — the scene stays put", timeout)
        return SceneVerdict(failure=SceneFailure.TIMEOUT)
    except Exception:
        log.exception("scene-router: classification call failed — the scene stays put")
        return SceneVerdict(failure=SceneFailure.CALL_FAILED)
    raw = raw or ""
    if not raw.strip():
        log.info("scene-router: empty answer — the scene stays put")
        return SceneVerdict(raw=raw, failure=SceneFailure.EMPTY)
    try:
        data = json.loads(raw)
    except Exception:
        log.warning("scene-router: unparseable verdict %r — the scene stays put", raw[:120])
        return SceneVerdict(raw=raw, failure=SceneFailure.BAD_JSON)
    return to_scene_verdict(data, exits=offered, raw=raw)
