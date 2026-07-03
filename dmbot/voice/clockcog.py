"""Discord commands for consequence clocks: !uhr neu/tick/zurück/weg + !uhren (ADR 047).

A thin cog in the ADR-039 style — clocks are session/world-state pressure, not adventure-scoped
(SceneCog) and not dice (DiceCog), so they get their own ~100 lines. Clocks are created and
removed by humans only (never the LLM, ADR 047 #5); the *automatic* ``<<UHR>>`` tick proposal
lives in the delivery pipeline (ADR 035). Advancing a clock is deterministic by design (golden
rule #3). Manual commands apply immediately — the human at the table IS the confirm. Bot replies
are German.
"""
from __future__ import annotations

import logging

from discord.ext import commands

from ..memory.state import CLOCK_SIZES, clock_segments
from ..runtime import SessionRuntime

log = logging.getLogger(__name__)


class ClockCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime

    def _state(self, ctx: commands.Context):
        return self._rt._state.get(self._rt._brain_channel(ctx.channel))

    async def _after_change(self, ctx: commands.Context) -> None:
        """Shared post-mutation tail: persist + prompt refresh + panel edit-in-place."""
        self._rt._persist_and_refresh(ctx.channel)
        await self._rt.update_clock_panel()

    @commands.group(name="uhr", invoke_without_command=True)
    async def uhr(self, ctx: commands.Context) -> None:
        """`!uhr <neu|tick|zurück|weg>` — manage consequence clocks (ADR 047)."""
        await ctx.send(
            "Nutzung: `!uhr neu \"<Name>\" <4|6|8>` · `!uhr tick <id>` · "
            "`!uhr zurück <id>` · `!uhr weg <id>` · `!uhren` zeigt alle."
        )

    @uhr.command(name="neu")
    async def neu(self, ctx: commands.Context, name: str = "", size: int = 6) -> None:
        """`!uhr neu "<Name>" <4|6|8>` — create a clock. The id is derived from the name and
        echoed back — it's what `<<UHR id>>` and the other subcommands take."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not name:
            await ctx.send('Nutzung: `!uhr neu "<Name>" <4|6|8>` (Standard: 6 Segmente).')
            return
        if size not in CLOCK_SIZES:
            await ctx.send(f"Ungültige Größe `{size}` — erlaubt: {', '.join(map(str, CLOCK_SIZES))}.")
            return
        clock = state.add_clock(name, size)
        await self._after_change(ctx)
        log.info("clock new: %s (%s, %d segments)", clock.name, clock.id, clock.size)
        await ctx.send(
            f"⏱ Neue Uhr: **{clock.name}** (`{clock.id}`) {clock_segments(clock)} 0/{clock.size}"
        )

    @uhr.command(name="tick")
    async def tick(self, ctx: commands.Context, clock_id: str = "") -> None:
        """`!uhr tick <id>` — advance one segment. Manual = unclamped (ADR 047 #2): the human
        is the authority; only the `<<UHR>>` marker path is limited to +1 per clock per turn."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not clock_id:
            await ctx.send("Nutzung: `!uhr tick <id>` — `!uhren` zeigt die IDs.")
            return
        existing = state.find_clock(clock_id)
        if existing is not None and existing.full:
            await ctx.send(
                f"⌛ **{existing.name}** ist bereits voll — Konsequenz ausspielen, dann `!uhr weg {existing.id}`."
            )
            return
        clock = self._rt._tick_clock(ctx.channel, clock_id)
        if clock is None:
            await ctx.send(f"Unbekannte Uhr `{clock_id}` — `!uhren` zeigt alle.")
            return
        await self._after_change(ctx)
        log.info("clock tick: %s → %d/%d", clock.id, clock.filled, clock.size)
        suffix = " — **VOLL**" if clock.full else ""
        await ctx.send(
            f"⏱ **{clock.name}** (`{clock.id}`) {clock_segments(clock)} {clock.filled}/{clock.size}{suffix}"
        )

    @uhr.command(name="zurück", aliases=["zurueck"])
    async def zurueck(self, ctx: commands.Context, clock_id: str = "") -> None:
        """`!uhr zurück <id>` — take one segment back (undo an accidental tick; from a full
        clock this also retracts the still-queued consequence note)."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not clock_id:
            await ctx.send("Nutzung: `!uhr zurück <id>` — `!uhren` zeigt die IDs.")
            return
        clock = self._rt._untick_clock(ctx.channel, clock_id)
        if clock is None:
            await ctx.send(f"Unbekannte Uhr `{clock_id}` — `!uhren` zeigt alle.")
            return
        await self._after_change(ctx)
        log.info("clock untick: %s → %d/%d", clock.id, clock.filled, clock.size)
        await ctx.send(
            f"⏱ **{clock.name}** (`{clock.id}`) {clock_segments(clock)} {clock.filled}/{clock.size}"
        )

    @uhr.command(name="weg", aliases=["entfernen", "loeschen"])
    async def weg(self, ctx: commands.Context, clock_id: str = "") -> None:
        """`!uhr weg <id>` — remove a clock (a spent consequence, or a stale one)."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not clock_id:
            await ctx.send("Nutzung: `!uhr weg <id>` — `!uhren` zeigt die IDs.")
            return
        clock = state.remove_clock(clock_id)
        if clock is None:
            await ctx.send(f"Unbekannte Uhr `{clock_id}` — `!uhren` zeigt alle.")
            return
        await self._after_change(ctx)
        log.info("clock removed: %s (%s)", clock.name, clock.id)
        await ctx.send(f"🗑 Uhr entfernt: **{clock.name}** (`{clock.id}`).")

    @commands.command(name="uhren")
    async def uhren(self, ctx: commands.Context) -> None:
        """`!uhren` — list all clocks (and re-anchor the panel at the bottom)."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not state.clocks:
            await ctx.send('Keine Uhren. Anlegen: `!uhr neu "<Name>" <4|6|8>`.')
            return
        # Re-post the panel at the bottom (fresh anchor) instead of duplicating the list here.
        await self._rt.clear_panel("_clock_panel")
        await self._rt.update_clock_panel()
