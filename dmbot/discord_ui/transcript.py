"""The player half of the story in the text channel: one line per DM-routed utterance."""

from __future__ import annotations

import discord


def format_player_line(speaker: str, text: str) -> str:
    """``🗣 **Speaker:** text`` — markdown in the transcript is escaped so a stray ``*`` or ``_``
    from STT can't bold half the channel, and mention syntax can't ping anyone."""
    body = discord.utils.escape_mentions(discord.utils.escape_markdown(text.strip()))
    name = discord.utils.escape_markdown(speaker.strip() or "Spieler")
    return f"🗣 **{name}:** {body}"
