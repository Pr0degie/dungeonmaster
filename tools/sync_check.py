"""Sync fingerprint for the untracked must-have artifacts — run on BOTH machines, compare blocks.

    uv run python tools/sync_check.py

The adventure compendia, ``rag.db`` and the ``.env`` keys don't travel with git, so they drift
silently between machines. This prints one compact, copy-pasteable block per machine; a line
that differs is exactly the thing to send over / rebuild. Short sha256 is the truth criterion
(copying changes mtimes — the mtime column is only a human-readable hint).

Runs offline (no bot, no Ollama), degrade-don't-die per line: a missing artifact prints a
FEHLT line instead of crashing. Output carries file names + counts only — never book content
(no headings, no chunk text) and never ``.env`` values.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # so `dmbot` imports when run as a script

from dmbot.rag.adventure import Adventure  # noqa: E402 (after the path insert)

ADVENTURES_DIR = REPO_ROOT / "data" / "adventures"
RAG_DB = REPO_ROOT / "data" / "vectordb" / "rag.db"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
ENV_FILE = REPO_ROOT / ".env"
# The tracked seed families a stale privately-sent copy can collide with (the ADR-040 case).
SEED_PATHS = ["data/sessions", "data/party", "data/lore", "data/rules_de", "data/systems"]

_LABEL_WIDTH = 12


def fmt(label: str, text: str) -> str:
    """One fingerprint line — fixed label column so two machines' blocks diff cleanly."""
    return f"[sync] {label:<{_LABEL_WIDTH}}{text}"


def _rel(path: Path) -> str:
    """Repo-relative display form — the block must diff cleanly across machines/user names."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def short_sha(path: Path) -> str:
    """First 7 hex chars of the file's sha256 — the comparison criterion (mtime lies on copy)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:7]


