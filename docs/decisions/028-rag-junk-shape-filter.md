# ADR 028 — RAG junk-shape filter (drop OCR/statblock noise from per-turn retrieval)

- **Status:** Accepted
- **Date:** 2026-06-13
- **Refs:** decision log D59 in progress.md; refines ADR 019 (RAG) and ADR 025 (German rules
  glossary + the 0.45 calibration)

## Context

In the first live playtest, the per-turn rulebook RAG injected irrelevant chunks during **pure
roleplay** turns that contained no rule question at all (a bar/sex scene). Logged hits were OCR'd
table-of-contents / bestiary statblock headings sitting right at the threshold: `WARRIOR` (d=0.43),
`PLaGUeBearer (eLite)` (0.44), `--------------- PSYCHIC POWERS---------------` (0.45), `MACHARIAN
TOMES` (0.45). This noise wastes the prompt/context budget (which ADR 027 is fighting) and adds
nothing. ADR 025's calibration had already concluded that `MAX_DISTANCE = 0.45` is the best single
threshold for the German rule questions — positives and narration negatives overlap in the embedding
space, so lowering the threshold trades real recall for a few fewer leaks.

## Decision

Keep `MAX_DISTANCE = 0.45` and add a **distance-independent junk-shape filter** (`_is_junk_hit`) to
`fetch_block` (the per-turn narration gate only — `lookup` / `!rules` / `!lore` are untouched). It
drops three unambiguous OCR/layout shapes: dash-run headings (`-{4,}`), statblock-tag headings
ending in `(eLite)`/`(trOOP)`/`(LeaDer)`, and picture-text bodies (`----- start of picture text -----`).
Coverage: 103 / 2482 chunks (4%), all noise.

## Alternatives

- **Tighten MAX_DISTANCE to 0.42/0.40.** Rejected with data: the calibration tool showed it drops a
  real combat-rule answer (`CRITICAL HIT` @0.439) for only −2 negative leaks — measurable recall cost.
- **An epigraph/flavour-quote filter** (to also kill `WARRIOR`-type hits). Rejected: every variant
  tested also flagged legitimate rules-section openers (`MedicaL care`, `ranged Weapons` open with the
  same `_**…**_` epigraph) — too risky for recall.

## Consequences

- **Positive:** the reported dash-run, statblock-tag and picture-text noise no longer reaches the
  prompt; recall@1/@3 **unchanged** (52% / 81% — the filter only post-processes `fetch_block`, never
  the recall path). Frees a little context budget on every narration turn.
- **Negative / known gap:** `WARRIOR`-style epigraph rows (flavour quotes whose shape overlaps real
  section openers) are a **deliberate non-fix** — eliminating them cleanly needs a chunking-level
  change at ingest (re-splitting epigraphs off their section bodies + rebuilding the store), which is
  out of scope here. Documented as a future ingestion task.
