"""Lore pages — turn a ``data/lore/*.md`` compendium file into ``!lore`` embed pages.

The curated lore files (ADR 021) double as the player-facing rundown: every ``##``/``###``
heading is already written as a display label ("Khorne — der Blutgott"), so the pages for the
paged Discord view (``RulesView``) fall straight out of the markdown. Pure functions, no I/O
here — the cog reads the file and hands the text in.
"""

from __future__ import annotations

from pathlib import Path

# Discord caps an embed description at 4096 chars; stay a little under so the footer and a
# repeated title never push a page over. Today's largest section is ~1.6k — future-proofing.
MAX_PAGE_CHARS = 4000


def lore_pages(md_text: str) -> list[tuple[str, str]]:
    """``(title, body)`` pages from a lore markdown file, one per ``##``/``###`` heading.

    The ``#`` H1 and the leading ``>`` blockquote (the bot-internal source note — not for
    player eyes) are skipped. A section longer than :data:`MAX_PAGE_CHARS` is split at
    paragraph boundaries, repeating its title.
    """
    pages: list[tuple[str, str]] = []
    title: str | None = None
    body_lines: list[str] = []

    def flush() -> None:
        if title is None:
            return
        body = "\n".join(body_lines).strip()
        if not body:
            return
        for part in _split_long(body):
            pages.append((title, part))

    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if level == 1:  # the H1 document title — not a page
                continue
            flush()
            title = stripped.lstrip("#").strip()
            body_lines = []
        elif stripped.startswith(">"):
            continue  # the source-note blockquote header
        else:
            if title is not None:
                body_lines.append(line)
    flush()
    return pages


def _split_long(body: str) -> list[str]:
    """Split a body at paragraph boundaries so every part fits one embed description."""
    if len(body) <= MAX_PAGE_CHARS:
        return [body]
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for para in body.split("\n\n"):
        if current and size + len(para) + 2 > MAX_PAGE_CHARS:
            parts.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para) + 2
    if current:
        parts.append("\n\n".join(current))
    return parts


def available_topics(lore_dir: Path) -> list[str]:
    """The topics ``!lore <topic>`` can show — the ``*.md`` stems in ``data/lore/``, sorted."""
    if not lore_dir.is_dir():
        return []
    return sorted(p.stem for p in lore_dir.glob("*.md"))
