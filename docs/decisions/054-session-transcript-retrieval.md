# ADR 054 — Campaign memory: session-transcript retrieval (hybrid KNN+FTS over played sessions)

- **Status:** Accepted (code-complete; threshold live-tuning pending)
- **Date:** 2026-07-17
- **Refs:** consumes the **ADR 053** journal extensions (scene events as chunk boundaries);
  built on the **ADR 019** RAG substrate (sqlite-vec store, heading-aware ingest patterns,
  degrade-silently discipline) and the **ADR 021** source/label conventions; journal semantics
  (redo collapse, rotation) from **D41/ADR 046**; the debug-campaign exclusion reacts to
  **ADR 052**. Touches `dmbot/rag/ingest_session.py` (new), `dmbot/rag/ingest.py`,
  `dmbot/rag/retrieve.py`, `dmbot/orchestrator.py`, `dmbot/runtime.py`,
  `dmbot/voice/voicecog.py`, `dmbot/config.py`, `tools/rag_calibrate.py`,
  `tools/rag_golden_set.json`, `tools/fixtures/fixture/`.

## Context

The DM remembers past sessions only through the rolling recap and the structured state
(NpcMemory, clocks, Chekhov). That compresses away exactly the details players ask about
weeks later: "Was hat der Händler Vosk in Session 3 zu uns gesagt?" The raw material exists —
every session leaves a rotated `history.jsonl` — but nothing reads it back. What's missing is
an episodic layer: verbatim scenes from *played* sessions, retrievable by meaning **and by
name**, without ever becoming a second source of truth for facts the state already owns.

## Decision

1. **Played-vs-planned is the boundary — ADR 019 sharpened, not weakened.** Only rotated
   journals (`history.<stamp>.jsonl`) are ingested: what the table actually experienced. The
   adventure text stays out of the store exactly as before; the live `history.jsonl` is never
   ingested (the current session is already in the prompt as history and must not echo back
   through retrieval).
2. **Chunking per scene on the ADR 053 events** (`dmbot/rag/ingest_session.py`, pure +
   unit-tested): scene events are hard boundaries; an oversized scene splits into turn groups
   at turn boundaries (never mid-turn); pre-ADR-053 journals fall back to size-based turn
   groups under scene "unbekannt". Redos are collapsed with `load_recent` semantics before
   chunking. Each chunk *opens* with `[Session vom <Datum>, Szene: <id>]` embedded in the
   text — anchoring the embedding and giving the DM temporal framing for free. No LLM
   anywhere in the pipeline: raw transcript chunks only (the recap already compresses).
3. **Storage in the existing store, stamp-idempotent — but a separate vec table.** Source
   `session_<channel_id>` in `data/vectordb/rag.db`; chunk rows carry the rotation stamp
   (new `stamp` column, added in place — no migration system; the rulebook rows keep an
   empty stamp). Session vectors live in their **own** `session_chunks_vec` (verifier
   finding): vec0's `k` is global per table and the source filter prunes only *afterwards*,
   so sharing `chunks_vec` would let ~1700 book chunks starve the session top-k — and
   session vectors (scoring tighter, DE-vs-DE) would shrink the book path's candidate pool,
   silently breaking its zero-behavior-change guarantee. Separate tables give both by
   construction. Re-ingesting a stamp is a transactional delete+insert; mirror inserts
   (vec + FTS) clear their rowid first, so stale rows from an interrupted ingest self-heal
   instead of failing. The meta table records `session_ingested:<source>:<stamp>` —
   recorded even for an empty journal (so catch-up never retries it forever; without any
   store yet, an empty journal creates no bare DB and is simply re-read next join).
   Session ingest always embeds with the **store's own model** (meta table), never
   triggering `ensure_schema`'s rebuild; a deliberate rebuild (model change) also drops
   the FTS mirror + session vec table and forgets all session stamps, so catch-up
   re-ingests.
4. **Two triggers, one code path, self-healing:** on `!leave` the just-rotated file is
   ingested in a background thread (`asyncio.to_thread`, fire-and-forget, log-only failure);
   on `!join` a catch-up scan ingests every rotated file whose stamp the meta table doesn't
   know. The catch-up covers crashes and shutdown-during-ingest, and doubles as the one-time
   backfill of pre-feature sessions. Manual runs: `python -m dmbot.rag.ingest_session
   <dir|file>` wraps the same function — and refuses any file not named
   `history.<stamp>.jsonl`, so the live journal cannot be ingested even by hand.
5. **Exclusions:** `DM_SESSION_MEMORY=0` disables ingest **and** retrieval together.
   Debug-campaign runs (ADR 052) play in the SAME channel as live play, so channel isolation
   cannot cover them: a `testplan.json` next to the loaded adventure (pure path check,
   independent of `DM_DEBUG_OVERLAY`) skips ingest entirely.
   `SessionRuntime._session_ingest_source` is the explicit seam where the debug-campaign
   follow-up will return a sandboxed debug source instead of skipping.
