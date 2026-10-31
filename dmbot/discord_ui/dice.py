"""Dice-test button (Discord UI) — the manual/visible half of the marker flow (Phase 8).

When the DM requests a test (a ``<<TEST …>>`` marker, or the ``!test`` command), the cog posts
one of these: a single 🎲 button labelled with who rolls what at which difficulty. Clicking it
hands control to the cog's roll callback, which calls the **rules engine** (never inline dice —
golden rule #2), shows the result, and feeds it back so the DM narrates the consequence.

Same structure as :class:`~dmbot.discord_ui.mic.MicToggleView`: the View is dumb (ack + lock the
button on click), all logic lives in the cog callback it's handed. ``timeout=None`` keeps it live.
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import discord

from ..dice_images import EMBED_COLOURS, TARGET_PREFIX

DICE_FILENAME = "dice.png"
TARGET_FILENAME = "target.png"
THROW_FILENAME = "dice.gif"


def result_embed(text: str, image: Path | None, palette: str) -> tuple[discord.Embed, discord.File | None]:
    """A dice result as an embed (``!roll``, Manifest): the unchanged German result line as the
    description, the die as a small thumbnail. ``image=None`` → the embed without a picture, so a
    failed render never loses the result. Dice-button tests use :func:`result_picture` instead."""
    embed = discord.Embed(description=text, colour=discord.Colour(EMBED_COLOURS.get(palette, EMBED_COLOURS["red"])))
    if image is None:
        return embed, None
    embed.set_thumbnail(url=f"attachment://{DICE_FILENAME}")
    return embed, discord.File(image, filename=DICE_FILENAME)


def picture_embed(filename: str) -> discord.Embed:
    """A box holding only a picture — no text, no coloured side bar (2026-10-31, Tobi: "Kasten nur
    ums Bild"). The dice-button test keeps its words in the message text, so swapping the picture
    changes nothing else. Still an embed, not a plain attachment, because only an embed can point at
    a stored GIF (ADR 064) and spare the upload."""
    embed = discord.Embed()
    embed.set_image(url=f"attachment://{filename}")
    return embed


def target_text(target: int) -> str:
    """The posted test's target in words — part of the message text, above the picture."""
    return f"Zielwert **{TARGET_PREFIX}{target}**"


def target_embed(image: Path) -> tuple[discord.Embed, discord.File]:
    """The posted test's target picture: the steel "≤45" die big above the 🎲 button. (The picture
    itself can't be the button — Discord embeds aren't clickable for interactions.)"""
    return picture_embed(TARGET_FILENAME), discord.File(image, filename=TARGET_FILENAME)


def result_picture(image: Path) -> tuple[discord.Embed, discord.File]:
    """The rolled die big, for a dice-button test; the result line is the message text."""
    return picture_embed(DICE_FILENAME), discord.File(image, filename=DICE_FILENAME)


def throw_link_embed(url: str) -> discord.Embed:
    """:func:`throw_embed` for a flight GIF already stored in Discord (ADR 064): the box points
    at its link, so the edit carries no upload."""
    embed = discord.Embed()
    embed.set_image(url=url)
    return embed


def throw_embed(gif: Path) -> tuple[discord.Embed, discord.File]:
    """The die in the air: the throw GIF in the target picture's place — only the picture changes."""
    return picture_embed(THROW_FILENAME), discord.File(gif, filename=THROW_FILENAME)


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
