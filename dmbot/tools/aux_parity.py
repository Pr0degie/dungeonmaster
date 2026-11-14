"""Replay parity for the combined post-turn classifier call (ADR 066, step 4) —
``uv run python -m dmbot.tools.aux_parity``.

Before the one combined call of option B may replace the three separate post-turn calls on
Claude, both paths answer the same recorded turns and the verdicts are compared. A turn is a
:class:`ParityCase`: the three question sets exactly as the runtime builds them (through the
runtime's own builder, :meth:`dmbot.session.scenes.SceneFlowMixin._post_turn_questions`) plus
the verdicts the recording holds. Cases come from two sources:

- a **replay journal** (``history*.jsonl``, ADR 046): every turn record with post-turn notes,
  its questions rebuilt from ``state_before``, the previous record's answer and its own player
  lines; the recorded verdicts are the record's ``scene_router`` / ``facts`` / ``npcs`` notes.
  (Caveat seen while building this: when two turns overlap, a turn's notes can land in the next
  record or be overwritten — the recorded column is informational, the parity is separate
  against combined.)
- a **case file** (JSONL, one :func:`case_from_spec` record per line) — the positives found in
  the debug logs, whose journals are gone, written down with the state they were classified in.

Each case is asked twice, through the separate classifiers and through the combined call
(without its fallback: the combined answer itself is under test). Verdicts are compared in a
normalised form (:func:`normalise`): the scene's target, the commitment's kind, and the people a
presence verdict names — each as the scene-card person code identifies it, else ``*``.

Required for B (ADR 066 step 4): the same verdict on every positive, no new positive on a turn
that was empty, no malformed combined answer. Exit 0 = all three hold, 1 = not, 2 = unusable
input. Without ``--live`` nothing is called: the cases and the number of calls are printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..llm.fact_router import classify_commitment
from ..llm.npc_router import card_person, classify_present_npcs
from ..llm.post_turn import POST_TURN_KINDS, classify_post_turn
from ..llm.scene_router import classify_scene_move
from ..memory.state import WorldState
from ..rag.adventure import Adventure
from ..session.npcs import NpcMemoryMixin
from ..session.scenes import SceneFlowMixin

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

ChatFn = Callable[..., Awaitable[str]]

_SEPARATE = {
    "scene": classify_scene_move,
    "fact": classify_commitment,
    "npc": classify_present_npcs,
}


class ParityInputError(Exception):
    """A journal or case file that cannot be turned into cases — exit 2, never a traceback."""


# ---- building the questions the runtime way ------------------------------------------------


class _Names:
    def __init__(self, names: Iterable[str]) -> None:
        self._names = [n for n in names if n]

    def character_names(self) -> list[str]:
        return list(self._names)


class _QuestionBuilder(SceneFlowMixin, NpcMemoryMixin):
    """Just enough of a runtime to call its own question builder: the adventure, the party and
    the three layer switches (all on), plus the scene context's previous narration and lines."""

    def __init__(self, adventure: Adventure | None, party: Iterable[str]) -> None:
        self._adventure = adventure
        self._characters = _Names(party)
        self._scene_router = True
        self._fact_router = True
        self._npc_router = True
        self._last_narration: dict[int, str] = {}
        self._lines: list[tuple[str, str]] = []
        self._brain = SimpleNamespace(last_actions=lambda _cid: list(self._lines))

    def questions(self, state: WorldState, answer: str, *, previous: str = "",
                  lines: Iterable[Iterable[str]] = ()) -> dict[str, dict]:
        self._last_narration = {0: previous}
        self._lines = [(str(n), str(t)) for n, t in (tuple(x)[:2] for x in lines)]
        context = self._scene_context(0, answer)
        return self._post_turn_questions(state, answer, context=context)


# ---- cases ---------------------------------------------------------------------------------


@dataclass
class ParityCase:
    """One turn to ask both ways. ``expected`` holds the recorded verdict per kind in
    :func:`normalise` form for the scene and the fact, and the number of sightings for the
    presence classifier (the recording has labels, not identities); a kind without a recorded
    verdict is missing."""

    id: str
    source: str
    questions: dict[str, dict]
    expected: dict[str, Any] = field(default_factory=dict)


def load_adventure(adventure_id: str) -> Adventure | None:
    directory = REPO_ROOT / "data" / "adventures" / adventure_id
    return Adventure.load(directory) if adventure_id and directory.is_dir() else None


