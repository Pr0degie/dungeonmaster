"""Dice-test button (Discord UI) — the manual/visible half of the marker flow (Phase 8).

When the DM requests a test (a ``<<TEST …>>`` marker, or the ``!test`` command), the cog posts
one of these: a single 🎲 button labelled with who rolls what at which difficulty. Clicking it
hands control to the cog's roll callback, which calls the **rules engine** (never inline dice —
golden rule #2), shows the result, and feeds it back so the DM narrates the consequence.

Same structure as :class:`~dmbot.discord_ui.mic.MicToggleView`: the View is dumb (ack + lock the
button on click), all logic lives in the cog callback it's handed. ``timeout=None`` keeps it live.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord


class DiceTestView(discord.ui.View):
    """A one-shot 🎲 button; the cog's ``on_roll`` does the rolling + narration."""

    def __init__(self, label: str, on_roll: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self._on_roll = on_roll
        self._button: discord.ui.Button = discord.ui.Button(
            label=label[:80], style=discord.ButtonStyle.primary, emoji="🎲"
        )
        self._button.callback = self._on_click
        self.add_item(self._button)

    async def _on_click(self, interaction: discord.Interaction) -> None:
        self._button.disabled = True  # one roll per request — lock it so it can't be double-clicked
        await interaction.response.edit_message(view=self)  # ack + lock right away
        await self._on_roll(interaction)  # cog rolls via the engine, edits the message, narrates
