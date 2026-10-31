"""Pre-uploaded throw GIFs (ADR 064): upload once to a storage channel, then only point at them.

Editing a message with a ~300 KB attachment took ~1.2 s of the ~1.8 s between the 🎲 click and the
GIF showing (2026-10-30, live). An edit that only points at an already uploaded file skips that.
So the 75 flight-only GIFs (25 trajectories × red/gold/green, no landing — one GIF serves every
result) are uploaded **once** into a storage channel (``DM_DICE_ASSET_CHANNEL``, a name such as
``botcommands`` or a channel id), ten per message. The message ids are kept in
``data/dice/anim/assets.json``; Discord's attachment links expire after about a day, so fresh links
come from re-fetching those few messages, never from uploading again.

Presentation only and fail-open: no channel, no permission, not ready yet → ``url()`` is ``None``
and the dice flow uploads the GIF like before. Nothing here touches the engine or the journal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import discord

from . import dice_images

log = logging.getLogger(__name__)

STATE_FILE = dice_images.ANIM_DIR / "assets.json"
PER_MESSAGE = 10            # Discord's attachment cap per message
REFRESH_AFTER_S = 6 * 3600  # links live ~24 h; re-fetch well before


def _norm(name: str) -> str:
    """``"🤖-bot-commands"`` → ``"botcommands"``: compare channel names by letters and digits."""
    return re.sub(r"[^0-9a-z]", "", name.lower())


def asset_name(seed: int, palette: str) -> str:
    return f"flight_v{dice_images._load_renderer().gif_version()}_s{seed}_{palette}.gif"


class DiceAssetStore:
    """Per guild: the storage channel, the uploaded flight GIFs' links, and their message ids."""

    def __init__(self, spec: str, *, state_file: Path | None = None) -> None:
        self._spec = spec.strip()
        self._state_file = state_file or STATE_FILE
        self._urls: dict[int, dict[str, str]] = {}       # guild id → asset name → link
        self._fetched_at: dict[int, float] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._refreshing: set[int] = set()
        self._tasks: set[asyncio.Task] = set()
        self._file_lock = threading.Lock()

    # --- lookup ----------------------------------------------------------------------------------

    def resolve_channel(self, guild):
        """The storage channel in ``guild``: by id if the spec is a number, else by name."""
        if not self._spec or guild is None:
            return None
        channels = list(getattr(guild, "text_channels", []) or [])
        if self._spec.isdigit():
            return next((c for c in channels if c.id == int(self._spec)), None)
        want = _norm(self._spec)
        return next((c for c in channels if _norm(c.name) == want), None)

    def url(self, guild, seed: int, palette: str) -> str | None:
        """The link of the stored flight GIF, or ``None`` (not stored / not ready → upload path).
        A link older than :data:`REFRESH_AFTER_S` still works (~24 h); a refresh starts quietly."""
        if guild is None:
            return None
        urls = self._urls.get(guild.id)
        if not urls:
            return None
        if time.monotonic() - self._fetched_at.get(guild.id, 0.0) > REFRESH_AFTER_S:
            self._start_refresh(guild)
        return urls.get(asset_name(seed, palette))

    # --- state file ------------------------------------------------------------------------------

    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_guild(self, guild_id: int, entry: dict) -> None:
        with self._file_lock:
            state = self._load_state()
            state[str(guild_id)] = entry
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_file.with_name(f".assets.{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
                os.replace(tmp, self._state_file)
            finally:
                tmp.unlink(missing_ok=True)

    # --- upload once, refresh by fetching --------------------------------------------------------

    async def ensure(self, guild) -> bool:
        """Make every flight GIF available in ``guild``'s storage channel: fetch the messages we
        stored before, upload only what is missing. Idempotent; ``True`` when all are stored."""
        channel = self.resolve_channel(guild)
        if channel is None:
            log.warning("dice assets: no storage channel %r in %s — throws upload their GIF",
                        self._spec, getattr(guild, "name", guild))
            return False
        lock = self._locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            try:
                return await self._ensure(guild, channel)
            except (discord.HTTPException, OSError, ValueError):
                log.warning("dice assets: storing the throw GIFs failed — throws upload their GIF",
                            exc_info=True)
                return False

    async def _ensure(self, guild, channel) -> bool:
        version = dice_images._load_renderer().gif_version()
        entry = self._load_state().get(str(guild.id), {})
        if entry.get("channel_id") != channel.id or entry.get("version") != version:
            entry = {"channel_id": channel.id, "version": version, "messages": {}}
        urls = await self._fetch(channel, entry)
        self._publish(guild.id, urls)

        seeds = await asyncio.to_thread(dice_images.throw_seeds)
        needed = [(seed, palette) for palette in dice_images.RESULT_PALETTES for seed in seeds]
        missing = [(s, p) for s, p in needed if asset_name(s, p) not in urls]
        if missing:
            log.info("dice assets: uploading %d throw GIFs once to #%s", len(missing), channel.name)
        parts = [missing[i:i + PER_MESSAGE] for i in range(0, len(missing), PER_MESSAGE)]
        for n, part in enumerate(parts, 1):
            paths = [(await asyncio.to_thread(dice_images.get_flight_gif, s, p))[0] for s, p in part]
            files = [discord.File(path, filename=asset_name(s, p)) for path, (s, p) in zip(paths, part)]
            message = await channel.send(
                f"🎲 Würfel-Animationen für den DM-Bot — Ablage, bitte nicht löschen ({n}/{len(parts)})",
                files=files,
            )
            entry["messages"][str(message.id)] = [a.filename for a in message.attachments]
            urls.update({a.filename: a.url for a in message.attachments})
            self._save_guild(guild.id, entry)
            self._publish(guild.id, urls)
        self._save_guild(guild.id, entry)
        complete = all(asset_name(s, p) in urls for s, p in needed)
        log.info("dice assets: %d/%d throw GIFs ready in #%s", sum(asset_name(s, p) in urls for s, p in needed),
                 len(needed), channel.name)
        return complete

    async def _fetch(self, channel, entry: dict) -> dict[str, str]:
        """Fresh links for the stored messages; a message gone (deleted) drops out of ``entry``."""
        urls: dict[str, str] = {}
        for message_id in list(entry.get("messages", {})):
            try:
                message = await channel.fetch_message(int(message_id))
            except discord.NotFound:
                log.info("dice assets: storage message %s is gone — its GIFs get uploaded again",
                         message_id)
                del entry["messages"][message_id]
                continue
            urls.update({a.filename: a.url for a in message.attachments})
        return urls

    def _publish(self, guild_id: int, urls: dict[str, str]) -> None:
        self._urls[guild_id] = dict(urls)
        self._fetched_at[guild_id] = time.monotonic()

    def _start_refresh(self, guild) -> None:
        if guild.id in self._refreshing:
            return
        self._refreshing.add(guild.id)

        async def _refresh() -> None:
            try:
                await self.ensure(guild)
            finally:
                self._refreshing.discard(guild.id)

        try:
            task = asyncio.get_running_loop().create_task(_refresh())
        except RuntimeError:  # no running loop (sync caller) — the next lookup tries again
            self._refreshing.discard(guild.id)
            return
        self._tasks.add(task)  # keep a reference until it's done
        task.add_done_callback(self._tasks.discard)
