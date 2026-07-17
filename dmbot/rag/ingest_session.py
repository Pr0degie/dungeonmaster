"""Session-transcript ingestion (ADR 054): rotated ``history.jsonl`` → per-scene chunks → rag.db.

Campaign memory over *played* sessions: on ``!leave`` the freshly rotated
``data/sessions/<channel_id>/history.<stamp>.jsonl`` is chunked per scene (the ADR 053
``{"kind": "scene"}`` events are the boundaries), embedded and stored in the existing sqlite-vec
store under the source ``session_<channel_id>``, so the retriever can pull episodic memories back
into the prompt weeks later ("Was hat der Händler Vosk in Session 3 gesagt?"). This sharpens the
ADR 019 spoiler boundary rather than weakening it: only what was actually *played* is ever
ingested — the adventure text stays out of the store.

Never ingests the live ``history.jsonl`` (the current session is already in the prompt as
history); only stamped, rotated files. Re-ingesting a stamp is a transactional delete+insert
(idempotent, mirroring the rulebook ingester's ``--source`` replace); the meta table records each
ingested stamp so the ``!join`` catch-up scan (crash recovery + backfill) only picks up missing
ones. Alongside the vectors an FTS5 table over the chunk text is maintained for exact-term
proper-noun recall — where embeddings are weakest. No LLM anywhere: raw transcript chunks only.

Debug-run sandbox (ADR 055): debug-campaign runs share the live channel's session directory,
so their rotated archives carry a ``.debug`` filename marker and route — by filename alone —
into the separate source ``session_debug_<channel_id>``. Cross-contamination with the live
campaign's memory is structurally impossible in both directions.

Runtime callers run everything here via ``asyncio.to_thread`` and degrade silently (log only).
Manual runs:

    uv run python -m dmbot.rag.ingest_session data/sessions/<channel_id>
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import sqlite_vec

from .ingest import CHUNK_CHARS, EMBED_MODEL, embed_texts, ensure_schema

log = logging.getLogger(__name__)

# Rotated-journal filename → rotation stamp (memory/history.rotate uses %Y%m%d-%H%M%S). The
# pattern deliberately does NOT match the live ``history.jsonl``. The optional ``.debug``
# marker is the debug-run sandbox (ADR 055): debug-campaign runs share the live channel's
# session directory, so their archives carry the marker and route to a separate source.
_STAMP_RE = re.compile(r"^history\.(?P<stamp>\d{8}-\d{6})(?P<debug>\.debug)?\.jsonl$")


def session_source(channel_id: int | str, *, debug: bool = False) -> str:
    """The store's source tag for one channel's played sessions — retrieval resolves the active
    channel to exactly this source, so other channels' sessions are never searched. Debug-run
    archives (ADR 055) get their own ``session_debug_<channel_id>`` sandbox source: a debug
    campaign played in the live channel must never write into — or be read back from — the
    real campaign's memory."""
    return f"session_debug_{channel_id}" if debug else f"session_{channel_id}"


def is_debug_archive(path: Path) -> bool:
    """True iff ``path`` is a debug-run archive (``history.<stamp>.debug.jsonl``, ADR 055).
    Routing keys on the filename alone, so a ``.debug`` file can never reach the live source
    regardless of the caller's mode — and vice versa."""
    m = _STAMP_RE.match(Path(path).name)
    return bool(m and m.group("debug"))


def stamp_date_de(stamp: str) -> str:
    """``20260712-213045`` → ``12.07.2026`` for the chunk header / prompt label; anything
    unparseable → ``"unbekannt"`` (manual ingests of oddly named files)."""
    try:
        return datetime.strptime(stamp.split("-")[0], "%Y%m%d").strftime("%d.%m.%Y")
    except ValueError:
        return "unbekannt"


# --- journal → chunks (pure, unit-tested) --------------------------------------------------------

