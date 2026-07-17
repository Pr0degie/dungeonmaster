"""Session-transcript ingest (ADR 054): per-scene chunking over rotated journals (pure), the
stamp-idempotent store write with FTS5 mirror, the !join catch-up bookkeeping and the runtime
trigger seams — all offline, fake embeddings, no Ollama in the loop.
"""

from __future__ import annotations

import json
import sqlite3
import types
from pathlib import Path

import sqlite_vec

from dmbot.rag import ingest_session
from dmbot.rag.ingest import ensure_schema
from dmbot.rag.ingest_session import (
    chunk_session,
    ingest_session_file,
    ingested_stamps,
    is_debug_archive,
    load_journal,
    pending_files,
    session_source,
    stamp_date_de,
    wipe_debug_source,
)
from dmbot.runtime import SessionRuntime

STAMP = "20260712-213045"


def _write_journal(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8"
    )
    return path


def _turn(user: str, answer: str, **extra) -> dict:
    return {"ts": "2026-07-12T21:00:00", "user_msg": user, "answer": answer, **extra}


def _scene(scene_id: str) -> dict:
    return {"kind": "scene", "scene_id": scene_id, "ts": "2026-07-12T21:00:00"}


# --- journal loading ---------------------------------------------------------------------------

def test_load_journal_collapses_redos_and_skips_headers_and_torn_lines(tmp_path) -> None:
    p = tmp_path / "history.jsonl"
    p.write_text(
        json.dumps({"kind": "session", "ts": "x", "profile": "im"}) + "\n"
        + json.dumps(_turn("Mortn: hallo", "Erste Antwort.")) + "\n"
        + json.dumps(_scene("sz_markt")) + "\n"
        + json.dumps(_turn("Mortn: nochmal", "Zweite Antwort.", redo=True)) + "\n"
        + '{"torn line', encoding="utf-8",
    )
    items = load_journal(p)
    # the redo replaced the prior turn (load_recent semantics), the scene event survives in order
    assert [i.get("kind", "turn") for i in items] == ["turn", "scene"]
    assert items[0]["answer"] == "Zweite Antwort."


# --- chunking ----------------------------------------------------------------------------------

def test_chunks_split_at_scene_boundaries_with_embedded_header() -> None:
    items = [
        _scene("sz_ankunft"),
        _turn("Mortn: wir kommen an", "Der Zug hält."),
        _scene("sz_markt"),
        _turn("Seskin: ich rede mit Vosk", "Der Händler Vosk mustert euch."),
    ]
    chunks = chunk_session(items, stamp=STAMP)
    assert [scene for scene, _ in chunks] == ["sz_ankunft", "sz_markt"]
    assert chunks[0][1].startswith("[Session vom 12.07.2026, Szene: sz_ankunft]")
    assert "Der Zug hält." in chunks[0][1] and "Vosk" not in chunks[0][1]
    assert "Spielleitung: Der Händler Vosk mustert euch." in chunks[1][1]


def test_duplicate_same_scene_events_are_not_boundaries() -> None:
    # crash-restored sessions write a duplicate scene event mid-file (ADR 053) — one chunk
    items = [_scene("sz_markt"), _turn("A: a", "b"), _scene("sz_markt"), _turn("A: c", "d")]
    assert len(chunk_session(items, stamp=STAMP)) == 1


def test_oversized_scene_splits_at_turn_boundaries_never_mid_turn() -> None:
    long_answer = "Wort " * 120  # ~600 chars per turn
    items = [_scene("sz_lang")] + [_turn(f"A: Zug {i}", long_answer) for i in range(6)]
    chunks = chunk_session(items, stamp=STAMP, chunk_chars=1000)
    assert len(chunks) > 1
    assert all(scene == "sz_lang" for scene, _ in chunks)
    # never mid-turn: every chunk carries complete turns (each opens with its player line)
    for _, text in chunks:
        assert text.count("Spielleitung:") == text.count("A: Zug")


