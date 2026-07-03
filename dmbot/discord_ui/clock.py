"""Clock-tick confirm/cancel buttons (Discord UI) — the visible half of the ``<<UHR>>`` marker
flow (ADR 047, consequence clocks).

When the DM narrates a consequence advancing it emits an ``<<UHR id>>`` marker; the delivery
pipeline validates the id against ``WorldState.clocks`` (max +1 per clock per turn) and posts this
View. One click applies the tick: the confirm callback performs the deterministic clock advance
and refreshes prompt + panel — mirroring how :class:`~dmbot.discord_ui.flag.FlagView` is the
visible half of ``<<ERLEDIGT>>``. Cancel just dismisses (no state work). With
``DM_FLAG_CONFIRM=0`` this View is skipped entirely (auto-apply; one knob for both flows).

Same structure as FlagView: the View is dumb (ack + lock on click), all logic lives in the
callback it's handed. ``timeout=None`` keeps it live.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord


class ClockView(discord.ui.View):
    """Confirm/cancel one tick on a clock; ``on_confirm`` applies the tick."""

    def __init__(self, clock_id: str, name: str,
                 on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self.clock_id = clock_id
        self.name = name
        self._on_confirm = on_confirm
        self._confirm_btn: discord.ui.Button = discord.ui.Button(
            label="Tick", style=discord.ButtonStyle.success, emoji="⏱"
        )
        self._cancel_btn: discord.ui.Button = discord.ui.Button(
            label="Abbrechen", style=discord.ButtonStyle.secondary
        )
        self._confirm_btn.callback = self._on_confirm_click
        self._cancel_btn.callback = self._on_cancel_click
        self.add_item(self._confirm_btn)
        self.add_item(self._cancel_btn)

    async def _on_confirm_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # one tick per request — lock both against double-clicks
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(view=self)  # ack + lock right away
        await self._on_confirm(interaction)  # callback ticks the clock, refreshes prompt + panel

    async def _on_cancel_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # dismiss — no state work, just lock + mark it
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(content="Kein Tick.", view=self)
