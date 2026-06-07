"""PDF -> Markdown ingestion helper (Phase-10 RAG prep).

    uv run python tools/pdf_to_md.py "data/pdfs/Imperium Maledictum Core.pdf"
    uv run python tools/pdf_to_md.py book.pdf -o data/pdfs/md/im_core.md
    uv run python tools/pdf_to_md.py book.pdf --pages 40-60        # just the test/difficulty pages

Why this exists: 40k rulebooks are multi-column and table-heavy (CLAUDE.md). Naive PDF text
extraction scrambles the reading order, so RAG would chunk "layout garbage" and retrieve poorly.
``pymupdf4llm`` reconstructs the reading order and renders tables as Markdown, giving the Phase-10
ingestion clean text to chunk + embed.

This is an OFFLINE prep step — it does NOT touch the bot runtime. It reads a PDF you legally own
and writes a ``.md`` file (default under ``data/pdfs/md/``) that the Phase-10 RAG ingestion will
consume. ASCII-only console output so it prints on any Windows console; the Markdown itself is UTF-8.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "pdfs" / "md"


def _parse_pages(spec: str | None) -> list[int] | None:
    """Parse a 1-based human page spec ("40-60", "1,3,5-9") into a 0-based list pymupdf4llm wants.
    None (no --pages) means the whole document."""
    if not spec:
        return None
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            start, end = int(lo), int(hi)
            if start > end:
                start, end = end, start
            pages.extend(range(start - 1, end))  # 1-based inclusive -> 0-based
        else:
            pages.append(int(part) - 1)
    if any(p < 0 for p in pages):
        raise ValueError("page numbers are 1-based; got a value < 1")
    return sorted(set(pages))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a (legally owned) PDF rulebook to Markdown for RAG ingestion."
    )
    parser.add_argument("pdf", type=Path, help="input PDF path")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="output .md path (default: data/pdfs/md/<name>.md)",
    )
    parser.add_argument(
        "--pages", default=None,
        help="1-based page selection, e.g. '40-60' or '1,3,5-9' (default: all pages)",
    )
    parser.add_argument(
        "--images", action="store_true",
        help="also extract embedded images next to the .md (default: text only - better for RAG)",
    )
    args = parser.parse_args(argv)

    pdf: Path = args.pdf
    if not pdf.is_file():
        print(f"[FAIL] no such PDF: {pdf}", file=sys.stderr)
        return 2

    try:
        import pymupdf4llm  # heavy-ish (PyMuPDF) — imported here so the CLI errors clearly if absent
    except ImportError:
        print("[FAIL] pymupdf4llm is not installed. Run: uv add pymupdf4llm", file=sys.stderr)
        return 2

    try:
        pages = _parse_pages(args.pages)
    except ValueError as exc:
        print(f"[FAIL] bad --pages value: {exc}", file=sys.stderr)
        return 2

    out: Path = args.output or (_DEFAULT_OUT_DIR / f"{pdf.stem}.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[..]  converting {pdf.name}"
          + (f" (pages {args.pages})" if args.pages else " (all pages)") + " ...")
    markdown = pymupdf4llm.to_markdown(
        str(pdf), pages=pages, write_images=args.images,
        image_path=str(out.parent / f"{pdf.stem}_images") if args.images else None,
    )
    out.write_text(markdown, encoding="utf-8")

    print(f"[OK]  wrote {len(markdown):,} chars to {out}")
    print("      Next (Phase 10): point the RAG ingestion at this .md to chunk + embed it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
