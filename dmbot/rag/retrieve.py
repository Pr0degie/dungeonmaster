"""Rulebook retrieval — the runtime half of stage 3 (Phase 10a, ADR 019).

Per DM turn the brain asks for a ``## Regelwerk`` block for the current player input: embed the
query (Ollama ``/api/embed``, async) and KNN-search the sqlite-vec store **with a distance
threshold** — most turns are narration, not rule questions, so most turns get no block at all and
the prompt stays lean. Only ``source='rulebook'`` rows are searched; the adventure never enters
the vector store (spoiler discipline, ADR 019). Degrades silently: no DB / Ollama hiccup → no
block, never a broken turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path

import httpx
import sqlite_vec

log = logging.getLogger(__name__)

# Cosine *distance* (1 − similarity) ceiling for a chunk to count as relevant. Generous enough
# for paraphrased German questions against English rule text, tight enough that table talk
# ("ich greife ihn an") doesn't drag rule chunks into every prompt. Tune against live logs.
MAX_DISTANCE = 0.45
TOP_K = 2


class RulebookRetriever:
    """Embeds a query and returns the matching rulebook chunks as a German prompt block."""

    def __init__(
        self,
        db_path: Path,
        host: str,
        *,
        k: int = TOP_K,
        max_distance: float = MAX_DISTANCE,
    ) -> None:
        self._db_path = db_path
        self._host = host.rstrip("/")
        self._k = k
        self._max_distance = max_distance
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

    def _search(self, vector: list[float]) -> list[tuple[str, str, float]]:
        """KNN over the store (sync sqlite — run via to_thread). → [(heading, text, distance)]."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            rows = conn.execute(
                "SELECT c.heading, c.text, v.distance FROM chunks_vec v "
                "JOIN chunks c ON c.id = v.rowid "
                "WHERE v.embedding MATCH ? AND v.k = ? AND c.source = 'rulebook' "
                "ORDER BY v.distance",
                (json.dumps(vector), self._k * 3),  # over-fetch: the source filter prunes
            ).fetchall()
        finally:
            conn.close()
        return [(h, t, d) for h, t, d in rows][: self._k]

    async def fetch_block(self, query: str) -> str:
        """The ``## Regelwerk`` prompt block for ``query``, or ``""`` when nothing is relevant
        (the common case) or anything fails (never breaks a turn)."""
        query = (query or "").strip()
        if not query:
            return ""
        try:
            vector = await self._embed_query(query)
            hits = await asyncio.to_thread(self._search, vector)
        except Exception:
            log.exception("rulebook retrieval failed — turn continues without it")
            return ""
        hits = [(h, t, d) for h, t, d in hits if d <= self._max_distance]
        if not hits:
            return ""
        log.info("📚 Regelwerk: %s", "; ".join(f"{h!r} (d={d:.2f})" for h, _, d in hits))
        lines = ["## Regelwerk (Auszüge aus dem Regelbuch — Grundlage für Regelfragen)"]
        for heading, text, _ in hits:
            lines.append(f"[Quelle: {heading}]")
            lines.append(text)
        return "\n".join(lines)
