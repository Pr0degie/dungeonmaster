"""Discord commands for the adventure scene pointer + element flags: !ort/!szenen/!ortmodus,
!erledigt/!offen (ADR 043), !fakt (ADR 058) and !automatik (the D107 kill switches).

A thin cog split out of DMCog (ADR 039, the deferred ADR-035 follow-up) so an agent editing
scene-pointer behaviour loads ~70 lines instead of the whole turn pipeline. The commands only
touch shared state on SessionRuntime (dmbot/runtime.py); the *automatic* <<ORT>> scene change
lives in the delivery pipeline (ADR 035). Moving the plot pointer is deterministic by design
(golden rule #3) — the human at the table does it, never the model. Bot replies are German.
"""
from __future__ import annotations

import logging

from discord.ext import commands

from ..memory.state import TURN_ADVANCE_MINUTES, WorldState, fact_line_de
from ..rules.scene_flow import MoveTrigger
from ..runtime import SessionRuntime

log = logging.getLogger(__name__)

# The live kill switches of D107: table-facing name → (runtime attribute, one German line).
# One command instead of five, because five separate `!…modus` commands nobody remembers is how
# the confirm button of 2026-08-22 ended up unused.
_SWITCHES: dict[str, tuple[str, str]] = {
    "szene": ("_scene_router", "Szenenwechsel: nach jedem Zug wird geprüft, ob ihr wirklich "
                               "woanders angekommen seid (ADR 057)."),
    "flaggen": ("_scene_flag_gate", "Ist in einer Szene alles abgehakt und führt genau ein Weg "
                                    "weiter, zieht die Sitzung von selbst weiter."),
    "fakten": ("_fact_router", "Übergebene Gegenstände, angenommene Aufträge und Zusagen werden "
                               "als harte Fakten festgehalten (ADR 058)."),
    "zeit": ("_turn_time_advance", "Jeder Zug kostet ein paar Minuten Spielzeit (ADR 059)."),
    "panel": ("_player_panel_enabled", "Die Übersicht im Kanal: Ort, Ziel, Uhrzeit, Frist, "
                                       "was hier noch offen ist."),
}

