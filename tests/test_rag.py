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
from dmbot.rag.retrieve import RulebookRetriever, _is_junk_hit


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


def test_lookup_filters_to_the_requested_sources(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    # near BOTH the rulebook chunk and the lore chunk — but only lore sources are searched
    r = _retriever(db, [0.6, 0.0, 0.6, 0.0])
    hits = asyncio.run(r.lookup("Chaosgötter?", sources=("lore_chaos", "setting")))
    assert hits and all(s in ("lore_chaos", "setting") for s, _, _, _ in hits)
    assert any(h == "DIE VIER CHAOSGOETTER" for _, h, _, _ in hits)
    assert not any(s == "rulebook" for s, _, _, _ in hits)


# --- junk filter (live tuning after ADR 025) ------------------------------------------------------

def test_is_junk_hit_classifies_ocr_noise_but_spares_real_answers() -> None:
    # junk SHAPES dropped regardless of distance: dash-run heading, statblock tag, picture-text body
    assert _is_junk_hit("player_guide", "--------------- PSYCHIC POWERS---------------", "x")
    assert _is_junk_hit("rulebook", "PLaGUeBearer (eLite)", "stat line")
    assert _is_junk_hit("rulebook", "CULtist (trOOP)", "stat line")
    assert _is_junk_hit("rulebook", "COMMissar (LeaDer)", "stat line")
    assert _is_junk_hit("player_guide", "NAME", "**----- Start of picture text -----**<br>NAME WR")
    # real rule answers (these exact headings are golden-set positives) are NOT junk
    assert not _is_junk_hit("rulebook", "CRITICAl HIT", "If you roll a Critical on your attack Test…")
    assert not _is_junk_hit("conditions", "Blutend (Bleeding)", "Der Charakter verliert…")
    assert not _is_junk_hit("rulebook", "COVeR", "There are three types of cover…")
    # a statblock word in the middle of a real heading must not trip the end-anchored tag
    assert not _is_junk_hit("rulebook", "ELITE TROOPS AND THEIR ROLE", "rules about elite units")


def test_junk_heading_is_filtered_even_within_threshold(tmp_path) -> None:
    """A chunk close enough to pass the distance gate is still dropped if its heading is OCR junk,
    so a pure-narration turn whose nearest neighbour is a statblock injects nothing."""
    db = tmp_path / "rag.db"
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn, model="fake-embed", dim=4)
    # only chunk in the store is a bestiary statblock, sitting right on the query vector (d≈0)
    cur = conn.execute(
        "INSERT INTO chunks (source, heading, text) VALUES (?, ?, ?)",
        ("rulebook", "WARRIOR (eLite)", "WS 45 BS 30 — a flavour statblock, not a rule."),
    )
    conn.execute(
        "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
        (cur.lastrowid, json.dumps([1.0, 0.0, 0.0, 0.0])),
    )
    conn.commit()
    conn.close()
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])  # exact match → distance 0, well under the ceiling
    assert asyncio.run(r.fetch_block("ich setze mich an den Tisch und warte")) == ""


def test_lookup_respects_ceiling_and_degrades_silently(tmp_path) -> None:
    db = _fixture_db(tmp_path)
    r = _retriever(db, [0.7, 0.0, 0.7, 0.0])  # ~0.29 cosine distance from the lore chunk
    assert asyncio.run(r.lookup("x", sources=("lore_chaos",), max_distance=0.1)) == []
    assert asyncio.run(r.lookup("  ", sources=("lore_chaos",))) == []

    async def boom(query: str) -> list[float]:
        raise RuntimeError("ollama down")

    r._embed_query = boom  # type: ignore[method-assign]
    assert asyncio.run(r.lookup("Frage?", sources=("lore_chaos",))) == []  # never breaks the command
