# ADR 021 — Curated German lore compendium (Imperium + Chaos) as RAG sources

- **Status:** Accepted (built, offline-verified; live `📚` gate pending)
- **Date:** 2026-06-13
- **Refs:** decision log D48 in `progress.md`; partially resolves **D28** (the open Phase-10
  lore-corpus item — the user-facing factions, not the broad wiki corpus). Extends **ADR 019**
  (3-stage hybrid: joins `rulebook`/`setting` as stage-3 sources; tracking differs — see
  Consequences) and the **D46** `setting` precedent. Content-authoring
  precedent: the hand-authored `data/adventures/chemical_burn/` compendium (ADR 019).
  Suite 181 → 183. No new deps.

## Context

A live retrieval probe (2026-06-13, German questions vs the store) showed the lore corpus is
lopsided:

- **Human/Imperium lore retrieves well** from the English Core Rulebook (Imperium structure
  d=0.27, Inquisition d=0.34, Mechanicus d=0.26 — all under the 0.45 ceiling), but every hit is
  labeled `## Regelwerk` — lore framed as rules ground truth.
- **Chaos cosmology is absent.** "Wer sind die vier Chaosgötter?" (d=0.53) and
  "Khorne/Nurgle/Tzeentch/Slaanesh?" (d=0.55) miss; only daemon *statblocks* and corruption
  *mechanics* exist. The IM books treat Chaos as hidden horror by design — RAG cannot retrieve
  what was never written.
- **Cross-lingual penalty:** German queries against English text inflate cosine distances;
  several human-lore questions (Astronomican, Space Marines) sat just over the threshold.

Tobi's requirement: **human lore + Chaos lore** must be reliably available to the DM. Other
xenos factions (Tyranids, Necrons, T'au) are explicitly fine to stay absent — the DM staying
silent or shallow there is acceptable.

## Decision

Hand-author a **curated German lore compendium** under `data/lore/` (committed — see the
revised tracking note under Consequences) and ingest it as **two new RAG sources**:

- `data/lore/imperium.md` → `--source lore_imperium` → label
  `## Weltwissen (Imperium — Hintergrund, nur als Färbung nutzen)`. Full German primer
  (Tobi's choice: ausführlich, not gap-fill-only): Emperor/Golden Throne/Astronomican/Custodes/
  Ecclesiarchy, High Lords/Adeptus Terra/tithe, Astartes overview, Astra Militarum, Navis
  Imperialis, Mechanicus, Inquisition + Ordos, Astra Telepathica, Navigators, psykers,
  Macharian-Sector context.
- `data/lore/chaos.md` → `--source lore_chaos` → label
  `## Weltwissen (Chaos — verbotenes Wissen, nur als Färbung nutzen)`. The Warp/Gellerfeld,
  the four Chaos Gods (one section each), the Great Game/Undivided, daemon taxonomy,
  corruption/cults/heresy, Horus Heresy + Horus, Chaos Space Marines, the Imperium's response.

Design points:

- **Grimdark in-world register** (Tobi's choice), not wiki-neutral — the text is prompt colour
  for a German narrator. The chaos.md header reminds the DM this knowledge is *forbidden*
  in-world and only voiced by fitting characters.
- **Two files = two sources** (Tobi's choice) so either half can be re-authored + re-ingested
  without re-embedding the other (ingest replaces per source).
- **Headings are the citations**: `chunk_markdown` is heading-aware and `fetch_block` renders
  `[Quelle: <heading>]`, so every `##`/`###` reads as a German source label
  (`### Khorne — der Blutgott`). Entity sections open with a *definitional* sentence — probe
  tuning showed bare entity questions ("Wer ist Horus?") need the definition near the top to
  clear the threshold.
- **Block order** in `_SOURCES`: rulebook → lore_imperium → lore_chaos → setting (rules ground
  truth → broad lore → local Rokarth colour). The `setting` label gained "lokaler Hintergrund"
  to disambiguate. No other code change — `_search`/`fetch_block` self-wire from the dict.
- **Threshold stays global 0.45.** It was calibrated for the hard cross-lingual case;
  German-vs-German scores comfortably lower (verified ~0.27–0.44).

## Alternatives

- **D28 wiki dump (Lexicanum/Fandom ingestion):** deferred, not rejected. Heavy (scraping,
  cleaning, licensing), and breadth isn't the need — the two requested factions are. Stays the
  later breadth expansion if play demands it.
- **Re-tag the rulebook's lore chunks** (fix the `## Regelwerk` mislabel): rejected — needs
  per-chunk topic classification at ingest, brittle machinery for a cosmetic problem. The
  German lore out-ranks those chunks for German lore questions, making the mislabel mostly
  moot. Recorded as an accepted limitation.
- **Loosen the threshold / translate queries** to fix the cross-lingual near-misses:
  unnecessary once German lore exists, and loosening would let table talk drag chunks in.
- **Per-source thresholds / cross-source dedup:** deferred until live `📚` logs show a need.

## Consequences

- Lore questions get grounded German answers that naturally win TOP_K over the English
  rulebook; Chaos cosmology is retrievable for the first time. Offline-verified (24-question
  probe): all target Imperium + Chaos questions hit the right chunk under 0.45 (typically
  0.28–0.44); regressions clean — rules → `rulebook`, Rokarth → `setting`, table talk and the
  Voll spoiler question stay silent.
- **Tracking (revised same day, Tobi):** `data/lore/` is **committed**. Unlike the adventure
  compendium (a retelling of a bought book), the lore is an *own-wording* digest of freely
  available 40k common knowledge — no licensing boundary applies. A fresh clone carries the
  two files; only the `ingest` runs are needed to rebuild the sources.
- Golden rule #7 ("lore from PDFs") gains a second sanctioned deviation after the adventure
  compendium: *curated* content — but the facts still live in RAG, never fine-tuned into the
  model, and the engine/profile split is untouched.
- Tyranids/Necrons/T'au remain absent by explicit scope decision; the DM answers those from
  model knowledge or stays vague. D28's broad wiki corpus stays open.
- Store now holds 4 sources: rulebook 1505, setting 201, lore_imperium 18, lore_chaos 17 chunks.
