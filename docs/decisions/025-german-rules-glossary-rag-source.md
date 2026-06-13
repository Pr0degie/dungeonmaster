# ADR 025 — German rules-glossary RAG source + retrieval calibration outcome

- **Status:** Accepted (code-complete; live verification pending)
- **Date:** 2026-06-13
- **Refs:** builds on **ADR 019** (rulebook RAG: bge-m3, sqlite-vec, threshold 0.45) and **ADR 021**
  (curated German source to fix DE→EN retrieval — same spirit, for *rules*); the 2026-06-13
  calibration entry in `progress.md`. Suite 234.

## Context

The DM answers rule questions from the RAG, threshold-gated (`MAX_DISTANCE=0.45` narration / 0.55
`!rules` / 0.52 `!lore`). After ingesting the two Inquisition guides this session, none of the three
thresholds was data-validated, and Tobi reported the DM getting German condition questions wrong.

Prompt-5 (RAG calibration) was run: a committed golden set (`tools/rag_golden_set.json`, 21 positives
/ 10 negatives — own German questions + expected source/heading, **no rulebook passages**) +
`tools/rag_calibrate.py` (imports the real `dmbot/rag/retrieve.py` path; recall@1/@3 + a 0.35–0.60
threshold sweep per context; report → gitignored `tools/rag_calibrate_report.md`).

**Finding:** rule-question and narration embeddings **overlap badly** — at 0.45 the narration gate
already leaks ~4/10 table-talk lines, and no threshold separates positives from negatives cleanly
(leak-free ≤0.375 loses most real retrieval; ≥0.50 leaks almost everything). The real gaps were
**content/chunking**, not the threshold: German condition names ("Blutend") missed the English
condition chunks, and weapon-stat **tables** don't retrieve at all.

## Decision

1. **Keep the thresholds (`MAX_DISTANCE` 0.45, `!rules` 0.55, `!lore` 0.52).** The sweep gave no
   confident better operating point — don't tune blindly on 10 negatives.
2. **Fix DE→EN retrieval at the source:** a hand-authored **German rules glossary** as a new
   **committed RAG source category `data/rules_de/`** (first member `conditions.md` — the IM Zustände
   in own German words, grounded in the rulebook). New source **`conditions`** → `## Regelwerk`,
   wired into `_SOURCES` and the `!rules` search. Same move as ADR 021's curated German *lore*, now
   for *rules*: a German source matches German questions that the scrambled English OCR doesn't.
3. **Schema constraint (the key insight):** the ingest embeds the chunk **body, not the heading**, so
   each glossary section must **lead its body with the German term** ("Der Zustand **Blutend**
   bedeutet: …"). That pulled the specific chunk to the top (Blutend 0.40 → **0.29**); without it the
   generic intro chunk won and the model hallucinated.
4. **Keep the golden set committed** as a regression check for future ingests; the report stays
   gitignored (it quotes headings + distances).

## Alternatives

- **Tune `MAX_DISTANCE`.** The sweep showed overlapping distributions — lowering loses positives,
  raising floods the prompt. A threshold can't fix a content gap. Rejected as the primary fix.
- **Re-embed / change embedder.** Calibration would have flagged a systematic embedding failure; it
  didn't — rulebook questions land fine. The gap is specifically German *names* → English chunks,
  which a German source fixes directly.
- **Translate the rulebook conditions appendix into the `rulebook` source.** Re-ingests bought-book
  prose; the hand-authored glossary is own-words (committable like the system profile), denser, and
  cleaner to maintain.

## Consequences

- **Positive:** `!rules` answers German condition questions correctly (Blutend/Betäubt/Vergiftet/
  Brennend exact; before, Blutend hallucinated). recall@1 38→52%, recall@3 67→81%, narration hits
  13→15/21 with **zero** new negative leaks. The golden set is a regression net.
- **Binding:** hand-authored RAG glossaries live under **`data/rules_de/`** (committed via the
  `.gitignore` allowlist), grouped under `## Regelwerk`, and **must lead each section's body with the
  German term** (the ingest embeds the body). Threshold changes need golden-set evidence, not vibes.
- **Open:** weapon / stat-block **tables** still don't retrieve (table-row chunking) — a separate
  ingestion session; a German weapon glossary in `data/rules_de/` is the likely fix, same pattern.
- **To verify live:** `!rules Was bewirkt Blutend?` → the correct German effect (1 Schaden am
  Zugende, ignoriert Rüstung).
