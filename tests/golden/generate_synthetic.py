"""Regenerate the synthetic goldens (the bless step for tests/golden/, ADR 046).

The two committed goldens are built here through the REAL capture path — ``DMBrain`` with a
``PlaybackClient``, ``take_replay_turn``/``last_router``, and the same verdict functions the
live delivery pipeline uses — so their record shape can't drift from what the autosave writes.

Run it only when a pipeline behaviour change is *intended* (marker grammar, sanitizer, router
parsing, verdict rules): ``uv run python tests/golden/generate_synthetic.py``, then READ the
git diff of the .jsonl files — every changed line is a behaviour change you are blessing.
Goldens pulled from live sessions are re-recorded live instead (see README.md).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dmbot.memory.state import WorldState
from dmbot.orchestrator import DMBrain
from dmbot.rag.adventure import Adventure
from dmbot.rules import profile as profile_mod
from dmbot.rules.marker import ErledigtRequest
from dmbot.tools.eval_replay import PlaybackClient
from dmbot.voice.delivery import erledigt_verdict

HERE = Path(__file__).resolve().parent
TS = "2026-07-03T12:00:00"  # fixed stamp — goldens must diff cleanly across regenerations
CID = 1


def _header(*, profile: str = "", adventure: str = "", adventure_path: str = "",
            scene_mode: str = "verbunden") -> dict:
    rec = {"kind": "session", "ts": TS, "profile": profile, "adventure": adventure,
           "scene_mode": scene_mode}
    if adventure_path:
        rec["adventure_path"] = adventure_path  # goldens resolve fixtures relative to themselves
    return rec


def _drain(brain: DMBrain) -> None:
    """What the cogs do after a turn: drain the pending queues (buttons/proposals)."""
    brain.take_pending_tests(CID)
    brain.take_pending_manifests(CID)
    brain.take_pending_scenes(CID)
    brain.take_pending_erledigt(CID)


async def _play_turn(brain: DMBrain, client: PlaybackClient, raw: str, *,
                     lines: list[tuple[str, str]] = (), results: list[str] = ()) -> dict:
    """One captured turn record, exactly as ``_autosave_turn`` would write it."""
    for name, text in lines:
        brain.add_player_line(CID, name, text)
    for line in results:
        brain.add_test_result(CID, line)
    client.load([raw])
    answer = await brain.respond(CID)
    assert answer, "synthetic turn came back empty — echo guard fired on the scripted raw?"
    record = brain.take_replay_turn(CID) or {}
    record.update({"ts": TS, "user_msg": brain.last_user_msg(CID), "answer": answer,
                   "redo": False})
    _drain(brain)
    return record


async def build_dice_flow() -> list[dict]:
    """Golden 1: the dice conversation loop — marker parse, router verdict, results-only
    suppression. No adventure, so no state category."""
    profile = profile_mod.load("imperium_maledictum")
    client = PlaybackClient()
    brain = DMBrain(client, profile=profile)
    records: list[dict] = [_header(profile="imperium_maledictum")]

    # Turn 1 — a player action; the narration model also emits an inline <<TEST>> marker.
    action = "Ich schleiche mich an den Wachposten heran."
    rec = await _play_turn(
        brain, client,
        "Der Nebel liegt schwer über dem Hof, als du dich Stück für Stück an den Wachposten "
        "heranschiebst. Seine Laterne schwenkt träge hin und her. "
        "<<TEST Heimlichkeit Herausfordernd für Tobi>>",
        lines=[("Tobi", action)],
    )
    # The dice cog then classifies the action (ADR 014) — capture the router verdict.
    skills = ["Heimlichkeit", "Athletik", "Wahrnehmung"]
    client.load([json.dumps(
        {"needs_test": True, "skill": "Heimlichkeit", "difficulty": "Herausfordernd"}
    )])
    req = await brain.classify_test(action=action, character="Tobi", skills=skills)
    assert req is not None and brain.last_router is not None
    rec["router"] = {"action": action, "character": "Tobi", "skills": skills,
                     **brain.last_router}
    records.append(rec)

    # Turn 2 — results-only consequence narration: an inline marker MUST be suppressed.
    rec = await _play_turn(
        brain, client,
        "Die Wache bemerkt nichts; du gleitest lautlos an ihr vorbei in den Schatten der "
        "Mauer. <<TEST Wahrnehmung für Tobi>>",
        results=["🎲 Heimlichkeit (Herausfordernd): 27 gegen 45 — Erfolg (SL +1)"],
    )
    records.append(rec)

    # Turn 3 — plain narration, no markers, router said "no test".
    action = "Ich sehe mich im Hof um."
    rec = await _play_turn(
        brain, client,
        "Zwischen den Kisten stapeln sich leere Promethium-Fässer; irgendwo tropft Wasser "
        "auf Blech.",
        lines=[("Tobi", action)],
    )
    client.load([json.dumps({"needs_test": False, "skill": "", "difficulty": ""})])
    req = await brain.classify_test(action=action, character="Tobi", skills=skills)
    assert req is None and brain.last_router is not None
    rec["router"] = {"action": action, "character": "Tobi", "skills": skills,
                     **brain.last_router}
    records.append(rec)
    return records


async def build_scene_flags() -> list[dict]:
    """Golden 2: scene-move + element-flag verdicts against the fixture adventure — one
    accepted move + valid flag, then a gated move + unknown flag (both rejected)."""
    profile = profile_mod.load("imperium_maledictum")
    adventure = Adventure.load(HERE / "fixtures" / "mini_adventure")
    assert adventure is not None, "fixture adventure failed to load"
    client = PlaybackClient()
    brain = DMBrain(client, profile=profile)
    state = WorldState(system="imperium_maledictum", session_id="golden", scene_id="tor")
    records: list[dict] = [_header(
        profile="imperium_maledictum", adventure="mini_adventure",
        adventure_path="fixtures/mini_adventure",
    )]

    def verdicts_for(rec: dict) -> None:
        """What the delivery pipeline notes for this turn: the state snapshot + the scene/flag
        verdicts, computed by the same functions it uses live (resolve_move/erledigt_verdict)."""
        rec["state_before"] = state.to_dict()
        scenes = rec.get("markers", {}).get("scenes") or []
        if scenes:
            requested = scenes[0]["scene_id"]
            target = adventure.resolve_move(
                state.scene_id, requested, "verbunden",
                resolved_ids=state.resolved_ids(state.scene_id),
            )
            rec["scene_verdict"] = {"requested": requested, "accepted": target is not None,
                                    "mode": "verbunden"}
        erledigt = rec.get("markers", {}).get("erledigt") or []
        if erledigt:
            scene = adventure.get_scene(state.scene_id)
            valid = set(scene.element_ids())
            already = set(state.resolved_ids(scene.id))
            seen: set[str] = set()
            out = []
            for d in erledigt:
                r = ErledigtRequest(**d)
                v = erledigt_verdict(r, valid=valid, already=already, seen=seen)
                if v == "ok":
                    seen.add(r.element_id)
                out.append({"id": r.element_id or r.raw,
                            "verdict": "proposed" if v == "ok" else "rejected"})
            rec["flag_verdicts"] = out

    # Turn 1 — valid flag + a legal neighbour move (halle is in tor's leads_to, ungated).
    rec = await _play_turn(
        brain, client,
        "Ihr lenkt die Wache mit dem Scheppern einer leeren Konserve ab und schlüpft durch "
        "das Tor in die Halle. <<ERLEDIGT opp-wache>> <<ORT halle>>",
        lines=[("Timo", "Wir lenken die Wache ab und gehen durch das Tor.")],
    )
    verdicts_for(rec)
    records.append(rec)

    # Turn 2 — a gated move (krypta requires geh-tunnel, unresolved) + an unknown flag id:
    # both must be rejected. state_before still has scene_id "tor" — the proposed move above
    # was confirm-gated and (in this synthetic session) never clicked.
    rec = await _play_turn(
        brain, client,
        "Von der Krypta trennt euch mehr als eine Tür — der Weg hinab ist euch noch nicht "
        "bekannt. <<ORT krypta>> <<ERLEDIGT geh-quatsch>>",
        lines=[("Timo", "Wir steigen sofort in die Krypta hinab!")],
    )
    verdicts_for(rec)
    records.append(rec)
    return records


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    print(f"wrote {path} ({len(records)} records)")


def main() -> None:
    _write(HERE / "dice_flow.jsonl", asyncio.run(build_dice_flow()))
    _write(HERE / "scene_flags.jsonl", asyncio.run(build_scene_flags()))


if __name__ == "__main__":
    main()
