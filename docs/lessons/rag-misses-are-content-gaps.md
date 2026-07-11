# RAG misses are content gaps, not threshold problems

**No retrieval miss was ever fixed by tuning the distance threshold — the causes were
embedder/language fit, content that simply isn't there, query vocabulary missing from the
chunk body, or junk chunk shape. Thresholds change only with golden-set evidence, per
consumer, where an honest "steht nichts im Weltwissen" beats a misleading hit.**

## What happened

- German queries against the English rulebook barely matched with nomic-embed-text — the
  only "hit" was a wrong block; embedder swapped to bge-m3 and verified against real German
  questions (D45 → ADR 019; `docs/research-notes.md` §2).
- Even with bge-m3, DE-vs-EN inflates distances — domains that must hit got **curated
  German sources** (`data/rules_de/`, `data/lore/`), which then win top-k (D48 → ADR 021).
- Calibration found no clean threshold separation; the real fix was content shape: the
  ingest embeds the chunk **body, not the heading** — leading the body with the German term
  took Blutend 0.40→0.29, recall@1 38%→52%; entity sections need a definitional first
  sentence (Horus 0.51→0.43) plus synonyms ("Dunkle Götter") (ADR 025; D48).
- Tightening 0.45→0.42 was rejected **with data** (drops a real combat-rule answer to
  remove 2 leaks); OCR junk got a distance-independent shape filter instead (D59 → ADR 028).
- Per-consumer ceilings were tuned on live probes: `!lore` 0.52 (0.45 too tight for
  explicit asks, 0.54 grabbed the wrong Tyranid chunk), `!rules` 0.55 (D49/D50).

## The correction

When a query misses, work this order: (0) inspect the actual hit chunks
(`docs/conventions.md` RAG section — layout soup is real); (1) is the content there at all?
(2) in the query's language, or does it need a curated German source? (3) does the chunk
*body* lead with the asked term + synonyms? (4) is it junk shape → shape filter, not
threshold; (5) only then the threshold — with `tools/rag_calibrate.py` + the golden question
set as evidence, never vibes, calibrated per consumer including a known off-corpus question.

## Why it matters

The threshold is the single visible dial, so it's reached for first — four rounds in a row
found the cause elsewhere, and the open items (weapon tables, Rokarth answering in English)
are the same class again.
