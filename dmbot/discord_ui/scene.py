"""Scene-change confirm/cancel buttons (Discord UI) — the visible half of the auto scene-transition
marker flow (ADR 026).

When the DM narrates the party into a new location it emits a ``<<ORT id>>`` marker; the cog
validates the id against the adventure's scene map and posts this View. One click does the move:
the cog's confirm callback performs the deterministic ``state.scene_id`` advance and refreshes the
narration — mirroring how :class:`~dmbot.discord_ui.dice.DiceTestView` is the visible half of the
``<<TEST>>`` flow. Cancel just dismisses (no cog work).

Same structure as DiceTestView: the View is dumb (ack + lock on click), all logic lives in the cog
callback it's handed. ``timeout=None`` keeps it live.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord


class SceneChangeView(discord.ui.View):
    """Confirm/cancel an automatic scene transition; the cog's ``on_confirm`` does the move."""

    def __init__(self, title: str, part: int,
                 on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self.title = title
        self.part = part
        self._on_confirm = on_confirm
        self._confirm_btn: discord.ui.Button = discord.ui.Button(
            label="Wechseln", style=discord.ButtonStyle.primary, emoji="📖"
        )
        self._cancel_btn: discord.ui.Button = discord.ui.Button(
            label="Abbrechen", style=discord.ButtonStyle.secondary
        )
        self._confirm_btn.callback = self._on_confirm_click
        self._cancel_btn.callback = self._on_cancel_click
        self.add_item(self._confirm_btn)
        self.add_item(self._cancel_btn)

    async def _on_confirm_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # one move per request — lock both so it can't be double-clicked
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(view=self)  # ack + lock right away
        await self._on_confirm(interaction)  # cog moves state.scene_id, refreshes the narration

    async def _on_cancel_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # dismiss — no cog work, just lock + mark it cancelled
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(content="Szenenwechsel abgebrochen.", view=self)


async def retire_scene_proposal(proposals: dict, channel_id: int, moved) -> None:
    """Close a pending ``<<ORT>>`` proposal once the scene has moved by any path (2026-10-25).

    ``proposals`` maps a channel to ``(message, proposed scene id)``. The proposal is edited to say
    what happened and loses its buttons, so a "Wechseln" never lingers after the classifier already
    moved. Best effort: a message that can no longer be edited is just forgotten."""
    record = proposals.pop(channel_id, None)
    if record is None:
        return
    message, proposed = record
    if moved.id == proposed:
        content = f"📖 Szene gewechselt: **{moved.title_de}** (Teil {moved.part})."
    else:
        content = f"📖 Vorschlag nicht mehr aktuell — ihr seid jetzt in **{moved.title_de}**."
    try:
        await message.edit(content=content, view=None)
    except Exception:  # noqa: BLE001 — a deleted/foreign message must not break the move
        pass
