"""Fate choice under a failed test (ADR 063, IM Core p.220).

A failed roll by a character with Fate left gets two buttons: "🙏 Neu würfeln" spends one Fate and
rerolls (the second result stands), "Hinnehmen" keeps the failure. Nobody clicking counts as
"Hinnehmen" once the timeout runs out, so the table is never stuck waiting. The DM narrates only
after the decision — one narration per test.

Like :class:`~dmbot.discord_ui.dice.DiceTestView` the View is dumb: it locks itself, and the cog's
``on_decide(interaction | None, spend)`` does the work. Only the first decision counts.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord

Decide = Callable[["discord.Interaction | None", bool], Awaitable[None]]


class FateView(discord.ui.View):
    def __init__(self, available: int, on_decide: Decide, *, timeout: float = 20.0) -> None:
        super().__init__(timeout=timeout)
        self._on_decide = on_decide
        self._decided = False
        self._spend_btn: discord.ui.Button = discord.ui.Button(
            label=f"Neu würfeln (Schicksal, noch {available})", style=discord.ButtonStyle.primary,
            emoji="🙏",
        )
        self._accept_btn: discord.ui.Button = discord.ui.Button(
            label="Hinnehmen", style=discord.ButtonStyle.secondary,
        )
        self._spend_btn.callback = self._on_spend
        self._accept_btn.callback = self._on_accept
        self.add_item(self._spend_btn)
        self.add_item(self._accept_btn)

    def _claim(self) -> bool:
        """True for the first decision only (a click racing the timeout must not run twice)."""
        if self._decided:
            return False
        self._decided = True
        self._spend_btn.disabled = True
        self._accept_btn.disabled = True
        self.stop()
        return True

    async def _on_spend(self, interaction: discord.Interaction) -> None:
        if not self._claim():
            return
        await interaction.response.edit_message(view=self)
        await self._on_decide(interaction, True)

    async def _on_accept(self, interaction: discord.Interaction) -> None:
        if not self._claim():
            return
        await interaction.response.edit_message(view=self)
        await self._on_decide(interaction, False)

    async def on_timeout(self) -> None:
        if self._claim():
            await self._on_decide(None, False)
