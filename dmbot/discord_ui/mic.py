"""Push-to-talk mic toggle (Discord UI).

One shared button for the whole table: tap it before you start speaking to the DM, tap it again
when you're done — one tap is enough for everyone (it flips a single global listen gate, not a
per-user one). The callback flips the :class:`~dmbot.voice.recv.VadSink` listen gate via a coroutine
the cog passes in, then re-styles the button to show the current state. ``timeout=None`` keeps it
live for the whole session; the cog re-posts it on ``!join`` / ``!mic``.

This is the structural fix for the continuous-transcription backlog: with the gate off by default,
the bot transcribes nothing until the table opts in, so STT never falls minutes behind on table talk.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

import discord

_LABEL_OFF = "🎙 Tippen, um mit dem DM zu reden"
_LABEL_ON = "🔴 DM hört zu — nochmal tippen zum Stoppen"


class MicToggleView(discord.ui.View):
    """A single toggle button wired to the cog's listen gate."""

    def __init__(
        self,
        toggle: Callable[[], Awaitable[bool]],
        *,
        listening: bool = False,
        on_stop: Optional[Callable[[discord.Interaction], Awaitable[None]]] = None,
    ) -> None:
        # toggle() flips the gate and returns the NEW listening state. on_stop (optional) runs after
        # the gate goes OFF — the cog uses it to auto-trigger the DM turn (players asked for this).
        super().__init__(timeout=None)
        self._toggle = toggle
        self._on_stop = on_stop
        self._button: discord.ui.Button = discord.ui.Button()
        self._button.callback = self._on_click
        self.add_item(self._button)
        self._sync(listening)

    def _sync(self, listening: bool) -> None:
        self._button.label = _LABEL_ON if listening else _LABEL_OFF
        self._button.style = (
            discord.ButtonStyle.danger if listening else discord.ButtonStyle.success
        )

    async def _on_click(self, interaction: discord.Interaction) -> None:
        listening = await self._toggle()
        self._sync(listening)
        await interaction.response.edit_message(view=self)  # ack + update the button right away
        if not listening and self._on_stop is not None:
            await self._on_stop(interaction)  # auto-send the DM turn (long-running; interaction acked)