def _recorded(record: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    scene, facts, npcs = record.get("scene_router"), record.get("facts"), record.get("npcs")
    if isinstance(scene, dict) and not scene.get("failure"):
        out["scene"] = str(scene.get("verdict") or "")
    if isinstance(facts, dict) and not facts.get("failure"):
        verdict = facts.get("verdict")
        out["fact"] = str(verdict.get("kind") or "") if isinstance(verdict, dict) else ""
    if isinstance(npcs, dict) and not npcs.get("failure"):
        out["npc"] = len(npcs.get("verdict") or [])
    return out


def cases_from_journal(path: Path, *, adventure: Adventure | None = None) -> list[ParityCase]:
    """Every turn record of a replay journal that carries post-turn notes, as a case."""
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ParityInputError(f"{path}: {exc}") from exc
    if adventure is None:
        header = next((r for r in records if r.get("kind") == "session"), {})
        adventure = load_adventure(str(header.get("adventure") or ""))
    cases: list[ParityCase] = []
    previous = ""
    for number, record in enumerate(records):
        if "answer" not in record:
            continue
        answer = str(record.get("answer") or "")
        state_before = record.get("state_before")
        has_notes = any(isinstance(record.get(k), dict) for k in ("scene_router", "facts", "npcs"))
        if has_notes and isinstance(state_before, dict) and answer.strip():
            state = WorldState.from_dict(state_before)
            builder = _QuestionBuilder(adventure, [c.name for c in state.characters])
            cases.append(ParityCase(
                id=f"{path.stem}#{number}",
                source=f"{path.name} {record.get('ts', '')}",
                questions=builder.questions(state, answer, previous=previous,
                                            lines=record.get("lines") or ()),
                expected=_recorded(record),
            ))
        previous = answer
    return cases


def case_from_spec(spec: dict, *, adventures: dict[str, Adventure | None] | None = None,
                   ) -> ParityCase:
    """A case written down by hand from a log: ``id``, ``source``, ``adventure``, ``scene_id``,
    ``party``, ``present`` (people registered in that scene), optional ``resolved`` (scene flags)
    — or, instead of ``scene_id``/``present``/``resolved``, a whole ``state`` (a journal's
    ``state_before``) —
    ``previous`` (the narration before), ``lines`` (``[[speaker, text]]``), ``answer`` and
    ``expected`` (``scene`` target or "", ``fact`` kind or "", ``npc`` count of sightings)."""
    try:
        adventure_id = str(spec.get("adventure") or "")
        cache = adventures if adventures is not None else {}
        if adventure_id not in cache:
            cache[adventure_id] = load_adventure(adventure_id)
        adventure = cache[adventure_id]
        party = [str(p) for p in spec.get("party") or []]
        if isinstance(spec.get("state"), dict):  # a journal's state_before, taken as it is
            state = WorldState.from_dict(spec["state"])
        else:
            state = WorldState(session_id="parity")
            state.scene_id = str(spec["scene_id"])
            for name in spec.get("present") or []:
                state.place_npc(str(name), state.scene_id, wounds=1)
            for scene_id, ids in (spec.get("resolved") or {}).items():
                state.scene_flags[str(scene_id)] = [str(i) for i in ids]
        builder = _QuestionBuilder(adventure, party)
        questions = builder.questions(state, str(spec["answer"]),
                                      previous=str(spec.get("previous") or ""),
                                      lines=spec.get("lines") or ())
        return ParityCase(id=str(spec["id"]), source=str(spec.get("source") or ""),
                          questions=questions, expected=dict(spec.get("expected") or {}))
    except (KeyError, TypeError, ValueError) as exc:
        raise ParityInputError(f"case {spec.get('id', '?')}: {exc!r}") from exc


def cases_from_file(path: Path) -> list[ParityCase]:
    try:
        specs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("//")]
    except (OSError, json.JSONDecodeError) as exc:
        raise ParityInputError(f"{path}: {exc}") from exc
    adventures: dict[str, Adventure | None] = {}
    return [case_from_spec(spec, adventures=adventures) for spec in specs]


def merge_cases(positives: list[ParityCase], journal: list[ParityCase]) -> list[ParityCase]:
    """The positives first, then the journal turns whose answer no positive already carries."""
    seen = {_answer(c) for c in positives}
    return [*positives, *(c for c in journal if _answer(c) not in seen)]


def _answer(case: ParityCase) -> str:
    for kind, key in (("scene", "turn_text"), ("fact", "answer_text"), ("npc", "answer_text")):
        if kind in case.questions:
            return str(case.questions[kind].get(key) or "").strip()
    return ""


