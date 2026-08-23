"""The "Zurücknehmen" control under an automatic scene change (ADR 057 #4).

The 2026-08-22 run proved that a control nobody knows about is the same as no control: the
`<<ORT>>` marker's confirm button never fired in 22 turns because nothing announced it. So the
scene now changes *immediately* and this view is the recovery — one click restores the previous
pointer and scene time — and it expires on its own after about a minute, because an undo that
still sits there three scenes later is a trap, not a safety net.

Same shape as :class:`~dmbot.discord_ui.scene.SceneChangeView`: the View is dumb (ack + lock on
click), all logic lives in the runtime callback it is handed. Unlike that one it uses a real
``timeout`` — the expiry IS the feature — and disables itself when it runs out, so a late click
reads as "too late" instead of failing silently.

Bot text is German; code/logs English (CLAUDE.md).
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

import discord

log = logging.getLogger(__name__)

#: The German label of the expired control — the message keeps its text, only the button greys out.
EXPIRED_LABEL_DE = "Zurücknehmen (abgelaufen)"


class SceneUndoView(discord.ui.View):
    """One "Zurücknehmen" button that lives for ``timeout`` seconds.

    ``on_undo`` performs the deterministic restore (``scene_flow.apply_scene_undo`` + persist +
    prompt refresh) and edits the announcement; this class only acks, locks and expires."""

    def __init__(
        self,
        on_undo: Callable[[discord.Interaction], Awaitable[None]],
        *,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self._on_undo = on_undo
        self.message: discord.Message | None = None  # set by the poster, so on_timeout can edit
        self._button: discord.ui.Button = discord.ui.Button(
            label="Zurücknehmen", style=discord.ButtonStyle.secondary, emoji="↩"
        )
        self._button.callback = self._on_click
        self.add_item(self._button)

    async def _on_click(self, interaction: discord.Interaction) -> None:
        self._button.disabled = True  # one undo per change — lock before the work starts
        self.stop()
        await interaction.response.edit_message(view=self)  # ack + lock right away
        await self._on_undo(interaction)

    async def on_timeout(self) -> None:
        """Grey the button out when the minute is up (best-effort — a deleted message is fine)."""
        self._button.disabled = True
        self._button.label = EXPIRED_LABEL_DE
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            log.debug("scene-undo: could not disable the expired button", exc_info=True)
