"""Campaign-memory retrieval (ADR 054): hybrid KNN+FTS over played sessions against a fixture
store with fake embeddings — budget, threshold, recency, channel isolation, the exact-term FTS
rescue and every degrade-silently path. The rulebook/lore path must stay byte-identical
(pinned by tests/test_rag.py — nothing here touches it).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import sqlite_vec

from dmbot.rag.ingest import ensure_schema
from dmbot.rag.ingest_session import _ensure_session_schema
from dmbot.rag.retrieve import (
    SESSION_MAX_DISTANCE,
    RulebookRetriever,
    _query_terms,
)

OLD, NEW = "20260601-200000", "20260712-213045"


def _store(tmp_path: Path, session_rows, *, fts: bool = True) -> Path:
    """Fixture store: one rulebook chunk plus the given session rows
    ``(source, scene, text, stamp, vec)``. 4-dim fake embeddings like tests/test_rag.py.
    Session vectors go into their own ``session_chunks_vec`` (ADR 054) — vec0's ``k`` is
    global per table, so sharing would let the corpora starve each other."""
    db = tmp_path / "rag.db"
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn, model="fake-embed", dim=4)
    _ensure_session_schema(conn, dim=4)
    rows = [("rulebook", "DIFFICULTY", "Difficulty ladder rules.", "", [1.0, 0.0, 0.0, 0.0])]
    rows += session_rows
    for source, heading, text, stamp, vec in rows:
        cur = conn.execute(
            "INSERT INTO chunks (source, heading, text, stamp) VALUES (?, ?, ?, ?)",
            (source, heading, text, stamp),
        )
        vec_table = "session_chunks_vec" if source.startswith("session_") else "chunks_vec"
        conn.execute(f"INSERT INTO {vec_table} (rowid, embedding) VALUES (?, ?)",
                     (cur.lastrowid, json.dumps(vec)))
        if fts:
            conn.execute("INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)",
                         (cur.lastrowid, text))
    conn.commit()
    conn.close()
    return db


def _retriever(db: Path, query_vec: list[float], **kw) -> RulebookRetriever:
    r = RulebookRetriever(db, "http://unused", **kw)

    async def fake_embed(query: str) -> list[float]:
        return query_vec

    r._embed_query = fake_embed  # type: ignore[method-assign]
    return r


def _chunk(scene: str, body: str, stamp: str, vec, channel: str = "42"):
    text = f"[Session vom 12.07.2026, Szene: {scene}]\n{body}"
    return (f"session_{channel}", scene, text, stamp, vec)


# --- KNN half ----------------------------------------------------------------------------------

def test_close_session_chunk_yields_the_memory_block_after_the_rulebook(tmp_path) -> None:
    db = _store(tmp_path, [
        _chunk("sz_markt", "Spielleitung: Der Händler mustert euch.", NEW, [0.9, 0.44, 0.0, 0.0]),
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Wie funktioniert die Schwierigkeit?", channel_id=42))
    assert "## Früher in der Kampagne" in block
    assert "kann veraltet sein" in block and "haben immer Vorrang" in block
    assert "[Session vom 12.07.2026, Szene: sz_markt]" in block
    assert block.index("## Regelwerk") < block.index("## Früher in der Kampagne")


def test_session_budget_is_two_on_top_of_the_rulebook_top_k(tmp_path) -> None:
    db = _store(tmp_path, [
        _chunk(f"sz_{i}", f"Erinnerung {i}.", NEW, [0.95, 0.05 * (i + 1), 0.0, 0.0])
        for i in range(4)
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Wie funktioniert die Schwierigkeit?", channel_id=42))
    assert block.count("[Session vom") == 2  # own ceiling — memories never crowd out rules
    assert "Difficulty ladder rules." in block  # …and don't displace the rulebook hit either


def test_session_threshold_is_tighter_than_the_book_ceiling(tmp_path) -> None:
    # cosine distance ~0.42: passes the 0.45 book ceiling but NOT SESSION_MAX_DISTANCE
    db = _store(tmp_path, [
        _chunk("sz_fern", "Weit weg.", NEW, [0.6, 0.8, 0.0, 0.0]),
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Wie funktioniert die Schwierigkeit?", channel_id=42))
    assert "## Früher in der Kampagne" not in block
    assert "## Regelwerk" in block  # the book path is untouched


def test_other_channels_sessions_are_never_searched(tmp_path) -> None:
    db = _store(tmp_path, [
        _chunk("sz_fremd", "Fremde Kampagne.", NEW, [1.0, 0.0, 0.0, 0.0], channel="999"),
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Wie funktioniert die Schwierigkeit?", channel_id=42))
    assert "Fremde Kampagne." not in block


def test_debug_run_reads_only_the_sandbox_and_a_normal_run_never_does(tmp_path) -> None:
    # ADR 055: same channel, two sources — retrieval isolation in both directions
    db = _store(tmp_path, [
        _chunk("sz_live", "Echte Kampagne.", NEW, [1.0, 0.0, 0.0, 0.0]),
        ("session_debug_42", "sz_dbg",
         "[Session vom 12.07.2026, Szene: sz_dbg]\nDebug-Durchlauf.", NEW, [1.0, 0.0, 0.0, 0.0]),
    ])
    normal = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(normal.fetch_block("Was war da nochmal?", channel_id=42))
    assert "Echte Kampagne." in block and "Debug-Durchlauf." not in block
    dbg = _retriever(db, [1.0, 0.0, 0.0, 0.0], debug_sessions=True)
    block = asyncio.run(dbg.fetch_block("Was war da nochmal?", channel_id=42))
    assert "Debug-Durchlauf." in block and "Echte Kampagne." not in block


def test_recency_malus_prefers_the_newer_session_on_a_tie(tmp_path) -> None:
    db = _store(tmp_path, [
        _chunk("sz_alt", "Alte Erinnerung.", OLD, [0.9, 0.1, 0.0, 0.0]),
        _chunk("sz_neu", "Neue Erinnerung.", NEW, [0.9, 0.1, 0.0, 0.0]),
        _chunk("sz_neu2", "Noch eine neue.", NEW, [0.9, 0.11, 0.0, 0.0]),
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Was war da nochmal?", channel_id=42))
    assert "Neue Erinnerung." in block and "Noch eine neue." in block
    assert "Alte Erinnerung." not in block  # same distance + one session of age → ranked out


# --- FTS half ----------------------------------------------------------------------------------

def test_fts_finds_a_proper_noun_the_knn_misses(tmp_path) -> None:
    # orthogonal vector → KNN can't see it; the rare name "Vosk" rescues it via FTS
    db = _store(tmp_path, [
        _chunk("sz_markt", "Spielleitung: Der Händler Vosk verlangt fünfzig Thrones.",
               OLD, [0.0, 0.0, 1.0, 0.0]),
        _chunk("sz_other", "Nichts damit zu tun.", NEW, [0.0, 0.0, 0.0, 1.0]),
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Mortn: Was hat Vosk uns damals gesagt?", channel_id=42))
    assert "Vosk verlangt fünfzig Thrones" in block  # exact-term hit, malus-exempt despite age


def test_pure_narration_retrieves_no_memories(tmp_path) -> None:
    # negative case: common table vocabulary in every chunk → over the df cap → no FTS query,
    # and the vector sits far from everything → no KNN hit either
    rows = [
        _chunk(f"sz_{i}", f"Ich ziehe die Waffe und gehe zur Tür. Nummer {i}.",
               NEW, [0.0, 0.0, 1.0, 0.0])
        for i in range(4)
    ]
    db = _store(tmp_path, rows)
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Mortn: Ich ziehe die Waffe und gehe zur Tür.",
                                      channel_id=42))
    assert "## Früher in der Kampagne" not in block


def test_speaker_labels_do_not_become_fts_terms() -> None:
    terms = _query_terms("Mortn: Was hat der Händler Vosk gesagt?\n[Würfel] Seskin: Erfolg")
    assert "Vosk" in terms and "Händler" in terms
    assert "Mortn" not in terms and "Seskin" not in terms  # leading labels stripped
    assert "Was" not in terms  # capitalized function word


def test_sentence_initial_words_are_not_fts_terms() -> None:
    # German capitalizes every sentence start — utterance-opening words carry no name signal
    assert _query_terms("Mortn: Vielleicht gehen wir einfach weiter.") == []
    assert _query_terms("Mortn: Draußen regnet es. Gehen wir rein.") == []
    # accepted trade-off: a name that OPENS the sentence loses its FTS rescue too
    assert _query_terms("Mortn: Vosk hat uns betrogen!") == []
    # …but the common case — the name mentioned mid-sentence — stays a candidate
    assert _query_terms("Mortn: Ich glaube Vosk hat uns betrogen!") == ["Vosk"]


def test_session_vectors_never_enter_the_book_knn(tmp_path) -> None:
    # ADR 054: separate vec tables — a store full of session chunks must not shrink the book
    # path's candidate pool (zero behavior change), nor vice versa
    db = _store(tmp_path, [
        _chunk(f"sz_{i}", f"Session-Text {i}.", NEW, [1.0, 0.0, 0.0, 0.0]) for i in range(6)
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    book_only = asyncio.run(r.fetch_block("Wie funktioniert die Schwierigkeit?"))
    assert "Difficulty ladder rules." in book_only  # 6 perfect-match session vecs can't starve it
    assert "Session-Text" not in book_only


# --- degrade silently ---------------------------------------------------------------------------

def test_missing_fts_table_degrades_to_knn_only(tmp_path) -> None:
    db = _store(tmp_path, [
        _chunk("sz_markt", "Vosk war hier.", NEW, [0.9, 0.1, 0.0, 0.0]),
    ], fts=False)
    conn = sqlite3.connect(db)
    conn.execute("DROP TABLE IF EXISTS chunks_fts")
    conn.commit()
    conn.close()
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Wo ist Vosk?", channel_id=42))
    assert "Vosk war hier." in block  # KNN half still works, no error


def test_pre_session_store_without_stamp_column_stays_silent(tmp_path) -> None:
    # a store that only ever saw the rulebook ingest: no stamp column, no FTS table
    db = tmp_path / "rag.db"
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn, model="fake-embed", dim=4)
    cur = conn.execute(
        "INSERT INTO chunks (source, heading, text) VALUES ('rulebook', 'DIFFICULTY', 'Rules.')"
    )
    conn.execute("INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                 (cur.lastrowid, json.dumps([1.0, 0.0, 0.0, 0.0])))
    conn.commit()
    conn.close()
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    block = asyncio.run(r.fetch_block("Regelfrage?", channel_id=42))
    assert "## Regelwerk" in block and "## Früher in der Kampagne" not in block


def test_flag_off_and_legacy_call_skip_the_session_path(tmp_path) -> None:
    db = _store(tmp_path, [
        _chunk("sz_markt", "Erinnerung.", NEW, [1.0, 0.0, 0.0, 0.0]),
    ])
    r_off = _retriever(db, [1.0, 0.0, 0.0, 0.0], session_memory=False)
    assert "## Früher" not in asyncio.run(r_off.fetch_block("Frage?", channel_id=42))
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])
    assert "## Früher" not in asyncio.run(r.fetch_block("Frage?"))  # no channel → book only


def test_session_search_failure_never_breaks_the_book_block(tmp_path, monkeypatch) -> None:
    db = _store(tmp_path, [
        _chunk("sz_markt", "Erinnerung.", NEW, [1.0, 0.0, 0.0, 0.0]),
    ])
    r = _retriever(db, [1.0, 0.0, 0.0, 0.0])

    def boom(vector, query, channel_id):
        raise RuntimeError("session index broken")

    monkeypatch.setattr(r, "_search_session", boom)
    block = asyncio.run(r.fetch_block("Wie funktioniert die Schwierigkeit?", channel_id=42))
    assert "## Regelwerk" in block  # the turn still gets its rules


def test_session_ceiling_constant_is_tighter_than_the_book() -> None:
    assert SESSION_MAX_DISTANCE < 0.45
