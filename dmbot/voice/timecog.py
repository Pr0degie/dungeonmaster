"""Discord commands for in-game time + deadlines: !zeit, !frist neu/weg, !fristen (ADR 048).

A thin cog in the ADR-039 style — time is session/world-state pressure like clocks (ClockCog),
but distinct state with distinct commands, so it gets its own ~130 lines. Deadlines are created
and removed by humans only (never the LLM, ADR 048 #7); the *automatic* ``<<ZEIT>>`` advance
proposal lives in the delivery pipeline (ADR 035). Advancing time is deterministic by design
(golden rule #3). Manual commands apply immediately and are unclamped — the human at the table
IS the authority; only the marker path is limited to +12h per turn. Bot replies are German.
"""
from __future__ import annotations

import logging

from discord.ext import commands

from ..memory.gametime import (
    next_morning,
    parse_duration_de,
    remaining_de,
    render_time_de,
    render_time_phase_de,
)
from ..runtime import SessionRuntime

log = logging.getLogger(__name__)


class TimeCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime

    def _state(self, ctx: commands.Context):
        return self._rt._state.get(self._rt._brain_channel(ctx.channel))

    @commands.command(name="zeit")
    async def zeit(self, ctx: commands.Context, arg: str = "") -> None:
        """`!zeit` — show the in-game time. `!zeit +6h` — let time pass (m/min/h/std).
        `!zeit tag` — jump to the next morning, 08:00."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not arg:
            reply = f"🕐 {render_time_phase_de(state.time_minutes)}"
            for dl in state.deadlines:
                reply += f"\n⏳ **{dl.label}** (`{dl.id}`) — {remaining_de(dl.due_minutes, state.time_minutes)}"
            await ctx.send(reply)
            return
        if arg.strip().lower() in ("tag", "morgen"):
            minutes = next_morning(state.time_minutes) - state.time_minutes
        else:
            parsed = parse_duration_de(arg)
            if parsed is None:
                await ctx.send("Nutzung: `!zeit` · `!zeit +6h` (auch m/min/std) · `!zeit tag`.")
                return
            minutes = parsed
        applied = await self._rt._advance_time(ctx.channel, minutes)
        log.info("time advance (manual): +%d min → %s", applied, render_time_de(state.time_minutes))
        await ctx.send(f"🕐 Zeit vergangen: **+{applied} Min** → jetzt **{render_time_phase_de(state.time_minutes)}**.")

    @commands.group(name="frist", invoke_without_command=True)
    async def frist(self, ctx: commands.Context) -> None:
        """`!frist <neu|weg>` — manage in-game deadlines (ADR 048)."""
        await ctx.send(
            'Nutzung: `!frist neu "<Label>" <+Dauer>` (z.B. `+2h`, `+1 tag` via `+24h`) · '
            "`!frist weg <id>` · `!fristen` zeigt alle."
        )

    @frist.command(name="neu")
    async def neu(self, ctx: commands.Context, label: str = "", dauer: str = "") -> None:
        """`!frist neu "<Label>" <+Dauer>` — create a deadline. The id is derived from the
        label and echoed back — it's what `!frist weg` takes."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not label or not dauer:
            await ctx.send('Nutzung: `!frist neu "<Label>" <+Dauer>` (z.B. `!frist neu "Zug nach Sibellus" +24h`).')
            return
        minutes = parse_duration_de(dauer)
        if minutes is None:
            await ctx.send(f"Ungültige Dauer `{dauer}` — z.B. `+30m`, `+6h`, `+2 std`.")
            return
        deadline = state.add_deadline(label, minutes)
        self._rt._persist_and_refresh(ctx.channel)
        await self._rt.update_clock_panel()
        log.info("deadline new: %s (%s, due %s)", deadline.label, deadline.id,
                 render_time_de(deadline.due_minutes))
        await ctx.send(
            f"⏳ Neue Frist: **{deadline.label}** (`{deadline.id}`) — fällig "
            f"{render_time_de(deadline.due_minutes)} ({remaining_de(deadline.due_minutes, state.time_minutes)})."
        )

    @frist.command(name="weg", aliases=["entfernen", "loeschen"])
    async def weg(self, ctx: commands.Context, deadline_id: str = "") -> None:
        """`!frist weg <id>` — remove a deadline (spent consequence, or obsolete)."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not deadline_id:
            await ctx.send("Nutzung: `!frist weg <id>` — `!fristen` zeigt die IDs.")
            return
        deadline = state.remove_deadline(deadline_id)
        if deadline is None:
            await ctx.send(f"Unbekannte Frist `{deadline_id}` — `!fristen` zeigt alle.")
            return
        self._rt._persist_and_refresh(ctx.channel)
        await self._rt.update_clock_panel()
        log.info("deadline removed: %s (%s)", deadline.label, deadline.id)
        await ctx.send(f"🗑 Frist entfernt: **{deadline.label}** (`{deadline.id}`).")

    @commands.command(name="fristen")
    async def fristen(self, ctx: commands.Context) -> None:
        """`!fristen` — list all deadlines (and re-anchor the pressure panel at the bottom)."""
        state = self._state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not state.deadlines:
            await ctx.send('Keine Fristen. Anlegen: `!frist neu "<Label>" <+Dauer>`.')
            return
        # Re-post the panel at the bottom (fresh anchor) instead of duplicating the list here.
        await self._rt.clear_panel("_clock_panel")
        await self._rt.update_clock_panel()
