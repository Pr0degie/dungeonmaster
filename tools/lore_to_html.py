"""Render the curated lore compendium (data/lore/*.md, ADR 021) into one styled standalone
HTML (docs/lore.html) — the review/handout view, same grimdark theme as how-to-play.html.

Re-run after editing the lore files:  uv run python tools/lore_to_html.py
The markdown subset is deliberately tiny (headings, paragraphs, **bold**) — the lore files
use nothing else, so no dependency is needed.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LORE_DIR = ROOT / "data" / "lore"
OUT = ROOT / "docs" / "lore.html"

# Chapter order + display meta; lore files not listed here are appended alphabetically.
CHAPTERS: dict[str, tuple[str, str]] = {
    "imperium": ("Das Imperium der Menschheit", "Was jeder Bürger glaubt — und was dahinter liegt"),
    "chaos": ("Das Chaos", "Verbotenes Wissen — im Spiel kennt eure Figur davon fast nichts"),
}

_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Weltwissen — Imperium Maledictum</title>
<style>
  :root {{
    --bg: #0d0b09; --panel: #16120e; --ink: #d8cfc0; --ink-dim: #9a8f7d;
    --gold: #c9a227; --gold-soft: #8a6f1f; --blood: #8e2f2f; --border: #2e2620;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg);
    background-image: radial-gradient(ellipse at 50% -10%, #1d160d 0%, var(--bg) 60%);
    color: var(--ink); font-family: Georgia, "Times New Roman", serif;
    line-height: 1.65; font-size: 17px;
  }}
  .page {{ max-width: 880px; margin: 0 auto; padding: 32px 22px 80px; }}
  header {{ text-align: center; padding: 28px 0 8px; }}
  .eyebrow {{ letter-spacing: .35em; text-transform: uppercase; font-size: 12px;
              color: var(--gold-soft); margin-bottom: 10px; }}
  h1 {{ font-size: clamp(34px, 6vw, 52px); margin: 0 0 6px; color: var(--gold);
        letter-spacing: .04em; font-variant: small-caps;
        text-shadow: 0 0 28px rgba(201,162,39,.18); }}
  .subtitle {{ color: var(--ink-dim); font-style: italic; margin: 0; }}
  .rule-line {{ height: 1px; margin: 26px auto; width: 70%;
                background: linear-gradient(90deg, transparent, var(--gold-soft), transparent); }}
  h2.chapter {{ color: var(--blood); font-variant: small-caps; letter-spacing: .06em;
                font-size: 32px; margin: 64px 0 0; text-align: center; border: none; }}
  p.chapter-sub {{ text-align: center; color: var(--ink-dim); font-style: italic; margin: 4px 0 24px; }}
  h2 {{ color: var(--gold); font-variant: small-caps; letter-spacing: .05em; font-size: 26px;
        margin: 44px 0 6px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  h3 {{ color: var(--ink); font-size: 19px; margin: 26px 0 6px; }}
  p {{ margin: 10px 0; }}
  strong {{ color: #efe6d2; }}
  nav.toc {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
             padding: 18px 22px; margin: 26px 0; }}
  nav.toc .toc-title {{ font-variant: small-caps; letter-spacing: .08em; color: var(--gold);
                        font-size: 15px; margin-bottom: 8px; }}
  nav.toc ul {{ margin: 0; padding-left: 20px; columns: 2; column-gap: 32px; }}
  nav.toc li {{ margin: 3px 0; }}
  nav.toc a {{ color: var(--ink); text-decoration: none; }}
  nav.toc a:hover {{ color: var(--gold); }}
  footer {{ margin-top: 64px; text-align: center; color: var(--ink-dim); font-size: 14px;
            font-style: italic; }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="eyebrow">Imperium Maledictum</div>
  <h1>Weltwissen</h1>
  <p class="subtitle">Der Hintergrund des 41. Jahrtausends — zum Nachlesen für die Runde</p>
  <div class="rule-line"></div>
</header>
{toc}
{body}
<footer>Der Imperator schützt. — gleicher Text wie das Weltwissen des Spielleiters (<code>!lore</code>)</footer>
</div>
</body>
</html>
"""

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _inline(text: str) -> str:
    return _BOLD.sub(r"<strong>\1</strong>", html.escape(text, quote=False))


def render_chapter(stem: str, md_text: str) -> tuple[str, list[tuple[str, str]]]:
    """One chapter's HTML + its [(anchor, heading)] TOC entries."""
    title, subtitle = CHAPTERS.get(stem, (stem.title(), ""))
    out: list[str] = [f'<h2 class="chapter" id="{_slug(stem)}">{html.escape(title)}</h2>']
    if subtitle:
        out.append(f'<p class="chapter-sub">{html.escape(subtitle)}</p>')
    toc: list[tuple[str, str]] = [(_slug(stem), title)]
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped.lstrip("#").strip()
            if level == 1:
                continue  # file H1 — the chapter header replaces it
            anchor = f"{_slug(stem)}-{_slug(heading)}"
            tag = "h2" if level == 2 else "h3"
            out.append(f'<{tag} id="{anchor}">{_inline(heading)}</{tag}>')
            if level == 2:
                toc.append((anchor, heading))
        elif stripped.startswith(">"):
            continue  # bot-internal source note
        elif not stripped:
            flush()
        else:
            para.append(stripped)
    flush()
    return "\n".join(out), toc


def main() -> None:
    stems = [s for s in CHAPTERS if (LORE_DIR / f"{s}.md").is_file()]
    stems += sorted(p.stem for p in LORE_DIR.glob("*.md") if p.stem not in CHAPTERS)
    chapters: list[str] = []
    toc_items: list[str] = []
    for stem in stems:
        chapter_html, toc = render_chapter(stem, (LORE_DIR / f"{stem}.md").read_text(encoding="utf-8"))
        chapters.append(chapter_html)
        head_anchor, head_title = toc[0]
        toc_items.append(f'<li><a href="#{head_anchor}"><strong>{html.escape(head_title)}</strong></a></li>')
        toc_items += [f'<li><a href="#{a}">{html.escape(t)}</a></li>' for a, t in toc[1:]]
    toc_html = (
        '<nav class="toc"><div class="toc-title">Inhalt</div><ul>'
        + "\n".join(toc_items)
        + "</ul></nav>"
    )
    OUT.write_text(_TEMPLATE.format(toc=toc_html, body="\n".join(chapters)), encoding="utf-8")
    print(f"[OK] {OUT.relative_to(ROOT)} ({len(stems)} chapters)")


if __name__ == "__main__":
    main()
