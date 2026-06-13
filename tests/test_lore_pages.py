"""`!lore` page builder (ADR 021): markdown sections → (title, body) embed pages, pure."""

from __future__ import annotations

from pathlib import Path

from dmbot.rag.lore import MAX_PAGE_CHARS, available_topics, lore_pages

_LORE_DIR = Path(__file__).resolve().parents[1] / "data" / "lore"

_FIXTURE = """# Das Imperium — Weltwissen

> Bot-interner Hinweis (Quelle lore_imperium, ADR 021). Nicht für Spieleraugen.
> Zweite Headerzeile.

## Der Imperator

Seit zehntausend Jahren auf dem Goldenen Thron.

## Die Inquisition

Das Schwert über allen Schwertern.

### Die Ordos der Inquisition

Malleus, Hereticus, Xenos.
"""


def test_headings_become_pages_and_header_is_skipped() -> None:
    pages = lore_pages(_FIXTURE)
    titles = [t for t, _ in pages]
    assert titles == ["Der Imperator", "Die Inquisition", "Die Ordos der Inquisition"]
    assert all(isinstance(t, str) and isinstance(b, str) and t and b for t, b in pages)
    combined = " ".join(b for _, b in pages)
    assert "Goldenen Thron" in combined
    assert "ADR 021" not in combined  # the blockquote source note never reaches players
    assert "Weltwissen" not in " ".join(titles)  # the H1 is not a page


def test_long_sections_split_under_the_embed_cap() -> None:
    long_md = "## Lang\n\n" + "\n\n".join("Absatz. " * 80 for _ in range(12))
    pages = lore_pages(long_md)
    assert len(pages) > 1
    assert all(t == "Lang" for t, _ in pages)  # title repeats on continuation pages
    assert all(len(b) <= MAX_PAGE_CHARS for _, b in pages)


def test_real_compendium_files_parse() -> None:
    imperium = lore_pages((_LORE_DIR / "imperium.md").read_text(encoding="utf-8"))
    chaos = lore_pages((_LORE_DIR / "chaos.md").read_text(encoding="utf-8"))
    assert len(imperium) >= 10 and len(chaos) >= 8
    assert all(len(b) <= MAX_PAGE_CHARS for _, b in imperium + chaos)


def test_available_topics_lists_the_md_stems(tmp_path) -> None:
    assert {"imperium", "chaos"} <= set(available_topics(_LORE_DIR))
    assert available_topics(tmp_path / "missing") == []
