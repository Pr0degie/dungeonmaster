"""RAG calibration (Prompt 5): golden-set eval + MAX_DISTANCE sweep against the EXISTING store.

    uv run python tools/rag_calibrate.py

Measures what the bot actually does — it imports `dmbot/rag/retrieve.py` and reuses the real
`RulebookRetriever._embed_query` + `_search` (bge-m3 via Ollama, sqlite-vec KNN over
`data/vectordb/rag.db`); it does NOT reimplement retrieval. Reads the golden set from
`tools/rag_golden_set.json` (own German questions + expected source/heading keyword — no rulebook
passages). Reports per-query hits, recall@1/@3, a threshold sweep per retrieval context, and a
failure analysis, to stdout and to `tools/rag_calibrate_report.md` (gitignored). Only
source/heading/distance are printed — never chunk text — so the report carries no rulebook prose.

No pipeline change: this is measurement. Tuning `MAX_DISTANCE` / the `!rules`/`!lore` ceilings is a
separate, deliberate edit informed by the numbers here (ADR 019 anticipated live tuning).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, so `dmbot` imports
try:
    sys.stdout.reconfigure(encoding="utf-8")  # the report has ✓/→/…; survive a cp1252 console
except Exception:
    pass

from dmbot.rag import retrieve as R  # noqa: E402 (after the path insert)

GOLDEN = Path("tools/rag_golden_set.json")
DB = Path("data/vectordb/rag.db")
REPORT = Path("tools/rag_calibrate_report.md")
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
TOPK = 5  # over-fetch per query for the analysis (the bot uses TOP_K=3 / k=2/3)
SWEEP = [round(0.35 + 0.025 * i, 3) for i in range(11)]  # 0.35 … 0.60

# The retrieval contexts the bot runs, each with its current ceiling (the thing we calibrate).
CONTEXTS = {
    "narration  (fetch_block, ALL sources)": {"sources": tuple(R._SOURCES), "cur": R.MAX_DISTANCE},
    "!rules     (rulebook+conditions+player_guide+gm_guide)": {
        "sources": ("rulebook", "conditions", "player_guide", "gm_guide"), "cur": 0.55},
}

_out_lines: list[str] = []


def emit(line: str = "") -> None:
    print(line)
    _out_lines.append(line)


def _is_correct(hit: tuple, pos: dict) -> bool:
    s, h, _t, _d = hit
    return s in pos["sources"] and pos["heading"].lower() in h.lower()


async def _hits_per_context(retr, query: str) -> dict[str, list[tuple]]:
    """Embed once, then KNN per context (each filters its own sources)."""
    vector = await retr._embed_query(query)
    out = {}
    for name, ctx in CONTEXTS.items():
        out[name] = retr._search(vector, ctx["sources"], TOPK)
    return out


async def main() -> int:
    if not DB.is_file():
        emit(f"[!!] no store at {DB}")
        return 1
    gs = json.loads(GOLDEN.read_text(encoding="utf-8"))
    positives, negatives = gs["positives"], gs["negatives"]
    retr = R.RulebookRetriever(DB, host=HOST)

    # --- gather hits -------------------------------------------------------------------------
    pos_hits = [await _hits_per_context(retr, p["q"]) for p in positives]
    neg_hits = [await _hits_per_context(retr, q) for q in negatives]
    await retr.aclose()

    emit("# RAG calibration report")
    emit(f"\nStore: {DB} · contexts: {', '.join(CONTEXTS)} · positives: {len(positives)} · "
         f"negatives: {len(negatives)} · top-{TOPK} per query\n")

    # --- per-positive recall (strict: expected source AND heading keyword) -------------------
    emit("## Positives — recall (strict = expected source + heading keyword)\n")
    emit("Context evaluated: !rules sources (the rules corpora). 'r@1/r@3' = correct hit in top-1/3.")
    emit("")
    emit("| # | Frage | r@1 | r@3 | bester Treffer (Quelle/Heading @ Distanz) |")
    emit("|---|---|---|---|---|")
    rules_ctx = next(k for k in CONTEXTS if k.startswith("!rules"))
    recall1 = recall3 = 0
    for i, (p, hits_by_ctx) in enumerate(zip(positives, pos_hits), 1):
        hits = hits_by_ctx[rules_ctx]
        r1 = bool(hits) and _is_correct(hits[0], p)
        r3 = any(_is_correct(h, p) for h in hits[:3])
        recall1 += r1
        recall3 += r3
        top = f"{hits[0][0]}/{hits[0][1][:26]} @ {hits[0][3]:.3f}" if hits else "—"
        tag = " ⚠table" if p.get("class") == "table" else ""
        emit(f"| {i} | {p['q'][:48]}{tag} | {'✓' if r1 else '·'} | {'✓' if r3 else '·'} | {top} |")
    n = len(positives)
    emit(f"\n**recall@1 = {recall1}/{n} ({recall1/n:.0%}) · recall@3 = {recall3}/{n} ({recall3/n:.0%})**\n")

    # --- threshold sweep per context --------------------------------------------------------
    for name, ctx in CONTEXTS.items():
        cur = ctx["cur"]
        emit(f"## Sweep — {name}  (aktuell: {cur})\n")
        emit("`pos✓` = Positive mit KORREKTEM Treffer ≤ T · `posAny` = Positive mit IRGENDEINEM "
             "Treffer ≤ T · `negLeak` = Negative mit Treffer ≤ T (→ leakt in den Prompt)\n")
        emit("| T | pos✓ | posAny | negLeak |")
        emit("|---|---|---|---|")
        for t in SWEEP:
            pc = pa = 0
            for p, hbc in zip(positives, pos_hits):
                hits = hbc[name]
                if hits and hits[0][3] <= t:
                    pa += 1
                if any(_is_correct(h, p) and h[3] <= t for h in hits):
                    pc += 1
            nl = sum(1 for hbc in neg_hits if hbc[name] and hbc[name][0][3] <= t)
            mark = "  ← aktuell" if abs(t - cur) < 1e-6 else ""
            emit(f"| {t:.3f} | {pc}/{len(positives)} | {pa}/{len(positives)} | "
                 f"{nl}/{len(negatives)} |{mark}")
        emit("")

    # --- failure analysis (missed positives = no correct hit in top-3, !rules ctx) ----------
    emit("## Verpasste Positives (kein korrekter Treffer in Top-3, !rules-Kontext)\n")
    misses = 0
    for i, (p, hbc) in enumerate(zip(positives, pos_hits), 1):
        hits = hbc[rules_ctx]
        if any(_is_correct(h, p) for h in hits[:3]):
            continue
        misses += 1
        tag = " ⚠table" if p.get("class") == "table" else ""
        emit(f"- **{i}. {p['q']}**{tag} (erwartet: {p['sources']} / `{p['heading']}`)")
        for h in hits[:3]:
            emit(f"    - {h[0]}/{h[1][:34]} @ {h[3]:.3f}")
    if not misses:
        emit("_(keine — alle Positives haben einen korrekten Top-3-Treffer)_")
    emit("")

    # --- negatives: best-hit distance (narration is the every-turn gate) --------------------
    nar_ctx = "narration  (fetch_block, ALL sources)"
    emit("## Negatives — bester Treffer-Abstand (narration-Kontext; muss > Schwelle bleiben)\n")
    emit("| Eingabe | bester Treffer (Quelle/Heading) | Distanz |")
    emit("|---|---|---|")
    for q, hbc in zip(negatives, neg_hits):
        hits = hbc[nar_ctx]
        best = f"{hits[0][0]}/{hits[0][1][:24]}" if hits else "—"
        d = f"{hits[0][3]:.3f}" if hits else "—"
        emit(f"| {q[:46]} | {best} | {d} |")
    emit("")

    REPORT.write_text("\n".join(_out_lines) + "\n", encoding="utf-8")
    print(f"\n[OK] report → {REPORT} (gitignored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