def test_journal_without_scene_events_falls_back_to_size_groups() -> None:
    items = [_turn(f"A: Zug {i}", "Antwort " * 80) for i in range(5)]
    chunks = chunk_session(items, stamp=STAMP, chunk_chars=1000)
    assert len(chunks) > 1
    assert all(scene == "unbekannt" for scene, _ in chunks)
    assert chunks[0][1].startswith("[Session vom 12.07.2026, Szene: unbekannt]")


def test_stamp_date_renders_german_or_unbekannt() -> None:
    assert stamp_date_de(STAMP) == "12.07.2026"
    assert stamp_date_de("gibberish") == "unbekannt"


# --- store write (fake embeddings) --------------------------------------------------------------

def _fake_embed(host, texts, *, model="fake-embed", prefix=""):
    return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def _ingest(tmp_path, monkeypatch, records, *, stamp=STAMP, channel="42") -> Path:
    monkeypatch.setattr(ingest_session, "embed_texts", _fake_embed)
    db = tmp_path / "rag.db"
    journal = _write_journal(tmp_path / "sessions" / channel / f"history.{stamp}.jsonl", records)
    ingest_session_file(journal, channel_id=channel, db_path=db, host="http://unused")
    return db


def _rows(db: Path, sql: str, *params):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_reingesting_a_stamp_replaces_instead_of_duplicating(tmp_path, monkeypatch) -> None:
    records = [_scene("sz_a"), _turn("A: a", "b"), _scene("sz_b"), _turn("A: c", "d")]
    db = _ingest(tmp_path, monkeypatch, records)
    journal = tmp_path / "sessions" / "42" / f"history.{STAMP}.jsonl"
    ingest_session_file(journal, channel_id="42", db_path=db, host="http://unused")
    rows = _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = ?", session_source("42"))
    assert rows[0][0] == 2  # replaced, not stacked
    fts = _rows(db, "SELECT COUNT(*) FROM chunks_fts")
    assert fts[0][0] == 2  # the FTS mirror was replaced too
    assert STAMP in ingested_stamps(db, session_source("42"))


def test_empty_journal_still_records_its_stamp_so_catchup_stops_retrying(
    tmp_path, monkeypatch
) -> None:
    # a store exists (a real session was ingested) → the empty journal's stamp is recorded
    db = _ingest(tmp_path, monkeypatch, [_scene("sz_a"), _turn("A: a", "b")])
    sess = tmp_path / "sessions" / "42"
    empty = _write_journal(sess / "history.20260713-101500.jsonl",
                           [{"kind": "session", "ts": "x"}])
    ingest_session_file(empty, channel_id="42", db_path=db, host="http://unused")
    assert "20260713-101500" in ingested_stamps(db, session_source("42"))
    assert pending_files(sess, db_path=db) == []


def test_empty_journal_without_a_store_creates_no_bare_db(tmp_path, monkeypatch) -> None:
    # nothing to store, nowhere to record → no rag.db (available() must not flip to True);
    # the catch-up just re-reads this journal next join — a cheap no-op
    monkeypatch.setattr(ingest_session, "embed_texts", _fake_embed)
    db = tmp_path / "rag.db"
    journal = _write_journal(tmp_path / "sessions" / "42" / f"history.{STAMP}.jsonl",
                             [{"kind": "session", "ts": "x"}])
    assert ingest_session_file(journal, channel_id="42", db_path=db, host="http://unused") == 0
    assert not db.is_file()


def test_pending_files_skips_ingested_stamps_and_the_live_journal(tmp_path, monkeypatch) -> None:
    records = [_scene("sz_a"), _turn("A: a", "b")]
    db = _ingest(tmp_path, monkeypatch, records)  # ingests STAMP
    sess = tmp_path / "sessions" / "42"
    _write_journal(sess / "history.20260713-101500.jsonl", records)
    _write_journal(sess / "history.jsonl", records)  # live journal — never ingested
    pending = pending_files(sess, db_path=db)
    assert [p.name for p in pending] == ["history.20260713-101500.jsonl"]


# --- debug-run sandbox (ADR 055) ----------------------------------------------------------------

