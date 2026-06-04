"""Voice receive sink (Phase 2).

Wraps the foreign ``discord-ext-voice-recv`` library — kept isolated in ``voice/`` per
CLAUDE.md. The sink receives per-user audio, undoes the DAVE/E2EE layer, decodes it to PCM,
and logs it; it also drops audio from Bot A (feedback protection **layer 1** —
non-negotiable, golden rule #4). Resampling to 16 kHz mono and VAD segmentation are Phase 3.

API checked against the *installed* discord-ext-voice-recv 0.5.2a179 (the sink callback
signature is version-sensitive — verify before trusting it):

    AudioSink.wants_opus(self) -> bool
    AudioSink.write(self, user: Optional[discord.User], data: VoiceData)
    AudioSink.cleanup(self)
    VoiceData.source: Optional[User];  VoiceData.opus: bytes;  VoiceData.pcm: bytes

**Why wants_opus=True (we decode ourselves).** Two reasons (see ADR 006):
1. *DAVE / E2EE.* discord.py negotiates Discord's end-to-end voice encryption, so each frame
   voice-recv hands us is still E2EE-wrapped (a DAVE frame ending in the ``0xFAFA`` magic,
   not plain Opus). voice-recv only undoes the *transport* layer. We must undo the DAVE
   layer via the connection's ``dave_session`` **before** Opus-decoding — only possible if
   we receive the raw frame.
2. *Fatal router.* With wants_opus=False the library decodes inside its packet-router
   thread, and that loop is fatal: a single ``OpusError`` makes ``PacketRouter.run`` call
   ``stop_listening()`` in its ``finally``, tearing down the whole receive. Decoding here
   lets us skip a bad frame instead of dying.

``write`` runs on the library's reader **thread** (single-threaded delivery under the router
lock), not the event loop — keep it non-async and never raise out of the callback.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import davey
import discord
from discord.ext import voice_recv
from discord.opus import Decoder, OpusError

log = logging.getLogger(__name__)

# Don't log every packet (~50/s/user floods); accumulate and emit a heartbeat per interval.
_FLUSH_INTERVAL_S = 2.0

# DAVE (Discord end-to-end voice encryption) media type for Opus audio frames.
_MEDIA_AUDIO = davey.MediaType.audio


@dataclass
class _UserTally:
    name: str
    packets: int = 0          # frames received
    decoded: int = 0          # successfully decoded to PCM
    decode_errors: int = 0    # skipped (corrupted/lost) — non-fatal
    pcm_bytes: int = 0        # decoded PCM bytes
    decoded_since_flush: int = 0


class PcmLogSink(voice_recv.AudioSink):
    """Decrypts (DAVE) and decodes incoming per-user Opus to PCM; drops Bot A (layer 1).

    Filtering is twofold: an explicit ``bot_a_user_id`` (from config) **and** any source
    whose ``.bot`` flag is set. The explicit ID is authoritative; the bot-flag check is
    belt-and-braces for when the ID isn't configured. Either way Bot A is never tallied.
    """

    def __init__(self, *, bot_a_user_id: int | None = None) -> None:
        super().__init__()
        self._bot_a_user_id = bot_a_user_id
        self._tallies: dict[int, _UserTally] = {}
        self._decoders: dict[int, Decoder] = {}  # one Opus decoder per user (per stream)
        self._filtered_ids: set[int] = set()
        self._last_flush = time.monotonic()
        self._dave_active_logged = False

    def wants_opus(self) -> bool:
        # True -> library hands us raw frames; we DAVE-decrypt then Opus-decode here (see
        # module docstring). It never decodes in its own fatal router loop.
        return True

    def _is_filtered(self, user: discord.User | discord.Member | None) -> bool:
        if user is None:
            return False
        if self._bot_a_user_id is not None and user.id == self._bot_a_user_id:
            return True
        return bool(getattr(user, "bot", False))

    def _decoder_for(self, user_id: int) -> Decoder:
        decoder = self._decoders.get(user_id)
        if decoder is None:
            decoder = Decoder()
            self._decoders[user_id] = decoder
        return decoder

    def _dave_session(self):
        """The connection's DAVE session if the call is end-to-end encrypted, else None."""
        conn = getattr(self.voice_client, "_connection", None)
        return getattr(conn, "dave_session", None)

    def write(self, user, data: voice_recv.VoiceData) -> None:  # reader thread
        try:
            if user is None:
                return

            if self._is_filtered(user):
                if user.id not in self._filtered_ids:
                    self._filtered_ids.add(user.id)
                    log.info(
                        "layer-1: filtering out %s (id=%s) — bot/Bot A voice dropped",
                        user.display_name,
                        user.id,
                    )
                return

            opus = data.opus
            if not opus:
                return

            # Undo the DAVE/E2EE layer if the call is encrypted (ADR 006). voice-recv only
            # undoes the transport layer, so the frame is still E2EE-wrapped; decrypt it via
            # the dave_session discord.py established over MLS.
            ds = self._dave_session()
            if ds is not None:
                if not ds.ready:
                    return  # MLS group not established yet — can't decrypt; wait for it
                try:
                    opus = ds.decrypt(user.id, _MEDIA_AUDIO, opus)
                except Exception:
                    return  # user not yet in the MLS group / transient — skip this frame
                if not self._dave_active_logged:
                    self._dave_active_logged = True
                    log.info("DAVE/E2EE active — decrypting incoming Opus via dave_session")

            tally = self._tallies.get(user.id)
            if tally is None:
                tally = _UserTally(name=user.display_name)
                self._tallies[user.id] = tally
                log.info("▶ receiving audio from %s (id=%s)", user.display_name, user.id)
            tally.packets += 1

            try:
                pcm = self._decoder_for(user.id).decode(opus, fec=False)
            except OpusError:
                tally.decode_errors += 1
                return

            tally.decoded += 1
            tally.decoded_since_flush += 1
            tally.pcm_bytes += len(pcm)
            self._maybe_flush()
        except Exception:
            log.exception("PcmLogSink.write failed")

    def _maybe_flush(self) -> None:
        now = time.monotonic()
        if now - self._last_flush < _FLUSH_INTERVAL_S:
            return
        self._last_flush = now

        active = [t for t in self._tallies.values() if t.decoded_since_flush]
        if not active:
            return
        parts = []
        for t in active:
            drops = f", {t.decode_errors} dropped" if t.decode_errors else ""
            parts.append(
                f"{t.name}: +{t.decoded_since_flush} decoded ({t.pcm_bytes // 1024} KiB){drops}"
            )
            t.decoded_since_flush = 0
        log.info("PCM ⟳ %s", " | ".join(parts))

    def cleanup(self) -> None:
        if self._tallies:
            summary = " | ".join(
                f"{t.name}: {t.decoded}/{t.packets} pkt decoded "
                f"({t.pcm_bytes // 1024} KiB, {t.decode_errors} dropped)"
                for t in self._tallies.values()
            )
            log.info("sink cleanup — per-user PCM totals: %s", summary)
        if self._filtered_ids:
            log.info("sink cleanup — filtered (layer 1): %s", sorted(self._filtered_ids))
        self._decoders.clear()
