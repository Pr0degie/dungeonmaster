# ADR 019 — Adventure into the DM: 3-stage hybrid (scene tracker + rulebook-only RAG)

- **Status:** Accepted (code-complete; live verification pending)
- **Date:** 2026-06-12
- **Refs:** decision log D44/D45 in `progress.md`; realises Phase 10's first half (roadmap) and
  **deviates** from the pure-vector plan in `architecture.md` §8 (rewritten in this change) and
  **D28** (embedder swapped). Builds on **ADR 015** (state split — the scene pointer lives in
  `state.json`), **ADR 018** (echo guard — extended here by the W4 self-repetition check),
  **ADR 005** (profile bootstrap = the still-open second half of Phase 10). Player feedback
  context: the 2026-06-12 session ("kein Plot, improvisiert aus dem Nichts") and Timo's
  architecture critique (prepared adventure docs + state tracking outside the narrator LLM).
  Suite 157 → 176. New dep `sqlite-vec`; embedder `bge-m3` (Ollama).

## Context

Phase 10's roadmap plan was classic vector RAG: chunk + embed all PDFs (rulebook, lore,
adventure), retrieve per turn. Building it for the first real adventure (*Chemical Burn*, 53 pp.,
a 5-part investigation with a part-2 location hub) surfaced three structural problems with
putting the **adventure** itself in a vector store:

1. **No plot state.** The retrieval query is the last player input; similarity can't answer
   "where are we in the story and what happens next". That gap was the loudest player critique —
   the DM improvised from nothing.
2. **Spoilers by similarity.** "Wer steckt dahinter?" in part 1 retrieves the part-4 reveal.
3. **Scene coherence stays a model problem** — exactly what every live round since ADR 014
   taught us not to leave to a 12B model.

Separately, Timo's (independently formed) architecture matches the project's design: prepared
adventure docs, state tracking in code, the narrator LLM "nur zum Reden". The missing piece was
plot state.

## Decision

**Three stages, only the third is vector search:**

1. **Adventure summary (always in the prompt).** A ~300-token German GM-knowledge digest
   (`summary_de`) of the whole arc, marked "niemals wörtlich vorlesen".
2. **Scene tracker (deterministic, golden rule #3).** The adventure is authored **once, offline**
   into German scene cards (`data/adventures/<id>/adventure.json`: description, NPCs present,
   opportunities with profile-aligned German skills/difficulties, **secrets** flagged
   never-say, leads_to, a guidance field for steering back from off-script play) plus
   `npcs.json` statblocks (wounds/TB/armour for the engine + roleplaying notes). A code-owned
   pointer — `WorldState.scene_id`, persisted like HP — selects the **one** card injected into
   the prompt. The pointer is moved by humans (`!ort <id>`, listed via `!szenen`), never by the
   model. `!npc add <Name>` resolves statblocks from the compendium; explicit numbers override.
3. **Rulebook-only RAG.** md → heading-aware ~400-token chunks → Ollama `/api/embed` →
   **sqlite-vec** (`data/vectordb/rag.db`, cosine; offline CLI `python -m dmbot.rag.ingest`).
   Per turn the brain embeds the player input and injects matching chunks as a `## Regelwerk`
   block **only above a relevance threshold** (0.45 cosine distance) — most turns are narration
   and carry no block. **The adventure is deliberately not ingested** (spoiler discipline; the
   scene cards cover it).

**Embedder: `bge-m3`, not D28's `nomic-embed-text`.** Verified against real questions: German
queries barely matched the English rulebook with nomic ("kritischer Erfolg" → no hit; the only
hit was a wrong psychic-power block). bge-m3 (multilingual) hits DIFFICULTY/CRITICAL HIT
correctly while table talk stays below the threshold. The store records its model+dim in a meta
table, so the retriever always queries with whatever built the store; re-ingesting with another
model rebuilds it.

**Prompt order** (CLAUDE.md order, extended): persona → recap → **adventure summary + scene
card** → world state → **Regelwerk hits** → alias hint → history. Measured: summary+card ≈ 1k
tokens on top of the ~3.3k baseline — comfortable under `num_ctx` 8192, watched by the D36
budget warning.

**W4 self-repetition guard** (extends ADR 018's echo guard): `is_self_repetition` flags a new
answer that re-tells the DM's own previous answer nearly verbatim (SequenceMatcher ≥ 0.75 on
normalized text — survives the pronoun swaps seen live; answers under 60 chars exempt). Same
retry-with-nudge-then-suppress flow; in the streaming path only when nothing was spoken yet
(audio can't be retracted — a spoken repetition is logged loudly instead).

**Licensing boundary:** the compendium is a substantial German derivative of the bought
adventure, and the repo is **public** — so `data/adventures/` stays untracked (it already falls
under the `data/**` ignore), exactly like the PDFs and the vector store. The authoring steps are
documented; the content lives only on the play machine.

## Alternatives

- **Pure vector RAG for everything** (the original plan): fastest to build, but all three
  problems above; rejected for the adventure, kept for the rulebook where lookup-by-similarity
  is the right shape.
- **Whole adventure in the prompt:** 53 pages ≫ 8k ctx; even summarised it would crowd out
  history and state.
- **A director LLM moves the scene pointer** (Timo's full vision): deferred — the deterministic
  pointer is its prerequisite, and a director without grounded content was the failure we just
  diagnosed. Re-evaluate once live play shows `!ort` friction.
- **Translate queries to English instead of swapping the embedder:** an extra LLM call per turn
  (latency + failure surface) vs. a one-time model pull.

## Consequences

- **Positive:** "Wo sind wir?" has a deterministic answer; part-3 secrets cannot leak in part 1;
  rule questions are grounded in the book (the Phase-10 gate's first half); ~20 NPCs are
  `!npc add`-ready with real values; the players get a plotted campaign instead of improv.
- **Cost:** one-time authoring per adventure (scene cards; LLM-assisted, human-reviewed); a new
  dep (`sqlite-vec`) + a pulled embedder (`bge-m3`); +1 embed call per turn (~50 ms).
- **Binding:** the scene pointer is moved by humans only; the adventure never enters the vector
  store; `adventure_block_de` / `fetch_block` are the prompt contracts; compendium content stays
  out of git while the repo is public.
- **Open:** the profile bootstrap (Phase 10's second half, ADR 005) is untouched; scene-change
  ergonomics (a DM-proposed change with a confirm button) and the lore corpus (D28) are later
  steps; `MAX_DISTANCE` 0.45 is calibrated on a handful of questions — tune against live logs
  (German condition names like "Blutend" sit just above it).
- **To verify live:** `!join` announces adventure + scene; a rule question is answered from the
  book (gate half 1); `!ort` changes what the DM narrates; a part-1 "wer steckt dahinter?" stays
  unspoiled; the W4 case ("Warum sind wir hier?") gets an answer, not a re-description.