def test_debug_archive_routes_to_the_sandbox_source_by_filename(tmp_path, monkeypatch) -> None:
    # routing keys on the filename alone — a .debug archive can never reach the live source
    monkeypatch.setattr(ingest_session, "embed_texts", _fake_embed)
    db = tmp_path / "rag.db"
    journal = _write_journal(
        tmp_path / "sessions" / "42" / f"history.{STAMP}.debug.jsonl",
        [_scene("sz_a"), _turn("A: a", "b")],
    )
    assert is_debug_archive(journal) and not is_debug_archive(Path("history.x.jsonl"))
    ingest_session_file(journal, channel_id="42", db_path=db, host="http://unused")
    assert _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = ?",
                 session_source("42", debug=True))[0][0] == 1
    assert _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = ?",
                 session_source("42"))[0][0] == 0


def test_plain_archive_never_routes_to_the_debug_source(tmp_path, monkeypatch) -> None:
    db = _ingest(tmp_path, monkeypatch, [_scene("sz_a"), _turn("A: a", "b")])
    assert _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = ?",
                 session_source("42"))[0][0] == 1
    assert _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = ?",
                 session_source("42", debug=True))[0][0] == 0


def test_pending_files_sees_only_the_requested_mode_in_both_directions(
    tmp_path, monkeypatch
) -> None:
    records = [_scene("sz_a"), _turn("A: a", "b")]
    db = _ingest(tmp_path, monkeypatch, records)  # plain STAMP already ingested
    sess = tmp_path / "sessions" / "42"
    _write_journal(sess / f"history.{STAMP}.debug.jsonl", records)  # same stamp, other mode
    _write_journal(sess / "history.20260713-101500.jsonl", records)
    # normal-mode scan: only plain files — the .debug archive is structurally invisible
    assert [p.name for p in pending_files(sess, db_path=db)] == ["history.20260713-101500.jsonl"]
    # debug-mode scan: only .debug files — its stamp bookkeeping is separate from the plain one
    assert [p.name for p in pending_files(sess, db_path=db, debug=True)] == [
        f"history.{STAMP}.debug.jsonl"
    ]


def test_wipe_debug_removes_only_the_sandbox_rows(tmp_path, monkeypatch) -> None:
    records = [_scene("sz_a"), _turn("A: a", "b")]
    db = _ingest(tmp_path, monkeypatch, records)  # live row under session_42
    debug_journal = _write_journal(
        tmp_path / "sessions" / "42" / f"history.{STAMP}.debug.jsonl", records
    )
    ingest_session_file(debug_journal, channel_id="42", db_path=db, host="http://unused")
    assert wipe_debug_source(db, "42") == 1
    assert _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = ?",
                 session_source("42", debug=True))[0][0] == 0
    assert ingested_stamps(db, session_source("42", debug=True)) == set()
    # the live campaign's rows, FTS mirror and stamp bookkeeping survive untouched
    assert _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = ?",
                 session_source("42"))[0][0] == 1
    assert _rows(db, "SELECT COUNT(*) FROM chunks_fts")[0][0] == 1
    assert STAMP in ingested_stamps(db, session_source("42"))
    # idempotent, and a missing store is a silent 0
    assert wipe_debug_source(db, "42") == 0
    assert wipe_debug_source(tmp_path / "nope.db", "42") == 0


def test_redo_collapse_holds_through_ingest(tmp_path, monkeypatch) -> None:
    records = [
        _scene("sz_a"),
        _turn("A: erste Frage", "Falsche Antwort."),
        _turn("A: erste Frage", "Richtige Antwort.", redo=True),
    ]
    db = _ingest(tmp_path, monkeypatch, records)
    (text,) = _rows(db, "SELECT text FROM chunks WHERE source = ?", session_source("42"))[0]
    assert "Richtige Antwort." in text and "Falsche Antwort." not in text