def mtime_str(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


# --- .env (keys only — NEVER values) --------------------------------------------------------


def parse_env_keys(text: str) -> list[str]:
    """The key names of a dotenv-style file, in order, deduplicated. Values are never returned."""
    keys: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def env_key_diff(example_keys: list[str], actual_keys: list[str]) -> tuple[list[str], list[str]]:
    """``(missing, extra)`` key names of the local .env vs the committed template, sorted."""
    example, actual = set(example_keys), set(actual_keys)
    return sorted(example - actual), sorted(actual - example)


def env_lines(example: Path, env: Path) -> list[str]:
    if not example.is_file():
        return [fmt(".env", f"FEHLT: {_rel(example)} (Repo kaputt?)")]
    example_keys = parse_env_keys(example.read_text(encoding="utf-8"))
    if not env.is_file():
        return [fmt(".env", f"FEHLT — aus {_rel(example)} anlegen ({len(example_keys)} keys)")]
    missing, extra = env_key_diff(example_keys, parse_env_keys(env.read_text(encoding="utf-8")))
    present = len(example_keys) - len(missing)
    lines = [fmt(".env", f"{present}/{len(example_keys)} keys gegenüber {_rel(example)} "
                         f"({len(missing)} fehlen, {len(extra)} überzählig)")]
    if missing:
        lines.append(fmt(".env", f"fehlen: {', '.join(missing)}"))
    if extra:
        lines.append(fmt(".env", f"überzählig: {', '.join(extra)}"))
    return lines


# --- rag.db (size + meta + per-source counts — never chunk text/headings) --------------------


def read_rag_meta(conn: sqlite3.Connection) -> dict[str, str]:
    """The store's meta table as a dict; ``{}`` for a DB without one (tolerant of old stores)."""
    try:
        return dict(conn.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return {}


def read_source_counts(conn: sqlite3.Connection) -> list[tuple[str, int]] | None:
    """``(source, chunk count)`` per source, sorted; ``None`` when the chunks table is missing."""
    try:
        return list(conn.execute(
            "SELECT source, COUNT(*) FROM chunks GROUP BY source ORDER BY source"))
    except sqlite3.Error:
        return None


def rag_lines(db_path: Path) -> list[str]:
    if not db_path.is_file():
        return [fmt("rag.db", f"FEHLT ({_rel(db_path)}) — kopieren oder per dmbot.rag.ingest bauen")]
    size_mb = db_path.stat().st_size / (1024 * 1024)
    conn = sqlite3.connect(db_path)  # meta + chunks are plain tables — no sqlite-vec needed
    try:
        meta = read_rag_meta(conn)
        counts = read_source_counts(conn)
    finally:
        conn.close()
    model = meta.get("model", "unbekannt")
    dim = meta.get("dim", "?")
    lines = [fmt("rag.db", f"{size_mb:.1f} MB  model={model} dim={dim}")]
    if counts is None:
        lines.append(fmt("rag.db", "WARNUNG: keine chunks-Tabelle lesbar — Store kaputt/leer?"))
        return lines
    lines.append(fmt("rag.db", "chunks: " + " ".join(f"{s}={n}" for s, n in counts)))
    # Ingest timestamps (meta rows `ingested:<source>`) — old DBs predate them: "unbekannt".
    lines.append(fmt("rag.db", "ingest: " + " ".join(
        f"{s}={meta.get(f'ingested:{s}', 'unbekannt')}" for s, _ in counts)))
    return lines


# --- adventures ------------------------------------------------------------------------------


def adventure_lines(root: Path) -> list[str]:
    dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not dirs:
        return [fmt("adventure", f"FEHLT — keine Kompendien unter {_rel(root)}/")]
    entries: list[tuple[str, str]] = []  # (file column, suffix) — padded after collection
    for directory in dirs:
        adventure = Adventure.load(directory)  # logs loudly on a broken compendium
        files = sorted(directory.glob("*.json"))
        if not files:
            entries.append((f"{directory.name}/", "FEHLT — keine JSON-Dateien"))
            continue
        for f in files:
            if adventure is None:
                metric = "(LADEFEHLER — siehe Log oben)"
            elif f.name == "adventure.json":
                metric = f"({len(adventure.scene_overview())} scenes)"
            elif f.name == "npcs.json":
                metric = f"({adventure.npc_count()} npcs)"
            else:
                metric = ""
            suffix = f"sha={short_sha(f)}  {mtime_str(f)}  {metric}".rstrip()
            entries.append((f"{directory.name}/{f.name}", suffix))
    width = max(len(name) for name, _ in entries) + 2
    return [fmt("adventure", f"{name:<{width}}{suffix}".rstrip()) for name, suffix in entries]


# --- git (repo pointer + local seed modifications) -------------------------------------------


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout.strip()


def repo_line() -> str:
    head = _git("rev-parse", "--short", "HEAD")
    dirty = [ln for ln in _git("status", "--porcelain").splitlines() if ln.strip()]
    state = "clean" if not dirty else f"dirty: {len(dirty)} Änderungen"
    return fmt("repo", f"{head} ({state})")


def seeds_lines() -> list[str]:
    """Local modifications to the tracked data seeds — a stale sent-around copy of e.g.
    ``characters.json`` shows up here (it collides with the committed default party, ADR 040)."""
    dirty = [ln for ln in _git("status", "--porcelain", "--", *SEED_PATHS).splitlines()
             if ln.strip()]
    if not dirty:
        return [fmt("seeds", "tracked seed files unmodified")]
    return [fmt("seeds", f"abweichend: {ln.strip()}") for ln in dirty]


# --- main ------------------------------------------------------------------------------------


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # survive a cp1252 Windows console
    except Exception:
        pass
    # The adventure loader reports broken compendia via logging — that IS a finding, show it.
    logging.basicConfig(level=logging.WARNING, format="[sync] %(levelname)s %(message)s")

    sections: list[tuple[str, object]] = [
        ("repo", lambda: [repo_line()]),
        ("adventure", lambda: adventure_lines(ADVENTURES_DIR)),
        ("rag.db", lambda: rag_lines(RAG_DB)),
        (".env", lambda: env_lines(ENV_EXAMPLE, ENV_FILE)),
        ("seeds", seeds_lines),
    ]
    for label, build in sections:  # degrade-don't-die: one broken section must not eat the rest
        try:
            for line in build():
                print(line)
        except Exception as exc:  # noqa: BLE001 — the whole point is to keep printing
            print(fmt(label, f"FEHLER: {exc}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