# ---- normalised verdicts and the comparison ------------------------------------------------


def normalise(kind: str, verdict: Any, question: dict | None = None) -> str:
    """One comparable string per verdict: ``"!<failure>"`` for a degraded answer, ``""`` for
    "nothing happened", else the scene id, the commitment kind, or the people named — each as
    the card person code identifies (:func:`card_person`), else ``*`` — sorted, comma-joined."""
    if verdict is None:
        return "!missing"
    failure = getattr(verdict, "failure", None)
    if failure is not None:
        return f"!{failure.value}"
    if kind == "scene":
        return verdict.target_id
    if kind == "fact":
        return verdict.commitment.kind if verdict.commitment is not None else ""
    candidates = (question or {}).get("candidates") or ()
    return ",".join(sorted(card_person(s, candidates) or "*" for s in verdict.sightings))


def _positive(value: Any) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        return value > 0
    return bool(value) and not str(value).startswith("!")


@dataclass
class KindResult:
    kind: str
    recorded: Any
    separate: str
    combined: str
    separate_label: str = ""
    combined_label: str = ""

    @property
    def agrees(self) -> bool:
        return self.separate == self.combined

    @property
    def positive(self) -> bool:
        """A positive in the sense of ADR 066 step 4: recorded or decided by the separate call."""
        return _positive(self.recorded) or _positive(self.separate)

    @property
    def new_positive(self) -> bool:
        """The combined call reports something on a turn the recording and the separate call
        both found empty."""
        return (_positive(self.combined) and not _positive(self.separate)
                and not _positive(self.recorded))


@dataclass
class CaseResult:
    case: ParityCase
    kinds: list[KindResult]
    combined_raw: str = ""
    malformed: tuple[str, ...] = ()
    combined_failure: str | None = None


def _labels(kind: str, verdict: Any) -> str:
    if kind == "npc" and verdict is not None and getattr(verdict, "failure", None) is None:
        return ", ".join(s.label for s in verdict.sightings)
    if kind == "fact" and verdict is not None and getattr(verdict, "commitment", None):
        return verdict.commitment.text
    return ""


async def run_case(chat: ChatFn, case: ParityCase) -> CaseResult:
    """Ask one case both ways — the separate calls side by side, then the combined call."""
    kinds = [k for k in POST_TURN_KINDS if k in case.questions]
    separate = await asyncio.gather(*(_SEPARATE[k](chat, **case.questions[k]) for k in kinds))
    combined = await classify_post_turn(chat, **case.questions)
    rows = []
    for kind, verdict in zip(kinds, separate):
        question = case.questions[kind]
        other = combined.verdicts.get(kind)
        rows.append(KindResult(
            kind=kind,
            recorded=case.expected.get(kind),
            separate=normalise(kind, verdict, question),
            combined=normalise(kind, other, question) if kind not in combined.retry
            else (f"!{combined.failure.value}" if combined.failure else "!malformed"),
            separate_label=_labels(kind, verdict),
            combined_label=_labels(kind, other),
        ))
    malformed = combined.retry if combined.failure is None or combined.asked else ()
    return CaseResult(case=case, kinds=rows, combined_raw=combined.raw,
                      malformed=tuple(malformed),
                      combined_failure=combined.failure.value if combined.failure else None)


async def run_all(chat: ChatFn, cases: list[ParityCase], *, concurrency: int = 3,
                  progress: Callable[[CaseResult], None] | None = None) -> list[CaseResult]:
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(case: ParityCase) -> CaseResult:
        async with gate:
            result = await run_case(chat, case)
        if progress is not None:
            progress(result)
        return result

    return list(await asyncio.gather(*(one(c) for c in cases)))


def calls_needed(cases: list[ParityCase]) -> int:
    """Separate calls (one per asked question) plus one combined call per case."""
    return sum(len(c.questions) + 1 for c in cases)


@dataclass
class Verdict:
    cases: int
    questions: int
    agreements: int
    positives: int
    positive_mismatches: list[str]
    new_positives: list[str]
    malformed: list[str]

    @property
    def holds(self) -> bool:
        return not (self.positive_mismatches or self.new_positives or self.malformed)


