"""The Discord panels of :class:`~dmbot.runtime.SessionRuntime`: the player panel (posted once,
then edited in place), the clock panel, the sweep of panels left by earlier runs, and the
operator channel the 🧪 debug overlay posts into.

A mixin, split out of dmbot/runtime.py for context-leanness (ADR 065): the methods are still
methods of the one ``SessionRuntime`` object — ``self`` is the runtime, all state is created in
its ``__init__`` — and every moved body is byte-identical.

Two renderers stay in runtime.py: ``_panel_text`` and ``update_debug_overlay`` read the debug
sidecar, and the ADR 052 pin allows only runtime.py to name it.
"""
from __future__ import annotations

import logging

import discord

from ..memory.state import pressure_panel_de

log = logging.getLogger(__name__)

# The player panel's first line (discord_ui/panel.py) — how old panels of this bot are recognised.
PANEL_MARK = "📍 **Wo ihr seid:**"
PANEL_SWEEP_LIMIT = 100  # recent messages searched for this bot's panel after a restart


class PanelsMixin:
    """Panel posting, editing and sweeping. Mixed into ``SessionRuntime``; holds no state of its own."""

    async def update_clock_panel(self) -> None:
        """(Re)render the pressure panel (time + deadlines + clocks, ADR 047/048) in the
        session's text channel — edit-in-place (the pause-panel pattern), so ticks/advances
        update one message instead of spamming. No clocks AND no deadlines → the panel is
        removed (`!zeit` shows the bare time on demand). Best-effort: a send/edit failure
        logs, never breaks a turn/command."""
        if self._text_channel is None:
            return
        if self._player_panel_enabled:
            # Time, deadlines (and clocks) live in the player panel — one message, not two (D133).
            await self.clear_panel("_clock_panel")
            await self._sweep_pressure_panels()
            await self.update_player_panel()
            return
        state = self._state.get(self._active_vc_id) if self._active_vc_id is not None else None
        clocks = self.clocks_enabled
        if state is None or not ((clocks and state.clocks) or state.deadlines):
            await self.clear_panel("_clock_panel")
            return
        content = pressure_panel_de(state, clocks=clocks)
        if self._clock_panel is not None:
            try:
                await self._clock_panel.edit(content=content)
                return
            except discord.HTTPException:
                self._clock_panel = None  # message gone — fall through and re-post
        try:
            self._clock_panel = await self._text_channel.send(content)
        except discord.HTTPException:
            log.warning("could not post the clock panel", exc_info=True)

    async def _sweep_pressure_panels(self) -> None:
        """Delete this bot's separate pressure panels (time + deadlines) left by earlier runs, now
        that the player panel carries them (D133). Once per channel and run, recent history only."""
        channel = self._text_channel
        seen = self._pressure_swept_channels
        if getattr(channel, "id", None) in seen:
            return
        seen.add(getattr(channel, "id", None))
        me = getattr(getattr(channel, "guild", None), "me", None)
        history = getattr(channel, "history", None)
        if me is None or history is None:
            return
        try:
            async for msg in history(limit=PANEL_SWEEP_LIMIT):
                text = msg.content or ""
                if (getattr(msg.author, "id", None) == me.id and text.startswith("🕐 **")
                        and "\n⏳ **" in text):
                    try:
                        await msg.delete()
                    except discord.HTTPException:
                        pass
        except discord.HTTPException:
            log.info("could not read the channel history to sweep old pressure panels")

    def _operator_channel(self):
        """The configured ``DM_DEBUG_CHANNEL``, or ``None`` when none is set or it cannot be
        resolved — never the game channel.

        Everything that would leak campaign structure if the table read it (scene ids, gate
        conditions, verdict internals) goes here and nowhere else. ``DM_DEBUG_CHANNEL`` is empty
        in ``.env.example``, so "fall back to the game channel" means "read it out to the
        players"; for those lines the log plus the model-facing ``[Regie]`` note are the whole
        delivery."""
        if not self._debug_channel_id:
            return None
        guild = getattr(self._text_channel, "guild", None)
        ch = guild.get_channel(self._debug_channel_id) if guild is not None else None
        if ch is not None:
            return ch
        if not self._debug_channel_warned:
            log.warning("🧪 DM_DEBUG_CHANNEL=%s not resolvable — overlay falls back to "
                        "the game channel", self._debug_channel_id)
            self._debug_channel_warned = True
        return None

    def _debug_overlay_channel(self):
        """The 🧪 overlay's target: the operator channel when there is one, else the session's
        text channel. The overlay itself is spoiler-safe by construction (ADR 052), so the
        fallback is fine here — unlike for the operator lines above."""
        return self._operator_channel() or self._text_channel

    async def update_player_panel(self, *, reanchor: bool = False) -> None:
        """(Re)render the player panel in the session's text channel.

        Posted once at the bottom, then only ever edited in place — it is never re-posted, so it
        drifts up as the table plays (Tobi's choice, D132). One per channel: after a restart the
        bot adopts its newest panel from the channel instead of posting another, and deletes
        older duplicates. ``reanchor=True`` (tests, a manual reset) deletes and posts it anew.
        Best-effort: a send/edit failure logs and never breaks a turn."""
        if not self._player_panel_enabled or self._text_channel is None:
            return
        content = self._panel_text()
        if not content:
            return
        async with self._player_panel_lock:  # two quick updates must not post two panels
            if reanchor:
                await self.clear_panel("_player_panel")
            elif self._player_panel is None:
                self._player_panel = await self._adopt_old_panel()
            if self._player_panel is not None:
                try:
                    await self._player_panel.edit(content=content)
                    return
                except discord.HTTPException:
                    self._player_panel = None  # message gone — fall through and post anew
            try:
                self._player_panel = await self._text_channel.send(content)
            except discord.HTTPException:
                log.warning("could not post the player panel", exc_info=True)

    async def _adopt_old_panel(self):
        """This bot's newest player panel in the text channel, to edit instead of posting another
        (a restart forgets the handle); older duplicates are deleted. Once per channel and run,
        recent history only; best-effort — no permission / no history → ``None``."""
        channel = self._text_channel
        seen = self._panel_swept_channels
        if getattr(channel, "id", None) in seen:
            return None
        seen.add(getattr(channel, "id", None))
        me = getattr(getattr(channel, "guild", None), "me", None)
        history = getattr(channel, "history", None)
        if me is None or history is None:
            return None
        found = []
        try:
            async for msg in history(limit=PANEL_SWEEP_LIMIT):  # newest first
                if getattr(msg.author, "id", None) == me.id and (msg.content or "").startswith(PANEL_MARK):
                    found.append(msg)
        except discord.HTTPException:
            log.info("could not read the channel history to find the player panel")
            return None
        for dupe in found[1:]:
            try:
                await dupe.delete()
            except discord.HTTPException:
                pass
        return found[0] if found else None