def load_journal(path: Path) -> list[dict]:
    """Read one journal's records in order, with ``load_recent``'s redo semantics applied: a
    ``redo`` turn *replaces* the previous turn (wherever it sits between scene events), so a
    superseded answer never reaches the store. Scene events pass through as boundaries; other
    typed events (session headers) and corrupt/torn lines are skipped."""
    items: list[dict] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue  # torn tail line — tolerated exactly like load_recent
        if rec.get("kind") == "scene":
            items.append(rec)
            continue
        if rec.get("user_msg") is None or rec.get("answer") is None:
            continue  # session header / unknown event kinds
        if rec.get("redo"):
            for i in range(len(items) - 1, -1, -1):
                if "user_msg" in items[i]:
                    items[i] = rec
                    break
            else:
                items.append(rec)
        else:
            items.append(rec)
    return items


def _render_turn(rec: dict) -> str:
    """One turn as plain transcript text. ``user_msg`` already carries the ``Name: text`` /
    ``[Würfel]`` lines the DM saw; the answer is labeled as the Spielleitung's."""
    return f"{rec.get('user_msg', '').strip()}\nSpielleitung: {rec.get('answer', '').strip()}"


def chunk_session(
    items: list[dict], *, stamp: str, chunk_chars: int = CHUNK_CHARS
) -> list[tuple[str, str]]:
    """Chunk one session's journal items into ``(scene_id, chunk_text)`` pairs.

    Scene events are hard boundaries; a scene exceeding ``chunk_chars`` is split into turn
    groups at turn boundaries (never mid-turn — one oversized turn stays one chunk). Journals
    without scene events (pre-ADR-053 backfill) fall through to pure size-based turn groups
    under scene ``"unbekannt"``. Consecutive events with the same scene id (crash-restored
    sessions, ADR 053) are not boundaries. Each chunk opens with a header line embedded *in*
    the text — ``[Session vom <Datum>, Szene: <id>]`` — anchoring the embedding and giving the
    DM the temporal framing for free."""
    date = stamp_date_de(stamp)
    chunks: list[tuple[str, str]] = []
    scene = ""
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        scene_label = scene or "unbekannt"
        header = f"[Session vom {date}, Szene: {scene_label}]"
        chunks.append((scene_label, "\n".join([header, *buf])))
        buf.clear()

    for rec in items:
        if rec.get("kind") == "scene":
            new_scene = str(rec.get("scene_id") or "")
            if new_scene != scene:
                flush()
                scene = new_scene
            continue
        buf.append(_render_turn(rec))
        if sum(len(b) + 1 for b in buf) >= chunk_chars:
            flush()
    flush()
    return chunks


# --- store bookkeeping ---------------------------------------------------------------------------

def _ensure_session_schema(conn: sqlite3.Connection, *, dim: int) -> None:
    """Session extras on top of :func:`ensure_schema`: the ``stamp`` column on ``chunks`` (empty
    for rulebook/lore rows — pre-session stores gain it in place, no migration system), a
    **separate** vec0 table for the session vectors, and the FTS5 table for exact-term recall.
    Session vectors get their own table because vec0's ``k`` is global per table (the source
    filter prunes *after* the KNN): sharing ``chunks_vec`` would let thousands of book chunks
    starve the session top-k — and session vectors would shrink the book path's candidate pool,
    breaking its zero-behavior-change guarantee. An sqlite built without FTS5 just skips that
    table — retrieval degrades to pure KNN."""
    try:
        conn.execute("ALTER TABLE chunks ADD COLUMN stamp TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already there
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS session_chunks_vec USING vec0("
        f"embedding float[{dim}] distance_metric=cosine)"
    )
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text)")
    except sqlite3.OperationalError:
        log.warning("sqlite has no FTS5 — session retrieval will run KNN-only")


def _store_model(db_path: Path) -> str | None:
    """The embedder an existing store was built with (meta table), or ``None`` without a store.
    The session ingest must always embed with the store's own model — passing a different one
    into :func:`ensure_schema` would drop the whole store, rulebook included."""
    if not Path(db_path).is_file():
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'model'").fetchone()
    except sqlite3.OperationalError:
        return None  # no meta table yet
    finally:
        conn.close()
    return row[0] if row else None