def judge(results: list[CaseResult]) -> Verdict:
    rows = [(r, k) for r in results for k in r.kinds]
    return Verdict(
        cases=len(results),
        questions=len(rows),
        agreements=sum(k.agrees for _, k in rows),
        positives=sum(k.positive for _, k in rows),
        positive_mismatches=[f"{r.case.id} {k.kind}" for r, k in rows
                             if k.positive and not k.agrees],
        new_positives=[f"{r.case.id} {k.kind}" for r, k in rows if k.new_positive],
        malformed=[f"{r.case.id} {','.join(r.malformed) or r.combined_failure}"
                   for r in results if r.malformed],
    )


def report(results: list[CaseResult]) -> list[str]:
    out = ["[parity] case | kind | recorded | separate | combined"]
    for r in results:
        for k in r.kinds:
            mark = "  " if k.agrees else "≠ "
            labels = ""
            if k.separate_label or k.combined_label:
                labels = f"  ({k.separate_label or '—'} / {k.combined_label or '—'})"
            out.append(f"{mark}{r.case.id} | {k.kind} | {k.recorded!s:>4} | "
                       f"{k.separate or '∅'} | {k.combined or '∅'}{labels}")
    v = judge(results)
    out += [
        f"[parity] {v.cases} turns, {v.questions} questions, "
        f"{v.agreements}/{v.questions} verdicts agree, {v.positives} positives",
        f"[parity] positives with another combined verdict: {', '.join(v.positive_mismatches) or 'none'}",
        f"[parity] new positives on empty turns: {', '.join(v.new_positives) or 'none'}",
        f"[parity] malformed combined answers: {', '.join(v.malformed) or 'none'}",
        f"[parity] {'HOLDS' if v.holds else 'DOES NOT HOLD'} (ADR 066 step 4)",
    ]
    return out


# ---- command line --------------------------------------------------------------------------


def _claude_chat():
    """The real aux tier: a bare :class:`ClaudeClient` (no failover — a failure must show)."""
    import os

    from ..llm.claude_client import ClaudeClient

    client = ClaudeClient(aux_model=os.environ.get("CLAUDE_MODEL_AUX", "haiku").strip() or "haiku",
                          cli_path=os.environ.get("CLAUDE_CLI_PATH", "").strip() or None)
    return client


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="aux_parity",
        description="Replay parity: three separate post-turn calls vs one combined (ADR 066).",
    )
    parser.add_argument("--journal", type=Path, action="append", default=[],
                        help="a replay journal (history*.jsonl); repeatable")
    parser.add_argument("--cases", type=Path, action="append", default=[],
                        help="a case file (JSONL, see case_from_spec); repeatable")
    parser.add_argument("--limit", type=int, default=0, help="at most this many cases (0 = all)")
    parser.add_argument("--live", action="store_true",
                        help="ask the real aux model (Claude); without it nothing is called")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--out", type=Path, help="write the per-case results as JSONL here")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s | %(message)s")
    try:
        positives = [c for path in args.cases for c in cases_from_file(path)]
        journal = [c for path in args.journal for c in cases_from_journal(path)]
    except ParityInputError as exc:
        print(f"[parity] unusable input: {exc}")
        return 2
    cases = merge_cases(positives, journal)
    if args.limit:
        cases = cases[:args.limit]
    print(f"[parity] {len(cases)} cases ({len(positives)} from case files), "
          f"{calls_needed(cases)} calls")
    if not args.live:
        for case in cases:
            print(f"  {case.id} | {', '.join(case.questions)} | recorded {case.expected}")
        return 0
    client = _claude_chat()

    def progress(result: CaseResult) -> None:
        print(f"  … {result.case.id}: " + " ".join(
            f"{k.kind}={k.separate or '∅'}/{k.combined or '∅'}" for k in result.kinds),
            flush=True)

    async def go() -> list[CaseResult]:
        try:
            return await run_all(client.chat, cases, concurrency=args.concurrency,
                                 progress=progress)
        finally:
            await client.aclose()

    results = asyncio.run(go())
    order = {c.id: i for i, c in enumerate(cases)}
    results.sort(key=lambda r: order[r.case.id])
    for line in report(results):
        print(line)
    if args.out:
        with args.out.open("w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps({
                    "id": r.case.id, "source": r.case.source, "combined_raw": r.combined_raw,
                    "malformed": list(r.malformed), "failure": r.combined_failure,
                    "kinds": [{"kind": k.kind, "recorded": k.recorded, "separate": k.separate,
                               "combined": k.combined, "separate_label": k.separate_label,
                               "combined_label": k.combined_label} for k in r.kinds],
                }, ensure_ascii=False) + "\n")
    return 0 if judge(results).holds else 1


if __name__ == "__main__":
    raise SystemExit(main())
