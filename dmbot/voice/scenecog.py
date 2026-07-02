"""Discord commands for the adventure scene pointer + element flags: !ort/!szenen/!ortmodus
and !erledigt/!offen (ADR 043).

A thin cog split out of DMCog (ADR 039, the deferred ADR-035 follow-up) so an agent editing
scene-pointer behaviour loads ~70 lines instead of the whole turn pipeline. The commands only
touch shared state on SessionRuntime (dmbot/runtime.py); the *automatic* <<ORT>> scene change
lives in the delivery pipeline (ADR 035). Moving the plot pointer is deterministic by design
(golden rule #3) — the human at the table does it, never the model. Bot replies are German.
"""
from __future__ import annotations

import logging

from discord.ext import commands

from ..runtime import SessionRuntime

log = logging.getLogger(__name__)


class SceneCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime

    @commands.command(name="ort", aliases=["szene"])
    async def ort(self, ctx: commands.Context, scene_id: str = "") -> None:
        """`!ort <szenen-id>` — set the adventure's scene pointer (Phase 10a): the DM's prompt then
        carries that scene's card. Deterministic by design (golden rule #3) — the human at the
        table moves the plot pointer, the model never does."""
        if self._rt._adventure is None:
            await ctx.send("Kein Abenteuer geladen (`DM_ADVENTURE` in `.env`).")
            return
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not scene_id:
            scene = self._rt._adventure.get_scene(state.scene_id)
            current = f"**{scene.title_de}** (`{scene.id}`)" if scene else "—"
            reply = f"Aktuelle Szene: {current}. Wechsel: `!ort <id>` (`!szenen` zeigt alle)."
            elements = self._element_status_de(scene, state) if scene else ""
            if elements:
                reply += f"\nElemente: {elements} (`!erledigt <id>` / `!offen <id>`)"
            await ctx.send(reply)
            return
        scene = self._rt._set_scene(state, scene_id)
        if scene is None:
            await ctx.send(f"Unbekannte Szene `{scene_id}` — `!szenen` zeigt alle Ids.")
            return
        self._rt._persist_and_refresh(ctx.channel)
        log.info("scene → %s (%s)", scene.id, scene.title_de)
        await ctx.send(f"📖 Szene gewechselt: **{scene.title_de}** (Teil {scene.part}).")

    @commands.command(name="szenen")
    async def szenen(self, ctx: commands.Context) -> None:
        """List the loaded adventure's scenes by part — the ids `!ort` accepts."""
        if self._rt._adventure is None:
            await ctx.send("Kein Abenteuer geladen (`DM_ADVENTURE` in `.env`).")
            return
        cid = self._rt._brain_channel(ctx.channel)
        current = self._rt._state[cid].scene_id if cid in self._rt._state else ""
        by_part: dict[int, list[str]] = {}
        for part, sid, title in self._rt._adventure.scene_overview():
            marker = " ◀" if sid == current else ""
            by_part.setdefault(part, []).append(f"`{sid}` {title}{marker}")
        lines = [f"**Teil {part}:** " + " · ".join(entries)
                 for part, entries in sorted(by_part.items())]
        state = self._rt._state.get(cid)
        scene = self._rt._adventure.get_scene(current) if state is not None else None
        if scene is not None:
            elements = self._element_status_de(scene, state)
            if elements:
                lines.append(f"Elemente hier: {elements}")
        await ctx.send(f"📖 **{self._rt._adventure.title}**\n" + "\n".join(lines))

    @commands.command(name="ortmodus", aliases=["szenenmodus"])
    async def ortmodus(self, ctx: commands.Context, mode: str = "") -> None:
        """`!ortmodus [verbunden|frei]` — how far an automatic scene change (ADR 026) may jump.
        `verbunden` (default): only the current scene's `leads_to` neighbours. `frei`: any scene.
        No argument shows the current mode."""
        mode = mode.strip().lower()
        if not mode:
            await ctx.send(
                f"Automatischer Szenenwechsel: **{self._rt._scene_mode}** "
                f"(`verbunden` = nur Nachbarorte, `frei` = jede Szene). Wechsel: `!ortmodus <modus>`."
            )
            return
        if mode not in ("verbunden", "frei"):
            await ctx.send(f"Unbekannter Modus `{mode}` — erlaubt: `verbunden`, `frei`.")
            return
        self._rt._scene_mode = mode
        log.info("scene mode → %s", mode)
        await ctx.send(f"📖 Szenenmodus: **{mode}**.")

    @commands.command(name="erledigt")
    async def erledigt(self, ctx: commands.Context, element_id: str = "") -> None:
        """`!erledigt <element-id>` — flag a Gelegenheit/Geheimnis of the current scene resolved
        (ADR 043). The manual override for the `<<ERLEDIGT>>` marker: the human IS the confirm,
        so the flag applies immediately, no button."""
        await self._flag(ctx, element_id, resolved=True)

    @commands.command(name="offen")
    async def offen(self, ctx: commands.Context, element_id: str = "") -> None:
        """`!offen <element-id>` — undo `!erledigt`: re-open a flagged element of the current
        scene (it moves back to the card's open list)."""
        await self._flag(ctx, element_id, resolved=False)

    async def _flag(self, ctx: commands.Context, element_id: str, *, resolved: bool) -> None:
        """Shared !erledigt/!offen body: guards, validate via the runtime's deterministic mutator
        (golden rule #3), persist + refresh, reply in German."""
        if self._rt._adventure is None:
            await ctx.send("Kein Abenteuer geladen (`DM_ADVENTURE` in `.env`).")
            return
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not element_id:
            scene = self._rt._adventure.get_scene(state.scene_id)
            elements = self._element_status_de(scene, state) if scene else ""
            cmd = "erledigt" if resolved else "offen"
            await ctx.send(f"Nutzung: `!{cmd} <element-id>`. Elemente hier: {elements or '—'}")
            return
        text = self._rt._set_scene_flag(state, element_id, resolved=resolved)
        if text is None:
            await ctx.send(f"Unbekanntes Element `{element_id}` — `!ort` zeigt die IDs der aktuellen Szene.")
            return
        self._rt._persist_and_refresh(ctx.channel)
        log.info("element flag %s → %s (scene %s)", element_id, resolved, state.scene_id)
        if resolved:
            await ctx.send(f"✅ Abgehakt: **{text}** (`{element_id}`).")
        else:
            await ctx.send(f"⬜ Wieder offen: **{text}** (`{element_id}`).")

    @staticmethod
    def _element_status_de(scene, state) -> str:
        """One compact German status line for a scene's flaggable elements: `id` ✅/⬜ per element."""
        resolved = set(state.resolved_ids(scene.id))
        return " · ".join(
            f"`{eid}` {'✅' if eid in resolved else '⬜'}" for eid in scene.element_ids()
        )
