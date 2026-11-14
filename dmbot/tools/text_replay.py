"""Replay six turns of the 2026-11-14 evening through the narration model with other personas —
``uv run python -m dmbot.tools.text_replay``.

The question it answers: what does a change to ``prompts/dm_core_de.md`` do to the shape of a
spoken turn (length, sentence length, cuts) — measured on real turns before a table hears it.
Background and the first measurements: ``docs/plans/textvergleich-2026-11-14.md``.

The session journal of that evening is gone, so the inputs are rebuilt from ``logs/debug-d1.log``
(git-ignored; the tool needs that file): the player lines and the spoken answers become the
history, the dice lines and the world-state events of the evening (:data:`EVENTS`) are written
down here, and the prompt blocks come from the runtime's own builders
(``PersistenceMixin._persist_and_refresh``). Each turn then runs through
:meth:`DMBrain.respond_streaming` and a bare :class:`ClaudeClient` — the path a turn takes at the
table, without the failover (a failure must show). Only the persona file differs per variant; the
file in ``prompts/`` is never written (a running bot reads it on every turn).

    uv run python -m dmbot.tools.text_replay dry
        # no model call: the rebuilt inputs of all turns, the six replayed ones marked
    uv run python -m dmbot.tools.text_replay run heute=HEAD kurz=path/to/dm_core_variant.md
        # six calls per variant; a variant is <label>=<git commit> or <label>=<persona file>
    uv run python -m dmbot.tools.text_replay show
        # the numbers of everything in the results file, no model call

``run`` appends to ``--out`` (default: ``text_replay.json`` in the system temp dir) and skips a
variant/turn that is already in it, so an interrupted run costs no call twice. ``--num-predict``
overrides ``DM_NUM_PREDICT``. The numbers: characters per answer, sentences, characters per
sentence (the split of the report: a sentence ends at ``.!?…`` or a closing quote before a
capital), answers cut at the spoken budget.

Limits: one sample per turn and variant — differences of a few dozen characters are scatter; all
six turns lie before the evening's auto-recap (19:20), whose text was never logged.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import logging
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CID = 1  # one synthetic channel — every replayed turn gets a fresh brain
DEFAULT_LOG = REPO_ROOT / "logs" / "debug-d1.log"
DEFAULT_SHEET = REPO_ROOT / "data" / "sessions" / "1343673766487654464" / "characters.json"
DEFAULT_OUT = Path(tempfile.gettempdir()) / "text_replay.json"

# Display name in the log → the character the line was buffered under (identity by Discord id).
SPEAKERS = {"Pr0degie": "Fridolin Feuchtgebietheld", "Sezgin": "Rektalus Zerfickus"}
# The replayed turns, by the log time of their answer, and what kind of turn each is.
REPLAY = {
    "19:07:12": "Erste Begegnung", "19:09:14": "Probe misslungen", "19:10:05": "Probe gelungen",
    "19:11:39": "Ankunft", "19:15:01": "Gespräch", "19:19:06": "Offener Moment",
}
LAST = max(REPLAY)
# Dice lines the model was fed, by the time of the answer that narrated them (dicecog's lines).
DICE = {
    "19:09:14": ["🙏 Fridolin Feuchtgebietheld gibt einen Schicksalspunkt aus (noch 2) und würfelt neu "
                 "— dieses Ergebnis gilt: 🎲 Fridolin Feuchtgebietheld auf Überreden, Herausfordernd "
                 "(Ziel 42): 88 — Fehlschlag, 4 EG."],
    "19:10:05": ["🎲 Fridolin Feuchtgebietheld auf Überreden, Herausfordernd (Ziel 42): 26 — Erfolg, 2 EG."],
}
# What the log shows happening to the world state, by the time of the answer it followed
# (``fate`` is spent before the answer that narrates the reroll).
EVENTS = {
    "19:04:30": [("item", "Auftragspergament mit Inquisitionssiegel", "Seneschall Bramwell Kaad")],
    "19:05:57": [("scene", "schrein")],
    "19:11:39": [("resolved", "schrein", "vall-gestaendnis"),
                 ("sighting", "Person hinter dem Sehschlitz", "schrein")],
    "19:12:46": [("scene", "pfandhalle")],
}
FATE_BEFORE = {"19:09:14": "Fridolin Feuchtgebietheld"}

_ENTRY = re.compile(r"^\d\d:\d\d:\d\d (?:DEBUG|INFO|WARNING|ERROR|CRITICAL)")
_MARKER = re.compile(r"\s*`?<<[^>]*>>?`?")
_SENTENCE_GAP = re.compile(r"(?<=[.!?…“\"])\s+(?=[A-ZÄÖÜ„])")


def log_entries(text: str) -> list[str]:
    """The log's entries, one string each — an answer with a paragraph break is logged over
    several lines, and read line by line it would lose everything after the break."""
    entries: list[str] = []
    for line in text.splitlines():
        if _ENTRY.match(line) or not entries:
            entries.append(line)
        elif line.strip():
            entries[-1] += " " + line.strip()
    return entries


def parse_turns(text: str, *, until: str = LAST) -> list[dict]:
    """The evening's DM turns up to ``until``: the player lines that led to each answer, the raw
    answer and what was spoken. Pure."""
    turns: list[dict] = []
    buffered: list[tuple[str, str]] = []
    for entry in log_entries(text):
        body = entry.split(" | ", 1)[1] if " | " in entry else ""
        if "📝" in entry and "→DM | " in entry:
            who = body.split("📝 ", 1)[1].split(" |", 1)[0].strip()
            buffered.append((SPEAKERS.get(who, who), entry.split("→DM | ", 1)[1].strip()))
        elif "LLM roh" in entry:
            if entry[:8] > until:
                break
            turns.append({"t": entry[:8], "lines": buffered, "raw": body.split("): ", 1)[1], "spoken": ""})
            buffered = []
        elif "voice.delivery | 🎭" in entry and turns:
            turns[-1]["spoken"] = body[2:].strip()
    return turns


def sentences(answer: str) -> list[str]:
    """The answer's sentences, markers removed — the measure the report's numbers use."""
    return [s for s in _SENTENCE_GAP.split(_MARKER.sub("", answer or "").strip()) if s.strip()]


def measure(answers: list[str], cut: int | str = 0) -> dict:
    """The numbers of one variant over its answers. Pure."""
    lengths = [len(a) for a in answers]
    per_sentence = [len(s) for a in answers for s in sentences(a)]
    return {
        "answers": len(answers),
        "chars_mean": round(statistics.mean(lengths)) if lengths else 0,
        "chars_max": max(lengths, default=0),
        "over_600": sum(n > 600 for n in lengths),
        "sentences": len(per_sentence),
        "sentence_mean": round(statistics.mean(per_sentence)) if per_sentence else 0,
        "sentence_median": round(statistics.median(per_sentence)) if per_sentence else 0,
        "sentences_200": sum(n >= 200 for n in per_sentence),
        "cut": cut,
    }


def user_message(turn: dict, *, opening: bool) -> str:
    """The turn's user message as ``DMBrain._prepare_turn`` composes it."""
    from ..llm.director_msgs import OPENING_DIRECTOR_MSG
    from ..llm.echo_guard import _ROLL_DIRECTIVE

    if opening:
        return OPENING_DIRECTOR_MSG
    dice = DICE.get(turn["t"], [])
    parts = [f"[Würfel] {line}" for line in dice] + [f"{name}: {text}" for name, text in turn["lines"]]
    if dice and not turn["lines"]:
        parts.append(_ROLL_DIRECTIVE)
    return "\n".join(parts)


