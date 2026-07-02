"""Validate an adventure-compendium draft against the real loader (dmbot.rag.adventure).

Usage:  uv run python .claude/skills/author-adventure/validate.py <adventure-id-or-path>

Part of the /author-adventure skill (pass 5). Imports ``Adventure.load`` instead of
re-implementing schema knowledge, and adds the checks the loader itself only logs or
silently tolerates: scene-id collisions (dict collapse), dangling ``leads_to`` targets,
missing ``start_scene``, statblock coverage of ``npcs_here``, and the tracked-path guard
(bought-book derivatives must never land in git). Exit code 0 = draft loads clean.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dmbot.rag.adventure import Adventure  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    arg = sys.argv[1]
    directory = Path(arg) if "/" in arg or "\\" in arg else REPO_ROOT / "data" / "adventures" / arg
    adv_path = directory / "adventure.json"
    errors: list[str] = []
    warnings: list[str] = []

    # -- tracked-path guard (hard rule 4): the draft must be git-ignored ------------------
    ignored = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", str(adv_path)],
        check=False,
    ).returncode == 0
    if not ignored:
        print(f"ABORT: {adv_path} would be TRACKED by git — bought-book derivatives must stay local.")
        return 1

    if not adv_path.is_file():
        print(f"ABORT: no adventure.json under {directory}")
        return 1

    # -- raw-JSON checks the loader tolerates silently ------------------------------------
    raw = json.loads(adv_path.read_text(encoding="utf-8"))
    raw_scenes = raw.get("scenes", []) or []
    raw_ids = [str(s.get("id", "") or "") for s in raw_scenes]
    dupes = {i for i in raw_ids if raw_ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate scene ids (collapse silently in the loader): {sorted(dupes)}")
    if "" in raw_ids:
        errors.append("scene with empty id (dropped silently by the loader)")

    # -- load through the real parser, capturing its ERROR logs ---------------------------
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record))

    handler = _Capture(level=logging.WARNING)
    logging.getLogger("dmbot.rag.adventure").addHandler(handler)
    try:
        adv = Adventure.load(directory)
    finally:
        logging.getLogger("dmbot.rag.adventure").removeHandler(handler)
    if adv is None:
        print(f"ABORT: Adventure.load returned None for {directory} (broken JSON?)")
        return 1
    errors.extend(f"loader log: {r}" for r in records)

    # -- referential integrity -------------------------------------------------------------
    known = {sid for _, sid, _ in adv.scene_overview()}
    if not adv.start_scene:
        errors.append("no start_scene (and no scenes to default to)")
    elif adv.start_scene not in known:
        errors.append(f"start_scene '{adv.start_scene}' is not a known scene id")
    if not (adv.summary_de or "").strip():
        errors.append("summary_de is empty — stage 1 of the prompt block would be blank")

    statblocks_missing: list[str] = []
    for _, sid, _ in adv.scene_overview():
        scene = adv.get_scene(sid)
        assert scene is not None
        for target in scene.leads_to:
            if target not in known:
                errors.append(f"scene '{sid}': leads_to '{target}' is not a known scene id")
        for target in scene.exit_requires:
            if target not in scene.leads_to:
                errors.append(f"scene '{sid}': gate on '{target}' which is not in leads_to")
        if not scene.description_de.strip():
            warnings.append(f"scene '{sid}': empty description_de")
        for name in scene.npcs_here:
            if adv.npc(name) is None:
                statblocks_missing.append(f"{name} (in '{sid}')")
    # unreachable scenes (ignoring gates; frei mode reaches everything, still worth a note)
    raw_reachable = {adv.start_scene}
    frontier = [adv.start_scene]
    while frontier:
        s = adv.get_scene(frontier.pop())
        if s is None:
            continue
        for t in s.leads_to:
            if t in known and t not in raw_reachable:
                raw_reachable.add(t)
                frontier.append(t)
    unreachable = known - raw_reachable
    if unreachable:
        warnings.append(f"scenes unreachable from start via leads_to: {sorted(unreachable)}")
    if statblocks_missing:
        warnings.append(
            "npcs_here without a statblock in npcs.json (narrative-only? checklist item): "
            + ", ".join(statblocks_missing)
        )
    # gated exits: report for the human (gate targets are hidden until unlocked)
    for _, sid, _ in adv.scene_overview():
        scene = adv.get_scene(sid)
        for ziel, req in (scene.exit_requires or {}).items():
            # ASCII only: the Windows console is cp1252 (repo gotcha — no fancy arrows)
            print(f"  gate: {sid} -> {ziel} requires '{req}'")

    print(f"loaded: {adv.title or adv.id} — {len(known)} scenes, {adv.npc_count()} statblocks, "
          f"start='{adv.start_scene}'")
    for w in warnings:
        print(f"  WARN: {w}")
    for e in errors:
        print(f"  ERROR: {e}")
    print("RESULT: " + ("FAIL" if errors else "OK"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