def test_session_ingest_uses_the_stores_model_never_rebuilding_it(tmp_path, monkeypatch) -> None:
    # a store built by the rulebook ingest with another embedder must survive session ingest
    db = tmp_path / "rag.db"
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn, model="fake-embed", dim=4)
    conn.execute("INSERT INTO chunks (source, heading, text) VALUES ('rulebook', 'H', 'Rule.')")
    conn.commit()
    conn.close()

    seen: dict = {}

    def spy_embed(host, texts, *, model="x", prefix=""):
        seen["model"] = model
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(ingest_session, "embed_texts", spy_embed)
    journal = _write_journal(
        tmp_path / "sessions" / "42" / f"history.{STAMP}.jsonl",
        [_scene("sz_a"), _turn("A: a", "b")],
    )
    ingest_session_file(journal, channel_id="42", db_path=db, host="http://unused", model="other")
    assert seen["model"] == "fake-embed"  # the store's model wins — no drop of the rulebook rows
    assert _rows(db, "SELECT COUNT(*) FROM chunks WHERE source = 'rulebook'")[0][0] == 1


def test_model_change_forgets_session_stamps_and_fts(tmp_path, monkeypatch) -> None:
    db = _ingest(tmp_path, monkeypatch, [_scene("sz_a"), _turn("A: a", "b")])
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    ensure_schema(conn, model="new-embed", dim=8)  # a rebuild with another embedder
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM meta WHERE key LIKE 'session_ingested:%'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name = 'chunks_fts'"
    ).fetchone()[0] == 0  # stale FTS rowids dropped with the chunks
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name = 'session_chunks_vec'"
    ).fetchone()[0] == 0  # the session vec table goes with them
    conn.close()


# --- runtime trigger seams (stub runtime, no Discord) -------------------------------------------

def _rt_stub(tmp_path, *, session_memory=True, testplan=False) -> types.SimpleNamespace:
    adventure_dir = tmp_path / "adventures" / "demo"
    if testplan:
        adventure_dir.mkdir(parents=True)
        (adventure_dir / "testplan.json").write_text("{}", encoding="utf-8")
    return types.SimpleNamespace(
        _session_memory=session_memory, _adventure_dir=adventure_dir
    )


def test_ingest_source_is_channel_scoped_and_off_switchable(tmp_path) -> None:
    rt = _rt_stub(tmp_path)
    assert SessionRuntime._session_ingest_source(rt, 42) == "session_42"
    rt_off = _rt_stub(tmp_path, session_memory=False)
    assert SessionRuntime._session_ingest_source(rt_off, 42) is None


def test_debug_campaign_runs_route_to_the_sandbox_source(tmp_path) -> None:
    # ADR 052/055: debug runs play in the SAME channel — the testplan.json sidecar marks them;
    # they get their own sandbox source instead of skipping (gate G10 needs the full path)
    rt = _rt_stub(tmp_path, testplan=True)
    assert SessionRuntime._session_ingest_source(rt, 42) == "session_debug_42"


def test_schedule_without_event_loop_degrades_to_a_noop(tmp_path) -> None:
    rt = _rt_stub(tmp_path)
    rt._session_ingest_source = lambda cid: SessionRuntime._session_ingest_source(rt, cid)
    rt._spawn_session_ingest = lambda paths, cid: SessionRuntime._spawn_session_ingest(
        rt, paths, cid
    )
    rt._spawn_session_task = lambda work: SessionRuntime._spawn_session_task(rt, work)
    # no running loop → logged debug, no exception, nothing scheduled
    SessionRuntime.schedule_session_ingest(rt, 42, tmp_path / "history.x.jsonl")
    SessionRuntime.schedule_session_ingest(rt, 42, None)  # rotate() returned None — no-op


def test_failed_ingest_only_logs_and_skips_the_file(tmp_path) -> None:
    rt = types.SimpleNamespace(
        _retriever=types.SimpleNamespace(_db_path=tmp_path / "rag.db"),
        _ollama_host="http://unused",
    )
    # a directory where a file is expected → OSError inside → logged, never raised
    SessionRuntime._ingest_one(rt, tmp_path, 42)