def ingested_stamps(db_path: Path, source: str) -> set[str]:
    """The rotation stamps already ingested for ``source`` (meta table) — the catch-up's
    dedupe. Missing store / meta table → empty set."""
    if not Path(db_path).is_file():
        return set()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT key FROM meta WHERE key LIKE ?", (f"session_ingested:{source}:%",)
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()
    prefix = f"session_ingested:{source}:"
    return {r[0][len(prefix):] for r in rows}


def pending_files(session_dir: Path, *, db_path: Path, debug: bool = False) -> list[Path]:
    """The rotated journals in ``session_dir`` whose stamp is not in the meta table yet, oldest
    first — the ``!join`` catch-up (covers crashes, shutdown-during-ingest, and the one-time
    backfill of pre-feature sessions). The live ``history.jsonl`` never matches. Only archives
    of the requested mode are returned (ADR 055): a debug run's catch-up sees only ``.debug``
    files, a normal run's only plain ones — the other mode's archives are structurally
    invisible, in both directions."""
    session_dir = Path(session_dir)
    if not session_dir.is_dir():
        return []
    done = ingested_stamps(db_path, session_source(session_dir.name, debug=debug))
    out = []
    for p in sorted(session_dir.iterdir()):
        m = _STAMP_RE.match(p.name)
        if m and bool(m.group("debug")) == debug and m.group("stamp") not in done:
            out.append(p)
    return out


