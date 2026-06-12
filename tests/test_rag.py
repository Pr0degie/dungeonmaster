"""Rulebook RAG, stage 3 (Phase 10a, ADR 019): heading-aware chunking (pure) and threshold-gated
retrieval against a tiny fixture store with fake embeddings — no Ollama in the loop.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import sqlite_vec

from dmbot.rag.ingest import chunk_markdown, ensure_schema
from dmbot.rag.retrieve import RulebookRetriever


# --- chunking ----------------------------------------------------------------------------------

def test_chunks_never_cross_headings_and_carry_them() -> None:
    md = (
        "## DIFFICULTY\n" + ("Difficulty rules. " * 30) + "\n"
        "## CRITICAL HIT\n" + ("Crit rules. " * 30) + "\n"
    )
    chunks = chunk_markdown(md)
    headings = [h for h, _ in chunks]
    assert "DIFFICULTY" in headings and "CRITICAL HIT" in headings
    for heading, body in chunks:
        assert "Difficulty rules" not in body or "Crit rules" not in body  # no boundary crossing


def test_chunking_drops_layout_noise_and_tiny_fragments() -> None:
    md = (
        "## A\n**==> picture [43 x 43] intentionally omitted <==**\n339\nIV\nshort\n"
        "## B\n" + ("Real rule text here. " * 10)
    )
    chunks = chunk_markdown(md)
    assert all("picture" not in body and "\n339" not in body for _, body in chunks)
    assert all(len(body) >= 80 for _, body in chunks)  # the 'short' fragment under A is dropped


def test_long_sections_split_into_multiple_chunks() -> None:
    md = "## LONG\n" + ("One sentence of rules. " * 300)
    chunks = chunk_markdown(md)
    assert len(chunks) > 1
    assert all(h == "LONG" for h, _ in chunks)


# --- retrieval (fixture DB, fake 4-dim embeddings) ------------------------------------------------

def _fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "rag.db"
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn, model="fake-embed", dim=4)
    rows = [
        ("rulebook", "DIFFICULTY", "Difficulty ladder rules.", [1.0, 0.0, 0.0, 0.0]),
        ("rulebook", "CRITICAL HIT", "Crit rules.", [0.0, 1.0, 0.0, 0.0]),
        ("setting", "NOBLE HOUSES", "House Castyx rules Rokarth.", [0.9, 0.1, 0.0, 0.0]),
        ("gm_only", "VOLL", "Secret GM lore.", [1.0, 0.05, 0.0, 0.0]),  # near, but unsearched source
        # curated lore compendium (ADR 021) — orthogonal vector, invisible to the queries above
        ("lore_chaos", "DIE VIER CHAOSGOETTER", "Khorne, Nurgle, Tzeentch, Slaanesh.",
         [0.0, 0.0, 1.0, 0.0]),
    ]
    for source, heading, text, vec in rows:
        cur = conn.execute("INSERT INTO chunks (source, heading, text) VALUES (?, ?, ?)",
                           (source, heading, text))
        conn.execute("INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                     (cur.lastrowid, json.dumps(vec)))
    conn.commit()
    conn.close()
    return db


def _retriever(db: Path, query_vec: list[float], **kw) -> RulebookRetriever:
    r = RulebookRetriever(db, "http://unused", **kw)

    async def fake_embed(query: str) -> list[float]:
        return query_vec

    r._embed_query = fake_embed  # type: ignore[method-assign]
    return r


def test_relevant_hit_yields_a_regelwerk_block_with_source(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Wie funktioniert die Schwierigkeit?"))
    assert block.startswith("## Regelwerk")
    assert "[Quelle: DIFFICULTY]" in block and "Difficulty ladder rules." in block
    assert "Secret GM lore." not in block  # unsearched sources stay out (spoiler discipline)


def test_setting_hits_group_under_weltwissen_after_regelwerk(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    # near both the DIFFICULTY rule chunk and the setting chunk → both pass the threshold
    r = _retriever(db, [0.97, 0.05, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Wer regiert Rokarth?"))
    assert "## Weltwissen" in block and "House Castyx rules Rokarth." in block
    assert block.index("## Regelwerk") < block.index("## Weltwissen")  # rules truth before colour


def test_below_threshold_yields_no_block(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    # equidistant-ish from everything → cosine distance above the ceiling → silence
    r = _retriever(db, [0.5, 0.5, 0.5, 0.5], max_distance=0.2)
    assert asyncio.run(r.fetch_block("ich gehe zur Tür")) == ""


def test_empty_query_and_failures_degrade_to_no_block(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    r = RulebookRetriever(db, "http://unused")
    assert asyncio.run(r.fetch_block("  ")) == ""

    async def boom(query: str) -> list[float]:
        raise RuntimeError("ollama down")

    r._embed_query = boom  # type: ignore[method-assign]
    assert asyncio.run(r.fetch_block("Regelfrage?")) == ""  # never breaks a turn


def test_availability_reflects_the_store_file(tmp_path) -> None:
    assert not RulebookRetriever(tmp_path / "missing.db", "http://x").available()
    assert RulebookRetriever(_fixture_db(tmp_path), "http://x").available()


def test_meta_table_pins_the_embedding_model(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    r = RulebookRetriever(db, "http://unused")
    assert r._embed_model() == "fake-embed"  # queries must use whatever built the store


def test_lore_hit_yields_a_weltwissen_block(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    r = _retriever(db, [0.0, 0.0, 1.0, 0.0])
    block = asyncio.run(r.fetch_block("Wer sind die Chaosgötter?"))
    assert block.startswith("## Weltwissen")
    assert "[Quelle: DIE VIER CHAOSGOETTER]" in block
    assert "Khorne, Nurgle, Tzeentch, Slaanesh." in block


def test_block_order_rules_then_lore_then_setting(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    # near the rulebook, lore, AND setting chunks at once → all three pass the threshold
    r = _retriever(db, [0.6, 0.0, 0.6, 0.0], k=4)
    block = asyncio.run(r.fetch_block("Imperium und Chaos und Rokarth?"))
    assert block.index("## Regelwerk") < block.index("Chaos — verbotenes Wissen")
    assert block.index("Chaos — verbotenes Wissen") < block.index("lokaler Hintergrund")
