"""Discord commands for the human GM's NPC bookkeeping: !npc/!nsc (register an enemy, list them),
!npcmem (what an NPC remembers, ADR 044), !agenda and !agenden (offscreen goals, ADR 049).

A thin cog split out of DiceCog for context-leanness (ADR 039): the four commands have nothing to
do with dice and only touch shared state on SessionRuntime (dmbot/runtime.py). No hook needed —
no other cog calls them. Bot replies are German.
"""
from __future__ import annotations

from discord.ext import commands

from ..runtime import SessionRuntime


class NpcCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime

    @commands.command(name="npc", aliases=["nsc"])
    async def npc(
        self, ctx: commands.Context, action: str = "", name: str = "",
        wounds: str = "", tb: str = "", armour: str = "",
    ) -> None:
        """Register an enemy the party can damage: `!npc add Kultist 10 3 2` (Wunden, ToughnessBonus,
        Rüstung). With a loaded adventure, `!npc add Alecto` fills the statblock from the
        compendium's npcs.json (Phase 10a) — explicit numbers still override. `!npc list` shows
        them. (NSC-Namen ohne Leerzeichen — z. B. `Raguel_der_Rote`.)

        Wounds/TB/armour are parsed tolerantly (str + manual ``int``) so a stray non-numeric token
        gives a clear usage hint instead of discord.py's raw ``BadArgument`` traceback — the error
        that blocked the Phase-9 live gate."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if action.lower() in ("", "list"):
            if not state.npcs:
                await ctx.send("Keine NSCs registriert. `!npc add <Name> [Wunden] [TB] [Rüstung]`.")
                return
            lines = "; ".join(
                f"{n.name} {n.wounds}/{n.max_wounds}" + (f" [{n.attitude}]" if n.attitude else "")
                for n in state.npcs
            )
            await ctx.send(f"**NSCs:** {lines}")
            return
        if action.lower() == "add":
            if not name:
                await ctx.send("Nutzung: `!npc add <Name> [Wunden] [ToughnessBonus] [Rüstung]`.")
                return
            # Compendium statblock (Phase 10a): a known adventure NPC brings its own values;
            # explicit numbers override field by field. No adventure → the old 10/0/0 defaults.
            block = self._rt._adventure.npc(name) if self._rt._adventure is not None else None
            try:
                w = int(wounds) if wounds else (block.wounds if block else 10)
                t = int(tb) if tb else (block.toughness_bonus if block else 0)
                a = int(armour) if armour else (block.armour if block else 0)
            except ValueError:
                await ctx.send(
                    "Wunden, ToughnessBonus und Rüstung müssen Zahlen sein. "
                    "Nutzung: `!npc add <Name> [Wunden] [TB] [Rüstung]` — z. B. `!npc add Kultist 10 3`. "
                    "(NSC-Namen ohne Leerzeichen, z. B. `Raguel_der_Rote`.)"
                )
                return
            display = block.name if block is not None else name  # canonical spelling from the sheet
            n = state.add_or_update_npc(
                display, wounds=w, max_wounds=w, toughness_bonus=t, armour=a,
                faction=block.faction if block is not None else "",
                goal=block.goal_de if block is not None else "",
            )
            self._rt._persist_and_refresh(ctx.channel)
            src = " *(Statblock aus dem Abenteuer)*" if block is not None and not wounds else ""
            await ctx.send(
                f"➕ NSC **{n.name}**: {n.wounds} Wunden, TB {n.toughness_bonus}, "
                f"Rüstung {n.armour}.{src}"
            )
            return
        await ctx.send("Nutzung: `!npc add <Name> [Wunden] [TB] [Rüstung]` oder `!npc list`.")

    @commands.command(name="npcmem")
    async def npcmem(self, ctx: commands.Context, name: str = "") -> None:
        """`!npcmem "<Name>"` — read-only debug view of an NPC's stored memories (ADR 044): gist,
        importance, source, believed flag. Editing stays out of scope (state is code-owned)."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not name:
            with_mem = [n.name for n in state.npcs if n.memories]
            await ctx.send(
                'Nutzung: `!npcmem "<Name>"`. NSCs mit Erinnerungen: '
                + (", ".join(with_mem) if with_mem else "—")
            )
            return
        npc = next((n for n in state.npcs if n.name.lower() == name.strip().lower()), None)
        if npc is None:
            await ctx.send(f"Unbekannter NSC `{name}` — `!npc list` zeigt alle.")
            return
        if not npc.memories:
            await ctx.send(f"**{npc.name}** hat noch keine Erinnerungen.")
            return
        lines = [f"🧠 **{npc.name}** — Haltung: {npc.attitude or '—'}"
                 + (f", Fraktion: {npc.faction}" if npc.faction else "")]
        for i, m in enumerate(npc.memories):
            tags = [f"W{m.importance}", m.source]
            if not m.believed:
                tags.append("LÜGE aufgeflogen")
            quote = f" — Zitat: „{m.quote}“" if m.quote else ""
            lines.append(f"[{i}] ({', '.join(tags)}) {m.gist}{quote}")
        await self._rt._send_with_retry(ctx.channel, "\n".join(lines))

    @commands.command(name="agenda")
    async def agenda(self, ctx: commands.Context, name: str = "", *, goal: str = "") -> None:
        """`!agenda "<NSC>" <Ziel>` / `!agenda "<NSC>" weg` — set/change/remove an NPC's offscreen
        goal (ADR 049). Goals are human-set, never LLM output; the log survives removal."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        goal = goal.strip().strip('"„“').strip()
        if not name or not goal:
            await ctx.send(
                "Nutzung: `!agenda <NSC> \"<Ziel>\"` setzt/ändert ein Ziel, "
                "`!agenda <NSC> weg` entfernt es, `!agenden` listet alle."
            )
            return
        npc = next((n for n in state.npcs if n.name.lower() == name.strip().lower()), None)
        if npc is None:
            await ctx.send(f"Unbekannter NSC `{name}` — `!npc list` zeigt alle.")
            return
        if goal.lower() == "weg":
            if not npc.goal:
                await ctx.send(f"**{npc.name}** hat kein Ziel gesetzt.")
                return
            npc.goal = ""
            self._rt._persist_and_refresh(ctx.channel)
            await ctx.send(f"🎯 Ziel von **{npc.name}** entfernt (Verlauf bleibt erhalten).")
            return
        npc.goal = goal
        self._rt._persist_and_refresh(ctx.channel)
        note = ""
        agenda_count = sum(1 for n in state.npcs if n.goal)
        if agenda_count > 5:
            note = (
                f"\n⚠️ {agenda_count} Agenda-NSCs — mehr als ~5 fressen Kontext und "
                "Extraktions-Tokens (ADR 049)."
            )
        await ctx.send(f"🎯 **{npc.name}** verfolgt jetzt: {goal}{note}")

    @commands.command(name="agenden")
    async def agenden(self, ctx: commands.Context) -> None:
        """`!agenden` — list every agenda NPC's goal + its most recent offscreen steps."""
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        agenda_npcs = [n for n in state.npcs if n.goal]
        if not agenda_npcs:
            await ctx.send("Keine Agenda-NSCs. `!agenda <NSC> \"<Ziel>\"` setzt ein Ziel.")
            return
        lines: list[str] = []
        for npc in agenda_npcs:
            dead = " (tot)" if npc.wounds <= 0 else ""
            lines.append(f"🎯 **{npc.name}**{dead} — {npc.goal}")
            for step in npc.agenda_log[-3:]:
                ts = f" [{step.ts_ingame}]" if step.ts_ingame else ""
                lines.append(f"  •{ts} {step.text}")
        await self._rt._send_with_retry(ctx.channel, "\n".join(lines))
