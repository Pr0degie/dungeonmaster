"""Golden-transcript replay harness — ``uv run dm-eval`` (ADR 046).

Plays recorded sessions (the extended ``history.jsonl`` replay journals, trimmed into goldens
under ``tests/golden/``) back through the deterministic pipeline with the LLM mocked: a
:class:`PlaybackClient` returns each turn's recorded raw response, and the harness diffs what
today's code makes of it against what the recorded session saw — the composed turn input, the
sanitised answer, the parsed markers, the roll router's decision and the scene/flag verdicts.
**Regression, not quality:** the model's prose is frozen; only the machinery around it is
measured. Timing, audio and prompt content are deliberately out of scope (ADR 046).

Report + exit contract (the ``dm-sync`` pattern, D89/D90): a compact ``[eval]`` block, one line
per deviation (``Turn <n> <kategorie>: Soll … → Ist …``); exit 0 = green, 1 = deviations,
2 = unusable transcript (pre-ADR-046 journal, broken JSON, unknown profile).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..memory.state import WorldState
from ..orchestrator import DMBrain
from ..rag.adventure import Adventure
from ..rules import profile as profile_mod
from ..rules.marker import ErledigtRequest
from ..rules.profile import ProfileError
from ..voice.delivery import erledigt_verdict

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"

# One synthetic channel id per replayed file — the brain is fresh per golden, the id is arbitrary.
_CID = 1

_LABEL_WIDTH = 10

# The marker categories a turn records/queues, in report order (mirrors _markers_dict).
_MARKER_KEYS = ("tests", "manifests", "scenes", "erledigt")


class TranscriptError(Exception):
    """The golden can't be replayed (broken JSON, pre-ADR-046 record, unknown profile) —
    reported as a clean ``[eval]`` error + exit 2, never a traceback."""


class PlaybackExhausted(RuntimeError):
    """The replayed turn asked the LLM more often than the recording holds (e.g. an echo-guard
    retry that didn't fire live) — surfaces as an ``llm`` deviation, not a crash."""


class PlaybackClient:
    """Stands in for ``OllamaClient``: hands out the recorded raw responses in call order.

    Batch-only by design (ADR 046): the harness replays every turn through ``respond()`` /
    ``respond_opening()``; stream-recorded turns rely on the ADR-017 ``finalize_answer`` parity."""

    def __init__(self) -> None:
        self._queue: list[str] = []
        self.calls = 0
        self.last_stats: dict | None = None

    def load(self, responses: list[str]) -> None:
        self._queue = list(responses)
        self.calls = 0

    @property
    def unused(self) -> int:
        return len(self._queue)

    async def chat(self, system, messages, *, options=None, format=None) -> str:
        self.calls += 1
        if not self._queue:
            raise PlaybackExhausted(f"LLM-Aufruf {self.calls} — keine aufgezeichnete Antwort mehr")
        return self._queue.pop(0)

    async def chat_stream(self, system, messages, *, options=None):
        raise RuntimeError("replay is batch-only (ADR 046) — chat_stream must never be called")


@dataclass(frozen=True, slots=True)
class Deviation:
    """One Soll≠Ist finding: the report line ``Turn <n> <kategorie>: Soll … → Ist …``."""

    turn: int
    category: str  # turn | answer | marker | router | state | llm
    soll: str
    ist: str


@dataclass
class FileResult:
    """Everything one golden produced: deviations (gate-relevant) + notes (skipped checks)."""

    path: Path
    turns: int = 0
    deviations: list[Deviation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _short(value: object, limit: int = 90) -> str:
    """Compact one-line rendering for a report side; long answers are elided, not dumped."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace("\n", "⏎")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _jsonable(value: object) -> object:
    """Normalise for comparison: everything through JSON, so tuples/lists and recorded (JSON)
    vs replayed (dataclass→asdict) shapes can't differ on type alone."""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


# ---- loading ---------------------------------------------------------------------------------


def load_golden(path: Path) -> tuple[dict, list[dict]]:
    """Parse a golden journal into ``(session header, turn records)``.

    Mirrors ``load_recent``'s tolerance shape but is strict where replay needs it: broken JSON,
    a missing session header or a turn without replay fields (``raw``) is a
    :class:`TranscriptError` (old pre-ADR-046 journals are refused, not crashed on). ``redo``
    records replace the prior turn (same semantics as the crash restore); suppressed turns
    (empty answer — never entered history live) are dropped."""
    if not path.is_file():
        raise TranscriptError(f"{path}: Datei fehlt")
    header: dict | None = None
    turns: list[dict] = []
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            rec = json.loads(raw_line)
        except ValueError as exc:
            raise TranscriptError(f"{path.name}: Zeile {lineno} ist kein JSON ({exc})") from exc
        if not isinstance(rec, dict):
            raise TranscriptError(f"{path.name}: Zeile {lineno} ist kein Objekt")
        kind = rec.get("kind")
        if kind == "session":
            if header is None:
                header = rec
            continue  # later rejoin headers: first one wins (README: trim goldens to one)
        if kind is not None:
            continue  # unknown typed events: tolerated like load_recent tolerates extras
        if rec.get("user_msg") is None or rec.get("answer") is None:
            raise TranscriptError(f"{path.name}: Zeile {lineno} ist weder Header noch Turn")
        if not str(rec.get("answer", "")).strip():
            continue  # a suppressed turn never entered history live — nothing to replay against
        if rec.get("redo") and turns:
            turns[-1] = rec
        else:
            turns.append(rec)
    if header is None:
        raise TranscriptError(
            f"{path.name}: kein Session-Header — Journal stammt aus einer Zeit vor ADR 046; "
            "Golden aus einer frischen Session ziehen"
        )
    if not turns:
        raise TranscriptError(f"{path.name}: keine Turns")
    for i, turn in enumerate(turns, start=1):
        if not isinstance(turn.get("raw"), str) or not turn["raw"]:
            raise TranscriptError(
                f"{path.name}: Turn {i} ohne 'raw' — Autosave vor ADR 046; Golden neu ziehen"
            )
    return header, turns


def _load_profile(header: dict):
    name = str(header.get("profile", "") or "")
    if not name:
        return None
    try:
        return profile_mod.load(name)
    except ProfileError as exc:
        raise TranscriptError(f"Systemprofil '{name}' nicht ladbar: {exc}") from exc


def _load_adventure(header: dict, golden_path: Path, result: FileResult) -> Adventure | None:
    """The adventure behind the header, or None with a note. ``adventure_path`` (relative to the
    golden file) wins — committable goldens point it at a fixture; a live-pulled golden names
    the real (git-ignored) adventure, which may simply be absent on this machine."""
    rel = str(header.get("adventure_path", "") or "")
    adv_id = str(header.get("adventure", "") or "")
    if rel:
        directory = (golden_path.parent / rel).resolve()
    elif adv_id:
        directory = REPO_ROOT / "data" / "adventures" / adv_id
    else:
        return None
    adventure = Adventure.load(directory) if directory.is_dir() else None
    if adventure is None:
        result.notes.append(
            f"Abenteuer '{adv_id or rel}' nicht gefunden — state-Kategorie übersprungen"
        )
    return adventure


# ---- replay ----------------------------------------------------------------------------------


def _compare(result: FileResult, turn_no: int, category: str, soll: object, ist: object) -> None:
    if _jsonable(soll) != _jsonable(ist):
        result.deviations.append(
            Deviation(turn=turn_no, category=category, soll=_short(soll), ist=_short(ist))
        )


def _replay_state_verdicts(
    result: FileResult, turn_no: int, turn: dict, *,
    adventure: Adventure | None, scene_mode: str, replayed_markers: dict,
) -> None:
    """Re-run the scene-move + element-flag validation (ADR 026/043) against the recorded
    ``state_before`` and compare the verdicts — the deterministic state-machinery decisions.
    Numeric mutations (wounds/warp) are deliberately not replayed (ADR 046)."""
    scene_verdict = turn.get("scene_verdict")
    flag_verdicts = turn.get("flag_verdicts")
    if scene_verdict is None and flag_verdicts is None:
        return
    state_before = turn.get("state_before")
    if adventure is None or state_before is None:
        result.notes.append(f"Turn {turn_no}: state-Vergleich übersprungen (kein Abenteuer/state_before)")
        return
    state = WorldState.from_dict(state_before)
    if scene_verdict is not None:
        scenes = replayed_markers.get("scenes") or []
        requested = scenes[0]["scene_id"] if scenes else str(scene_verdict.get("requested", ""))
        mode = str(scene_verdict.get("mode", "") or scene_mode)
        target = adventure.resolve_move(
            state.scene_id, requested, mode, resolved_ids=state.resolved_ids(state.scene_id)
        )
        _compare(
            result, turn_no, "state",
            {"requested": scene_verdict.get("requested"), "accepted": scene_verdict.get("accepted")},
            {"requested": requested, "accepted": target is not None},
        )
    if flag_verdicts is not None:
        scene = adventure.get_scene(state.scene_id)
        actual: list[dict] = []
        if scene is not None:
            valid = set(scene.element_ids())
            already = set(state.resolved_ids(scene.id))
            seen: set[str] = set()
            for d in replayed_markers.get("erledigt") or []:
                req = ErledigtRequest(**d)
                verdict = erledigt_verdict(req, valid=valid, already=already, seen=seen)
                if verdict == "ok":
                    seen.add(req.element_id)
                actual.append({"id": req.element_id or req.raw, "verdict": verdict})
        # Recorded "proposed"/"applied" both mean the request passed validation — whether it was
        # confirm-gated is a config (DM_FLAG_CONFIRM), not pipeline behaviour to regress on.
        soll = [
            {"id": v.get("id"), "verdict": "rejected" if v.get("verdict") == "rejected" else "ok"}
            for v in flag_verdicts
        ]
        _compare(result, turn_no, "state", soll, actual)


async def _replay_turn(
    result: FileResult, turn_no: int, turn: dict, *,
    brain: DMBrain, client: PlaybackClient, profile, adventure: Adventure | None, scene_mode: str,
) -> None:
    responses = [turn["raw"]]
    router = turn.get("router")
    replay_router = bool(router and router.get("raw") and profile is not None)
    if router and router.get("raw") and profile is None:
        result.notes.append(f"Turn {turn_no}: router-Vergleich übersprungen (kein Profil)")
    if replay_router:
        responses.append(router["raw"])
    client.load(responses)

    try:
        if turn.get("opening"):
            answer = await brain.respond_opening(_CID, turn["user_msg"])
        else:
            for name, text in turn.get("lines") or []:
                brain.add_player_line(_CID, str(name), str(text))
            for line in turn.get("results") or []:
                brain.add_test_result(_CID, str(line))
            answer = await brain.respond(_CID)
    except PlaybackExhausted as exc:
        result.deviations.append(Deviation(
            turn=turn_no, category="llm",
            soll=f"{len(responses)} aufgezeichnete LLM-Antworten",
            ist=f"mehr Aufrufe als aufgezeichnet ({exc}) — Guard-Retry, der live nicht feuerte?",
        ))
        return

    if answer is None:
        result.deviations.append(Deviation(
            turn=turn_no, category="turn", soll=_short(turn["user_msg"]),
            ist="respond() fand nichts zu beantworten (leerer Turn-Input)",
        ))
        return
    _compare(result, turn_no, "turn", turn["user_msg"], brain.last_user_msg(_CID) or "")
    _compare(result, turn_no, "answer", turn["answer"], answer)

    # Markers: what today's parse queued vs the recording. Draining also resets the queues for
    # the next turn (results-only suppression recorded empty lists — compared all the same).
    replayed_markers = {
        "tests": [asdict(r) for r in brain.take_pending_tests(_CID)],
        "manifests": [asdict(r) for r in brain.take_pending_manifests(_CID)],
        "scenes": [asdict(r) for r in brain.take_pending_scenes(_CID)],
        "erledigt": [asdict(r) for r in brain.take_pending_erledigt(_CID)],
    }
    recorded_markers = turn.get("markers")
    if recorded_markers is None:
        result.notes.append(f"Turn {turn_no}: marker-Vergleich übersprungen (nicht aufgezeichnet)")
    else:
        for key in _MARKER_KEYS:
            _compare(
                result, turn_no, "marker",
                {key: recorded_markers.get(key, [])}, {key: replayed_markers[key]},
            )

    if replay_router:
        req = await brain.classify_test(
            action=str(router.get("action", "") or ""),
            character=router.get("character"),
            skills=[str(s) for s in router.get("skills") or []],
        )
        _compare(
            result, turn_no, "router",
            router.get("decision"), asdict(req) if req is not None else None,
        )

    _replay_state_verdicts(
        result, turn_no, turn,
        adventure=adventure, scene_mode=scene_mode, replayed_markers=replayed_markers,
    )

    if client.unused:
        result.deviations.append(Deviation(
            turn=turn_no, category="llm",
            soll=f"{len(responses)} LLM-Aufrufe",
            ist=f"{len(responses) - client.unused} — {client.unused} aufgezeichnete Antworten unverbraucht",
        ))


async def replay_file(path: Path) -> FileResult:
    """Replay one golden end to end: fresh brain + playback client, every turn in order."""
    result = FileResult(path=path)
    header, turns = load_golden(path)
    profile = _load_profile(header)
    adventure = _load_adventure(header, path, result)
    scene_mode = str(header.get("scene_mode", "") or "verbunden")
    client = PlaybackClient()
    brain = DMBrain(client, profile=profile)
    result.turns = len(turns)
    for turn_no, turn in enumerate(turns, start=1):
        await _replay_turn(
            result, turn_no, turn, brain=brain, client=client,
            profile=profile, adventure=adventure, scene_mode=scene_mode,
        )
    return result


# ---- report ----------------------------------------------------------------------------------


def _line(label: str, text: str) -> str:
    return f"[eval] {label:<{_LABEL_WIDTH}}{text}"


def report(result: FileResult) -> list[str]:
    try:
        shown = result.path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        shown = str(result.path)
    lines = [_line("golden", shown), _line("turns", str(result.turns))]
    for note in result.notes:
        lines.append(_line("hinweis", note))
    for dev in result.deviations:
        lines.append(_line("DIFF", f"Turn {dev.turn} {dev.category}: Soll {dev.soll} → Ist {dev.ist}"))
    lines.append(_line(
        "ergebnis",
        "OK — keine Abweichungen" if not result.deviations
        else f"{len(result.deviations)} Abweichung(en)",
    ))
    return lines


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # survive a cp1252 Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.WARNING, format="[eval] %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        prog="dm-eval",
        description="Replay golden transcripts through the deterministic pipeline (ADR 046).",
    )
    parser.add_argument(
        "files", nargs="*", type=Path,
        help=f"golden .jsonl files (default: {GOLDEN_DIR.relative_to(REPO_ROOT).as_posix()}/*.jsonl)",
    )
    args = parser.parse_args()
    files = args.files or sorted(GOLDEN_DIR.glob("*.jsonl"))
    if not files:
        print(_line("FEHLER", f"keine Goldens unter {GOLDEN_DIR}"))
        return 2

    exit_code = 0
    for path in files:
        try:
            result = asyncio.run(replay_file(Path(path)))
        except TranscriptError as exc:
            print(_line("golden", str(path)))
            print(_line("FEHLER", str(exc)))
            exit_code = max(exit_code, 2)
            continue
        for line in report(result):
            print(line)
        if result.deviations:
            exit_code = max(exit_code, 1)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
