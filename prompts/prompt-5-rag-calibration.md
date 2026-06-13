# RAG calibration: golden-set eval + MAX_DISTANCE tuning against the EXISTING store

Session ritual first (CLAUDE.md). This replaces the old "which embedder" question — that's
**decided and built** (ADR 019: bge-m3, sqlite-vec, heading-aware ~400-token chunks,
threshold 0.45). What's left is your own carry-over #5: the threshold is calibrated on a
handful of questions, and German condition names ("Blutend") sit just above it. This
session validates retrieval **systematically** and tunes the threshold **with data** —
measurement only, no pipeline changes beyond possibly the `MAX_DISTANCE` constant.

## Step 1 — golden set

Draft ~20 German questions of the kind that should trigger the `## Regelwerk` block,
spread across: core mechanics, conditions/Zustände (include the known-marginal ones like
"Blutend"), equipment/weapon table lookups, and edge rules. **Plus ~10 negative examples**:
table talk and pure narration ("Ich schaue mich in der Bar um") that must stay BELOW the
threshold — false positives pollute the prompt and cost tokens. For each positive, record
the expected source section (heading path as stored in the chunk metadata).
**Stop and show me the set for confirmation before measuring.**

## Step 2 — eval

`tools/rag_calibrate.py`, standalone, against the existing `data/vectordb/rag.db` and the
existing `dmbot/rag/retrieve.py` path (import it — measure what the bot actually does,
don't reimplement):

- per positive question: top-5 hits with distances; recall@1/@3 vs. the expected section,
- per negative: best-hit distance (should be > threshold),
- a **threshold sweep** (e.g. 0.35–0.60 in 0.025 steps): plot/table of
  positives-retrieved vs. negatives-leaked per value; recommend the operating point,
- failure analysis: every missed positive with its top-3 hits — if misses cluster on
  table content, report whether the *chunking* (tables split mid-row?) or the *embedding*
  is at fault; only that finding would reopen the embedder/chunking question, with
  evidence.
- report → `tools/rag_calibrate_report.md` (gitignored — section titles may appear,
  rulebook passages may NOT).

## Step 3 — outcome

- If the sweep supports it: change `MAX_DISTANCE` (one constant) + D-entry citing the
  numbers. No ADR — ADR 019 anticipated live tuning.
- If chunking/table problems surface: report only; fixing ingestion is a separate session.
- Keep the golden set in `tools/` (questions + heading paths only) — it becomes the
  regression check when "Villains on Voll" or other sources get ingested later
  (carry-over #4).

## Constraints

- Never commit. Rulebook content never appears in tracked files. No new dependencies
  (sqlite-vec, numpy, httpx are in). `uv run pytest` stays green.
- `progress.md` per the ritual.
