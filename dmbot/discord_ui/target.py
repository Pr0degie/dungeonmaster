"""Target-selection dropdown (Discord UI) — the 'apply damage to whom?' step of auto-combat (Phase 9).

When an attack test succeeds, the cog rolls the weapon's damage and must apply it to a target. If
there's more than one candidate (NPCs in the scene + the party), it posts one of these dropdowns;
the cog's ``on_pick`` callback does the soak math, applies the wounds to the world state, persists
it, and feeds the result back so the DM narrates the consequence.

Same pattern as :class:`~dmbot.discord_ui.dice.DiceTestView`: the View is dumb (ack + lock on pick),
all logic lives in the cog callback it's handed. ``timeout`` is finite — a stale picker shouldn't
linger forever, but it's long enough for the table to decide.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord


class TargetSelectView(discord.ui.View):
    """A dropdown of candidate targets; the cog's ``on_pick(interaction, name)`` applies the damage."""

    def __init__(
        self, names: list[str], on_pick: Callable[[discord.Interaction, str], Awaitable[None]]
    ) -> None:
        super().__init__(timeout=300)
        self._on_pick = on_pick
        # Discord caps a select at 25 options; combat rarely has more candidates, but truncate safely.
        self._select: discord.ui.Select = discord.ui.Select(
            placeholder="Ziel des Treffers wählen …",
            options=[discord.SelectOption(label=n[:100]) for n in names[:25]],
            min_values=1,
            max_values=1,
        )
        self._select.callback = self._on_select
        self.add_item(self._select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        name = self._select.values[0]
        self._select.disabled = True  # one pick per hit — lock it
        await interaction.response.edit_message(view=self)  # ack + lock right away
        await self._on_pick(interaction, name)  # cog applies damage, edits the message, narrates
