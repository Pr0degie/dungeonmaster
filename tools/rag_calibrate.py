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

from dmbot.rag import ingest_session as ING  # noqa: E402 (after the path insert)
from dmbot.rag import retrieve as R  # noqa: E402

GOLDEN = Path("tools/rag_golden_set.json")
DB = Path("data/vectordb/rag.db")
REPORT = Path("tools/rag_calibrate_report.md")
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
TOPK = 5  # over-fetch per query for the analysis (the bot uses TOP_K=3 / k=2/3)
SWEEP = [round(0.35 + 0.025 * i, 3) for i in range(11)]  # 0.35 … 0.60
# Session recall (ADR 054) sweeps its own, tighter band: DE-vs-DE transcript matches score far
# below the DE-vs-EN rulebook case, and SESSION_MAX_DISTANCE starts at 0.38.
SESSION_SWEEP = [round(0.26 + 0.02 * i, 3) for i in range(11)]  # 0.26 … 0.46

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

    await _session_recall_section(gs)

    REPORT.write_text("\n".join(_out_lines) + "\n", encoding="utf-8")
    print(f"\n[OK] report → {REPORT} (gitignored)")
    return 0


async def _session_recall_section(gs: dict) -> None:
    """Campaign-memory recall (ADR 054): sweep ``SESSION_MAX_DISTANCE`` against the
    ``session_recall`` golden section. The committed fixture session is (re)ingested first
    (stamp-idempotent) so the sweep always has a session source; the ``session_fixture``
    source is inert at runtime (retrieval only ever searches the active channel's
    ``session_<channel_id>``)."""
    sr = gs.get("session_recall")
    if not sr:
        return
    src, fixture_dir = sr["source"], Path(sr["fixture_dir"])
    for f in sorted(fixture_dir.glob("history.*.jsonl")):
        ING.ingest_session_file(f, channel_id=fixture_dir.name, db_path=DB, host=HOST)
    retr = R.RulebookRetriever(DB, host=HOST)
    conn = R._vec_conn(DB)

    async def probe(q: str):
        vector = await retr._embed_query(q)
        # raw distances over the separate session vec table, no malus/threshold
        knn = retr._knn_sessions(conn, vector, src, TOPK)  # (id, scene, text, stamp, dist)
        fts = retr._fts_session_hits(conn, q, src)
        return knn, fts

    pos = [(p, *(await probe(p["q"]))) for p in sr["positives"]]
    neg = [(q, *(await probe(q))) for q in sr["negatives"]]
    await retr.aclose()

    import re as _re
    live = [
        s for (s,) in conn.execute(
            "SELECT DISTINCT source FROM chunks WHERE source LIKE 'session_%'"
        ) if _re.fullmatch(r"session_\d+", s)
    ]

    emit(f"## Session-Recall (ADR 054) — Quelle `{src}`  (aktuell: {R.SESSION_MAX_DISTANCE})\n")
    if not live:
        emit("_Hinweis: keine echten rotierten Sessions im Store — Sweep laeuft gegen die "
             "Fixture-Session; **Live-Tuning steht noch aus**._\n")
    emit("| Frage | bester Treffer korrekt? | Distanz | FTS-Treffer |")
    emit("|---|---|---|---|")

    def _ok(hits, match):  # 'match' = lowercased substring expected in the hit text
        return any(match in t.lower() for _, _, t, _, _ in hits)

    for p, knn, fts in pos:
        d = f"{knn[0][4]:.3f}" if knn else "—"
        fts_ok = any(p["match"] in text.lower() for _, _, text, _ in fts)
        emit(f"| {p['q'][:44]} | {'✓' if _ok(knn[:2], p['match']) else '·'} | {d} | "
             f"{'✓' if fts_ok else '·'} |")
    emit("")
    emit("| T | pos✓KNN (nur KNN ≤ T) | pos✓ (KNN ≤ T oder FTS) | negLeak (KNN ≤ T oder FTS) |")
    emit("|---|---|---|---|")
    for t in SESSION_SWEEP:
        def _knn_ok(p, knn, t=t):
            return any(p["match"] in txt.lower() and d <= t for _, _, txt, _, d in knn[:2])

        pk = sum(1 for p, knn, _ in pos if _knn_ok(p, knn))
        pc = sum(
            1 for p, knn, fts in pos
            if _knn_ok(p, knn) or any(p["match"] in txt.lower() for _, _, txt, _ in fts)
        )
        nl = sum(1 for _, knn, fts in neg if (knn and knn[0][4] <= t) or fts)
        mark = "  ← aktuell" if abs(t - R.SESSION_MAX_DISTANCE) < 1e-6 else ""
        emit(f"| {t:.3f} | {pk}/{len(pos)} | {pc}/{len(pos)} | {nl}/{len(neg)} |{mark}")
    emit("")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
