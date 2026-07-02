"""Scene-element flag confirm/cancel buttons (Discord UI) — the visible half of the ``<<ERLEDIGT>>``
marker flow (ADR 043, stateful scene cards).

When the DM narrates a Gelegenheit completed or a Geheimnis revealed it emits an
``<<ERLEDIGT id>>`` marker; the delivery pipeline validates the id against the current scene card
and posts this View. One click applies the flag: the confirm callback performs the deterministic
``WorldState.scene_flags`` update and refreshes the prompt — mirroring how
:class:`~dmbot.discord_ui.scene.SceneChangeView` is the visible half of ``<<ORT>>``. Cancel just
dismisses (no state work). With ``DM_FLAG_CONFIRM=0`` this View is skipped entirely (auto-apply).

Same structure as SceneChangeView: the View is dumb (ack + lock on click), all logic lives in the
callback it's handed. ``timeout=None`` keeps it live.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord


class FlagView(discord.ui.View):
    """Confirm/cancel flagging a scene element resolved; ``on_confirm`` applies the flag."""

    def __init__(self, element_id: str, text_de: str,
                 on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self.element_id = element_id
        self.text_de = text_de
        self._on_confirm = on_confirm
        self._confirm_btn: discord.ui.Button = discord.ui.Button(
            label="Abhaken", style=discord.ButtonStyle.success, emoji="✅"
        )
        self._cancel_btn: discord.ui.Button = discord.ui.Button(
            label="Abbrechen", style=discord.ButtonStyle.secondary
        )
        self._confirm_btn.callback = self._on_confirm_click
        self._cancel_btn.callback = self._on_cancel_click
        self.add_item(self._confirm_btn)
        self.add_item(self._cancel_btn)

    async def _on_confirm_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # one flag per request — lock both against double-clicks
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(view=self)  # ack + lock right away
        await self._on_confirm(interaction)  # callback updates scene_flags, refreshes the prompt

    async def _on_cancel_click(self, interaction: discord.Interaction) -> None:
        self._confirm_btn.disabled = True  # dismiss — no state work, just lock + mark it
        self._cancel_btn.disabled = True
        await interaction.response.edit_message(content="Nicht abgehakt.", view=self)
