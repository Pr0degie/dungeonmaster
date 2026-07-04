"""Discord commands for the Chekhov list: !fäden, !faden neu/erledigt/weg (ADR 050).

A thin cog in the ADR-039/048 style — the thread list is distinct session state with distinct
commands, like time (TimeCog) and clocks (ClockCog). Threads are normally extracted at wrap-up
by the LLM, but the human keeps their hands on the list: seed one manually (`!faden neu` —
authority, and it makes the live gate testable without a full extraction), mark one resolved,
or drop one. All list mutations are code-owned (dedupe/cap/status in
:mod:`dmbot.memory.chekhov`); commands apply immediately — the human IS the confirm.
Bot replies are German.
"""
from __future__ import annotations

import logging

from discord.ext import commands

from ..runtime import SessionRuntime

log = logging.getLogger(__name__)


class ChekhovCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime

    def _cid(self, ctx: commands.Context) -> int:
        return self._rt._brain_channel(ctx.channel)

    @commands.command(name="fäden", aliases=["faeden"])
    async def faeden(self, ctx: commands.Context) -> None:
        """`!fäden` — list the open threads (and the recently resolved ones)."""
        clist = self._rt.chekhov_list(self._cid(ctx))
        open_threads = clist.open_threads()
        resolved = clist.resolved_threads()
        if not open_threads and not resolved:
            await ctx.send('Keine losen Fäden. Anlegen: `!faden neu "<Detail>" [1-3]` — oder beim `!wrap` extrahieren lassen.')
            return
        lines: list[str] = []
        if open_threads:
            lines.append("🧵 **Lose Fäden (offen):**")
            for t in open_threads:
                origin = f" — Szene: {t.origin_scene}" if t.origin_scene else ""
                since = f", seit {t.created_session}" if t.created_session else ""
                lines.append(f"- `{t.id}` (Gewicht {t.weight}{since}{origin}) {t.detail}")
        if resolved:
            lines.append("✅ **Aufgelöst:**")
            lines.extend(f"- `{t.id}` {t.detail}" for t in resolved)
        await ctx.send("\n".join(lines))

    @commands.group(name="faden", invoke_without_command=True)
    async def faden(self, ctx: commands.Context) -> None:
        """`!faden <neu|erledigt|weg>` — manage the Chekhov list (ADR 050)."""
        await ctx.send(
            'Nutzung: `!faden neu "<Detail>" [1-3]` · `!faden erledigt <id>` · '
            "`!faden weg <id>` · `!fäden` zeigt alle."
        )

    @faden.command(name="neu")
    async def neu(self, ctx: commands.Context, detail: str = "", gewicht: int = 1) -> None:
        """`!faden neu "<Detail>" [gewicht 1-3]` — seed a thread by hand. The id is echoed
        back — it's what `!faden erledigt`/`weg` take."""
        if not detail:
            await ctx.send('Nutzung: `!faden neu "<Detail>" [1-3]` (z. B. `!faden neu "Die Münze aus der Bar" 2`).')
            return
        cid = self._cid(ctx)
        clist = self._rt.chekhov_list(cid)
        state = self._rt._state.get(cid)
        thread = clist.add_thread(
            detail,
            weight=gewicht,
            origin_scene=state.scene_id if state is not None else "",
        )
        if thread is None:
            await ctx.send("Das ähnelt einem bestehenden Faden — `!fäden` zeigt alle.")
            return
        self._rt.save_chekhov(cid)
        self._rt._persist_and_refresh(ctx.channel)
        log.info("chekhov thread new (manual): [%s] %s", thread.id, thread.detail)
        await ctx.send(f"🧵 Neuer Faden: **{thread.detail}** (`{thread.id}`, Gewicht {thread.weight}).")

    @faden.command(name="erledigt", aliases=["aufgelöst", "aufgeloest"])
    async def erledigt(self, ctx: commands.Context, thread_id: str = "") -> None:
        """`!faden erledigt <id>` — mark a thread resolved (it leaves the callback offer)."""
        if not thread_id:
            await ctx.send("Nutzung: `!faden erledigt <id>` — `!fäden` zeigt die IDs.")
            return
        cid = self._cid(ctx)
        thread = self._rt.chekhov_list(cid).resolve(thread_id)
        if thread is None:
            await ctx.send(f"Kein offener Faden `{thread_id}` — `!fäden` zeigt alle.")
            return
        self._rt.save_chekhov(cid)
        self._rt._persist_and_refresh(ctx.channel)
        log.info("chekhov thread resolved (manual): [%s] %s", thread.id, thread.detail)
        await ctx.send(f"✅ Faden aufgelöst: **{thread.detail}** (`{thread.id}`).")

    @faden.command(name="weg", aliases=["entfernen", "loeschen"])
    async def weg(self, ctx: commands.Context, thread_id: str = "") -> None:
        """`!faden weg <id>` — drop a thread entirely (a dud, not worth resolving)."""
        if not thread_id:
            await ctx.send("Nutzung: `!faden weg <id>` — `!fäden` zeigt die IDs.")
            return
        cid = self._cid(ctx)
        thread = self._rt.chekhov_list(cid).remove(thread_id)
        if thread is None:
            await ctx.send(f"Unbekannter Faden `{thread_id}` — `!fäden` zeigt alle.")
            return
        self._rt.save_chekhov(cid)
        self._rt._persist_and_refresh(ctx.channel)
        log.info("chekhov thread removed (manual): [%s] %s", thread.id, thread.detail)
        await ctx.send(f"🗑 Faden entfernt: **{thread.detail}** (`{thread.id}`).")
