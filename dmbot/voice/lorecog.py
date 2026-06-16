"""Discord commands for the Weltwissen reader: !lore (rundown / question / tts).

A thin cog split out of DMCog (ADR 039, the deferred ADR-035 follow-up) so an agent editing the
lore reader loads ~95 lines instead of the whole turn pipeline. Shared state lives on
SessionRuntime; the one cross-cog dependency — reading the compendium aloud — goes through the
``runtime.speak`` hook (set by DMCog to the delivery pipeline's _speak, ADR 029/035), so no
delivery/Bot-A logic leaks in here (golden rule #5). `!lore <frage>` is deterministic chunk
display, no LLM (golden rule #7). Bot replies are German; logs English.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from ..discord_ui.rules import RulesView
from ..discord_ui.lore_read import LoreReadView
from ..rag.lore import available_topics, lore_pages
from ..runtime import SessionRuntime, _DATA_DIR

log = logging.getLogger(__name__)


class LoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime

    # Display names for the curated lore topics (data/lore/<topic>.md, ADR 021); unknown
    # (future) files fall back to topic.title().
    _LORE_TITLES = {"imperium": "Weltwissen: Imperium", "chaos": "Weltwissen: Chaos"}
    # !lore questions search the Weltwissen sources only — rule questions belong to the DM
    # turn / !rules, and raw rulebook chunks are English layout soup, not player reading.
    _LORE_SOURCES = ("lore_imperium", "lore_chaos", "setting")
    _LORE_SOURCE_NAMES = {"lore_imperium": "Imperium", "lore_chaos": "Chaos", "setting": "Hive Rokarth"}

    @commands.command(name="lore", aliases=["hintergrund"])
    async def lore(self, ctx: commands.Context, *, arg: str = "") -> None:
        """Weltwissen: `!lore` / `!lore chaos` blättert den Rundown (◀/▶); `!lore <frage>`
        schlägt die passenden Kompendiums-Abschnitte nach (`!lore wer ist der Imperator?`).
        `!lore tts [thema]` liest das Kompendium über Bot A vor. Sonst Lese-Material, kein
        DM-Turn — wird nicht gesprochen. Alias: !hintergrund"""
        lore_dir = _DATA_DIR / "lore"
        topic = arg.lower().strip()
        head, _, rest = topic.partition(" ")
        if head == "tts":
            await self._lore_speak(ctx, lore_dir, rest.strip() or "imperium")
            return
        if not topic or (lore_dir / f"{topic}.md").is_file():
            await self._lore_rundown(ctx, lore_dir, topic or "imperium")
            return
        await self._lore_question(ctx, arg)

    async def _lore_rundown(self, ctx: commands.Context, lore_dir, topic: str) -> None:
        """The paged ◀/▶ view over data/lore/<topic>.md (the original !lore mode)."""
        path = lore_dir / f"{topic}.md"
        if not path.is_file():
            topics = available_topics(lore_dir)
            hint = ", ".join(f"`{t}`" for t in topics) if topics else "—"
            await ctx.send(f"Kein Lore-Thema `{topic}`. Verfügbar: {hint}")
            return
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        pages = lore_pages(text)
        if not pages:
            await ctx.send(f"`{path.name}` enthält keine lesbaren Abschnitte.")
            return
        view = RulesView(pages, self._LORE_TITLES.get(topic, topic.title()))
        await self._rt._send_with_retry(ctx.channel, view=view, embed=view.embed())

    async def _lore_speak(self, ctx: commands.Context, lore_dir, topic: str) -> None:
        """`!lore tts [thema]` — read the data/lore/<topic>.md compendium aloud via Piper +
        Bot A, section by section. Lese-Material that *is* spoken on demand (opposite of the
        silent rundown); reuses ``_speak`` so the feedback guard + WAV cleanup are identical to
        a DM turn. Pages are spoken one at a time so /speak blocks per section, not the whole
        file at once."""
        if not self._rt._tts_enabled:
            await ctx.send("Keine TTS-Stimme geladen (siehe SETUP B5).")
            return
        path = lore_dir / f"{topic}.md"
        if not path.is_file():
            topics = available_topics(lore_dir)
            hint = ", ".join(f"`{t}`" for t in topics) if topics else "—"
            await ctx.send(f"Kein Lore-Thema `{topic}`. Verfügbar: {hint}")
            return
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        pages = lore_pages(text)
        if not pages:
            await ctx.send(f"`{path.name}` enthält keine lesbaren Abschnitte.")
            return
        title = self._LORE_TITLES.get(topic, topic.title())
        guild_id = ctx.guild.id if ctx.guild else None
        log.info("📚 !lore tts %r → interactive reader, %d sections", topic, len(pages))
        # Interactive reader: shows each block's text in chat + reads it; ⏭ Weiter advances to the
        # next block (a fast click-through skips intermediate audio), ⏹ Stopp ends it. Bot A's
        # /speak blocks per WAV with no stop, so a running block can't be cut mid-playback.
        view = LoreReadView(pages, title, speak_fn=self._rt.speak, guild_id=guild_id)
        await self._rt._send_with_retry(ctx.channel, view=view, embed=view.embed())
        view.begin_speaking()  # speak block 0 now

    async def _lore_question(self, ctx: commands.Context, question: str) -> None:
        """`!lore <frage>` — show the best-matching Weltwissen sections (deterministic chunk
        display, no LLM: the compendium text IS the answer; the DM narrates in-game)."""
        if not self._rt._retriever.available():
            await ctx.send("Kein RAG-Store vorhanden — `!lore <frage>` braucht `data/vectordb/rag.db`.")
            return
        hits = await self._rt._retriever.lookup(question, sources=self._LORE_SOURCES)
        if not hits:
            await ctx.send(
                f"Dazu steht nichts im Weltwissen: *{question}*\n"
                f"(Rundown: `!lore` / `!lore chaos` — Regelfragen: `!rules`)"
            )
            return
        parts = []
        for source, heading, text, dist in hits:
            label = self._LORE_SOURCE_NAMES.get(source, source)
            parts.append(f"**{heading}** · _{label}_\n{text}")
            log.info("📚 !lore %r → %s:%r (d=%.2f)", question, source, heading, dist)
        description = "\n\n".join(parts)
        if len(description) > 4000:  # embed description cap; two lore chunks normally fit
            description = description[:4000].rsplit(" ", 1)[0] + " …"
        embed = discord.Embed(
            title="📚 Weltwissen", description=description, color=discord.Color.dark_gold()
        )
        await self._rt._send_with_retry(ctx.channel, embed=embed)
