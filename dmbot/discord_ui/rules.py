"""Rules view (Discord UI) — the essential rules of the active system, paged with ◀/▶ (`!rules`).

Like the turn-order/mic/dice views, the View is dumb: the pages (built from the active system
profile by :func:`dmbot.rules.summary.rules_pages_de`) are handed in, the buttons just flip the
page index and redraw the embed. ``timeout=None`` keeps it live for the whole session.
"""

from __future__ import annotations

import discord


def rules_embed(
    system_name: str, title: str, body: str, index: int, total: int, *, source: str = ""
) -> discord.Embed:
    """Render one rules page as an embed; the footer shows the page count (and the rulebook source)."""
    embed = discord.Embed(
        title=f"📖 {system_name} — {title}", description=body, color=discord.Color.blurple()
    )
    footer = f"Seite {index + 1}/{total}  ·  ◀ / ▶ zum Blättern"
    if source:
        footer += f"\n{source}"
    embed.set_footer(text=footer)
    return embed


class RulesView(discord.ui.View):
    """◀ / ▶ paging over the rules pages of the active system profile."""

    def __init__(self, pages: list[tuple[str, str]], system_name: str, *, source: str = "") -> None:
        super().__init__(timeout=None)
        self._pages = pages
        self._system = system_name
        self._source = source
        self._i = 0
        prev: discord.ui.Button = discord.ui.Button(
            label="◀ Zurück", style=discord.ButtonStyle.secondary
        )
        nxt: discord.ui.Button = discord.ui.Button(
            label="Weiter ▶", style=discord.ButtonStyle.secondary
        )
        prev.callback = self._on_prev
        nxt.callback = self._on_next
        self.add_item(prev)
        self.add_item(nxt)

    def embed(self) -> discord.Embed:
        title, body = self._pages[self._i]
        return rules_embed(
            self._system, title, body, self._i, len(self._pages), source=self._source
        )

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        self._i = (self._i - 1) % len(self._pages)  # wrap around so blättern never dead-ends
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self._i = (self._i + 1) % len(self._pages)
        await interaction.response.edit_message(embed=self.embed(), view=self)
