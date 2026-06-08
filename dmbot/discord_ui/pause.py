"""Pause control (Discord UI) — Variante C of the pause feature.

One button + a status embed (the "Kasten" in Discord) that mirror the single game-pause state.
The same state is also driven by the Esc key in the DMbot terminal (Variante A, in the cog); both
controls flip one flag via a coroutine the cog passes in, and both surfaces re-render from it.

Pause = freeze: the cog mutes the VAD/STT pipeline and blocks DM turns while paused. ``timeout=None``
keeps the button live for the whole session; the cog re-posts/edits the message on state change.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord

_LABEL_RUN = "⏸ Pause"
_LABEL_PAUSED = "▶ Fortsetzen"


def pause_embed(paused: bool) -> discord.Embed:
    """The status box shown in Discord — orange while paused, green while running."""
    if paused:
        return discord.Embed(
            title="⏸  Spiel pausiert",
            description=(
                "Niemand wird transkribiert, der Spielleiter wartet.\n"
                "Mit **Esc** (im DMbot-Terminal) oder dem Knopf unten geht es weiter."
            ),
            color=discord.Color.orange(),
        )
    return discord.Embed(
        title="▶  Spiel läuft",
        description="Mit **Esc** (im DMbot-Terminal) oder dem Knopf unten pausieren.",
        color=discord.Color.green(),
    )


class PauseToggleView(discord.ui.View):
    """A single pause/resume button wired to the cog's shared pause toggle."""

    def __init__(
        self,
        toggle: Callable[[], Awaitable[bool]],
        *,
        paused: bool = False,
    ) -> None:
        # toggle() flips the shared pause state and returns the NEW paused flag.
        super().__init__(timeout=None)
        self._toggle = toggle
        self._button: discord.ui.Button = discord.ui.Button()
        self._button.callback = self._on_click
        self.add_item(self._button)
        self._sync(paused)

    def _sync(self, paused: bool) -> None:
        self._button.label = _LABEL_PAUSED if paused else _LABEL_RUN
        self._button.style = (
            discord.ButtonStyle.success if paused else discord.ButtonStyle.secondary
        )

    async def _on_click(self, interaction: discord.Interaction) -> None:
        paused = await self._toggle()
        self._sync(paused)
        await interaction.response.edit_message(embed=pause_embed(paused), view=self)
