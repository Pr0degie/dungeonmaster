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

from ..dice_images import EMBED_COLOURS, TARGET_PALETTE, TARGET_PREFIX

DICE_FILENAME = "dice.png"
TARGET_FILENAME = "target.png"
THROW_FILENAME = "dice.gif"
THROW_TEXT = "🎲 *Der Würfel rollt …*"


def _show_picture(embed: discord.Embed, filename: str, large: bool) -> None:
    url = f"attachment://{filename}"
    if large:
        embed.set_image(url=url)      # full embed width, below the text
    else:
        embed.set_thumbnail(url=url)  # small, at message height


def result_embed(text: str, image: Path | None, palette: str, *,
                 large: bool = False) -> tuple[discord.Embed, discord.File | None]:
    """A dice result as an embed: the unchanged German result line as the description, the die
    as a small thumbnail — or, ``large`` (a dice-button test: target, throw and result all big),
    as the embed's big image. ``image=None`` → the embed without a picture, so a failed render
    never loses the result."""
    embed = discord.Embed(description=text, colour=discord.Colour(EMBED_COLOURS.get(palette, EMBED_COLOURS["red"])))
    if image is None:
        return embed, None
    _show_picture(embed, DICE_FILENAME, large)
    return embed, discord.File(image, filename=DICE_FILENAME)


def _big_embed(text: str, image: Path, palette: str, filename: str) -> tuple[discord.Embed, discord.File]:
    embed = discord.Embed(description=text, colour=discord.Colour(EMBED_COLOURS[palette]))
    _show_picture(embed, filename, large=True)
    return embed, discord.File(image, filename=filename)


def target_embed(target: int, image: Path) -> tuple[discord.Embed, discord.File]:
    """The posted test's target: the steel "≤45" die big above the 🎲 button, the target in words.
    (The picture itself can't be the button — Discord embeds aren't clickable for interactions.)"""
    return _big_embed(f"Zielwert **{TARGET_PREFIX}{target}**", image, TARGET_PALETTE, TARGET_FILENAME)


def throw_link_embed(url: str) -> discord.Embed:
    """:func:`throw_embed` for a flight GIF already stored in Discord (ADR 064): the embed points
    at its link, so the edit carries no upload."""
    embed = discord.Embed(description=THROW_TEXT, colour=discord.Colour(EMBED_COLOURS[TARGET_PALETTE]))
    embed.set_image(url=url)
    return embed


def throw_embed(gif: Path) -> tuple[discord.Embed, discord.File]:
    """The die in the air: the throw GIF big, in the target's place; the result line follows when
    it lands. The side bar stays steel — the result's colour would give a critical or a fumble
    away early."""
    return _big_embed(THROW_TEXT, gif, TARGET_PALETTE, THROW_FILENAME)


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
