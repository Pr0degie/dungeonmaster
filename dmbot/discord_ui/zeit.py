"""Time-advance confirm/cancel buttons (Discord UI) — the visible half of the ``<<ZEIT>>``
marker flow (ADR 048, in-game time).

When the DM narrates time passing it emits a ``<<ZEIT +4h>>`` marker; the delivery pipeline
parses + clamps the duration (max +12h per turn, first valid marker only) and posts this View.
One click applies the advance: the confirm callback performs the deterministic time advance
(incl. deadline-expiry notes) and refreshes prompt + panel — mirroring how
:class:`~dmbot.discord_ui.clock.ClockView` is the visible half of ``<<UHR>>``. Cancel just
dismisses (no state work). With ``DM_FLAG_CONFIRM=0`` this View is skipped entirely
(auto-apply; one knob for the whole marker-confirm class).

Same structure as ClockView: the View is dumb (ack + lock on click), all logic lives in the
callback it's handed. ``timeout=None`` keeps it live.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord


class ZeitView(discord.ui.View):
    """Confirm/cancel one time advance; ``on_confirm`` applies it."""

    def __init__(self, minutes: int,
                 on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self.minutes = minutes
        self._on_confirm = on_confirm
        self._confirm_btn: discord.ui.Button = discord.ui.Button(
            label="Zeit vergeht", style=discord.ButtonStyle.success, emoji="🕐"
        )
        self._cancel_btn: discord.ui.Button = discord.ui.Button(
            label="Abbrechen", style=discord.ButtonStyle.secondary
        )
        self._confirm_btn.callback = self._on_confirm_click
        self._cancel_btn.callback = self._on_cancel_click
        self.add_item(self._confirm_btn)
        self.add_item(self._cancel_btn)

    async def _on_confirm_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # one advance per request — lock against double-clicks
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(view=self)  # ack + lock right away
        await self._on_confirm(interaction)  # callback advances time, refreshes prompt + panel

    async def _on_cancel_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # dismiss — no state work, just lock + mark it
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(content="Keine Zeit vergangen.", view=self)
