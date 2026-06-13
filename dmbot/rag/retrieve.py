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
import sqlite3
from pathlib import Path

import httpx
import sqlite_vec

log = logging.getLogger(__name__)

# Cosine *distance* (1 − similarity) ceiling for a chunk to count as relevant. Generous enough
# for paraphrased German questions against English rule text, tight enough that table talk
# ("ich greife ihn an") doesn't drag rule chunks into every prompt. Tune against live logs.
MAX_DISTANCE = 0.45
TOP_K = 3  # total across both sources — lore may colour a scene, not flood the prompt

# Searched sources and their prompt labels, in block order (rules ground truth before colour,
# broad lore before local Rokarth colour). The curated German lore compendium (ADR 021) ships
# as two sources so either half can be re-authored + re-ingested without touching the other.
_SOURCES: dict[str, str] = {
    "rulebook": "## Regelwerk (Auszüge aus dem Regelbuch — Grundlage für Regelfragen)",
    "player_guide": "## Regelwerk (Inquisition Player's Guide — Psikräfte, Talente, Ausrüstung)",
    "lore_imperium": "## Weltwissen (Imperium — Hintergrund, nur als Färbung nutzen)",
    "lore_chaos": "## Weltwissen (Chaos — verbotenes Wissen, nur als Färbung nutzen)",
    "setting": "## Weltwissen (Hive Rokarth — lokaler Hintergrund, nur als Färbung nutzen)",
    "gm_guide": "## Weltwissen (Inquisition — Ordos, Philosophien & Methoden)",
}


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

    def _search(
        self, vector: list[float], sources: tuple[str, ...] | None = None, k: int | None = None
    ) -> list[tuple[str, str, str, float]]:
        """KNN over the store (sync sqlite — run via to_thread).
        → [(source, heading, text, distance)] for the searched sources, best first."""
        sources = sources or tuple(_SOURCES)
        k = k or self._k
        placeholders = ",".join("?" for _ in sources)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            rows = conn.execute(
                "SELECT c.source, c.heading, c.text, v.distance FROM chunks_vec v "
                "JOIN chunks c ON c.id = v.rowid "
                f"WHERE v.embedding MATCH ? AND v.k = ? AND c.source IN ({placeholders}) "
                "ORDER BY v.distance",
                (json.dumps(vector), k * 3, *sources),  # over-fetch: the filter prunes
            ).fetchall()
        finally:
            conn.close()
        return [(s, h, t, d) for s, h, t, d in rows][:k]

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
        return [(s, h, t, d) for s, h, t, d in hits if d <= max_distance]

    async def fetch_block(self, query: str) -> str:
        """The ``## Regelwerk`` / ``## Weltwissen`` prompt block(s) for ``query``, or ``""`` when
        nothing is relevant (the common case) or anything fails (never breaks a turn)."""
        query = (query or "").strip()
        if not query:
            return ""
        try:
            vector = await self._embed_query(query)
            hits = await asyncio.to_thread(self._search, vector)
        except Exception:
            log.exception("book retrieval failed — turn continues without it")
            return ""
        hits = [(s, h, t, d) for s, h, t, d in hits if d <= self._max_distance]
        if not hits:
            return ""
        log.info("📚 %s", "; ".join(f"{s}:{h!r} (d={d:.2f})" for s, h, _, d in hits))
        lines: list[str] = []
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
        return "\n".join(lines)
