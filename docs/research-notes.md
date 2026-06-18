# Research notes

External research that informed design decisions, kept so the reasoning (and sources) survive
context clears. Each thread links to the ADR/decision it fed.

---

## 1. Getting the LLM to actually call for a dice roll (→ ADR 014 / D29)

**Problem (observed live, 2026-06-08):** asking the *narration* model to emit an inline `<<TEST …>>`
marker fails — across a whole session only ~2 markers fired, both mis-placed; the model **self-resolves**
uncertain actions in prose ("du bemerkst …", "es gelingt dir …"). Happened on **both** mistral-nemo
*and* gemma3:12b.

**Key findings:**
- This is a **documented, model-size-independent LLM-GM failure**, not a 12B limit. LLMs are biased
  toward non-interactive storytelling ("yes, you succeed") and skip checks.
- The field's fix is **function calling / a structured roll step**, not a bigger model. The paper
  *"…Enhancing AI Game Masters with Function Calling"* reports a consistency lift **3.42 → 4.39** with
  dice/state functions, and a **"dice-roll deadlock"** without them — but it only evaluated GPT-4 (no
  model-size comparison).
- **Our own experiment settled the open question for our models:** as a *separate, constrained-JSON
  classification step* ("which test does this action need, or none?"), the same nemo that self-resolves
  in narration scored **8/8** (gemma3 7/8), including correct "no test" on trivial actions. → built as
  the roll-detection router (ADR 014).
- **Ollama supports structured outputs** (pass a JSON schema → converted to a grammar → token masking)
  and OpenAI-compatible function calling — reliable *format*, though it doesn't make the model *decide*
  to call a tool (that's what the separate step / two-turn structure is for; tool-awareness is poor in
  one shot, better in a dedicated second turn).

**Sources:**
- [arXiv 2409.06949 — Enhancing AI Game Masters with Function Calling](https://arxiv.org/html/2409.06949v1)
- [shiftmag — D&D meets AI: a smarter game engine](https://shiftmag.dev/dungeons-dragons-dnd-ai-game-engine-6240/)
- [Ollama structured outputs (JSON schema → grammar)](https://blog.danielclayton.co.uk/posts/ollama-structured-outputs/)
- [arXiv 2508.12566 — MCP-augmented LLMs (tool-awareness improves on the 2nd turn)](https://arxiv.org/pdf/2508.12566)
- [EN World — LLMs as a GM (community experience)](https://www.enworld.org/threads/llms-as-a-gm.714126/)

---

## 2. Representing 40k lore: RAG, not fine-tuning (→ D28; Phase 10 plan)

> **→ Embedder superseded:** this note (and D28) plans `nomic-embed-text`; Phase 10a (ADR 019) switched
> to **`bge-m3`** — nomic barely aligns German queries with the English rulebook (DE-query↔EN-text). The
> `nomic-embed-text` mention below is the original plan, kept for the record.

**Question:** how to give the DM Warhammer 40k lore — scrape a wiki? fine-tune mistral-nemo on it?

**Key findings:**
- **RAG, not fine-tuning, for facts.** Fine-tuning teaches *style/behaviour*, not reliable facts → it
  hallucinates confidently, can't cite, and must be retrained to update; a wiki doesn't fit in 12B
  weights/context. RAG keeps the corpus on disk, grounded + citeable + updatable in minutes (golden
  rule #7). The **only** place fine-tuning fits later is a **tone-LoRA** (style, on session logs) — never
  for facts. Continued-pretraining: overkill, dismissed.
- **Sizes (text only — images are excluded; they'd be many GB and useless for text RAG):**
  - **Lexicanum** (wh40k.lexicanum.com): **~48,590** articles. MediaWiki, canon-rich. No Fandom-style
    one-click dump → use the **MediaWiki API** (`allpages` + `revisions`, throttled + cached) or an
    archive.org/WikiTeam dump. ≈ 150–300 MB plaintext → ~0.6–1.1 GB vector DB.
  - **Fandom 40k wiki** (warhammer40k.fandom.com): **~7,284** articles. Has an **official XML dump**
    (Special:Statistics → "Current pages", `.7z`). ≈ 30–60 MB plaintext → ~120 MB vector DB.
  - Both together ≈ **0.8–1.3 GB**, one-time embedding ~40–100 min on the 4070.
- **Pipeline (Phase 10):** dump/API → `mwparserfromhell` strip → chunk (~400 tok) → `nomic-embed-text`
  via Ollama `/api/embed` → **`sqlite-vec`** (rulebook vs lore as separate `source`s). Mirrors the
  offline `tools/pdf_to_md.py` precedent. Full plan in the session plan file; recorded as **D28**.

**Sources:**
- [Lexicanum statistics / Export pages](https://wh40k.lexicanum.com/wiki/Warhammer_40k_-_Lexicanum:Statistics)
- [Fandom — Help:Database download](https://community.fandom.com/wiki/Help:Database_download)
- [nomic-embed-text (Ollama)](https://ollama.com/library/nomic-embed-text) ·
  [Ollama batch embeddings `/api/embed`](https://docs.ollama.com/capabilities/embeddings)
- [mwparserfromhell](https://github.com/earwig/mwparserfromhell) ·
  [mwclient](https://github.com/mwclient/mwclient) · [sqlite-vec](https://github.com/asg017/sqlite-vec)
