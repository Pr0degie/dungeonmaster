---
name: rag-ingest
description: Use when ingesting a new PDF or curated source into the RAG store, or when recalibrating retrieval. Converts PDF→markdown with page/spoiler control, inspects a real chunk, ingests with a source tag, wires the source into retrieval, calibrates the distance threshold, and verifies a sample question hits while a spoiler probe stays silent.
---

# Ingest a source into the RAG store

40k rulebooks are multi-column / table-heavy, so extracted text comes out scrambled
(golden rule #7: answer rule questions from chunks, never the model's gut). The store is
`data/vectordb/rag.db` (sqlite-vec, cosine) embedded with **bge-m3**.

## Procedure

1. **Discipline first.**
   - **Inspect a real chunk** before trusting retrieval — layout soup is silent, it won't error.
   - **Trim spoilers by page range.** Precedent: Setting Guide ingested `--pages 1-57` (villain
     resolution withheld); the GM-Guide was ingested spoiler-trimmed. Keep campaign secrets,
     villain reveals, and patron secrets *out* of the DB.
2. **Convert:** `uv run python tools/pdf_to_md.py "<pdf>" -o "<md>" --pages A-B`
3. **Inspect** the produced markdown — is a representative chunk readable, or column/table junk?
   If junk, fix the page range / re-extract before ingesting.
4. **Ingest:** `uv run python -m dmbot.rag.ingest "<md>" --source <tag>`
   (idempotent per `--source` — re-running with the same tag replaces those chunks).
5. **Wire the source** into `dmbot/rag/retrieve.py` `_SOURCES` and choose its group:
   `## Regelwerk` (rules) or `## Weltwissen` (lore/setting). Retrieval is self-wiring from
   `_SOURCES`; usually no other code change.
6. **Calibrate:** `uv run python tools/rag_calibrate.py`, then read
   `tools/rag_calibrate_report.md` (gitignored). `MAX_DISTANCE` **stays 0.45** unless the data
   clearly supports a change — positives (rule questions) and negatives (narration) overlap in
   embedding space, so no threshold separates them cleanly. Real gaps are usually
   content/chunking, not the threshold.
7. **Verify:** one factual question hits the right source at distance < 0.45; one **spoiler
   probe** returns nothing usable (secret pages aren't in the DB / generic hits sit above the
   gate). Check the `📚 <source>` log line fires in a real `!rules` / `!lore` query.

## Commit boundary

- **git-ignored** (bought-book derivatives): the generated `<…>.md`, the PDFs, `rag.db`.
- **committed** (own words, `.gitignore` allowlist): hand-authored curated sources under
  `data/lore/` and `data/rules_de/`.

## Content fixes beat threshold fixes

Two known levers from past rounds: a German term missing its English chunk (fixed by a curated
German glossary, e.g. `data/rules_de/conditions.md`, with the German name **in the body** since
the ingest embeds the body, not the heading); and weapon-stat **tables** that don't retrieve
(needs table-row chunking — a separate ingestion session).