class _Blocks:
    """Stands where the runtime expects the brain and keeps the prompt blocks it is handed."""

    def __init__(self) -> None:
        self.blocks: dict[str, str] = {}

    def set_context(self, _cid: int, **blocks: str) -> None:
        self.blocks = blocks

    def add_gm_note(self, _cid: int, _note: str) -> None:
        pass


def _runtime(config, sheet: Path, workdir: Path):
    """The runtime's prompt-context half without Discord, on a freshly seeded world state."""
    from ..memory.state import WorldState
    from ..rag.adventure import Adventure
    from ..rules import profile as profile_mod
    from ..rules.characters import CharacterStore
    from ..session.clocks import ClocksMixin
    from ..session.npcs import NpcMemoryMixin
    from ..session.persistence import PersistenceMixin
    from ..session.scenes import SceneFlowMixin
    from ..session.seeding import SeedingMixin

    class Runtime(ClocksMixin, NpcMemoryMixin, PersistenceMixin, SceneFlowMixin, SeedingMixin):
        def _brain_channel(self, _channel) -> int:
            return CID

        def _state_path(self, _cid: int) -> Path:
            return workdir / "state.json"

        def _chekhov_path(self, _cid: int) -> Path:
            return workdir / "chekhov.json"

    rt = Runtime()
    rt._profile = profile_mod.load(config.system)
    rt._characters = CharacterStore.load(sheet)
    rt._adventure = Adventure.load(profile_mod.systems_dir().parent / "adventures" / config.adventure)
    rt._brain = _Blocks()
    rt._scene_turns, rt._chekhov_lists = {CID: 0}, {}
    rt._clocks, rt._guidance_every = False, config.guidance_every
    rt._npc_memory, rt._npc_memory_top_k = False, 6
    rt._active_vc_id = CID
    state = WorldState.seed_from_store(rt._characters, system=rt._profile.name, session_id="text-replay")
    state.start_fate_session(default=rt._profile.fate_start())
    state.scene_id = rt._adventure.start_scene
    rt._state = {CID: state}
    rt._seed_adventure_state(state)
    return rt