# Fact kinds (ADR 058) as the table reads them in !fakt.
_FACT_KINDS_DE: dict[str, str] = {"item": "Gegenstand", "promise": "Zusage", "quest": "Auftrag"}


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
        # One mover, one path: persist, NPC registration, NPC-memory mining, travel time,
        # overlay and panel all live in move_scene, so !ort cannot drift away from the
        # classifier and the flag gate (runtime.py module docstring). The reachability check
        # is NOT part of it — the human at the table may jump anywhere the automation never
        # would, which is the whole point of the command. We announce ourselves, in the
        # channel the command came from, so move_scene's own line stays off.
        scene = await self._rt.move_scene(ctx.channel, scene_id,
                                          trigger=MoveTrigger.COMMAND, announce=False)
        if scene is None:
            await ctx.send(f"Unbekannte Szene `{scene_id}` — `!szenen` zeigt alle Ids.")
            return
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

    @commands.command(name="automatik", aliases=["auto"])
    async def automatik(self, ctx: commands.Context, *, args: str = "") -> None:
        """`!automatik [name] [an|aus]` — the live kill switches for the post-turn machinery
        (D107 / ADR 057/058/059). Bare `!automatik` shows what is on.

        Everything the round added runs after a narrated turn and can misfire at the table, so
        each block costs one command instead of the session: `szene` (the scene classifier),
        `flaggen` (the model-free flag gate), `fakten` (the fact classifier), `zeit` (the per-turn
        in-game minutes) and `panel` (the player panel). The defaults live in `.env`
        (`DM_SCENE_ROUTER`, `DM_SCENE_FLAG_GATE`, `DM_FACT_ROUTER`, `DM_TURN_TIME_ADVANCE`,
        `DM_PLAYER_PANEL`); this only changes the running session."""
        words = args.lower().split()
        names = [w for w in words if w in _SWITCHES]
        wanted = next((w in ("an", "ein", "on", "1") for w in words
                       if w in ("an", "ein", "on", "1", "aus", "off", "0")), None)
        if names and wanted is not None:
            for name in names:
                self._set_switch(name, wanted)
            log.info("automatik: %s → %s", ", ".join(names), "on" if wanted else "off")
            await ctx.send("🎚 " + self._switch_status_de())
            return
        lines = ["🎚 **Automatik** — was nach jedem Zug von selbst läuft (wirkt sofort).",
                 self._switch_status_de(), ""]
        lines += [f"• `{name}` — {text}" for name, (_, text) in _SWITCHES.items()]
        lines.append("**Ändern:** `!automatik <name> an|aus` (mehrere Namen auf einmal gehen).")
        if words and not names:
            lines.insert(0, f"❓ Unbekannt: {', '.join(words)}")
        await ctx.send("\n".join(lines))

    def _switch_value(self, name: str) -> bool:
        attr, _ = _SWITCHES[name]
        value = getattr(self._rt, attr, False)
        return bool(value)

    def _set_switch(self, name: str, on: bool) -> None:
        """Apply one switch. The time switch is an int (minutes), so turning it back on restores
        the configured default rather than an arbitrary 1."""
        attr, _ = _SWITCHES[name]
        if attr == "_turn_time_advance":
            self._rt._turn_time_advance = TURN_ADVANCE_MINUTES if on else 0
            return
        setattr(self._rt, attr, on)

    def _switch_status_de(self) -> str:
        return "Aktuell: " + " · ".join(
            f"{name} **{'an' if self._switch_value(name) else 'aus'}**" for name in _SWITCHES
        )

    # ----- hard facts (ADR 058): the operator's retraction path ---------------------------

    @commands.group(name="fakt", aliases=["fakten"], invoke_without_command=True)
    async def fakt(self, ctx: commands.Context) -> None:
        """`!fakt` — zeigt die harten Fakten dieser Sitzung; `!fakt weg <Text>` nimmt einen
        zurück.

        The post-turn classifier (ADR 058) writes items handed over and promises given straight
        into the world state, and a fact is prompt-resident from then on: a wrong one is worse
        than a forgotten right one. This is the retraction the ADR promises — without it
        ``revoke_fact`` had no caller at all (docs/lessons/unwired-knobs-and-silent-fallbacks)."""
        state = self._session_state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        facts = state.open_facts()
        if not facts:
            await ctx.send("Keine harten Fakten festgehalten. "
                           "(`!automatik fakten aus` schaltet die Aufnahme ab.)")
            return
        lines = ["📌 **Harte Fakten:**"]
        lines += [f"- {_FACT_KINDS_DE.get(f.kind, f.kind)}: {fact_line_de(f)}" for f in facts]
        lines.append("Zurücknehmen: `!fakt weg <Text>` (der Text vor dem Pfeil).")
        await ctx.send("\n".join(lines))

    @fakt.command(name="weg", aliases=["entfernen", "loeschen", "löschen"])
    async def fakt_weg(self, ctx: commands.Context, *, text: str = "") -> None:
        """`!fakt weg <Text>` — take a wrongly recorded fact back: it stops holding, and an item
        leaves the recipient's sheet again. Matched on the fact's label, case-insensitively."""
        state = self._session_state(ctx)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        label = text.strip()
        if not label:
            await ctx.send("Nutzung: `!fakt weg <Text>` — `!fakt` zeigt die Fakten.")
            return
        fact = state.revoke_fact(label)
        if fact is None:
            await ctx.send(f"Kein offener Fakt `{label}` — `!fakt` zeigt alle.")
            return
        self._rt._persist_and_refresh(ctx.channel)   # out of the prompt with the next turn
        await self._rt.update_player_panel()         # and off the table's panel (D107)
        log.info("fact revoked (manual): %s %s -> %s", fact.kind, fact.text, fact.holder)
        kind = _FACT_KINDS_DE.get(fact.kind, fact.kind)
        await ctx.send(f"🗑 Fakt zurückgenommen ({kind}): **{fact.text}**.")

    def _session_state(self, ctx: commands.Context) -> WorldState | None:
        """The world state of the channel this command came from, or None when no session runs."""
        return self._rt._state.get(self._rt._brain_channel(ctx.channel))

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
        await self._rt.update_player_panel()  # "what is still open here" just changed (D107)
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
