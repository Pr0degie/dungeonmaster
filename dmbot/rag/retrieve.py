"""Book retrieval — the runtime half of stage 3 (Phase 10a, ADR 019).

Per DM turn the brain asks for a prompt block for the current player input: embed the query
(Ollama ``/api/embed``, async) and KNN-search the sqlite-vec store **with a distance threshold**
— most turns are narration, not lookups, so most turns get no block at all and the prompt stays
lean. The sources in ``_SOURCES`` are searched and grouped under separate labels: ``rulebook``
(→ ``## Regelwerk``, rules ground truth), the curated German lore compendium ``lore_imperium`` /
``lore_chaos`` (→ ``## Weltwissen``, ADR 021), and ``setting`` (→ ``## Weltwissen``, Rokarth lore
from the Starter Set's Setting Guide — its spoiler chapter "Villains on Voll" is excluded at
ingest time). The adventure
itself never enters the vector store (spoiler discipline, ADR 019). Degrades silently: no DB /
Ollama hiccup → no block, never a broken turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import threading
from pathlib import Path

import httpx
import sqlite_vec

log = logging.getLogger(__name__)

# Cosine *distance* (1 − similarity) ceiling for a chunk to count as relevant. Generous enough
# for paraphrased German questions against English rule text, tight enough that table talk
# ("ich greife ihn an") doesn't drag rule chunks into every prompt. Tune against live logs.
MAX_DISTANCE = 0.45
TOP_K = 3  # total across both sources — lore may colour a scene, not flood the prompt

# --- campaign memory (ADR 054): retrieval over PLAYED sessions ---------------------------------
# Session transcripts are German-vs-German, so matches score much tighter than the DE-vs-EN
# rulebook case — a separate, stricter ceiling keeps stray narration out of the prompt.
SESSION_MAX_DISTANCE = 0.38
# Own budget, IN ADDITION to TOP_K — memories never crowd out rules/lore.
SESSION_TOP_K = 2
# Mild recency preference: distance malus per session of age (exact-term FTS hits are exempt —
# "Vosk" asked by name should surface no matter how old the session).
SESSION_RECENCY_MALUS = 0.01
_SESSION_LABEL = (
    "## Früher in der Kampagne (Erinnerungen aus Session vom {dates} — kann veraltet sein; "
    "aktueller Status, NPC-Stand und Uhren haben immer Vorrang)"
)

# FTS candidate terms: strip the per-line speaker labels and [Würfel]/[Regie] tags first — the
# acting character's name heads every player line and must not pull their whole past into every
# turn; only names *mentioned in* the utterance ("Was hat Vosk gesagt?") should count.
_LINE_LABEL = re.compile(r"^\s*(?:\[[^\]]{1,24}\]\s*)?(?:[\w'\-]+(?: [\w'\-]+){0,2}:\s*)?")
# German function words that start sentences capitalized — never a proper-noun signal. Content
# nouns are handled by the document-frequency gate in _search_session, not by this list.
_FTS_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer",
    "ich", "du", "wir", "ihr", "sie", "es", "er", "man", "mein", "dein", "sein", "uns", "euch",
    "und", "oder", "aber", "auch", "als", "wenn", "dass", "was", "wer", "wie", "wo", "wann",
    "warum", "nicht", "kein", "keine", "noch", "schon", "dann", "jetzt", "hier", "dort",
    "ist", "sind", "war", "waren", "hat", "hatte", "haben", "kann", "koennen", "können",
    "muss", "soll", "will", "wollen", "wird", "werden", "wurde", "bitte", "okay", "mal",
    "los", "gut", "nein", "doch", "etwas", "alles", "nichts", "wieder", "weiter", "damit",
}


_SENTENCE_END = ".!?…:;"


def _query_terms(query: str) -> list[str]:
    """Proper-noun candidates for the FTS half of the session search: label-stripped, ≥3 chars,
    capitalized **mid-sentence**, not a function word. Sentence-initial words are excluded —
    German capitalizes every sentence start ("Vielleicht gehen wir…"), so an utterance-opening
    word carries no proper-noun signal and would defeat the heuristic in young stores where the
    df gate is still loose. The rarity decision (document frequency) happens against the store —
    this only shapes the candidate list. Pure + unit-testable."""
    terms: list[str] = []
    for line in query.splitlines():
        body = _LINE_LABEL.sub("", line, count=1)
        for m in re.finditer(r"\w+", body):
            tok = m.group()
            prefix = body[: m.start()].rstrip()
            if not prefix or prefix[-1] in _SENTENCE_END:
                continue  # sentence-initial — capitalization is grammar, not a name
            if len(tok) < 3 or not tok[0].isupper() or tok.isdigit():
                continue
            if tok.lower() in _FTS_STOPWORDS:
                continue
            if tok not in terms:
                terms.append(tok)
    return terms[:6]

# Searched sources and their prompt labels, in block order (rules ground truth before colour,
# broad lore before local Rokarth colour). The curated German lore compendium (ADR 021) ships
# as two sources so either half can be re-authored + re-ingested without touching the other.
_SOURCES: dict[str, str] = {
    "rulebook": "## Regelwerk (Auszüge aus dem Regelbuch — Grundlage für Regelfragen)",
    "conditions": "## Regelwerk (Zustände — deutsche Spielwerte)",
    "player_guide": "## Regelwerk (Inquisition Player's Guide — Psikräfte, Talente, Ausrüstung)",
    "lore_imperium": "## Weltwissen (Imperium — Hintergrund, nur als Färbung nutzen)",
    "lore_chaos": "## Weltwissen (Chaos — verbotenes Wissen, nur als Färbung nutzen)",
    "setting": "## Weltwissen (Hive Rokarth — lokaler Hintergrund, nur als Färbung nutzen)",
    "gm_guide": "## Weltwissen (Inquisition — Ordos, Philosophien & Methoden)",
}

# --- junk filter (live tuning after ADR 025) ---------------------------------------------------
# On pure-narration turns the bge-m3 KNN still surfaces a handful of chunks that sit right at the
# 0.45 ceiling (d≈0.43–0.45) yet carry no rule content: scrambled multi-column OCR, picture-text
# dumps, and bestiary statblocks. They cost prompt budget and add nothing. The calibration sweep
# showed a pure threshold drop (→0.42) would also lose a real combat-rule answer (`CRITICAl HIT`
# @0.439), so instead we drop only chunks whose SHAPE is unambiguous junk — independent of
# distance. Each rule is verified against tools/rag_golden_set.json to catch zero legitimate
# rule answers (no golden-positive heading is a dash-run, a statblock tag, or a picture-text body).

# Heading that is OCR layout noise: a run of dashes used as a fake rule line in the source PDF,
# e.g. '--------------- PSYCHIC POWERS---------------'.
_JUNK_DASH_RUN = re.compile(r"-{4,}")
# Heading that is a creature/NPC statblock entry — '… (eLite)' / '(trOOP)' / '(LeaDer)' (the PDF's
# bestiary tag, OCR-cased). These are stat tables, never a rule answer or useful narration colour.
_JUNK_STATBLOCK = re.compile(r"\((?:elite|troop|leader)\)\s*$", re.IGNORECASE)
# Body that is a scrambled image dump rather than prose — the ingester's picture-text marker.
_JUNK_PICTURE_TEXT = "----- start of picture text -----"


def _is_junk_hit(source: str, heading: str, text: str) -> bool:
    """True for a chunk that is layout/OCR noise, not a real rule or lore passage — dropped from
    the every-turn narration block regardless of distance. Conservative by construction: every
    pattern here was checked against the golden set and matches no legitimate answer."""
    if _JUNK_DASH_RUN.search(heading) or _JUNK_STATBLOCK.search(heading):
        return True
    return _JUNK_PICTURE_TEXT in text.lstrip()[:64].lower()


# Per-thread, per-db-path read connection cache. Retrieval runs inside ``asyncio.to_thread`` (a
# thread pool), so a single shared connection would violate sqlite's threading rules — each thread
# keeps its own. Loading the sqlite-vec extension is a dlopen+init we don't want to repeat on every
# hot turn, so the connection (with the extension already loaded) is reused for the thread's life.
_conn_cache = threading.local()


def _vec_conn(db_path: Path) -> sqlite3.Connection:
    """A vec-loaded sqlite connection for this thread + ``db_path``, created on first use and
    cached. Recreated if a previously cached connection is closed/stale (a probe query fails)."""
    cache: dict[str, sqlite3.Connection] = getattr(_conn_cache, "conns", None)
    if cache is None:
        cache = _conn_cache.conns = {}
    key = str(db_path)
    conn = cache.get(key)
    if conn is not None:
        try:
            conn.execute("SELECT 1")  # cheap liveness probe — catches a closed/stale handle
            return conn
        except sqlite3.Error:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            cache.pop(key, None)
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    cache[key] = conn
    return conn


class RulebookRetriever:
    """Embeds a query and returns the matching rulebook chunks as a German prompt block."""

    def __init__(
        self,
        db_path: Path,
        host: str,
        *,
        k: int = TOP_K,
        max_distance: float = MAX_DISTANCE,
        session_memory: bool = True,
        debug_sessions: bool = False,
    ) -> None:
        self._db_path = db_path
        self._host = host.rstrip("/")
        self._k = k
        self._max_distance = max_distance
        self._session_memory = session_memory  # campaign-memory retrieval (ADR 054) on/off
        # Debug-run sandbox (ADR 055): read the session_debug_<id> source instead of the live
        # one — a debug campaign never sees the real campaign's memories, and vice versa.
        self._debug_sessions = debug_sessions
        self._client: httpx.AsyncClient | None = None
        self._model: str | None = None  # read from the store's meta table on first use

    def available(self) -> bool:
        """True when an ingested store exists — the cog only wires the retriever in then."""
        return self._db_path.is_file()

    def _embed_model(self) -> str:
        """The embedder the store was built with (meta table) — query vectors must match it."""
        if self._model is None:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute("SELECT value FROM meta WHERE key = 'model'").fetchone()
            finally:
                conn.close()
            self._model = row[0] if row else "bge-m3"
        return self._model

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _embed_query(self, query: str) -> list[float]:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        model = await asyncio.to_thread(self._embed_model)
        resp = await self._client.post(
            f"{self._host}/api/embed",
            json={"model": model, "input": [query]},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    def _search(
        self, vector: list[float], sources: tuple[str, ...] | None = None, k: int | None = None
    ) -> list[tuple[str, str, str, float]]:
        """KNN over the store (sync sqlite — run via to_thread).
        → [(source, heading, text, distance)] for the searched sources, best first."""
        sources = sources or tuple(_SOURCES)
        k = k or self._k
        placeholders = ",".join("?" for _ in sources)
        conn = _vec_conn(self._db_path)  # cached per thread + db path; vec extension already loaded
        rows = conn.execute(
            "SELECT c.source, c.heading, c.text, v.distance FROM chunks_vec v "
            "JOIN chunks c ON c.id = v.rowid "
            f"WHERE v.embedding MATCH ? AND v.k = ? AND c.source IN ({placeholders}) "
            "ORDER BY v.distance",
            (json.dumps(vector), k * 3, *sources),  # over-fetch: the filter prunes
        ).fetchall()
        return rows[:k]

    async def lookup(
        self,
        query: str,
        *,
        sources: tuple[str, ...],
        k: int = 2,
        max_distance: float = 0.52,
    ) -> list[tuple[str, str, str, float]]:
        """Explicit lookup (``!lore <frage>``): the matching chunks as raw hits, best first —
        ``[(source, heading, text, distance)]``. Unlike :meth:`fetch_block` this is a direct
        player request, so the ceiling is looser than the per-turn prompt gate (a best-effort
        answer beats silence — narrative phrasings land ~0.48) but still tight enough that an
        off-corpus topic (Tyranids, ~0.54) gets an honest "nothing found" instead of the
        nearest wrong chunk. The caller picks the sources. Degrades to ``[]`` on errors."""
        query = (query or "").strip()
        if not query:
            return []
        try:
            vector = await self._embed_query(query)
            hits = await asyncio.to_thread(self._search, vector, sources, k)
        except Exception:
            log.exception("lore lookup failed")
            return []
        return [hit for hit in hits if hit[3] <= max_distance]

    def _search_session(
        self, vector: list[float], query: str, channel_id: int
    ) -> list[tuple[str, str, str, float, bool]]:
        """Hybrid search over THIS channel's played sessions (sync — run via to_thread):
        KNN under ``SESSION_MAX_DISTANCE`` (with the recency malus applied) merged with an
        exact-term FTS5 lookup — proper-noun recall ("Vosk") is exactly where embeddings are
        weakest. An FTS hit outranks any borderline KNN hit and skips malus + threshold; dedupe
        by chunk id; at most ``SESSION_TOP_K`` rows. → ``[(scene, text, stamp, rank, exact)]``.
        A store without session rows / stamp column / FTS table → ``[]``, never an error."""
        from .ingest_session import session_source

        source = session_source(channel_id, debug=self._debug_sessions)
        conn = _vec_conn(self._db_path)
        try:
            rows = self._knn_sessions(conn, vector, source, SESSION_TOP_K * 3)
            # session age per rotation stamp: 0 = newest ingested session, 1 = the one before, …
            stamps = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT stamp FROM chunks WHERE source = ? ORDER BY stamp DESC",
                    (source,),
                )
            ]
        except sqlite3.OperationalError:
            return []  # pre-session store (no session vec table / stamp column)
        age = {stamp: i for i, stamp in enumerate(stamps)}
        merged: dict[int, tuple[str, str, str, float, bool]] = {}
        for cid, scene, text, stamp, dist in rows:
            rank = dist + age.get(stamp, 0) * SESSION_RECENCY_MALUS
            if rank <= SESSION_MAX_DISTANCE:
                merged[cid] = (scene, text, stamp, rank, False)
        for cid, scene, text, stamp in self._fts_session_hits(conn, query, source):
            merged[cid] = (scene, text, stamp, -1.0, True)  # exact term: outranks, no malus
        ranked = sorted(merged.values(), key=lambda r: (not r[4], r[3]))
        return ranked[:SESSION_TOP_K]

    def _knn_sessions(
        self, conn: sqlite3.Connection, vector: list[float], source: str, k: int
    ) -> list[tuple[int, str, str, str, float]]:
        """Raw KNN over the **separate** session vec table (ADR 054) → ``[(id, scene, text,
        stamp, distance)]``, best first. Sessions get their own vec0 table because ``k`` is
        global per table and the source filter prunes only afterwards — sharing ``chunks_vec``
        would let the book corpus starve session recall (and vice versa). May raise
        ``sqlite3.OperationalError`` on a pre-session store — callers handle it."""
        return conn.execute(
            "SELECT c.id, c.heading, c.text, c.stamp, v.distance FROM session_chunks_vec v "
            "JOIN chunks c ON c.id = v.rowid "
            "WHERE v.embedding MATCH ? AND v.k = ? AND c.source = ? ORDER BY v.distance",
            (json.dumps(vector), k, source),
        ).fetchall()

    def _fts_session_hits(
        self, conn: sqlite3.Connection, query: str, source: str
    ) -> list[tuple[int, str, str, str]]:
        """Exact-term FTS5 hits for the query's rare proper-noun candidates, best bm25 first.
        A term qualifies only when its document frequency in this source is small — recurring
        table vocabulary ("Waffe", "Tür") matches half the transcript and is exactly what the
        KNN threshold already handles; the FTS half exists for the rare name embeddings miss.
        Missing FTS table (old store, no-FTS5 sqlite) → ``[]`` silently."""
        terms = _query_terms(query)
        if not terms:
            return []
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE source = ?", (source,)
            ).fetchone()[0]
            if not total:
                return []
            df_cap = max(3, int(0.15 * total))
            rare = []
            for t in terms:
                df = conn.execute(
                    "SELECT COUNT(*) FROM chunks_fts f JOIN chunks c ON c.id = f.rowid "
                    "WHERE chunks_fts MATCH ? AND c.source = ?",
                    (f'"{t}"', source),
                ).fetchone()[0]
                if 0 < df <= df_cap:
                    rare.append(t)
            if not rare:
                return []
            match = " OR ".join(f'"{t}"' for t in rare)
            return conn.execute(
                "SELECT c.id, c.heading, c.text, c.stamp FROM chunks_fts f "
                "JOIN chunks c ON c.id = f.rowid "
                "WHERE chunks_fts MATCH ? AND c.source = ? "
                "ORDER BY bm25(chunks_fts) LIMIT ?",
                (match, source, SESSION_TOP_K),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    def _session_block(self, hits: list[tuple[str, str, str, float, bool]]) -> str:
        """Render session-memory hits as the ``## Früher in der Kampagne`` prompt block. Each
        chunk already opens with its own ``[Session vom …, Szene: …]`` header line (embedded at
        ingest), so the label carries the caveat and the chunks carry their framing."""
        from .ingest_session import stamp_date_de

        dates = list(dict.fromkeys(stamp_date_de(stamp) for _, _, stamp, _, _ in hits))
        lines = [_SESSION_LABEL.format(dates=" und ".join(dates))]
        for _, text, _, _, _ in hits:
            lines.append(text)
        return "\n".join(lines)

    async def fetch_block(self, query: str, *, channel_id: int | None = None) -> str:
        """The ``## Regelwerk`` / ``## Weltwissen`` prompt block(s) for ``query`` — plus, with a
        ``channel_id``, up to ``SESSION_TOP_K`` campaign memories from that channel's played
        sessions (ADR 054) appended under their own label. ``""`` when nothing is relevant (the
        common case) or anything fails (never breaks a turn)."""
        query = (query or "").strip()
        if not query:
            return ""
        try:
            vector = await self._embed_query(query)
            hits = await asyncio.to_thread(self._search, vector)
        except Exception:
            log.exception("book retrieval failed — turn continues without it")
            return ""
        hits = [
            (s, h, t, d)
            for s, h, t, d in hits
            if d <= self._max_distance and not _is_junk_hit(s, h, t)
        ]
        lines: list[str] = []
        if hits:
            log.info("📚 %s", "; ".join(f"{s}:{h!r} (d={d:.2f})" for s, h, _, d in hits))
            for source, label in _SOURCES.items():  # fixed order: rules ground truth before colour
                grouped = [(h, t) for s, h, t, _ in hits if s == source]
                if not grouped:
                    continue
                if lines:
                    lines.append("")
                lines.append(label)
                for heading, text in grouped:
                    lines.append(f"[Quelle: {heading}]")
                    lines.append(text)
        if self._session_memory and channel_id is not None:
            try:
                shits = await asyncio.to_thread(self._search_session, vector, query, channel_id)
            except Exception:
                log.exception("session-memory retrieval failed — turn continues without it")
                shits = []
            if shits:
                log.info("🗂 %s", "; ".join(
                    f"Szene {scene!r}/{stamp} ({'FTS' if exact else f'd={rank:.2f}'})"
                    for scene, _, stamp, rank, exact in shits
                ))
                if lines:
                    lines.append("")
                lines.append(self._session_block(shits))
        return "\n".join(lines)