def _apply(rt, event: tuple) -> None:
    state = rt._state[CID]
    kind = event[0]
    if kind == "item":
        state.give_item(event[1], to="Gruppe", by=event[2])
    elif kind == "scene":
        state.scene_id = event[1]
        state.advance_scene_change()
        rt._scene_turns[CID] = 0
        rt._register_scene_npcs(state, rt._adventure.get_scene(event[1]))
    elif kind == "resolved":
        state.mark_resolved(event[1], event[2])
    elif kind == "sighting":
        state.place_npc(event[1], event[2], wounds=10)


def build_contexts(turns: list[dict], config, sheet: Path, workdir: Path):
    """Walk the evening's events and give every turn the prompt blocks it was answered with.
    Returns the runtime (profile and party are read from it)."""
    rt = _runtime(config, sheet, workdir)
    state = rt._state[CID]
    for turn in turns:
        if turn["t"] in FATE_BEFORE:
            state.spend_fate(FATE_BEFORE[turn["t"]])
        rt._persist_and_refresh(None)
        turn["blocks"] = dict(rt._brain.blocks)
        rt._scene_turns[CID] += 1
        state.advance_turn()
        for event in EVENTS.get(turn["t"], []):
            _apply(rt, event)
    return rt


def persona_text(source: str) -> str:
    """``source`` is a persona file, or a git commit whose ``prompts/dm_core_de.md`` is meant."""
    path = Path(source)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    shown = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{source}:prompts/dm_core_de.md"],
        capture_output=True, check=True,
    )
    return shown.stdout.decode("utf-8")


async def _run(args, config, turns: list[dict], rt) -> dict:
    from .. import orchestrator
    from ..llm.claude_client import ClaudeClient
    from ..llm.persona import load_system_prompt
    from ..rag.retrieve import RulebookRetriever
    from ..rules import profile as profile_mod

    results = json.loads(args.out.read_text(encoding="utf-8")) if args.out.is_file() else {}
    num_predict = args.num_predict or config.dm_num_predict
    retriever = RulebookRetriever(profile_mod.systems_dir().parent / "vectordb" / "rag.db",
                                  host=config.ollama_host, session_memory=False)
    client = ClaudeClient(
        narration_model=config.claude_model_narration, aux_model=config.claude_model_aux,
        num_ctx=config.claude_num_ctx, cli_path=config.claude_cli_path or None,
        allow_api_key=config.claude_allow_api_key, app_version="text-replay",
    )
    stock = orchestrator.load_system_prompt
    core = Path(tempfile.mkdtemp(prefix="text_replay_")) / "dm_core_de.md"
    try:
        for variant in args.variants:
            label, _, source = variant.partition("=")
            core.write_text(persona_text(source or label), encoding="utf-8", newline="")
            orchestrator.load_system_prompt = functools.partial(load_system_prompt, core_path=core)
            for index, turn in enumerate(turns):
                key = f"{label}@{turn['t']}"
                if turn["t"] not in REPLAY or key in results:
                    continue
                brain = orchestrator.DMBrain(client, profile=rt._profile, num_predict=num_predict,
                                             retriever=retriever if retriever.available() else None)
                brain.set_known_speakers(CID, rt._characters.speaker_labels())
                brain.set_alias_hint(CID, rt._characters.alias_hint_de(with_mapping=False))
                brain.set_context(CID, **turn["blocks"])
                history = brain._session(CID).history
                for before, earlier in enumerate(turns[:index]):
                    history.append({"role": "user", "content": user_message(earlier, opening=before == 0)})
                    history.append({"role": "assistant", "content": earlier["spoken"]})
                for name, text in turn["lines"]:
                    brain.add_player_line(CID, name, text)
                for line in DICE.get(turn["t"], []):
                    brain.add_test_result(CID, line)

                async def on_sentence(_sentence: str) -> None:
                    return None

                answer = await brain.respond_streaming(CID, on_sentence=on_sentence) or ""
                stats = client.last_stats or {}
                results[key] = {
                    "variant": label, "persona": source or label, "t": turn["t"],
                    "num_predict": num_predict, "answer": answer,
                    "truncated": bool(stats.get("truncated")),
                    "prompt_tokens": stats.get("prompt_eval_count"),
                    "thinking": stats.get("thinking"),
                }
                args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"{key}: {len(answer)} Zeichen, {len(sentences(answer))} Sätze"
                      + (", abgeschnitten" if results[key]["truncated"] else ""), flush=True)
    finally:
        orchestrator.load_system_prompt = stock
        await client.aclose()
        await retriever.aclose()
    return results


