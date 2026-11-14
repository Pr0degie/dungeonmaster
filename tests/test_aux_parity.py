"""The replay-parity tool for the combined post-turn call (ADR 066 step 4) — with fakes only.

The tool's value rests on two things: it asks both paths exactly what the runtime would ask
(the questions come from the runtime's own builder), and it flags the three things ADR 066
forbids — another verdict on a positive, a new positive on an empty turn, a malformed combined
answer. A fake model that answers by the schema it is handed drives both.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dmbot.memory.state import Combatant, WorldState
from dmbot.tools import aux_parity
from dmbot.tools.aux_parity import (
    ParityCase,
    calls_needed,
    case_from_spec,
    cases_from_file,
    cases_from_journal,
    judge,
    merge_cases,
    report,
    run_all,
)

REPO = Path(__file__).resolve().parents[1]
ANSWER = "Die Tür schwingt auf, ihr tretet in den Schrein. Eine Schwester fährt herum."


def _state_dict(scene_id: str = "zollhaus") -> dict:
    state = WorldState(session_id="7", scene_id=scene_id)
    state.characters = [Combatant(name="Fridolin Feuchtgebietheld", wounds=10, max_wounds=10)]
    state.place_npc("Seneschall Bramwell Kaad", "zollhaus", wounds=8)
    return state.to_dict()


def _journal(tmp_path: Path) -> Path:
    note = {"raw": "{}", "verdict": "", "failure": None}
    records = [
        {"kind": "session", "ts": "t0", "profile": "imperium_maledictum",
         "adventure": "debug-kampagne"},
        {"ts": "t1", "answer": "Kaad schiebt euch die Akte hin.", "lines": [],
         "state_before": _state_dict(), "scene_router": note,
         "facts": {"raw": "{}", "verdict": {"kind": "item"}, "failure": None},
         "npcs": {"raw": "{}", "verdict": [], "failure": None}},
        {"ts": "t2", "answer": "Ein Nachtrag ohne Notizen.", "lines": []},
        {"ts": "t3", "answer": ANSWER, "lines": [["Fridolin Feuchtgebietheld", "Geh rein!"]],
         "state_before": _state_dict(), "scene_router": note, "facts": note,
         "npcs": {"raw": "{}", "verdict": [{"label": "Schwester"}], "failure": None}},
    ]
    path = tmp_path / "history.debug.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records),
                    encoding="utf-8")
    return path


def test_journal_cases_are_built_by_the_runtimes_own_question_builder(tmp_path) -> None:
    cases = cases_from_journal(_journal(tmp_path))

    assert [c.id for c in cases] == ["history.debug#1", "history.debug#3"]
    first, second = cases
    assert first.expected == {"scene": "", "fact": "item", "npc": 0}
    assert second.expected == {"scene": "", "fact": "", "npc": 1}
    scene = second.questions["scene"]
    assert scene["exits"] == {"schrein": "Schrein der Aschenheiligen"}
    # The context is the previous record's answer plus this turn's lines — as _scene_context has it.
    assert scene["context"] == ("Spielleitung: Ein Nachtrag ohne Notizen.\n"
                                "Fridolin Feuchtgebietheld: Geh rein!")
    npc = second.questions["npc"]
    assert npc["present"] == ["Seneschall Bramwell Kaad"]
    assert "Schwester Cassia Vall" in [c.name for c in npc["candidates"]]
    assert second.questions["fact"]["recipients"] == ["Fridolin Feuchtgebietheld"]


def test_a_spec_case_places_the_present_people_in_its_scene() -> None:
    case = case_from_spec({
        "id": "x", "adventure": "debug-kampagne", "scene_id": "pfandhalle",
        "party": ["Fridolin Feuchtgebietheld"], "present": ["Bree Marlok"],
        "previous": "Davor.", "lines": [], "answer": ANSWER, "expected": {"npc": 1},
    })
    assert case.questions["npc"]["present"] == ["Bree Marlok"]
    assert case.questions["scene"]["exits"] == {"lagerhaus": "Zwischenlager am Schwarzkanal"}
    assert case.expected == {"npc": 1}


def test_the_committed_positives_file_loads_and_fits_the_call_budget() -> None:
    cases = cases_from_file(REPO / "tests" / "aux_parity" / "log_positives.jsonl")
    assert len(cases) >= 9
    assert all(set(c.questions) == {"scene", "fact", "npc"} for c in cases)
    assert calls_needed(cases) == 4 * len(cases)


def test_positives_win_over_the_journal_turn_with_the_same_answer(tmp_path) -> None:
    journal = cases_from_journal(_journal(tmp_path))
    positive = ParityCase("pos", "log", journal[1].questions, {"npc": 1})
    assert [c.id for c in merge_cases([positive], journal)] == ["pos", "history.debug#1"]


# ---- running both paths against a fake model ---------------------------------------------------

def _model(*, scene="nein", art="nichts", npcs=(), combined_extra_npc=False, broken=False):
    """A chat that answers by the schema it is handed — like a model that decides the same
    either way, unless told to differ on the combined call."""

    async def chat(system, messages, *, options=None, format=None):
        fields = list(format["properties"])
        answer: dict = {}
        if "ziel" in fields:
            answer["ziel"] = scene
        if "art" in fields:
            answer.update({"art": art, "sache": "Akte" if art != "nichts" else "", "an": "",
                           "von": ""})
        if "npcs" in fields:
            people = [{"label": n, "statblock": ""} for n in npcs]
            if combined_extra_npc and len(fields) > 1:
                people.append({"label": "Hafenarbeiter", "statblock": ""})
            answer["npcs"] = people
        if broken and len(fields) > 1:
            answer.pop("npcs", None)
        return json.dumps(answer, ensure_ascii=False)

    return chat


def _case(expected=None) -> ParityCase:
    return case_from_spec({
        "id": "c1", "adventure": "debug-kampagne", "scene_id": "zollhaus",
        "party": ["Fridolin Feuchtgebietheld"], "present": ["Seneschall Bramwell Kaad"],
        "answer": ANSWER, "expected": expected or {"scene": "schrein", "fact": "", "npc": 1},
    })


def test_the_same_decisions_both_ways_hold_parity() -> None:
    results = asyncio.run(run_all(_model(scene="schrein", npcs=("Schreinschwester",)), [_case()]))
    verdict = judge(results)
    assert verdict.holds and verdict.agreements == verdict.questions == 3
    assert verdict.positives == 2
    # "Schreinschwester" is Schwester Cassia Vall by her role — the identity is compared.
    npc_row = next(k for k in results[0].kinds if k.kind == "npc")
    assert npc_row.separate == npc_row.combined == "Schwester Cassia Vall"
    assert report(results)[-1].endswith("HOLDS (ADR 066 step 4)")


def test_a_new_positive_on_an_empty_turn_breaks_parity() -> None:
    case = _case({"scene": "", "fact": "", "npc": 0})
    verdict = judge(asyncio.run(run_all(_model(combined_extra_npc=True), [case])))
    assert verdict.new_positives == ["c1 npc"] and not verdict.holds


def test_a_malformed_combined_answer_breaks_parity() -> None:
    verdict = judge(asyncio.run(run_all(_model(broken=True), [_case()])))
    assert verdict.malformed == ["c1 npc"] and not verdict.holds


def test_without_live_nothing_is_called(capsys, tmp_path, monkeypatch) -> None:
    def no_model():
        raise AssertionError("the dry run must not build a client")

    monkeypatch.setattr(aux_parity, "_claude_chat", no_model)
    code = aux_parity.main(["--journal", str(_journal(tmp_path))])
    assert code == 0
    assert "2 cases (0 from case files), 8 calls" in capsys.readouterr().out
