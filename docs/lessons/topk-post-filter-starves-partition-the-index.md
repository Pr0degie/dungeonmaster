# Top-k + post-filter starves the filtered class — partition the index instead

**Lesson (2026-07-17, Session-RAG-Runde / ADR 054, verifier-found pre-commit).**

A KNN store's `k` applies to the **whole table**; a `WHERE source = …` predicate prunes
*after* the nearest-k are chosen. Querying "top 6 nearest, then keep only session chunks"
against a table that also holds ~1700 rulebook chunks returns 6 book chunks and zero session
candidates — the filtered class is silently starved, and the failure is invisible in unit
tests whose fixture stores hold a handful of rows. The same sharing also worked in reverse:
tighter-scoring session vectors entering the shared table shrank the book path's effective
candidate pool, breaking a "zero behavior change" guarantee no test caught.

**Why it kept being missed:** the existing `_search` had the same over-fetch-then-filter
shape (`k*3`, "the filter prunes") and worked fine — because there the filter excludes only
a *tiny* minority class (gm_only). The pattern breaks exactly when the wanted class is the
minority.

**How to apply:**
- When two corpora of very different size (or score distribution) live behind one top-k
  index and are queried separately, give each its **own index/table** (here:
  `session_chunks_vec` next to `chunks_vec`). Partitioning by table makes isolation and
  "zero behavior change" true by construction — no over-fetch factor is ever safe against
  a 100:1 size ratio.
- Fixture stores must contain a realistic *majority class* when testing a minority-class
  query path, or add an explicit isolation test (see
  `test_session_vectors_never_enter_the_book_knn`).
- Related trap fixed the same day: sqlite reuses freed INTEGER PRIMARY KEYs, so mirror
  tables keyed by rowid (FTS, vec) must clear-before-insert or an interrupted/older ingest
  leaves stale rows that fail later inserts (`IntegrityError`) — make mirrors self-healing.