def report(results: dict, turns: list[dict]) -> list[str]:
    """One line per variant (the evening's own answers first), then one per turn."""
    spoken = {turn["t"]: turn["spoken"] for turn in turns}
    variants: dict[str, dict[str, dict]] = {}
    for entry in results.values():
        variants.setdefault(entry["variant"], {})[entry["t"]] = entry
    lines = ["Variante             Antw.  Zeichen (Mittel/längste)  über 600  Sätze  Zeichen je Satz (Mittel/Median)  ab 200  abgeschnitten"]

    def row(label: str, m: dict) -> str:
        return (f"{label:20} {m['answers']:5}  {m['chars_mean']:6} / {m['chars_max']:<15}  {m['over_600']:8}  "
                f"{m['sentences']:5}  {m['sentence_mean']:6} / {m['sentence_median']:<22}  {m['sentences_200']:6}  {m['cut']}")

    # The evening's own answers: whether one was cut is in its ✂ log line, not read here.
    lines.append(row("Original 14.11.", measure([spoken[t] for t in REPLAY if t in spoken], cut="–")))
    for label, by_turn in variants.items():
        answers = [by_turn[t]["answer"] for t in REPLAY if t in by_turn]
        lines.append(row(label, measure(answers, sum(by_turn[t]["truncated"] for t in by_turn))))
    lines.append("")
    for t, kind in REPLAY.items():
        cells = [f"{label}: {len(by_turn[t]['answer'])}/{len(sentences(by_turn[t]['answer']))}"
                 + ("✂" if by_turn[t]["truncated"] else "")
                 for label, by_turn in variants.items() if t in by_turn]
        lines.append(f"{t} {kind:17} Original: {len(spoken.get(t, ''))}/{len(sentences(spoken.get(t, '')))}  "
                     + "  ".join(cells) + "   (Zeichen/Sätze)")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="text_replay", description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("mode", choices=("dry", "run", "show"))
    parser.add_argument("variants", nargs="*", help="run: <label>=<git commit | persona file>")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="the evening's debug log")
    parser.add_argument("--sheet", type=Path, default=DEFAULT_SHEET, help="the party's characters.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="results file (appended to)")
    parser.add_argument("--num-predict", type=int, default=0, help="spoken budget (default: DM_NUM_PREDICT)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not args.log.is_file():
        print(f"[text-replay] log not found: {args.log}")
        return 2
    turns = parse_turns(args.log.read_text(encoding="utf-8", errors="replace"))
    if args.mode == "show":
        results = json.loads(args.out.read_text(encoding="utf-8")) if args.out.is_file() else {}
        print("\n".join(report(results, turns)))
        return 0

    from ..config import Config

    config = Config.load()
    logging.basicConfig(level=logging.WARNING)
    with tempfile.TemporaryDirectory(prefix="text_replay_state_") as workdir:
        rt = build_contexts(turns, config, args.sheet, Path(workdir))
    if args.mode == "dry":
        for index, turn in enumerate(turns):
            blocks = turn["blocks"]
            mark = f"   <== {REPLAY[turn['t']]}" if turn["t"] in REPLAY else ""
            print(f"--- {turn['t']}  Weltzustand {len(blocks.get('state_summary', ''))} / "
                  f"Abenteuer {len(blocks.get('adventure_block', ''))} Zeichen{mark}")
            print(user_message(turn, opening=index == 0))
        print(f"\n{len(REPLAY)} Aufrufe je Variante; Budget {args.num_predict or config.dm_num_predict}, "
              f"Modell {config.claude_model_narration}.")
        return 0
    if not args.variants:
        parser.error("run needs at least one <label>=<git commit | persona file>")
    results = asyncio.run(_run(args, config, turns, rt))
    print()
    print("\n".join(report(results, turns)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
