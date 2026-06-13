"""Lore read-aloud view (Discord UI) — the interactive `!lore tts …` reader.

A **manual paged reader**: each lore block's text is shown in the chat, and the player clicks
**⏭ Weiter vorlesen** to see + hear the next block. Bot A's `/speak` blocks until playback ends
and has no stop (two-bot isolation), so a block can't be cut mid-playback — instead the reader
advances per click and a fast click-through **skips intermediate audio**: clicks move the shown
block immediately, and once the current block finishes only the *latest* shown block is spoken
(the loop coalesces). **⏹ Stopp** ends it; **🔊 Nochmal** re-reads the current block when idle.

The View is otherwise dumb like the other views (mic/dice/rules): pages are handed in, the cog's
`_speak` is injected as ``speak_fn`` — the View never reaches back into the cog.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import discord

log = logging.getLogger(__name__)

SpeakFn = Callable[[str, "int | None"], Awaitable[bool]]


def advance_index(i: int, total: int) -> int:
    """Next block index, clamped at the last (the reader does NOT wrap — Weiter disables at the end).
    Pure + unit-testable."""
    return min(i + 1, total - 1) if total > 0 else 0


def lore_read_embed(title: str, block_title: str, body: str, index: int, total: int) -> discord.Embed:
    """Render the current lore block as an embed (its text is what the player reads along)."""
    embed = discord.Embed(
        title=f"📖 {title} — {block_title}", description=body, color=discord.Color.blurple()
    )
    embed.set_footer(text=f"Abschnitt {index + 1}/{total}  ·  ⏭ Weiter vorlesen  ·  ⏹ Stopp")
    return embed


class LoreReadView(discord.ui.View):
    """Manual block-by-block lore reader: shows each block's text + speaks it on demand."""

    def __init__(self, pages: list[tuple[str, str]], title: str, *, speak_fn: SpeakFn,
                 guild_id: int | None) -> None:
        super().__init__(timeout=None)
        self._pages = pages
        self._title = title
        self._speak = speak_fn
        self._guild_id = guild_id
        self._i = 0
        self._speaking = False  # one speak task in flight at a time (the bridge blocks per WAV)
        self._stopped = False
        self._next_btn: discord.ui.Button = discord.ui.Button(
            label="⏭ Weiter vorlesen", style=discord.ButtonStyle.primary
        )
        self._again_btn: discord.ui.Button = discord.ui.Button(
            label="🔊 Nochmal", style=discord.ButtonStyle.secondary
        )
        self._stop_btn: discord.ui.Button = discord.ui.Button(
            label="⏹ Stopp", style=discord.ButtonStyle.danger
        )
        self._next_btn.callback = self._on_next
        self._again_btn.callback = self._on_again
        self._stop_btn.callback = self._on_stop
        for b in (self._next_btn, self._again_btn, self._stop_btn):
            self.add_item(b)
        self._sync_buttons()

    # -- presentation ---------------------------------------------------------------------------

    def _sync_buttons(self) -> None:
        at_last = self._i >= len(self._pages) - 1
        self._next_btn.disabled = self._stopped or at_last
        self._again_btn.disabled = self._stopped
        self._stop_btn.disabled = self._stopped

    def embed(self) -> discord.Embed:
        title, body = self._pages[self._i]
        return lore_read_embed(self._title, title, body, self._i, len(self._pages))

    def begin_speaking(self) -> None:
        """Speak the first block (the cog posts the message, then calls this)."""
        self._request_speak()

    # -- buttons --------------------------------------------------------------------------------

    async def _on_next(self, interaction: discord.Interaction) -> None:
        if self._stopped:
            await interaction.response.defer()
            return
        self._i = advance_index(self._i, len(self._pages))
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)  # show next text now
        self._request_speak()

    async def _on_again(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if not self._stopped:
            self._request_speak(force=True)

    async def _on_stop(self, interaction: discord.Interaction) -> None:
        self._stopped = True
        self._sync_buttons()
        await interaction.response.edit_message(view=self)

    # -- speaking (one task in flight; coalesces fast click-through) -----------------------------

    def _request_speak(self, *, force: bool = False) -> None:
        if self._stopped or self._speaking:
            return  # a running loop re-checks self._i when it finishes; no overlapping audio
        self._speaking = True
        asyncio.create_task(self._speak_loop())

    async def _speak_loop(self) -> None:
        try:
            target = -1
            while not self._stopped and target != self._i:
                target = self._i
                heading, body = self._pages[target]
                ok = await self._speak(f"{heading}. {body}", self._guild_id)
                if not ok:
                    log.warning("lore read: playback failed at block %d/%d", target + 1,
                                len(self._pages))
                    break
        except Exception:
            log.exception("lore read speak loop failed")
        finally:
            self._speaking = False
