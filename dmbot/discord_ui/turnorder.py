"""Turn-order view (Discord UI) — "whose turn is it" with rotate buttons (Phase 8).

A small shared panel: it shows the running order (seeded from the voice-channel members at
``!join``) with the current player highlighted, and two buttons to rotate forward/back. Like the
mic and dice views, the View is dumb — order/index state lives in the cog, and the buttons call
cog callbacks that mutate it; ``render`` redraws the message. ``timeout=None`` keeps it live.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord


class TurnOrderView(discord.ui.View):
    """◀ / ▶ buttons over a cog-owned turn order; ``render`` returns the current status text."""

    def __init__(
        self,
        advance: Callable[[], Awaitable[None]],
        back: Callable[[], Awaitable[None]],
        render: Callable[[], str],
    ) -> None:
        super().__init__(timeout=None)
        self._advance = advance
        self._back = back
        self._render = render
        prev: discord.ui.Button = discord.ui.Button(label="◀ Zurück", style=discord.ButtonStyle.secondary)
        nxt: discord.ui.Button = discord.ui.Button(label="Weiter ▶", style=discord.ButtonStyle.success)
        prev.callback = self._on_back
        nxt.callback = self._on_next
        self.add_item(prev)
        self.add_item(nxt)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        await self._advance()
        await interaction.response.edit_message(content=self._render(), view=self)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await self._back()
        await interaction.response.edit_message(content=self._render(), view=self)
