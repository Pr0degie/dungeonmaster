"""Rulebook ingestion — stage 3 of the hybrid (Phase 10a, ADR 019): md → chunks → embeddings → sqlite-vec.

OFFLINE CLI, not the bot runtime (like ``tools/pdf_to_md.py``, which produces its input):

    uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium Maledictum Core Rulebook.md" --source rulebook

Heading-aware chunking (a chunk never crosses a ``#`` heading, so a retrieved rule passage carries
its section title as the source), embeddings via Ollama's ``/api/embed`` (``bge-m3``, multilingual —
see the ``EMBED_MODEL`` note below for why not nomic, and ``embed_texts`` re task prefixes), stored
in ``data/vectordb/rag.db`` (sqlite-vec, cosine distance). Re-running with the same ``--source``
replaces that source's rows. The adventure is deliberately NOT ingested — scene cards cover it,
and similarity search would surface part-3 spoilers in part 1 (ADR 019).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import httpx
import sqlite_vec

# Default embedder: bge-m3 (multilingual) — the play language is German but the rulebook is
# English; nomic-embed-text (D28's pick) barely aligns DE queries with EN text (verified against
# real rule questions, ADR 019). The store remembers its model+dim in a meta table, so the
# retriever always queries with whatever the store was built with.
EMBED_MODEL = "bge-m3"
CHUNK_CHARS = 1600  # ≈ 400 tokens of German/English prose
EMBED_BATCH = 32

# Lines that are layout noise in pdf_to_md output: omitted pictures and bare page numbers.
_NOISE = re.compile(r"^\s*(\*\*==> picture .*<==\*\*|\d{1,3}|[IVX]+)\s*$")


def _split_long_line(line: str) -> list[str]:
    """pdf_to_md emits one whole paragraph per line — split an overlong one at sentence ends so a
    chunk stays near CHUNK_CHARS instead of swallowing a page-long paragraph."""
    if len(line) <= CHUNK_CHARS:
        return [line]
    pieces: list[str] = []
    buf = ""
    for sent in re.split(r"(?<=[.!?])\s+", line):
        if buf and len(buf) + len(sent) + 1 > CHUNK_CHARS:
            pieces.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf:
        pieces.append(buf)
    return pieces


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split markdown into ``(heading, chunk_text)`` pairs of ~CHUNK_CHARS, never crossing a
    heading boundary. Pure + unit-testable."""
    chunks: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if len(body) >= 80:  # drop heading-only / noise-only fragments
            chunks.append((heading, body))
        buf.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            flush()
            heading = line.lstrip("# ").replace("*", "").strip()
            continue
        if _NOISE.match(line):
            continue
        for piece in _split_long_line(line):
            buf.append(piece)
            if sum(len(b) + 1 for b in buf) >= CHUNK_CHARS:
                flush()
    flush()
    return chunks


def embed_texts(
    host: str, texts: list[str], *, model: str = EMBED_MODEL, prefix: str = ""
) -> list[list[float]]:
    """Embed ``texts`` via Ollama ``/api/embed`` (batched). ``prefix`` carries a task prefix for
    models that want one (nomic: ``search_document: ``; bge-m3 needs none)."""
    out: list[list[float]] = []
    with httpx.Client(timeout=300.0) as client:
        for i in range(0, len(texts), EMBED_BATCH):
            batch = [prefix + t for t in texts[i : i + EMBED_BATCH]]
            resp = client.post(f"{host.rstrip('/')}/api/embed",
                               json={"model": model, "input": batch})
            resp.raise_for_status()
            out.extend(resp.json()["embeddings"])
    return out


def ensure_schema(conn: sqlite3.Connection, *, model: str, dim: int) -> None:
    """Create (or, on a model/dim change, drop + recreate) the store. The meta table pins which
    embedder built the store, so the retriever always queries with the matching model. It also
    carries one ``ingested:<source>`` row per source (set by ``ingest``) — a human-readable
    ingest timestamp for ``dm-sync`` (``dmbot/tools/sync_check.py``); DBs built before the row
    existed simply lack
    it and read as unknown."""
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    stored = dict(conn.execute("SELECT key, value FROM meta"))
    if stored and (stored.get("model") != model or stored.get("dim") != str(dim)):
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.execute("DROP TABLE IF EXISTS chunks_vec")
        conn.execute("DELETE FROM meta WHERE key LIKE 'ingested:%'")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, source TEXT NOT NULL, "
        "heading TEXT NOT NULL, text TEXT NOT NULL)"
    )
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0("
        f"embedding float[{dim}] distance_metric=cosine)"
    )
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('model', ?)", (model,))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('dim', ?)", (str(dim),))


def ingest(md_path: Path, *, source: str, db_path: Path, host: str, model: str = EMBED_MODEL) -> int:
    """Chunk + embed ``md_path`` and (re)write its rows under ``source``. Returns chunk count."""
    text = md_path.read_text(encoding="utf-8")
    chunks = chunk_markdown(text)
    if not chunks:
        return 0
    vectors = embed_texts(host, [body for _, body in chunks], model=model)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        ensure_schema(conn, model=model, dim=len(vectors[0]))
        # replace this source wholesale (re-ingestion = idempotent)
        old = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE source = ?", (source,))]
        if old:
            conn.executemany("DELETE FROM chunks_vec WHERE rowid = ?", [(i,) for i in old])
            conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
        for (heading, body), vec in zip(chunks, vectors):
            cur = conn.execute(
                "INSERT INTO chunks (source, heading, text) VALUES (?, ?, ?)",
                (source, heading, body),
            )
            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (cur.lastrowid, json.dumps(vec)),
            )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (f"ingested:{source}", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()
    finally:
        conn.close()
    return len(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a markdown book into the RAG store.")
    parser.add_argument("md", type=Path, help="markdown file (from tools/pdf_to_md.py)")
    parser.add_argument("--source", default="rulebook", help="source tag (default: rulebook)")
    parser.add_argument("--db", type=Path, default=Path("data/vectordb/rag.db"))
    parser.add_argument("--host", default=None, help="Ollama host (default: OLLAMA_HOST env)")
    parser.add_argument("--model", default=EMBED_MODEL, help=f"embedding model (default: {EMBED_MODEL})")
    args = parser.parse_args()
    import os

    host = args.host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if not args.md.is_file():
        print(f"[!!] not found: {args.md}")
        return 1
    print(f"[..] chunking + embedding {args.md.name} (source={args.source}, model={args.model}) via {host} ...")
    n = ingest(args.md, source=args.source, db_path=args.db, host=host, model=args.model)
    print(f"[OK] {n} chunks -> {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
