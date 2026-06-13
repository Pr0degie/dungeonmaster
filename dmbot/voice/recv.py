"""Voice receive sink (Phase 2).

Wraps the foreign ``discord-ext-voice-recv`` library — kept isolated in ``voice/`` per
CLAUDE.md. The sink receives per-user audio, undoes the DAVE/E2EE layer, decodes it to PCM,
and logs it; it also drops audio from Bot A (feedback protection **layer 1** —
non-negotiable, golden rule #4). :class:`VadSink` extends it with Phase-3 resampling
(48 kHz stereo → 16 kHz mono) and silero-vad utterance segmentation.

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
import threading
import time
from dataclasses import dataclass
from typing import Callable

import davey
import discord
from discord.ext import voice_recv
from discord.opus import Decoder, OpusError

from .resample import StereoResampler
from .vad import SileroVad, UtteranceSegmenter

log = logging.getLogger(__name__)

# Don't log every packet (~50/s/user floods); accumulate and emit a heartbeat per interval.
_FLUSH_INTERVAL_S = 2.0

# DAVE (Discord end-to-end voice encryption) media type for Opus audio frames.
_MEDIA_AUDIO = davey.MediaType.audio

# A DAVE-encrypted frame ends in the protocol's magic marker 0xFAFA (the sentinel that lets a
# receiver recognise an E2EE frame; ADR 006). We use it only as a canary: if we ever get such
# a frame but have no dave_session to decrypt it, the decrypt path has broken — warn, skip.
_DAVE_MAGIC = b"\xfa\xfa"


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
        self._dave_missing_logged = False
        # write() is called from TWO threads once a SilenceGeneratorSink wraps us: the
        # voice-recv reader thread (real frames) and the silence-generator thread (synthetic
        # silence during transmission gaps). Serialize per-user state with one lock.
        self._lock = threading.Lock()

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

    def write(self, user, data: voice_recv.VoiceData) -> None:  # reader / silence-gen thread
        try:
            if user is None:
                return
            with self._lock:
                self._write_locked(user, data)
        except Exception:
            log.exception("PcmLogSink.write failed")

    def _write_locked(self, user, data: voice_recv.VoiceData) -> None:
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
            # A SilenceGeneratorSink fills transmission gaps with synthetic frames that carry
            # decoded silence PCM (no opus, no DAVE layer). Feed it straight through so the
            # segmenter sees the gap and can close the open utterance — Discord clients send
            # nothing at all while a user is silent (voice activation), so without this the
            # utterance would never end until the next speech or disconnect.
            if data.pcm:
                self._on_pcm(user.id, user.display_name, data.pcm)
            return

        # Undo the DAVE/E2EE layer if the call is encrypted (ADR 006). voice-recv only
        # undoes the transport layer, so the frame is still E2EE-wrapped; decrypt it via
        # the dave_session discord.py established over MLS.
        ds = self._dave_session()
        if ds is None:
            # No DAVE session handle. Normally that means a non-encrypted call and `opus` is
            # plain Opus — decode it as before. But DAVE is effectively always on (Discord
            # rejects opt-out, voice close 4017), so a missing handle on an *encrypted* frame
            # means the decrypt path broke (discord.py internal moved — ADR 006). Detect that
            # via the DAVE trailer magic and warn loudly + skip, instead of silently
            # Opus-decoding ciphertext into a garbage transcript.
            if opus.endswith(_DAVE_MAGIC):
                if not self._dave_missing_logged:
                    self._dave_missing_logged = True
                    log.warning(
                        "DAVE-encrypted frame received but no dave_session is reachable — "
                        "the E2EE decrypt path is broken (discord.py internal moved? see "
                        "ADR 006). Skipping encrypted frames; decoding them would yield "
                        "garbage transcripts. Run the voice-stack preflight."
                    )
                return
        elif not ds.ready:
            return  # MLS group not established yet — can't decrypt; wait for it
        else:
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

        # Seam for subclasses (Phase 3+): hand the decoded 48 kHz stereo PCM onward.
        # Runs only for non-filtered users — Bot A never reaches here (layer 1).
        self._on_pcm(user.id, user.display_name, pcm)

    def _on_pcm(self, user_id: int, name: str, pcm: bytes) -> None:
        """Hook for decoded per-user PCM (48 kHz stereo s16le). No-op in the base sink."""

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


# Callback shape: (user_id, display_name, pcm_s16le_16k_mono, duration_s).
OnUtterance = Callable[[int, str, bytes, float], None]


class VadSink(PcmLogSink):
    """Phase 3: resample each user's decoded PCM to 16 kHz mono and segment into utterances.

    Inherits the whole receive path from :class:`PcmLogSink` — DAVE/E2EE decrypt, Opus
    decode, and crucially the **layer-1 Bot A filter** (golden rule #4) — and only adds the
    per-user resample + silero-vad pipeline via the ``_on_pcm`` seam. One resampler and one
    segmenter per user; all segmenters share a single loaded silero model.
    """

    def __init__(
        self, *, bot_a_user_id: int | None = None, on_utterance: OnUtterance
    ) -> None:
        super().__init__(bot_a_user_id=bot_a_user_id)
        self._vad = SileroVad()  # load the onnx model once, up front
        self._on_utterance = on_utterance
        self._resamplers: dict[int, StereoResampler] = {}
        self._segmenters: dict[int, UtteranceSegmenter] = {}
        # Feedback protection layer 2 (ADR 003): muted while Bot A speaks. A DEPTH COUNTER, not a
        # bool, because two independent owners nest: the DM-speaking paths in dmcog (_speak /
        # _deliver_streaming, balanced mute/unmute around /speak) and the operator pause/resume in
        # voicecog.set_paused. If the operator resumes mid-playback, a plain bool's unconditional
        # unmute would flip muting off while Bot A is still talking (FINDING #8). Counting keeps it
        # muted until BOTH owners have released. Read effective state via the `_muted` property.
        self._mute_depth = 0

    @property
    def _muted(self) -> bool:
        """Effective layer-2 mute state: muted while any owner holds the mute (depth > 0)."""
        return self._mute_depth > 0

    def _pipeline_for(
        self, user_id: int, name: str
    ) -> tuple[StereoResampler, UtteranceSegmenter]:
        seg = self._segmenters.get(user_id)
        if seg is None:
            self._resamplers[user_id] = StereoResampler()
            seg = UtteranceSegmenter(
                self._vad,
                lambda pcm, dur, uid=user_id, nm=name: self._on_utterance(
                    uid, nm, pcm, dur
                ),
            )
            self._segmenters[user_id] = seg
        return self._resamplers[user_id], seg

    def _on_pcm(self, user_id: int, name: str, pcm: bytes) -> None:  # holds self._lock
        # Feedback protection layer 2 (ADR 003): while Bot A is speaking we segment nothing — not
        # even the injected silence frames — so the DM never transcribes its own voice (over the
        # layer-1 user-ID filter). Otherwise transcription runs continuously: the FULL table is
        # recorded to the log; the push-to-talk button gates only what reaches the DM (in the cog,
        # not here), so the transcript log stays complete (useful for recaps/memory later).
        if self._muted:
            return
        resampler, seg = self._pipeline_for(user_id, name)
        mono16 = resampler.feed(pcm)
        if mono16.size:
            seg.feed(mono16)

    def _flush_all_locked(self) -> None:
        """Flush every per-user segmenter — emit any in-progress utterance, then reset to clean.
        Caller must hold ``self._lock``. Shared by mute and :meth:`flush_open` so the gate boundary
        captures the trailing speech instead of gluing it across the silent gap."""
        for seg in self._segmenters.values():
            try:
                seg.flush()
            except Exception:
                log.exception("segmenter flush failed")

    def mute(self) -> None:
        """Pause segmentation while Bot A speaks (feedback layer 2, ADR 003).

        Called from the event loop around the blocking ``/speak``. Flushes any in-progress
        utterance first so a player's pre-DM speech is captured instead of being glued across the
        DM's playback gap to whatever they say afterwards; thereafter :meth:`_on_pcm` drops every
        frame until the matching :meth:`unmute`.

        Reentrant via a depth counter: independent owners (DM-speaking vs. operator pause) nest, so
        an inner unmute can't reopen the VAD while an outer owner is still speaking (FINDING #8).
        The flush only fires on the 0→1 transition; a nested second mute does not re-flush.
        """
        with self._lock:
            self._mute_depth += 1
            if self._mute_depth == 1:  # 0→1 transition: first owner to mute flushes the open table
                self._flush_all_locked()

    def unmute(self) -> None:
        """Release one mute hold; resume segmentation only once the last owner has unmuted (ADR 003).

        Clamped at 0 so a stray unmute (more unmutes than mutes) can't drive the depth negative and
        leave the VAD wedged shut on the next mute.
        """
        with self._lock:
            if self._mute_depth > 0:
                self._mute_depth -= 1

    def flush_open(self) -> None:
        """Cut any in-progress utterance now (emit it). The cog calls this when the push-to-talk
        DM-routing gate toggles, so a trailing utterance is tagged with the gate state at the
        button press rather than only after the ~600 ms VAD silence gap has elapsed."""
        with self._lock:
            self._flush_all_locked()

    def cleanup(self) -> None:
        # The wrapping SilenceGeneratorSink is cleaned up first (walk_children yields the root
        # before its child), so its thread is already stopped here; the lock guards against any
        # in-flight reader-thread write all the same.
        with self._lock:
            for seg in self._segmenters.values():
                try:
                    seg.flush()  # emit any utterance still in progress at disconnect
                except Exception:
                    log.exception("segmenter flush failed")
            self._resamplers.clear()
            self._segmenters.clear()
        super().cleanup()