6. **Hybrid retrieval, session sources only.** Alongside KNN, an FTS5 (BM25) query runs over
   the session chunks — proper-noun recall ("Vosk") is exactly where embeddings are weakest,
   and FTS5 is built into sqlite (no new dependency). Candidate terms are label-stripped
   (the acting character's name heads every line and must not pull their past into every
   turn), capitalized **mid-sentence** (German capitalizes every sentence start, so an
   utterance-opening word carries no name signal — sentence-initial words are excluded,
   accepting that a name which *opens* a sentence loses its FTS rescue), non-function-words;
   a term qualifies only while its document frequency in the source is low (`max(3, 15%)`
   of chunks) — recurring table vocabulary ("Waffe", "Tür") is what the KNN threshold
   handles, the FTS half exists for the rare name. An exact-term FTS hit outranks any
   borderline KNN hit and is exempt from threshold and recency malus; dedupe by chunk id.
   **Rulebook/lore retrieval is byte-identical** (same thresholds, same `TOP_K`, pure
   vector over its own table — pinned by the untouched test_rag suite plus a new
   isolation test).
7. **Own budget and threshold:** at most `SESSION_TOP_K = 2` chunks *in addition to* the
   book's `TOP_K = 3` — memories never crowd out rules. `SESSION_MAX_DISTANCE = 0.38`
   (DE-vs-DE matches tighter than the 0.45 DE-vs-EN ceiling), plus a mild recency malus
   (`0.01` distance per session of age).
8. **Prompt block after Weltwissen, state wins over memory:** own label
   `## Früher in der Kampagne (Erinnerungen aus Session vom <Datum> — kann veraltet sein;
   aktueller Status, NPC-Stand und Uhren haben immer Vorrang)`. The retriever resolves the
   active channel id to its `session_<channel_id>` source; other channels' sessions are
   never searched. Episodic color only — hard facts stay with the JSON state (golden rule #3).
9. **Calibration:** `tools/rag_golden_set.json` gained a `session_recall` section
   (semantic + proper-name positives, pure-narration negatives) against a committed
   synthetic fixture session (`tools/fixtures/fixture/`, ingested by the calibrator as the
   runtime-inert source `session_fixture`); `tools/rag_calibrate.py` sweeps
   `SESSION_MAX_DISTANCE` (0.26–0.46) with a KNN-only column. First run: 5/5 positives hit
   (all carried by FTS), 0/5 negative leaks at every T — and KNN-only recall at 0.38 was
   0/5 against the fixture, i.e. **the FTS half is doing the proper-noun work by design;
   the KNN ceiling needs live-session data to tune** (fixture chunks are tiny-corpus,
   multi-topic — real evidence pending, report notes it).

## Alternatives

- **LLM-summarized memories instead of raw chunks:** rejected — the recap already exists for
  compression; a second summarizer adds an LLM call, a failure surface, and hallucination
  risk to a layer whose whole value is verbatim fidelity.
- **A separate vector DB / new dependency for FTS:** rejected — sqlite ships FTS5; one store,
  one degrade story, the existing per-thread connection cache just works.
- **Pure-vector session retrieval (no FTS):** rejected — the calibration run confirms the
  motivating hunch: short player questions naming an NPC sit far above any sane KNN ceiling
  while the exact term sits verbatim in the transcript.
- **Ingesting the live journal continuously:** rejected — the current session is already in
  the prompt as history; retrieval would echo it back, and rotation gives a natural,
  idempotent unit (the stamp).
- **A queue/migration framework for ingest recovery:** rejected — the meta table plus
  stamp-idempotent re-ingest *is* the recovery story; the catch-up scan makes every failure
  mode converge on "ingest it next join".

## Consequences

- **+** "Was hat Vosk damals gesagt?" gets the actual scene back, with its session date and
  scene id, at most 2 chunks, clearly labeled as fallible memory subordinate to state.
- **+** Every future session feeds itself into the store on `!leave` with zero operator
  work; the first `!join` after this lands backfills all existing rotated sessions.
- **−** `SESSION_MAX_DISTANCE = 0.38` is fixture-calibrated only; live tuning against real
  rotated sessions is pending (golden-set note + report flag). Threshold changes need
  golden-set evidence (lesson: rag-misses-are-content-gaps).
- **−** The `stamp` column and FTS table only exist after the first session ingest touches a
  store; all readers tolerate their absence (pinned by tests).
- **−** A retriever constructed while no `rag.db` exists stays inert for that process even
  after a first ingest creates the store (same pre-existing property as the rulebook path;
  next boot picks it up).
- **Bound for later work:** the debug-campaign follow-up (`03_debug-campaign.md`) replaces
  the testplan skip with a sandboxed debug source at the `_session_ingest_source` seam;
  live threshold tuning after the first real played-session ingests.
