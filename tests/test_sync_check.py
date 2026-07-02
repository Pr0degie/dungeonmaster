"""tools/sync_check.py — the pure parts: env key diff, fingerprint format, tolerant reading of
old rag.db stores (no ingest timestamps / no meta table), adventure fingerprint lines. No git,
no network; sqlite fixtures in tmp_path.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.sync_check import (  # noqa: E402
    adventure_lines,
    env_key_diff,
    env_lines,
    fmt,
    parse_env_keys,
    rag_lines,
    read_rag_meta,
    short_sha,
)

# --- .env key handling (keys only, never values) -------------------------------------------


def test_parse_env_keys_skips_comments_blanks_and_junk() -> None:
    text = (
        "# comment\n"
        "\n"
        "DISCORD_TOKEN_DMBOT=secret-value\n"
        "OLLAMA_HOST=http://x:11434  # trailing\n"
        "EMPTY=\n"
        "no_equals_line\n"
        "  SPACED = padded \n"
        "DISCORD_TOKEN_DMBOT=duplicate\n"
    )
    assert parse_env_keys(text) == ["DISCORD_TOKEN_DMBOT", "OLLAMA_HOST", "EMPTY", "SPACED"]


def test_env_key_diff_missing_and_extra_sorted() -> None:
    missing, extra = env_key_diff(["B_KEY", "A_KEY", "C_KEY"], ["C_KEY", "Z_LOCAL", "A_KEY"])
    assert missing == ["B_KEY"]
    assert extra == ["Z_LOCAL"]


def test_env_lines_never_leak_values(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text("TOKEN=\nHOST=http://template\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("TOKEN=super-secret-token\nLOCAL_ONLY=other-secret\n", encoding="utf-8")
    lines = env_lines(example, env)
    joined = "\n".join(lines)
    assert "super-secret-token" not in joined and "other-secret" not in joined
    assert "1/2 keys" in lines[0] and "(1 fehlen, 1 überzählig)" in lines[0]
    assert any("fehlen: HOST" in ln for ln in lines)
    assert any("überzählig: LOCAL_ONLY" in ln for ln in lines)


def test_env_lines_missing_env_degrades(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text("TOKEN=\n", encoding="utf-8")
    lines = env_lines(example, tmp_path / ".env")
    assert len(lines) == 1 and "FEHLT" in lines[0]


# --- fingerprint format ----------------------------------------------------------------------


def test_fmt_prefix_and_fixed_label_column() -> None:
    line = fmt("repo", "abc1234 (clean)")
    assert line.startswith("[sync] repo")
    assert line == "[sync] repo        abc1234 (clean)"  # label padded to 12


def test_short_sha_is_seven_hex_chars_of_sha256(tmp_path: Path) -> None:
    f = tmp_path / "blob.json"
    f.write_bytes(b'{"scenes": []}')
    expected = hashlib.sha256(b'{"scenes": []}').hexdigest()[:7]
    assert short_sha(f) == expected


# --- rag.db: tolerant reads ------------------------------------------------------------------


def _store(tmp_path: Path, *, meta: dict[str, str] | None, sources: dict[str, int]) -> Path:
    """A minimal fake store: plain meta + chunks tables (sync_check never touches chunks_vec)."""
    db = tmp_path / "rag.db"
    conn = sqlite3.connect(db)
    if meta is not None:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
    conn.execute(
        "CREATE TABLE chunks (id INTEGER PRIMARY KEY, source TEXT NOT NULL, "
        "heading TEXT NOT NULL, text TEXT NOT NULL)"
    )
    for source, n in sources.items():
        conn.executemany("INSERT INTO chunks (source, heading, text) VALUES (?, ?, ?)",
                         [(source, "h", "t")] * n)
    conn.commit()
    conn.close()
    return db


def test_rag_lines_old_db_without_ingest_stamps_reads_unbekannt(tmp_path: Path) -> None:
    db = _store(tmp_path, meta={"model": "bge-m3", "dim": "1024"},
                sources={"rulebook": 3, "setting": 2})
    lines = rag_lines(db)
    assert "model=bge-m3 dim=1024" in lines[0]
    assert "chunks: rulebook=3 setting=2" in lines[1]
    assert "ingest: rulebook=unbekannt setting=unbekannt" in lines[2]


def test_rag_lines_shows_ingest_stamp_when_present(tmp_path: Path) -> None:
    db = _store(tmp_path, meta={"model": "bge-m3", "dim": "1024",
                                "ingested:rulebook": "2026-07-01 12:00"},
                sources={"rulebook": 1, "setting": 1})
    lines = rag_lines(db)
    assert "ingest: rulebook=2026-07-01 12:00 setting=unbekannt" in lines[2]


def test_rag_lines_db_without_meta_table_degrades(tmp_path: Path) -> None:
    db = _store(tmp_path, meta=None, sources={"rulebook": 1})
    lines = rag_lines(db)
    assert "model=unbekannt" in lines[0]
    assert "chunks: rulebook=1" in lines[1]


def test_rag_lines_missing_db_is_a_fehlt_line(tmp_path: Path) -> None:
    lines = rag_lines(tmp_path / "nope" / "rag.db")
    assert len(lines) == 1 and "FEHLT" in lines[0]


def test_read_rag_meta_tolerates_missing_table() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        assert read_rag_meta(conn) == {}
    finally:
        conn.close()


# --- adventures ------------------------------------------------------------------------------


def test_adventure_lines_counts_via_loader(tmp_path: Path) -> None:
    d = tmp_path / "test_adv"
    d.mkdir()
    (d / "adventure.json").write_text(json.dumps({
        "id": "test_adv", "title": "T", "start_scene": "s1",
        "scenes": [{"id": "s1", "title_de": "Eins"}, {"id": "s2", "title_de": "Zwei"}],
    }), encoding="utf-8")
    (d / "npcs.json").write_text(json.dumps({"npcs": [{"name": "Grendel"}]}), encoding="utf-8")
    lines = adventure_lines(tmp_path)
    assert len(lines) == 2
    assert "test_adv/adventure.json" in lines[0] and "(2 scenes)" in lines[0]
    assert "test_adv/npcs.json" in lines[1] and "(1 npcs)" in lines[1]
    assert all("sha=" in ln for ln in lines)


def test_adventure_lines_broken_json_degrades_loudly(tmp_path: Path) -> None:
    d = tmp_path / "broken"
    d.mkdir()
    (d / "adventure.json").write_text("{not json", encoding="utf-8")
    lines = adventure_lines(tmp_path)
    assert len(lines) == 1 and "LADEFEHLER" in lines[0] and "sha=" in lines[0]


def test_adventure_lines_empty_root_is_fehlt(tmp_path: Path) -> None:
    lines = adventure_lines(tmp_path / "adventures")
    assert len(lines) == 1 and "FEHLT" in lines[0]


# --- ingest writes the per-source stamp (and a rebuild drops stale ones) ----------------------


def test_ensure_schema_model_change_clears_ingest_stamps() -> None:
    sqlite_vec = __import__("sqlite_vec")
    from dmbot.rag.ingest import ensure_schema

    conn = sqlite3.connect(":memory:")
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        ensure_schema(conn, model="old-model", dim=4)
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('ingested:rulebook', '2026-01-01 00:00')")
        ensure_schema(conn, model="new-model", dim=4)  # drop + recreate
        meta = dict(conn.execute("SELECT key, value FROM meta"))
        assert meta.get("model") == "new-model"
        assert "ingested:rulebook" not in meta  # stale stamp must not describe the new store
    finally:
        conn.close()