def ingest_session_file(
    path: Path, *, channel_id: int | str, db_path: Path, host: str, model: str | None = None
) -> int:
    """Chunk + embed one rotated journal and (re)write its rows under
    ``session_<channel_id>``. Idempotent per stamp: existing rows for the same stamp are
    replaced in the same transaction (vec + FTS + chunk rows), and the stamp is recorded in
    the meta table — even for a journal that yields no chunks, so the catch-up doesn't retry
    it forever. Returns the chunk count."""
    path = Path(path)
    m = _STAMP_RE.match(path.name)
    stamp = m.group("stamp") if m else path.stem.removeprefix("history.")
    # Routing keys on the filename (ADR 055): a ``.debug`` archive always lands in the debug
    # sandbox source, a plain one always in the live source — no caller can cross-route.
    source = session_source(channel_id, debug=is_debug_archive(path))
    model = _store_model(db_path) or model or EMBED_MODEL
    items = load_journal(path)
    chunks = chunk_session(items, stamp=stamp)
    if not chunks and not db_path.is_file():
        # nothing to store and no store to record the stamp in — don't create a bare rag.db
        # (available() would wire the retriever against an empty store); catch-up simply
        # re-reads this journal next join, which stays a cheap no-op.
        return 0
    vectors = embed_texts(host, [body for _, body in chunks], model=model) if chunks else []
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        if vectors:
            ensure_schema(conn, model=model, dim=len(vectors[0]))
            _ensure_session_schema(conn, dim=len(vectors[0]))
            old = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM chunks WHERE source = ? AND stamp = ?", (source, stamp)
                )
            ]
            for rowid in old:
                conn.execute("DELETE FROM session_chunks_vec WHERE rowid = ?", (rowid,))
                try:
                    conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (rowid,))
                except sqlite3.OperationalError:
                    pass  # no FTS5 build
            if old:
                conn.execute(
                    "DELETE FROM chunks WHERE source = ? AND stamp = ?", (source, stamp)
                )
            for (scene, body), vec in zip(chunks, vectors):
                cur = conn.execute(
                    "INSERT INTO chunks (source, heading, text, stamp) VALUES (?, ?, ?, ?)",
                    (source, scene, body, stamp),
                )
                # sqlite reuses freed ids (INTEGER PRIMARY KEY = max+1): clear any stale
                # mirror row first, so a leftover from an interrupted/older ingest can never
                # fail the insert — the mirrors self-heal instead
                conn.execute("DELETE FROM session_chunks_vec WHERE rowid = ?", (cur.lastrowid,))
                conn.execute(
                    "INSERT INTO session_chunks_vec (rowid, embedding) VALUES (?, ?)",
                    (cur.lastrowid, json.dumps(vec)),
                )
                try:
                    conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cur.lastrowid,))
                    conn.execute(
                        "INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)",
                        (cur.lastrowid, body),
                    )
                except sqlite3.OperationalError:
                    pass
        else:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (
                f"session_ingested:{source}:{stamp}",
                datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return len(chunks)


def wipe_debug_source(db_path: Path, channel_id: int | str) -> int:
    """Delete every row of the debug-run sandbox source ``session_debug_<channel_id>`` (ADR 055):
    chunk rows, their vec + FTS mirrors, and the ingested-stamp bookkeeping — so a debug-campaign
    reset can re-ingest from scratch. The live ``session_<channel_id>`` rows are never touched.
    Returns the removed chunk count; a missing store or missing tables → 0, never an error."""
    if not Path(db_path).is_file():
        return 0
    source = session_source(channel_id, debug=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        try:
            ids = [
                r[0] for r in conn.execute("SELECT id FROM chunks WHERE source = ?", (source,))
            ]
        except sqlite3.OperationalError:
            ids = []  # store without a chunks table
        for rowid in ids:
            for table in ("session_chunks_vec", "chunks_fts"):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))
                except sqlite3.OperationalError:
                    pass  # mirror table absent (no-FTS5 build / pre-session store)
        if ids:
            conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
        try:
            conn.execute(
                "DELETE FROM meta WHERE key LIKE ?", (f"session_ingested:{source}:%",)
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()
    return len(ids)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest rotated session journals into the RAG store (campaign memory)."
    )
    parser.add_argument(
        "path", type=Path, nargs="?",
        help="a session dir (data/sessions/<channel_id>; ingests missing stamps) "
             "or one rotated history.<stamp>.jsonl (always re-ingested)",
    )
    parser.add_argument("--channel", default=None,
                        help="channel id (default: the session dir's name)")
    parser.add_argument("--db", type=Path, default=Path("data/vectordb/rag.db"))
    parser.add_argument("--host", default=None, help="Ollama host (default: OLLAMA_HOST env)")
    parser.add_argument(
        "--wipe-debug", metavar="CHANNEL_ID", default=None,
        help="delete the debug-run sandbox source session_debug_<CHANNEL_ID> from the store "
             "(debug-campaign reset, ADR 055); live session rows stay untouched",
    )
    args = parser.parse_args()
    import os

    if args.wipe_debug is not None:
        n = wipe_debug_source(args.db, args.wipe_debug)
        print(f"[OK] wiped {n} chunks (source={session_source(args.wipe_debug, debug=True)})")
        return 0
    if args.path is None:
        parser.error("path is required (unless --wipe-debug is given)")
    host = args.host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if args.path.is_dir():
        channel = args.channel or args.path.name
        # manual runs backfill both modes; each file still routes by its own name
        files = pending_files(args.path, db_path=args.db) + pending_files(
            args.path, db_path=args.db, debug=True
        )
        if not files:
            print("[OK] nothing pending — all rotated sessions already ingested")
            return 0
    elif args.path.is_file():
        if not _STAMP_RE.match(args.path.name):
            # the live history.jsonl (or an oddly named copy) — the current session is in the
            # prompt as history and must never echo back through retrieval. Rotate first.
            print(f"[!!] refusing {args.path.name}: only rotated history.<stamp>.jsonl files "
                  f"are ingested (never the live journal)")
            return 1
        channel = args.channel or args.path.parent.name
        files = [args.path]
    else:
        print(f"[!!] not found: {args.path}")
        return 1
    for f in files:
        n = ingest_session_file(f, channel_id=channel, db_path=args.db, host=host)
        src = session_source(channel, debug=is_debug_archive(f))
        print(f"[OK] {f.name}: {n} chunks -> {args.db} (source={src})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
