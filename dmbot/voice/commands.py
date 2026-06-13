"""Discord commands to drive Phase 2 voice receive.

`!join`  — join the caller's voice channel and start the per-user VAD pipeline.
`!leave` — stop listening, print per-user totals, disconnect.
`!vstatus` — connection / listening / Opus state.

Foreign voice-recv wiring stays inside ``voice/`` (CLAUDE.md). Bot replies are German
(seen in Discord); logs are English.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import tempfile
import time
import wave
from dataclasses import dataclass
from datetime import datetime

import discord
from discord.ext import commands, voice_recv

from .recv import VadSink
from .preflight import check_dave_session, check_static
from ..stt import Transcriber
from ..llm.client import OllamaClient
from ..llm.roll_router import roll_button_source
from ..orchestrator import DMBrain
from ..tts.piper import PiperTTS
from ..tts.textsplit import has_speakable_content
from ..bridge import BridgeClient
from ..discord_ui.mic import MicToggleView
from ..discord_ui.dice import DiceTestView
from ..discord_ui.turnorder import TurnOrderView
from ..discord_ui.pause import PauseToggleView, pause_embed
from ..discord_ui.rules import RulesView
from ..discord_ui.target import TargetSelectView
from ..rules import engine, profile as profile_mod
from ..rules.profile import ProfileError, SystemProfile
from ..rules.characters import Character, CharacterStore, resolve_target
from ..rules.marker import TestRequest, extract_tests
from ..rules.summary import rules_pages_de
from ..memory.state import WorldState, world_state_summary_de
from ..memory import history as history_store
from ..shutdown import progress, to_daemon_thread
from ..rag.adventure import Adventure
from ..rag.lore import available_topics, lore_pages
from ..rag.retrieve import RulebookRetriever

# Repo data dir (data/systems is the profile root; sessions/ sits beside it).
_DATA_DIR = profile_mod.systems_dir().parent

log = logging.getLogger(__name__)

_SR_16K = 16_000

# Context-budget smoke signal: warn once a narration prompt fills more than this fraction of
# num_ctx. Above it, Ollama starts truncating the prompt *head* — which is the persona (the worst
# part to silently lose), since the system prompt leads. The grower is the 20-turn history + the
# recap + the state block, so the fix is to trim those, not raise the cap (KV-cache VRAM).
_CTX_WARN_FRACTION = 0.85


def _write_utterance_wav(name: str, index: int, pcm_s16le_mono_16k: bytes) -> str:
    """Write one utterance to a 16 kHz mono WAV in the OS temp dir (Phase-3 inspection).

    Uses ``tempfile.gettempdir()`` — never ``/tmp`` (Windows runtime, CLAUDE.md).
    """
    safe = "".join(c if c.isalnum() else "_" for c in name) or "user"
    path = os.path.join(tempfile.gettempdir(), f"dm_utt_{safe}_{index:03d}.wav")
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # s16le
        wav.setframerate(_SR_16K)
        wav.writeframes(pcm_s16le_mono_16k)
    return path


def _wav_duration_s(path: str) -> float | None:
    """Playback length of a WAV in seconds (frames / sample-rate), or None if it can't be read.
    Best-effort: it only contextualises the tts/bridge numbers in the [latency] line."""
    try:
        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            return w.getnframes() / rate if rate else None
    except (OSError, wave.Error, EOFError):
        return None


def _safe_remove(path: str) -> None:
    """Delete a temp WAV, ignoring a missing/locked file (the temp dir mustn't fill up, but a
    failed delete must never break a turn)."""
    try:
        os.remove(path)
    except OSError:
        pass


@dataclass
class _TurnTiming:
    """Per-DM-turn latency record (logging only — no behaviour change, no ADR). Timestamps are
    ``time.monotonic`` carried through the existing turn flow (trigger → respond → speak); the
    deltas are emitted as one ``[latency]`` line per turn at the end of ``_deliver_answer``.

    Stages: stt (last routed utterance's transcribe ms), trigger→llm_done (turn start → Ollama
    returned, with the autosend ``wait_idle`` portion broken out), tts (synth → WAV), bridge_wait
    (``/speak`` POST → return), total (trigger → ``/speak`` returned). ctx/gen come from Ollama.
    """

    turn: int
    trigger: float  # monotonic at turn start (the trigger fired)
    kind: str = ""  # "", "redo", "auto", "roll" — which trigger started the turn
    streamed: bool = False  # True when the turn used the streaming pipeline (ADR 017)
    wait_ms: int = 0  # wait_idle before respond (autosend only); 0 otherwise
    stt_ms: int | None = None  # transcribe ms of the last DM-routed utterance (None if not speech-driven)
    llm_done: float | None = None  # monotonic when Ollama returned (generation finished)
    first_audio: float | None = None  # monotonic at the first /speak POST (streaming time-to-first-audio)
    prompt_eval: int | None = None  # Ollama prompt_eval_count (context tokens)
    eval_count: int | None = None  # Ollama eval_count (generated tokens)
    num_ctx: int | None = None  # the num_ctx cap in effect
    answer_chars: int = 0
    tts_ms: int | None = None  # synth call → WAV ready (streaming: summed over sentences)
    wav_s: float | None = None  # WAV duration (streaming: summed); contextualises tts/bridge_wait
    bridge_ms: int | None = None  # /speak POST → return = playback + transfer (streaming: summed)
    end: float | None = None  # monotonic when the last /speak returned

    def take_llm_stats(self, stats: dict | None) -> None:
        if not stats:
            return
        self.prompt_eval = stats.get("prompt_eval_count")
        self.eval_count = stats.get("eval_count")
        self.num_ctx = stats.get("num_ctx")

    def respond_ms(self) -> int:
        """The pure LLM-generation time (trigger→llm_done minus the wait_idle portion) — i.e. the
        meaning of the existing ``⏱ LLM`` log line, preserved across the four trigger sites."""
        if self.llm_done is None:
            return 0
        return round((self.llm_done - self.trigger) * 1000) - self.wait_ms

    def ctx_over_budget(self, fraction: float = _CTX_WARN_FRACTION) -> bool:
        """True when this turn's prompt filled more than ``fraction`` of num_ctx — the early signal
        (before Ollama truncates the prompt head) that the growing system prompt needs trimming."""
        return (
            self.prompt_eval is not None
            and bool(self.num_ctx)
            and self.prompt_eval > fraction * self.num_ctx
        )

    def log_line(self) -> None:
        """Emit the one compact ``[latency]`` line for this turn (INFO → console + debug.log)."""
        def ms(v: int | None) -> str:
            return f"{v}ms" if v is not None else "—"

        parts = [f"turn={self.turn}"]
        if self.kind:
            parts.append(self.kind)
        if self.streamed:
            parts.append("stream")
        parts.append(f"stt={ms(self.stt_ms)}")
        if self.wait_ms:
            parts.append(f"wait={self.wait_ms}ms")
        t2l = round((self.llm_done - self.trigger) * 1000) if self.llm_done is not None else None
        parts.append(f"trigger→llm_done={ms(t2l)}")
        if self.prompt_eval is not None:
            parts.append(f"ctx={self.prompt_eval}/{self.num_ctx}" if self.num_ctx
                         else f"ctx={self.prompt_eval}")
        if self.eval_count is not None:
            parts.append(f"gen={self.eval_count}")
        parts.append(f"chars={self.answer_chars}")
        # Headline metric for streaming (ADR 017): trigger → first audio leaves Bot A.
        if self.first_audio is not None:
            parts.append(f"first_audio={round((self.first_audio - self.trigger) * 1000)}ms")
        parts.append(f"tts={ms(self.tts_ms)}")
        if self.wav_s is not None:
            parts.append(f"wav={self.wav_s:.1f}s")
        parts.append(f"bridge_wait={ms(self.bridge_ms)}")
        total = round((self.end - self.trigger) * 1000) if self.end is not None else None
        parts.append(f"total={ms(total)}")
        log.info("[latency] %s", " ".join(parts))
        # Context-budget early warning (narration turns only — those are the ones that build a
        # _TurnTiming). Above ~85% of num_ctx, Ollama truncates the prompt head (the persona) first.
        if self.ctx_over_budget():
            log.warning(
                "[ctx] prompt %d/%d tokens (>%d%% of num_ctx) — nearing the cap; Ollama will start "
                "truncating the prompt head (persona first). Trim history / recap / state block.",
                self.prompt_eval, self.num_ctx, round(_CTX_WARN_FRACTION * 100),
            )


class VoiceReceiveCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        bot_a_user_id: int | None = None,
        whisper_model: str = "medium",
        whisper_device: str = "cuda",
        whisper_compute: str = "float16",
        dump_utterances: bool = False,
        ollama_host: str = "http://127.0.0.1:11434",
        ollama_model: str = "mistral-nemo",
        dm_num_predict: int = 160,
        dm_max_lines: int = 8,
        system: str = "imperium_maledictum",
        adventure: str = "",
        push_to_talk: bool = True,
        pause_vad_while_speaking: bool = False,
        button_autosend: bool = True,
        roll_router: bool = False,
        streaming: bool = True,
        autosave: bool = True,
        tts_engine: str = "piper",
        tts_voice: str = "",
        tts_speaker: str = "",
        tts_device: str = "cpu",
        bridge_host: str = "127.0.0.1",
        bridge_port: int = 8765,
        bridge_secret: str = "",
    ) -> None:
        self.bot = bot
        # Preflight the version-sensitive voice stack at boot, so a drift surfaces as a loud
        # warning here instead of as a silent garbage transcript mid-session (ADR 006).
        check_static()
        self._bot_a_user_id = bot_a_user_id
        self._dump_utterances = dump_utterances
        self._utterance_counts: dict[int, int] = {}
        self._active_vc_id: int | None = None  # the voice channel we buffer/answer for
        # Per-turn latency instrumentation (logging only). A monotonic turn counter for the
        # [latency] line, and the transcribe ms of the last DM-routed utterance per channel (set on
        # the STT thread in _on_transcript, popped by the turn that consumes it) so a speech-driven
        # turn can report its stt stage without re-measuring.
        self._turn_seq = 0
        self._last_stt_ms: dict[int, int] = {}
        self._sink: VadSink | None = None  # set on join; muted while Bot A speaks (layer 2)
        self._mic_message: discord.Message | None = None  # the live mic button msg (kept at bottom)
        self._push_to_talk = push_to_talk
        # Push-to-talk DM-routing gate: the whole table is always transcribed + logged, but only
        # utterances captured while this is True are buffered for the DM. The mic button flips it.
        # With push-to-talk off it's always True (legacy: everything reaches the DM).
        self._dm_listening = not push_to_talk
        # Layer-2 feedback pause (opt-in, off by default): pause the VAD while Bot A speaks. Off so
        # the table keeps being transcribed during narration; layer 1 still blocks self-hearing.
        self._pause_vad_while_speaking = pause_vad_while_speaking
        # Release the mic button → auto-run the DM turn (no separate !dm). On by default; the turn
        # waits for the just-said utterances to transcribe first. DM_BUTTON_AUTOSEND=0 disables it.
        self._button_autosend = push_to_talk and button_autosend
        # Roll-detection router (ADR 014): classify the player's action in a separate constrained call
        # and post the dice button, instead of relying on the model's inline <<TEST>> (kept as fallback).
        self._roll_router = roll_router
        # Streaming pipeline (ADR 017): stream the LLM answer and speak it sentence-by-sentence so
        # the first audio plays while the rest is still generating. Off (DM_STREAMING=0) = the
        # byte-identical batch path. Only engages when a TTS backend loaded (else nothing to stream).
        self._streaming = streaming
        # Per-turn conversation autosave (D41): append every completed turn to
        # data/sessions/<id>/history.jsonl so a crash doesn't lose the evening's thread; restored on
        # !join, rotated on !leave. World state already persists separately (ADR 015).
        self._autosave = autosave
        # Rules engine (Phase 8): load the active system profile (data/systems/<system>.json). A
        # missing/broken profile must not down the bot — log loudly and run rules-less (no dice).
        self._profile: SystemProfile | None = None
        try:
            self._profile = profile_mod.load(system)
            log.info("loaded system profile %r (%s, %s)", self._profile.name,
                     self._profile.dice, self._profile.resolution)
        except ProfileError:
            log.exception("no usable system profile %r — running without the dice engine", system)
        # Characters: start from the example party so !test/!roll work out of the box; !join prefers
        # a channel-specific data/sessions/<id>/characters.json if present. Engine rolls (RNG) here.
        self._characters, _ = self._load_characters(None)
        # Adventure compendium (Phase 10a, ADR 019): German scene cards + NPC statblocks under
        # data/adventures/<name>/. The scene pointer lives in WorldState.scene_id; the block is
        # injected via _persist_and_refresh. Missing/broken → run without (logged loudly).
        self._adventure: Adventure | None = None
        if adventure:
            self._adventure = Adventure.load(_DATA_DIR / "adventures" / adventure)
            if self._adventure is not None:
                log.info("loaded adventure %r (%d scenes, %d NPC statblocks)",
                         self._adventure.title or adventure,
                         len(self._adventure.scene_overview()), self._adventure.npc_count())
        # Memory (Phase 9): the mutable world state per channel — current wounds/conditions, NPCs,
        # quests, location, recap. Loaded/seeded on !join (data/sessions/<id>/state.json), advanced
        # deterministically by code (golden rule #3), persisted on every change so HP survives a
        # restart. The read-only characters.json above stays the source (split, ADR 015).
        self._state: dict[int, WorldState] = {}
        self._rng = random.Random()  # production RNG (tests pass their own seeded Random)
        # Turn order ("whose turn"), seeded from the voice-channel members at !join (keyed by the
        # active voice-channel id, like the brain's buffers). The view rotates the index.
        self._turn_order: dict[int, list[str]] = {}
        self._turn_index: dict[int, int] = {}
        self._turn_message: discord.Message | None = None
        # Pause control: one shared flag driven by the terminal Esc key (Variante A) AND the Discord
        # ⏸ button (Variante C). Pause freezes everything — mute the VAD/STT pipeline + block DM
        # turns — until resumed. The text channel + panel message let an Esc-pause also show in Discord.
        self._paused = False
        self._pause_message: discord.Message | None = None
        self._text_channel: discord.abc.Messageable | None = None  # where panels are posted (set on join)
        self._esc_task: asyncio.Task | None = None    # terminal Esc listener (Windows)
        self._anim_task: asyncio.Task | None = None   # the animated "paused" box (rich)
        # Rulebook retriever (stage 3, ADR 019): only wired in when an ingested store exists
        # (data/vectordb/rag.db, built offline via `python -m dmbot.rag.ingest`). Without it the
        # brain runs exactly as before — retrieval is additive.
        self._retriever = RulebookRetriever(_DATA_DIR / "vectordb" / "rag.db", host=ollama_host)
        if self._retriever.available():
            log.info("rulebook RAG store found — retrieval is on")
        else:
            log.info("no RAG store under data/vectordb/ — rule questions run without the book")
        self._brain = DMBrain(
            OllamaClient(ollama_host, ollama_model),
            profile=self._profile,
            num_predict=dm_num_predict,
            max_buffer_lines=dm_max_lines,
            retriever=self._retriever if self._retriever.available() else None,
        )
        self._bridge = BridgeClient(bridge_host, bridge_port, secret=bridge_secret)
        # Load the TTS backend once. xtts is imported lazily so Piper users don't pull torch.
        # If loading fails, keep running text-only (answers still post, just aren't spoken).
        self._tts = None
        try:
            if tts_engine == "xtts":
                from ..tts.xtts import XttsTTS  # heavy import (torch) — only when selected

                self._tts = XttsTTS(tts_speaker, device=tts_device)
            else:
                self._tts = PiperTTS(tts_voice) if tts_voice else PiperTTS()
        except Exception:
            log.exception("TTS unavailable (%s) — DM answers won't be spoken", tts_engine)
        # STT worker (Phase 4): loads faster-whisper in its own thread, transcribes off the
        # audio path. Started here so a broken cuDNN surfaces at boot, not on first utterance.
        self._transcriber = Transcriber(
            self._on_transcript,
            model=whisper_model,
            device=whisper_device,
            compute_type=whisper_compute,
        )
        self._transcriber.start()

    def _on_utterance(self, user_id: int, name: str, pcm: bytes, duration_s: float) -> None:
        """Per cut utterance (voice-recv reader / silence-gen thread): hand the PCM to the STT
        worker (and optionally dump a WAV for debugging). Keep it light, never raise.
        """
        n = self._utterance_counts.get(user_id, 0) + 1
        self._utterance_counts[user_id] = n
        if self._dump_utterances:  # debug only — off by default so temp doesn't fill up
            try:
                path = _write_utterance_wav(name, n, pcm)
                log.debug("dumped %s utterance #%d (%.2fs) → %s", name, n, duration_s, path)
            except Exception:
                log.exception("failed to write utterance WAV")
        # Tag the utterance with the DM-routing gate state NOW (when it was cut), so the routing
        # decision reflects whether the button was engaged while it was spoken — not whenever the
        # async transcript happens to come back. The metric (clip · transcribe ms) is logged with
        # the transcript once STT returns (see _on_transcript).
        self._transcriber.submit(name, pcm, duration_s, for_dm=self._dm_listening)

    def _on_transcript(
        self, name: str, text: str, clip_s: float, latency_ms: float, for_dm: bool
    ) -> None:
        """STT result (on the STT worker thread). The German text with clip length + transcribe ms.

        The whole table is logged (full transcript record); only ``for_dm`` lines are buffered for
        the next DM turn — that is the push-to-talk gate (everything recorded, button picks what
        the DM hears). A ``→DM`` marker on the metric shows which lines were routed.
        """
        # "📝 name | clip·ms[ →DM] | text" — the console formatter renders the metric dim inline;
        # the file log keeps the same one-line, greppable form.
        marker = " →DM" if for_dm else ""
        log.info("📝 %s | %.1fs·%dms%s | %s", name, clip_s, round(latency_ms), marker, text)
        # Buffer the line for the next DM turn (triggered by !dm) only when routed. Runs on the STT
        # thread; the brain's buffer is lock-guarded.
        if for_dm and self._active_vc_id is not None:
            self._brain.add_player_line(self._active_vc_id, name, text)
            # Remember this utterance's transcribe ms as the turn's stt stage (reuse, don't
            # re-measure). A plain int write; the consuming turn pops it on the event loop.
            self._last_stt_ms[self._active_vc_id] = round(latency_ms)

    async def cog_load(self) -> None:
        # Terminal Esc → pause/resume (Variante A). Windows-only (msvcrt); on other platforms the
        # listener no-ops and the Discord ⏸ button still works. Runs for the whole bot lifetime.
        self._esc_task = asyncio.create_task(self._esc_key_listener())

    # Number of progress.step() calls in cog_unload — DMBot.close() sums this across cogs to
    # announce the total shutdown step count up front. Keep in sync with cog_unload.
    TEARDOWN_STEPS = 4

    async def cog_unload(self) -> None:
        with progress.step("STT-Transcriber stoppen (Backlog wird verworfen, max 2s)"):
            for task in (self._esc_task, self._anim_task):
                if task is not None:
                    task.cancel()
            # stop() does a (short) thread.join — run it off the event loop so the gateway
            # heartbeat keeps beating during shutdown (otherwise "voice heartbeat blocked").
            await asyncio.to_thread(self._transcriber.stop)
        with progress.step("LLM-Client (Ollama) schließen"):
            await self._brain.aclose()
        with progress.step("RAG-Retriever schließen"):
            await self._retriever.aclose()
        with progress.step("Bridge zu Bot A schließen"):
            await self._bridge.aclose()

    async def _speak(self, text: str, guild_id: int | None,
                     timing: _TurnTiming | None = None) -> bool:
        """Synthesise ``text`` and play it via Bot A's /speak bridge. Returns True if it played.

        Synthesis is blocking, so it runs in a thread. The WAV is deleted after playback so the
        temp dir doesn't fill up. Bot A's audio is filtered by user-ID (feedback layer 1), so
        DMbot does not transcribe its own DM voice even without pausing the VAD. ``timing`` (when
        a DM turn passes one) collects the tts / wav / bridge_wait stages for the [latency] line.
        """
        if self._tts is None:
            return False
        try:
            t0 = time.perf_counter()
            # Daemon thread, not asyncio.to_thread: a GPU synth in flight at Ctrl+C must not
            # join-block shutdown (the WAV is moot once we're quitting). See dmbot/shutdown.py.
            wav = await to_daemon_thread(self._tts.synthesize, text)
            tts_ms = round((time.perf_counter() - t0) * 1000)
            log.info("🔊 TTS %d ms → speaking", tts_ms)
        except Exception:
            log.exception("TTS synthesis failed")
            return False
        if timing is not None:
            timing.tts_ms = tts_ms
            timing.wav_s = _wav_duration_s(wav)
        # Feedback protection layer 2 (ADR 003), now OPT-IN and off by default: pause the VAD while
        # Bot A speaks. It's redundant in normal use — layer 1 (the Bot-A user-ID filter, golden
        # rule #4, always on) already keeps the DM from transcribing its own voice, and the
        # push-to-talk routing gate keeps narration-time table talk out of the DM. We default it off
        # so the table keeps being transcribed (full transcript record) while the DM talks. Enable
        # DM_PAUSE_VAD_WHILE_SPEAKING=1 to restore the pause. /speak blocks until playback ends
        # (D15), so unmuting in finally reopens exactly when Bot A goes quiet; snapshot the sink so
        # a !leave mid-playback still unmutes the one we muted.
        sink = self._sink if self._pause_vad_while_speaking else None
        if sink is not None:
            sink.mute()
        try:
            tb = time.monotonic()
            played = await self._bridge.speak(wav, guild_id=guild_id)
            if timing is not None:
                timing.bridge_ms = round((time.monotonic() - tb) * 1000)
            if not played:
                log.warning("playback did not succeed — is Bot A in the voice channel?")
            return played
        finally:
            if sink is not None:
                sink.unmute()
            try:
                os.remove(wav)
            except OSError:
                pass

    async def _send_with_retry(self, channel, content: str | None = None, *,
                               view: discord.ui.View | None = None,
                               embed: discord.Embed | None = None):
        """Send a message, retrying once on a transient Discord 5xx (e.g. the 503 seen mid-session)."""
        kwargs: dict = {}
        if view is not None:
            kwargs["view"] = view
        if embed is not None:
            kwargs["embed"] = embed
        try:
            return await channel.send(content, **kwargs)
        except discord.HTTPException as exc:
            if (getattr(exc, "status", 0) or 0) < 500:
                raise
            log.warning("Discord send failed (HTTP %s) — retrying once", getattr(exc, "status", "?"))
            await asyncio.sleep(1.0)
            try:
                return await channel.send(content, **kwargs)
            except discord.HTTPException:
                log.warning("Discord send retry also failed — dropping the message", exc_info=True)
                return None

    def _begin_turn(self, channel_id: int, *, kind: str = "") -> _TurnTiming:
        """Open a per-turn timing record: bump the turn counter, stamp the trigger, and claim the
        last DM-routed utterance's transcribe ms (the stt stage; None for typed/redo/dice turns)."""
        self._turn_seq += 1
        return _TurnTiming(
            turn=self._turn_seq,
            trigger=time.monotonic(),
            kind=kind,
            stt_ms=self._last_stt_ms.pop(channel_id, None),
        )

    def _use_streaming(self) -> bool:
        """Stream the answer (ADR 017) only when streaming is on AND a TTS backend loaded — a
        text-only run has nothing to stream audio for, so it takes the byte-identical batch path."""
        return self._streaming and self._tts is not None

    async def _handle_dice(self, channel) -> None:
        """Post the turn's dice button. The router wins when it's on (D43, flips D40's dedupe):
        the model's inline ``<<TEST>>`` requests are drained and **discarded** — the constrained
        classifier picks reliable skills, the narration model doesn't (seen live: Heimlichkeit
        for an attack). Markers post only as the fallback when the router is off. Runs
        concurrently with playback (D40) so the button appears while the DM still speaks."""
        markers = self._brain.take_pending_tests(self._brain_channel(channel))
        source = roll_button_source(self._roll_router, len(markers))
        if source == "router":
            if markers:
                log.info("🎲 %d Inline-Marker verworfen — der Router entscheidet (D43)", len(markers))
            await self._post_router_dice(channel)
        elif source == "marker":
            for req in markers:
                await self._post_dice_button(channel, req)

    async def _autosave_turn(self, channel, answer: str, *, user_msg: str | None = None,
                             redo: bool = False) -> None:
        """Append the just-completed turn to ``data/sessions/<id>/history.jsonl`` (D41) off the
        event loop, best-effort. World state persists separately (ADR 015); this is the narrative
        thread so a crash doesn't lose the evening's conversation.

        ``user_msg`` must be the value snapshotted at **generation end** (D43): this runs after
        playback, and a dice click during playback starts the next turn, which overwrites the
        brain's mutable ``_last_turn`` — reading it here pairs the wrong user_msg with the answer
        (seen live 2026-06-12 in history.jsonl). The read-now fallback covers legacy callers."""
        if not self._autosave:
            return
        cid = self._brain_channel(channel)
        if user_msg is None:
            user_msg = self._brain.last_user_msg(cid)
        if user_msg is None:
            return
        try:
            await asyncio.to_thread(
                history_store.append_turn, self._history_path(cid),
                ts=datetime.now().isoformat(timespec="seconds"),
                user_msg=user_msg, answer=answer, redo=redo,
            )
        except OSError:
            log.exception("could not autosave the turn history for channel %s", cid)

    async def _deliver_answer(self, channel, guild_id: int | None, answer: str,
                              timing: _TurnTiming) -> None:
        """Batch delivery: log, post (5xx-resilient), then speak and post the dice button
        **concurrently** so the 🎲 appears while the DM speaks (Task 2 / D40), and re-anchor the
        mic button. Closes out the per-turn ``timing`` (tts/bridge via ``_speak``) and emits the
        single ``[latency]`` line once ``/speak`` returned."""
        timing.answer_chars = len(answer)
        # Snapshot the turn's user_msg NOW (generation just ended): a dice click during the
        # playback below starts the next turn and overwrites the brain's _last_turn (D43 race fix).
        saved_user_msg = self._brain.last_user_msg(self._brain_channel(channel))
        if answer:
            log.info("🎭 %s", answer)  # rendered prominently in the console
        log.info("⏱ LLM %d ms%s", timing.respond_ms(), " (redo)" if timing.kind == "redo" else "")
        # A content-less answer (a marker-only turn the model wrapped in a code fence, etc.) must not
        # be posted or spoken — XTTS would read a lone quote for ~15 s. The dice button still posts.
        speakable = has_speakable_content(answer)
        speak_task = None
        if speakable:
            await self._send_with_retry(channel, answer)
            speak_task = asyncio.create_task(self._speak(answer, guild_id, timing))
        else:
            log.info("(inhaltslose Antwort — nichts gepostet/gesprochen; nur ggf. Würfel)")
        dice_task = asyncio.create_task(self._handle_dice(channel))
        if speak_task is not None:
            await speak_task
        timing.end = time.monotonic()  # /speak returned → total stops here (mic re-anchor excluded)
        timing.log_line()
        await dice_task  # the dice button must land before the mic button re-anchors at the bottom
        await self._autosave_turn(channel, answer, user_msg=saved_user_msg,
                                  redo=timing.kind == "redo")
        # Keep the mic button reachable: move it back to the bottom after the message + speech.
        if self._push_to_talk and self._sink is not None:
            await self._post_mic_button(channel)

    async def _deliver_streaming(self, channel, guild_id: int | None, timing: _TurnTiming, *,
                                 redo: bool = False, extra_text: str | None = None) -> str | None:
        """Streaming delivery (ADR 017): the producer drives the brain's streaming turn while a
        synth→playback pipeline speaks each sentence (synth N+1 while N plays); the Discord text
        post + 🎲 dice button happen at generation-end (mid-playback). Layer-2 mute spans the whole
        answer (not per sentence); pause stops emission cleanly. Returns the stored answer or None."""
        channel_id = self._brain_channel(channel)
        sentence_q: asyncio.Queue = asyncio.Queue()
        wav_q: asyncio.Queue = asyncio.Queue(maxsize=1)  # bounds synth to ~1 ahead of playback
        sink = self._sink if self._pause_vad_while_speaking else None
        holder: dict = {"answer": None}

        async def on_sentence(s: str) -> None:
            await sentence_q.put(s)

        async def producer() -> None:
            try:
                if redo:
                    holder["answer"] = await self._brain.redo_streaming(
                        channel_id, on_sentence=on_sentence, should_abort=lambda: self._paused,
                    )
                else:
                    holder["answer"] = await self._brain.respond_streaming(
                        channel_id, extra_text=extra_text, on_sentence=on_sentence,
                        should_abort=lambda: self._paused,
                    )
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._brain.last_llm_stats)
            finally:
                await sentence_q.put(None)  # sentinel: generation finished

        async def synth_worker() -> None:
            while True:
                s = await sentence_q.get()
                if s is None:
                    await wav_q.put(None)
                    return
                if self._paused or self._tts is None:
                    continue
                try:
                    t0 = time.perf_counter()
                    # Daemon thread (see dmbot/shutdown.py): a streamed-sentence synth in flight
                    # at Ctrl+C is abandoned, never join-blocking the shutdown.
                    wav = await to_daemon_thread(self._tts.synthesize, s)
                except Exception:
                    log.exception("TTS synthesis failed (streamed sentence) — skipping it")
                    continue
                timing.tts_ms = (timing.tts_ms or 0) + round((time.perf_counter() - t0) * 1000)
                dur = _wav_duration_s(wav)
                if dur is not None:
                    timing.wav_s = (timing.wav_s or 0.0) + dur
                await wav_q.put(wav)

        async def play_worker() -> None:
            while True:
                wav = await wav_q.get()
                if wav is None:
                    return
                if self._paused:
                    _safe_remove(wav)
                    continue
                if timing.first_audio is None:
                    timing.first_audio = time.monotonic()
                tb = time.monotonic()
                try:
                    await self._bridge.speak(wav, guild_id=guild_id)
                finally:
                    timing.bridge_ms = (timing.bridge_ms or 0) + round((time.monotonic() - tb) * 1000)
                    _safe_remove(wav)

        if sink is not None:
            sink.mute()  # layer 2: stay muted across the WHOLE answer, no flapping between sentences
        prod = asyncio.create_task(producer())
        sw = asyncio.create_task(synth_worker())
        pw = asyncio.create_task(play_worker())
        dice_task: asyncio.Task | None = None
        saved_user_msg: str | None = None
        try:
            try:
                await prod  # generation finished (mid-playback) — the full answer is known now
            except Exception:
                log.exception("streaming producer failed")
            # Snapshot the turn's user_msg NOW: the dice button below can be clicked while the
            # tail still plays, and that next turn overwrites _last_turn (D43 race fix).
            saved_user_msg = self._brain.last_user_msg(channel_id)
            answer = holder["answer"]
            if answer is not None:  # a turn happened ("" = a marker-only/content-less turn)
                timing.answer_chars = len(answer)
                if answer:
                    log.info("🎭 %s", answer)
                log.info("⏱ LLM %d ms%s", timing.respond_ms(),
                         " (redo)" if timing.kind == "redo" else "")
                # Post the text only if there's something to read; the sentences were already
                # filtered for speakability before synthesis. A marker-only turn posts no text but
                # still posts its dice button below.
                if has_speakable_content(answer):
                    await self._send_with_retry(channel, answer)
                dice_task = asyncio.create_task(self._handle_dice(channel))
            await asyncio.gather(sw, pw)  # wait for the last sentence to finish playing
        finally:
            if sink is not None:
                sink.unmute()
        if holder["answer"] is not None:
            timing.end = time.monotonic()  # last /speak returned
            timing.log_line()
            if dice_task is not None:
                await dice_task
            await self._autosave_turn(channel, holder["answer"], user_msg=saved_user_msg, redo=redo)
            if self._push_to_talk and self._sink is not None:
                await self._post_mic_button(channel)
        return holder["answer"]

    @commands.command(name="dm")
    async def dm(self, ctx: commands.Context, *, text: str = "") -> None:
        """Run a DM turn. `!dm` answers the buffered voice lines; `!dm <Text>` answers text."""
        if self._paused:
            await ctx.send("⏸ Pausiert — mit **Esc** oder dem ⏸-Knopf fortsetzen.")
            return
        channel_id = self._active_vc_id if self._active_vc_id is not None else ctx.channel.id
        if not text and self._brain.pending_count(channel_id) == 0:
            await ctx.send(
                "Nichts zu beantworten — sprecht etwas (nach `!j`) oder nutzt `!dm <Text>`."
            )
            return
        guild_id = ctx.guild.id if ctx.guild else None
        timing = self._begin_turn(channel_id)
        if self._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._deliver_streaming(
                        ctx.channel, guild_id, timing, extra_text=text or None
                    )
            except Exception:
                log.exception("DM turn failed (stream)")
                await ctx.send("(Der Spielleiter schweigt — Fehler bei der Antwort, siehe Log.)")
                return
            if answer is None:  # None = nothing to respond to; "" = a marker-only turn (dice posted)
                await ctx.send("(Nichts zu beantworten.)")
            return
        try:
            async with ctx.typing():
                answer = await self._brain.respond(channel_id, extra_text=text or None)
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._brain.last_llm_stats)
        except Exception:
            log.exception("DM turn failed")
            await ctx.send("(Der Spielleiter schweigt — Fehler bei der Antwort, siehe Log.)")
            return
        if answer is None:
            await ctx.send("(Nichts zu beantworten.)")
            return
        await self._deliver_answer(ctx.channel, guild_id, answer, timing)

    @commands.command(name="redo", aliases=["r"])
    async def redo(self, ctx: commands.Context) -> None:
        """Re-run the last DM turn with the same input — for when the DM misunderstood. Alias: !r"""
        if self._paused:
            await ctx.send("⏸ Pausiert — mit **Esc** oder dem ⏸-Knopf fortsetzen.")
            return
        channel_id = self._active_vc_id if self._active_vc_id is not None else ctx.channel.id
        guild_id = ctx.guild.id if ctx.guild else None
        timing = self._begin_turn(channel_id, kind="redo")
        if self._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._deliver_streaming(ctx.channel, guild_id, timing, redo=True)
            except Exception:
                log.exception("DM redo failed (stream)")
                await ctx.send("(Fehler beim Neu-Erzählen, siehe Log.)")
                return
            if answer is None:
                await ctx.send("Nichts zum Wiederholen — erst eine Runde mit `!dm` spielen.")
            return
        try:
            async with ctx.typing():
                answer = await self._brain.redo(channel_id)
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._brain.last_llm_stats)
        except Exception:
            log.exception("DM redo failed")
            await ctx.send("(Fehler beim Neu-Erzählen, siehe Log.)")
            return
        if answer is None:
            await ctx.send("Nichts zum Wiederholen — erst eine Runde mit `!dm` spielen.")
            return
        await self._deliver_answer(ctx.channel, guild_id, answer, timing)

    async def _auto_dm_turn(self, channel, guild_id: int | None) -> None:
        """Auto-trigger a DM turn when the mic button is released (push-to-talk). Waits for the
        just-said utterances to finish transcribing (so the last thing said is included), then
        answers if anything was routed to the DM. Silent no-op when nothing was — no nagging."""
        if self._paused:
            return
        channel_id = self._active_vc_id if self._active_vc_id is not None else channel.id
        # Trigger = mic release, before wait_idle, so trigger→llm_done covers the whole turn and the
        # wait_idle portion is broken out (wait=…ms).
        timing = self._begin_turn(channel_id, kind="auto")
        tw = time.monotonic()
        await asyncio.to_thread(self._transcriber.wait_idle, 4.0)  # let the final utterance land
        timing.wait_ms = round((time.monotonic() - tw) * 1000)
        # The triggering utterance is usually still transcribing during wait_idle, so re-claim the
        # stt stage now that it has landed (keep _begin_turn's value if nothing new arrived).
        timing.stt_ms = self._last_stt_ms.pop(channel_id, timing.stt_ms)
        if self._brain.pending_count(channel_id) == 0:
            return
        if self._use_streaming():
            timing.streamed = True
            try:
                await self._deliver_streaming(channel, guild_id, timing)
            except Exception:
                log.exception("DM turn failed (auto, stream)")
                await self._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        try:
            answer = await self._brain.respond(channel_id)
            timing.llm_done = time.monotonic()
            timing.take_llm_stats(self._brain.last_llm_stats)
        except Exception:
            log.exception("DM turn failed (auto)")
            await self._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        if answer is not None:  # "" = a marker-only turn → still deliver (posts the dice button)
            await self._deliver_answer(channel, guild_id, answer, timing)

    async def _on_mic_stop(self, interaction: discord.Interaction) -> None:
        """Mic button released → optionally run the DM turn automatically (players asked for this)."""
        if not self._button_autosend:
            return
        try:
            await self._auto_dm_turn(interaction.channel, interaction.guild_id)
        except Exception:
            log.exception("auto DM turn after mic release failed")

    # ----- Pause control: Esc (terminal) + ⏸ button (Discord), one shared state ----------

    async def toggle_pause(self) -> bool:
        """Flip the shared game-pause state; return the new flag. Called by Esc and the ⏸ button."""
        await self.set_paused(not self._paused)
        return self._paused

    async def set_paused(self, value: bool) -> None:
        """Freeze/resume the game. Pause mutes the VAD/STT pipeline (no transcription) and the DM
        turn guards block any answer; resume reverses both. Idempotent. Both surfaces (the terminal
        box and the Discord embed) are re-rendered from this one flag."""
        if value == self._paused:
            return
        self._paused = value
        if value:
            if self._sink is not None:
                self._sink.mute()  # freeze transcription (also flushes the open utterance)
            log.warning("⏸ Spiel pausiert — keine Transkription, der Spielleiter wartet.")
            if self._anim_task is not None and not self._anim_task.done():
                self._anim_task.cancel()
            self._anim_task = asyncio.create_task(self._run_pause_animation())
        else:
            if self._sink is not None:
                self._sink.unmute()  # (no DM turn runs while paused, so this can't fight layer 2)
            log.warning("▶ Spiel fortgesetzt.")
        await self._refresh_pause_panel()

    async def _esc_key_listener(self) -> None:
        """Variante A: poll the DMbot terminal for the Esc key and toggle pause. Non-blocking — it
        only reads a key when one is ready, so it never stalls the discord.py event loop. Windows
        only (``msvcrt``); elsewhere it no-ops (the Discord ⏸ button still works)."""
        try:
            import msvcrt  # Windows console key polling (D16: the runtime is Windows)
        except ImportError:
            return
        log.info("Esc-Taste im Terminal pausiert/setzt das Spiel fort.")
        try:
            while not self.bot.is_closed():
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch == "\x1b":  # Esc
                        await self.toggle_pause()
                    elif ch in ("\x00", "\xe0") and msvcrt.kbhit():
                        msvcrt.getwch()  # swallow the 2nd byte of arrow/function keys
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    async def _run_pause_animation(self) -> None:
        """Variante A's animated box: a spinning 'PAUSIERT' panel in the DMbot terminal while the
        game is frozen. Best-effort — if rich is missing or the console can't host a live region,
        it just skips (the Discord embed still shows the state). The pipeline is muted while paused,
        so the console is quiet and the box owns the screen cleanly."""
        try:
            from rich.align import Align
            from rich.live import Live
            from rich.panel import Panel
            from rich.spinner import Spinner
        except Exception:
            return
        spinner = Spinner(
            "dots12",
            text="  ⏸  PAUSIERT  —  Esc oder der ⏸-Knopf setzt fort  ",
            style="bold yellow",
        )
        panel = Panel(
            Align.center(spinner), title="[bold]DMbot[/]", border_style="yellow", padding=(1, 6)
        )
        try:
            with Live(panel, refresh_per_second=12, transient=True):
                while self._paused and not self.bot.is_closed():
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.debug("pause animation unavailable", exc_info=True)

    async def _refresh_pause_panel(self) -> None:
        """(Re)render the Discord pause panel (embed + button) to the current state. Posts it if a
        text channel is known and none exists yet, so an Esc-driven pause is also visible in Discord."""
        if self._text_channel is None:
            return
        view = PauseToggleView(self.toggle_pause, paused=self._paused)
        embed = pause_embed(self._paused)
        if self._pause_message is not None:
            try:
                await self._pause_message.edit(embed=embed, view=view)
                return
            except discord.HTTPException:
                self._pause_message = None  # message gone — fall through and re-post
        try:
            self._pause_message = await self._text_channel.send(embed=embed, view=view)
        except discord.HTTPException:
            log.warning("could not post the pause panel", exc_info=True)

    @commands.command(name="pausebutton")
    async def pausebutton(self, ctx: commands.Context) -> None:
        """(Re)post the pause control panel (embed + ⏸ button) at the bottom of the text channel."""
        self._text_channel = ctx.channel
        if self._pause_message is not None:
            try:
                await self._pause_message.delete()
            except discord.HTTPException:
                pass
            self._pause_message = None
        await self._refresh_pause_panel()

    # ----- Phase 8: dice engine, marker flow & turn order --------------------------------

    def _brain_channel(self, channel) -> int:
        """The id the brain/turn-state are keyed by — the active voice channel, text channel as
        fallback (matches the existing !dm/!redo convention)."""
        return self._active_vc_id if self._active_vc_id is not None else channel.id

    def _load_characters(self, channel_id: int | None) -> tuple[CharacterStore, bool]:
        """Load the party JSON: a channel-specific sheet if present, else the example party.
        Returns ``(store, fallback)`` — ``fallback`` is True when the example party was loaded so
        ``!join`` can warn loudly (D43: a session in the wrong channel silently ran the example
        party, wrong names + wrong sheet values, and nobody noticed until the DM felt broken).
        A missing file yields an empty store (the engine then rolls without a target)."""
        sessions = _DATA_DIR / "sessions"
        if channel_id is not None:
            specific = sessions / str(channel_id) / "characters.json"
            if specific.is_file():
                log.info("loaded characters from %s", specific)
                return CharacterStore.load(specific), False
        return CharacterStore.load(sessions / "_example" / "characters.json"), True

    def _state_path(self, channel_id: int) -> Path:
        """Where this channel's mutable world state lives (data/sessions/<id>/state.json)."""
        return _DATA_DIR / "sessions" / str(channel_id) / "state.json"

    def _history_path(self, channel_id: int) -> Path:
        """Where this channel's append-only conversation autosave lives (D41)."""
        return _DATA_DIR / "sessions" / str(channel_id) / "history.jsonl"

    def _load_or_seed_state(self, channel_id: int) -> WorldState:
        """Load the channel's saved state, or seed a fresh one from the sheet (ADR 004/015) on the
        first ever join. Either way it's the live mutable layer for this session."""
        existing = WorldState.load(self._state_path(channel_id))
        if existing is not None:
            log.info("loaded world state from %s", self._state_path(channel_id))
            return existing
        store = self._characters or CharacterStore()
        system = self._profile.name if self._profile else ""
        return WorldState.seed_from_store(store, system=system, session_id=str(channel_id))

    def _persist_and_refresh(self, channel) -> None:
        """Save the channel's world state to disk and re-inject recap + the compact state block into
        the brain's prompt, so the next DM turn sees current HP/conditions (and so the gate's 'HP
        survives a restart' holds — we save on every change)."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return
        try:
            state.save(self._state_path(cid))
        except OSError:
            log.exception("could not persist world state for channel %s", cid)
        adventure_block = ""
        if self._adventure is not None:
            adventure_block = self._adventure.adventure_block_de(state.scene_id)
        self._brain.set_context(
            cid, recap=state.recap, state_summary=world_state_summary_de(state),
            adventure_block=adventure_block,
        )

    def _toughness_bonus(self, target: Character | None) -> int:
        """Toughness Bonus for a player from the sheet: the profile's soak characteristic (IM: Tgh),
        rendered per soak mode (IM: tens digit). 0 if no profile/character/characteristic."""
        if self._profile is None or target is None:
            return 0
        char_key = self._profile.soak_characteristic()
        if not char_key:
            return 0
        value = None
        for name, v in target.characteristics.items():
            if name.lower() == char_key.lower():
                value = v
                break
        if value is None:
            return 0
        return value // 10 if self._profile.soak_mode() == "tens" else value

    async def _run_and_deliver(self, channel, guild_id: int | None) -> None:
        """Run a DM turn and deliver it — used after a dice roll feeds its result back in so the
        DM narrates the consequence (architecture §9)."""
        if self._paused:  # frozen — the roll result is already posted; narration waits for resume
            return
        timing = self._begin_turn(self._brain_channel(channel), kind="roll")
        if self._use_streaming():
            timing.streamed = True
            try:
                await self._deliver_streaming(channel, guild_id, timing)
            except Exception:
                log.exception("DM turn failed (after roll, stream)")
                await self._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        try:
            answer = await self._brain.respond(self._brain_channel(channel))
            timing.llm_done = time.monotonic()
            timing.take_llm_stats(self._brain.last_llm_stats)
        except Exception:
            log.exception("DM turn failed (after roll)")
            await self._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        if answer is not None:  # "" = the consequence narration was empty; nothing to deliver/speak
            await self._deliver_answer(channel, guild_id, answer, timing)

    async def _post_router_dice(self, channel) -> None:
        """Roll-detection router (ADR 014): classify the latest player action in a separate
        constrained-JSON call and post a dice button if it needs a test. Skips silently when there's
        no player action this turn (e.g. a post-roll narration) or no matching character."""
        if self._profile is None or self._characters is None:
            return
        action = self._brain.last_action(self._brain_channel(channel))
        if not action:
            return
        name, text = action
        char = self._characters.get(name)
        if char is None:
            return
        # Constrain the classifier to this character's sheet: skills first, then any same-named
        # governing characteristic (skill_value falls back to those).
        skills = list(char.skills) + [c for c in char.characteristics if c not in char.skills]
        req = await self._brain.classify_test(action=text, character=char.name, skills=skills)
        if req is not None:
            log.info("🎲 router: '%s' → %s (%s)", text[:50], req.skill, req.difficulty or "Standard")
            await self._post_dice_button(channel, req)

    async def _post_dice_button(self, channel, req: TestRequest) -> None:
        """Resolve a test request (skill value + difficulty → target, all in code) and post its button."""
        skill = req.skill or "Probe"
        resolved = resolve_target(
            self._profile, self._characters, skill=skill,
            target_name=req.target_name, difficulty=req.difficulty, modifier=req.modifier,
        )
        who = (resolved.character.name if resolved.character else req.target_name) or "Gruppe"
        if resolved.difficulty:
            diff = resolved.difficulty
        elif req.modifier is not None:
            diff = f"{req.modifier:+d}"
        else:
            diff = ""
        label = f"{who} würfelt: {skill}" + (f" ({diff})" if diff else "")
        note = "" if req.parsed else " (unklarer Marker — manuell prüfen)"
        await self._send_with_retry(
            channel, f"🎲 Probe angefordert{note}:",
            view=DiceTestView(label, self._make_dice_roll(channel, req, resolved)),
        )

    def _make_dice_roll(self, channel, req: TestRequest, resolved):
        """Build the roll callback for a dice button: the engine rolls + resolves, the message is
        replaced with the result, and it's fed back so the DM narrates the consequence."""
        skill = req.skill or "Probe"
        who = resolved.character.name if resolved.character else req.target_name

        async def _roll(interaction: discord.Interaction) -> None:
            guild_id = channel.guild.id if channel.guild else None
            result = None
            if resolved.target is None:  # no character/skill value — roll, ask them to compare
                d = engine.roll(self._profile.dice, self._rng)
                line = f"🎲 {skill}: {d.total} — kein hinterlegter Wert, vergleicht mit eurem Bogen."
            else:
                result = engine.resolve_test(self._profile, resolved.target, self._rng)
                line = engine.describe_result_de(
                    result, skill=skill, character=who, difficulty=resolved.difficulty
                )
            log.info("%s", line)  # `line` already starts with 🎲 (describe_result_de)
            try:
                await interaction.message.edit(content=line, view=None)  # show result, drop button
            except discord.HTTPException:
                await self._send_with_retry(channel, line)
            self._brain.add_test_result(self._brain_channel(channel), line)
            # Auto-combat (Phase 9): a successful attack rolls & applies weapon damage to a target
            # before the DM narrates, so the narration carries the consequence. Non-attacks, misses
            # and value-less rolls fall through to the normal immediate narration.
            if (
                result is not None
                and result.success
                and self._profile is not None
                and self._profile.combat_enabled()
                and self._profile.is_attack_skill(skill)
            ):
                if await self._begin_attack_damage(channel, attacker=who, result=result):
                    return  # the damage flow narrates once a target is chosen/auto-applied
            await self._run_and_deliver(channel, guild_id)

        return _roll

    def _choose_weapon(self, attacker: Character | None) -> tuple[str | None, str]:
        """Pick the attacker's weapon + its damage notation: the first inventory item the profile
        knows a damage value for, else the profile's default damage. ('', '') if neither exists."""
        if self._profile is None:
            return None, ""
        if attacker is not None:
            for item in attacker.inventory:
                notation = self._profile.weapon_damage(item)
                if notation:
                    return item, notation
        return None, self._profile.default_damage()

    async def _begin_attack_damage(self, channel, *, attacker: str | None, result) -> bool:
        """Start the auto-damage flow for a successful attack. Returns True if it took over (a target
        was auto-hit or a picker was posted — it will narrate); False if it couldn't (no weapon data
        or no target), so the caller narrates the hit plainly."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return False
        attacker_char = self._characters.get(attacker) if self._characters else None
        weapon, notation = self._choose_weapon(attacker_char)
        if not notation:
            return False  # no weapon damage data → can't auto-roll; narrate the hit plainly
        # Candidates: living NPCs (the usual enemy) first, then other party members (friendly fire).
        candidates = [n.name for n in state.npcs if n.wounds > 0]
        candidates += [
            c.name for c in state.characters if c.name.lower() != (attacker or "").lower()
        ]
        if not candidates:
            await self._send_with_retry(
                channel,
                "💥 Treffer! Aber kein Ziel hinterlegt — `!npc add <Name> [Wunden]`, dann erneut würfeln.",
            )
            return False
        if len(candidates) == 1:
            await self._apply_attack_damage(
                channel, attacker=attacker, weapon=weapon, notation=notation,
                result=result, target_name=candidates[0],
            )
            return True

        async def _pick(interaction: discord.Interaction, name: str) -> None:
            await self._apply_attack_damage(
                channel, attacker=attacker, weapon=weapon, notation=notation,
                result=result, target_name=name,
            )

        weap = f" ({weapon})" if weapon else ""
        await self._send_with_retry(
            channel, f"💥 Treffer von **{attacker}**{weap} — wen trifft es?",
            view=TargetSelectView(candidates, _pick),
        )
        return True

    async def _apply_attack_damage(
        self, channel, *, attacker: str | None, weapon: str | None, notation: str, result, target_name: str
    ) -> None:
        """Roll the weapon's damage, subtract the target's soak (Toughness Bonus + armour), apply the
        rest to its wounds, persist, and feed the result back so the DM narrates the consequence."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return
        target = state.find(target_name)
        if target is None:  # picker only lists state names, but guard: register an ad-hoc enemy
            target = state.add_or_update_npc(target_name, wounds=10)
        if target.is_npc:
            tb = target.toughness_bonus
        else:
            sheet = self._characters.get(target_name) if self._characters else None
            tb = self._toughness_bonus(sheet)
        soak = tb + target.armour
        weapon_roll = engine.roll_damage(notation, self._rng)
        dmg = engine.resolve_damage(weapon_roll, result.degrees, soak)
        state.apply_damage(target_name, dmg.applied)
        updated = state.find(target_name)
        downed = updated is not None and updated.wounds <= 0
        line = engine.describe_damage_de(
            dmg, attacker=attacker, target=target_name, weapon=weapon,
            new_wounds=updated.wounds if updated else 0,
            max_wounds=updated.max_wounds if updated else 0, downed=downed,
        )
        log.info("%s", line)
        await self._send_with_retry(channel, line)
        self._persist_and_refresh(channel)
        self._brain.add_test_result(cid, line)
        await self._run_and_deliver(channel, channel.guild.id if channel.guild else None)

    def _build_turn_order(self, voice_channel) -> list[str]:
        """Seed the turn order from a voice channel's human members (Bot A + bots filtered),
        preferring each player's character name via the alias map (open item F)."""
        names: list[str] = []
        for m in voice_channel.members:
            if m.bot or (self._bot_a_user_id and m.id == self._bot_a_user_id):
                continue
            char = self._characters.get(m.display_name) if self._characters else None
            names.append(char.name if char else m.display_name)
        return names

    def _render_turn(self, key: int) -> str:
        order = self._turn_order.get(key, [])
        if not order:
            return "Keine Teilnehmer erfasst — tretet dem Voice-Channel bei und nutzt `!turn`."
        i = self._turn_index.get(key, 0) % len(order)
        seq = " → ".join(f"**{n}**" if j == i else n for j, n in enumerate(order))
        return f"🗡 Dran: **{order[i]}**\n{seq}"

    def _turn_step(self, key: int, step: int) -> None:
        order = self._turn_order.get(key, [])
        if order:
            self._turn_index[key] = (self._turn_index.get(key, 0) + step) % len(order)

    async def _post_turn_order(self, channel) -> None:
        """(Re)post the turn-order panel, deleting the previous one so it doesn't duplicate."""
        key = self._active_vc_id
        if key is None:
            await self._send_with_retry(channel, "Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        if self._turn_message is not None:
            try:
                await self._turn_message.delete()
            except discord.HTTPException:
                pass
            self._turn_message = None

        async def advance() -> None:
            self._turn_step(key, +1)

        async def back() -> None:
            self._turn_step(key, -1)

        view = TurnOrderView(advance, back, lambda: self._render_turn(key))
        self._turn_message = await self._send_with_retry(channel, self._render_turn(key), view=view)

    @commands.command(name="roll")
    async def roll(self, ctx: commands.Context, *, dice: str = "1d100") -> None:
        """Roll raw dice through the engine: `!roll 1d100`, `!roll 2d10+3`. A smoke test."""
        try:
            result = engine.roll(dice, self._rng)
        except engine.DiceError:
            await ctx.send(f"Unverständlicher Würfelausdruck `{dice}` — z. B. `1d100`, `2d10+3`.")
            return
        detail = ""
        if result.dice:
            parts = "+".join(str(d) for d in result.dice)
            if result.modifier:
                parts += f"{result.modifier:+d}"
            detail = f" ({parts})"
        await ctx.send(f"🎲 `{dice}` → **{result.total}**{detail}")

    @commands.command(name="test")
    async def test(self, ctx: commands.Context, *, spec: str = "") -> None:
        """Manually request a test: `!test Wahrnehmung Schwer für Tobi`. Posts a dice button."""
        if self._profile is None:
            await ctx.send("Keine Würfel-Engine geladen (Systemprofil fehlt) — siehe Log.")
            return
        if not spec.strip():
            await ctx.send("Nutzung: `!test <Fertigkeit> [Schwierigkeit] [für <Name>]`.")
            return
        _, reqs = extract_tests(f"<<TEST {spec}>>", self._profile)
        if not reqs:
            await ctx.send("Konnte daraus keine Probe lesen.")
            return
        await self._post_dice_button(ctx.channel, reqs[0])

    @commands.command(name="turn", aliases=["order"])
    async def turn(self, ctx: commands.Context) -> None:
        """Show / rotate the turn order ('whose turn'). Rebuilds it from the voice channel. Alias: !order"""
        if self._active_vc_id is None:
            await ctx.send("Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        vc = ctx.voice_client
        if vc is not None and getattr(vc, "channel", None) is not None:
            self._turn_order[self._active_vc_id] = self._build_turn_order(vc.channel)
            self._turn_index.setdefault(self._active_vc_id, 0)
        await self._post_turn_order(ctx.channel)

    @commands.command(name="rules", aliases=["regeln"])
    async def rules(self, ctx: commands.Context) -> None:
        """Show the essential rules of the active system; page through with ◀/▶. Alias: !regeln"""
        if self._profile is None:
            await ctx.send("Kein Systemprofil geladen — keine Regeln verfügbar (siehe Log).")
            return
        pages = rules_pages_de(self._profile)
        if not pages:
            await ctx.send("Für dieses System sind keine Regeln hinterlegt.")
            return
        source = self._profile.raw.get("_source", "") if isinstance(self._profile.raw, dict) else ""
        view = RulesView(pages, self._profile.display_name or self._profile.name, source=source)
        await self._send_with_retry(ctx.channel, view=view, embed=view.embed())

    # Display names for the curated lore topics (data/lore/<topic>.md, ADR 021); unknown
    # (future) files fall back to topic.title().
    _LORE_TITLES = {"imperium": "Weltwissen: Imperium", "chaos": "Weltwissen: Chaos"}
    # !lore questions search the Weltwissen sources only — rule questions belong to the DM
    # turn / !rules, and raw rulebook chunks are English layout soup, not player reading.
    _LORE_SOURCES = ("lore_imperium", "lore_chaos", "setting")
    _LORE_SOURCE_NAMES = {"lore_imperium": "Imperium", "lore_chaos": "Chaos", "setting": "Hive Rokarth"}

    @commands.command(name="lore", aliases=["hintergrund"])
    async def lore(self, ctx: commands.Context, *, arg: str = "") -> None:
        """Weltwissen: `!lore` / `!lore chaos` blättert den Rundown (◀/▶); `!lore <frage>`
        schlägt die passenden Kompendiums-Abschnitte nach (`!lore wer ist der Imperator?`).
        Lese-Material, kein DM-Turn — wird nicht gesprochen. Alias: !hintergrund"""
        lore_dir = _DATA_DIR / "lore"
        topic = arg.lower().strip()
        if not topic or (lore_dir / f"{topic}.md").is_file():
            await self._lore_rundown(ctx, lore_dir, topic or "imperium")
            return
        await self._lore_question(ctx, arg)

    async def _lore_rundown(self, ctx: commands.Context, lore_dir, topic: str) -> None:
        """The paged ◀/▶ view over data/lore/<topic>.md (the original !lore mode)."""
        path = lore_dir / f"{topic}.md"
        if not path.is_file():
            topics = available_topics(lore_dir)
            hint = ", ".join(f"`{t}`" for t in topics) if topics else "—"
            await ctx.send(f"Kein Lore-Thema `{topic}`. Verfügbar: {hint}")
            return
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        pages = lore_pages(text)
        if not pages:
            await ctx.send(f"`{path.name}` enthält keine lesbaren Abschnitte.")
            return
        view = RulesView(pages, self._LORE_TITLES.get(topic, topic.title()))
        await self._send_with_retry(ctx.channel, view=view, embed=view.embed())

    async def _lore_question(self, ctx: commands.Context, question: str) -> None:
        """`!lore <frage>` — show the best-matching Weltwissen sections (deterministic chunk
        display, no LLM: the compendium text IS the answer; the DM narrates in-game)."""
        if not self._retriever.available():
            await ctx.send("Kein RAG-Store vorhanden — `!lore <frage>` braucht `data/vectordb/rag.db`.")
            return
        hits = await self._retriever.lookup(question, sources=self._LORE_SOURCES)
        if not hits:
            await ctx.send(
                f"Dazu steht nichts im Weltwissen: *{question}*\n"
                f"(Rundown: `!lore` / `!lore chaos` — Regelfragen: `!rules`)"
            )
            return
        parts = []
        for source, heading, text, dist in hits:
            label = self._LORE_SOURCE_NAMES.get(source, source)
            parts.append(f"**{heading}** · _{label}_\n{text}")
            log.info("📚 !lore %r → %s:%r (d=%.2f)", question, source, heading, dist)
        description = "\n\n".join(parts)
        if len(description) > 4000:  # embed description cap; two lore chunks normally fit
            description = description[:4000].rsplit(" ", 1)[0] + " …"
        embed = discord.Embed(
            title="📚 Weltwissen", description=description, color=discord.Color.dark_gold()
        )
        await self._send_with_retry(ctx.channel, embed=embed)

    @commands.command(name="damage", aliases=["schaden"])
    async def damage(self, ctx: commands.Context, name: str = "", amount: int = 0) -> None:
        """GM override: apply raw wounds. `!damage Seskin 3` (after soak — this is the final number).
        Auto-combat does this for you on a hit; this is for adjudicated/out-of-band damage."""
        cid = self._brain_channel(ctx.channel)
        state = self._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not name or amount <= 0:
            await ctx.send("Nutzung: `!damage <Name> <Wunden>` (z. B. `!damage Kultist 5`).")
            return
        c = state.apply_damage(name, amount)
        if c is None:
            await ctx.send(f"Niemand namens **{name}** im Weltzustand (Charakter oder NSC).")
            return
        self._persist_and_refresh(ctx.channel)
        downed = " — **kampfunfähig**" if c.wounds <= 0 else ""
        await ctx.send(f"💢 **{c.name}** −{amount} Wunden → {c.wounds}/{c.max_wounds}{downed}")

    @commands.command(name="heal", aliases=["heilung"])
    async def heal(self, ctx: commands.Context, name: str = "", amount: int = 0) -> None:
        """GM: restore wounds. `!heal Seskin 4` (clamps at max, clears 'kampfunfähig' above 0)."""
        cid = self._brain_channel(ctx.channel)
        state = self._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not name or amount <= 0:
            await ctx.send("Nutzung: `!heal <Name> <Wunden>`.")
            return
        c = state.heal(name, amount)
        if c is None:
            await ctx.send(f"Niemand namens **{name}** im Weltzustand.")
            return
        self._persist_and_refresh(ctx.channel)
        await ctx.send(f"➕ **{c.name}** +{amount} Wunden → {c.wounds}/{c.max_wounds}")

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
        cid = self._brain_channel(ctx.channel)
        state = self._state.get(cid)
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
            block = self._adventure.npc(name) if self._adventure is not None else None
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
                display, wounds=w, max_wounds=w, toughness_bonus=t, armour=a
            )
            self._persist_and_refresh(ctx.channel)
            src = " *(Statblock aus dem Abenteuer)*" if block is not None and not wounds else ""
            await ctx.send(
                f"➕ NSC **{n.name}**: {n.wounds} Wunden, TB {n.toughness_bonus}, "
                f"Rüstung {n.armour}.{src}"
            )
            return
        await ctx.send("Nutzung: `!npc add <Name> [Wunden] [TB] [Rüstung]` oder `!npc list`.")

    @commands.command(name="ort", aliases=["szene"])
    async def ort(self, ctx: commands.Context, scene_id: str = "") -> None:
        """`!ort <szenen-id>` — set the adventure's scene pointer (Phase 10a): the DM's prompt then
        carries that scene's card. Deterministic by design (golden rule #3) — the human at the
        table moves the plot pointer, the model never does."""
        if self._adventure is None:
            await ctx.send("Kein Abenteuer geladen (`DM_ADVENTURE` in `.env`).")
            return
        cid = self._brain_channel(ctx.channel)
        state = self._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not scene_id:
            scene = self._adventure.get_scene(state.scene_id)
            current = f"**{scene.title_de}** (`{scene.id}`)" if scene else "—"
            await ctx.send(f"Aktuelle Szene: {current}. Wechsel: `!ort <id>` (`!szenen` zeigt alle).")
            return
        scene = self._adventure.get_scene(scene_id)
        if scene is None:
            await ctx.send(f"Unbekannte Szene `{scene_id}` — `!szenen` zeigt alle Ids.")
            return
        state.scene_id = scene.id
        if scene.title_de:
            state.set_location(scene.title_de)  # keep the prose state block in sync
        self._persist_and_refresh(ctx.channel)
        log.info("scene → %s (%s)", scene.id, scene.title_de)
        await ctx.send(f"📖 Szene gewechselt: **{scene.title_de}** (Teil {scene.part}).")

    @commands.command(name="szenen")
    async def szenen(self, ctx: commands.Context) -> None:
        """List the loaded adventure's scenes by part — the ids `!ort` accepts."""
        if self._adventure is None:
            await ctx.send("Kein Abenteuer geladen (`DM_ADVENTURE` in `.env`).")
            return
        cid = self._brain_channel(ctx.channel)
        current = self._state[cid].scene_id if cid in self._state else ""
        by_part: dict[int, list[str]] = {}
        for part, sid, title in self._adventure.scene_overview():
            marker = " ◀" if sid == current else ""
            by_part.setdefault(part, []).append(f"`{sid}` {title}{marker}")
        lines = [f"**Teil {part}:** " + " · ".join(entries)
                 for part, entries in sorted(by_part.items())]
        await ctx.send(f"📖 **{self._adventure.title}**\n" + "\n".join(lines))

    @commands.command(name="wrap", aliases=["wrapup"])
    async def wrap(self, ctx: commands.Context, *, _arg: str = "") -> None:
        """`!wrap up` / `!wrapup` — generate & store the session recap (D14). It's re-injected at the
        front of the next session so the story carries over. Non-destructive: play can continue."""
        cid = self._brain_channel(ctx.channel)
        await ctx.send("📜 Ich fasse die Sitzung zusammen …")
        try:
            recap = await self._brain.summarize(cid)
        except Exception:
            log.exception("recap generation failed")
            await ctx.send("Konnte keine Zusammenfassung erstellen (siehe Log).")
            return
        if not recap:
            await ctx.send("Noch nichts passiert, das sich zusammenfassen ließe.")
            return
        state = self._state.get(cid)
        if state is not None:
            state.set_recap(recap)
            self._persist_and_refresh(ctx.channel)
            try:  # mirror to a human-readable recap.md beside state.json
                (self._state_path(cid).parent / "recap.md").write_text(recap + "\n", encoding="utf-8")
            except OSError:
                log.exception("could not write recap.md")
        await ctx.send(f"📜 **Was bisher geschah:**\n{recap}")

    @commands.command(name="say")
    async def say(self, ctx: commands.Context, *, text: str) -> None:
        """Speak arbitrary text through Piper + Bot A — a TTS/bridge smoke test."""
        if self._tts is None:
            await ctx.send("Keine TTS-Stimme geladen (siehe SETUP B5).")
            return
        if await self._speak(text, ctx.guild.id if ctx.guild else None):
            await ctx.send("🔊")
        else:
            await ctx.send(
                "Konnte nicht abspielen — läuft **Bot A** und ist es im selben Voice-Channel? "
                "Prüfe `!vstatus`; Details im Log (`logs/debug.log`)."
            )

    @commands.command(name="voice")
    async def voice(self, ctx: commands.Context, *, name: str = "") -> None:
        """Switch the XTTS speaker live: `!voice Dionisio Schuyler`. No arg → show current."""
        if not hasattr(self._tts, "set_speaker"):
            await ctx.send("Sprecher-Wechsel geht nur mit `TTS_ENGINE=xtts`.")
            return
        if not name:
            await ctx.send(f"Aktueller Sprecher: **{self._tts.speaker}**")
            return
        if self._tts.set_speaker(name):
            await ctx.send(f"Sprecher → **{name}**. Teste mit `!say …`.")
        else:
            await ctx.send(f"Unbekannter Sprecher `{name}`. Liste: `!voices`.")

    @commands.command(name="voices")
    async def voices(self, ctx: commands.Context) -> None:
        """List the XTTS built-in speakers."""
        if not hasattr(self._tts, "speakers"):
            await ctx.send("Nur mit `TTS_ENGINE=xtts` verfügbar.")
            return
        names = ", ".join(self._tts.speakers())
        await ctx.send(f"**XTTS-Sprecher:**\n{names[:1900]}")

    @commands.command(name="join", aliases=["j"])
    async def join(self, ctx: commands.Context) -> None:
        """Join the caller's voice channel and start logging per-user PCM. Alias: !j"""
        voice_state = ctx.author.voice
        if voice_state is None or voice_state.channel is None:
            await ctx.send("Du bist in keinem Voice-Channel — tritt erst einem bei.")
            return

        if ctx.voice_client is not None:
            await ctx.send("Ich bin schon in einem Voice-Channel. Nutze zuerst `!leave`.")
            return

        channel = voice_state.channel
        vc: voice_recv.VoiceRecvClient = await channel.connect(
            cls=voice_recv.VoiceRecvClient
        )
        # Confirm the live DAVE-decrypt path (ADR 006) is reachable on this client before we
        # start listening — an early, explicit signal if a discord.py upgrade moved the internal.
        check_dave_session(vc)
        # Wrap the VAD sink in voice-recv's SilenceGeneratorSink: Discord clients send no
        # packets at all while a user is silent (voice activation), so without injected silence
        # the segmenter never sees an utterance's trailing gap and can't close it. The wrapper
        # feeds synthetic silence frames during transmission downtime (cleanup propagates to the
        # child automatically — reader walks the sink tree).
        vad_sink = VadSink(
            bot_a_user_id=self._bot_a_user_id, on_utterance=self._on_utterance
        )
        self._sink = vad_sink  # keep the handle so _speak can mute it while Bot A talks (layer 2)
        self._dm_listening = not self._push_to_talk  # fresh session: gate closed if push-to-talk
        sink = voice_recv.SilenceGeneratorSink(vad_sink)
        vc.listen(sink, after=self._on_listen_done)
        self._active_vc_id = channel.id  # buffer transcripts + answer for this channel
        self._text_channel = ctx.channel  # where the pause panel (and other panels) are posted
        # Phase 8: load this channel's party (else the example), wire the "who plays whom" alias
        # hint into the prompt (open item F), and seed the turn order from the voice members.
        self._characters, char_fallback = self._load_characters(channel.id)
        self._brain.set_alias_hint(channel.id, self._characters.alias_hint_de())
        # All table names → cut-labels/stop sequences, so a puppeted "Seskin: …" script is truncated.
        self._brain.set_known_speakers(channel.id, self._characters.speaker_labels())
        self._turn_order[channel.id] = self._build_turn_order(channel)
        self._turn_index[channel.id] = 0
        # Memory (Phase 9): load this channel's world state (or seed it from the sheet on first join),
        # then inject the stored recap + current state into the prompt so the DM picks up where it
        # left off — the "next session opens with a correct recap" half of the gate.
        self._state[channel.id] = self._load_or_seed_state(channel.id)
        # Adventure (Phase 10a): point a fresh session at the start scene; a loaded state keeps
        # its stored pointer (the plot position survives restarts like HP does).
        if self._adventure is not None and not self._state[channel.id].scene_id:
            self._state[channel.id].scene_id = self._adventure.start_scene
        self._persist_and_refresh(channel)
        # Crash recovery (D41): restore the conversation thread from the autosave if the in-memory
        # history is empty (a fresh process after a crash). A clean !leave rotates the file away, so
        # this only fires when the previous session didn't shut down cleanly.
        if self._autosave:
            try:
                turns = history_store.load_recent(
                    self._history_path(channel.id), self._brain.max_history_turns
                )
            except OSError:
                log.exception("could not read the history autosave for channel %s", channel.id)
                turns = []
            restored = self._brain.restore_history(channel.id, turns)
            if restored:
                log.info("restored %d conversation turns from the autosave (!redo unavailable for the last)", restored)

        log.info(
            "joined voice '%s' (id=%s) and started VAD pipeline (16k mono + silero, push_to_talk=%s)",
            channel.name, channel.id, self._push_to_talk,
        )
        if self._push_to_talk:
            close = (
                "wenn ihr fertig seid – **dann antwortet die Spielleitung automatisch** (kein `!dm` nötig)"
                if self._button_autosend
                else "wenn ihr fertig seid (ein Tipp gilt für alle), dann `!dm`"
            )
            await ctx.send(
                f"Beigetreten: **{channel.name}**. Ich schreibe **alles** mit (Protokoll im Log), "
                f"aber nur was im **Knopf-Fenster** gesagt wird, geht an die Spielleitung: tippt den "
                f"Knopf *bevor* ihr mit ihr redet und nochmal, {close}. "
                f"(Opus: {discord.opus.is_loaded()})"
            )
            await self._post_turn_order(ctx.channel)  # before the mic button so mic stays at bottom
            await self._refresh_pause_panel()
            await self._post_mic_button(ctx.channel)
        else:
            await ctx.send(
                f"Beigetreten: **{channel.name}** — ich höre durchgehend zu, alles geht an die "
                f"Spielleitung. Sprecht, dann `!dm` (oder `!dm <Text>`). (Opus: {discord.opus.is_loaded()})"
            )
            await self._post_turn_order(ctx.channel)
            await self._refresh_pause_panel()

        # Name the loaded party — and warn loudly on the example-party fallback (D43): a session
        # in the wrong channel once silently ran Mortn/Seskin/Vask with wrong sheet values, and it
        # only surfaced as "the DM feels broken". Better one loud line than a quiet wrong game.
        party = ", ".join(c.name for c in self._characters.characters())
        if char_fallback:
            log.warning("no characters.json for channel %s — example party loaded (%s)",
                        channel.id, party or "leer")
            await ctx.send(
                f"⚠ **Keine `characters.json` für diesen Channel** — Beispiel-Party geladen "
                f"({party or '—'}). Würfe nutzen die falschen Werte! Lege "
                f"`data/sessions/{channel.id}/characters.json` an (oder spielt im Stamm-Channel)."
            )
        elif party:
            await ctx.send(f"👥 **Party:** {party}")

        # Announce the loaded adventure + current scene, so the table knows the plot is on rails.
        if self._adventure is not None:
            scene = self._adventure.get_scene(self._state[channel.id].scene_id)
            where = f" — Szene: **{scene.title_de}**" if scene is not None else ""
            await ctx.send(f"📖 **Abenteuer:** {self._adventure.title}{where} "
                           f"(`!szenen` zeigt alle, `!ort <id>` wechselt)")

        # If a recap was stored from a previous session, show it so the table picks up the thread.
        state = self._state.get(channel.id)
        if state is not None and state.recap:
            await ctx.send(f"📜 **Was bisher geschah:** {state.recap}")

    async def toggle_listening(self) -> bool:
        """Flip the push-to-talk DM-routing gate; return the new state. Called by the mic button.

        Flushes the open utterance **before** flipping, so the trailing thing said right at the
        press is cut now and tagged with the current gate state (on press-off it still counts as
        DM; on press-on the pre-press fragment stays out of the DM). Transcription itself keeps
        running either way — only DM routing toggles."""
        if self._sink is not None:
            self._sink.flush_open()  # cut + tag the trailing utterance under the OLD gate state
        self._dm_listening = not self._dm_listening
        log.info("push-to-talk → %s", "🎙 an die Spielleitung" if self._dm_listening else "⏸ nur Protokoll")
        return self._dm_listening

    async def _post_mic_button(self, channel) -> None:
        """(Re)post the push-to-talk button at the bottom of the text channel, deleting the previous
        one so it doesn't scroll out of reach as the DM talks (players asked for this). Best-effort —
        a failed delete/post never breaks a turn."""
        if self._mic_message is not None:
            try:
                await self._mic_message.delete()
            except discord.HTTPException:
                pass
            self._mic_message = None
        view = MicToggleView(
            self.toggle_listening, listening=self._dm_listening, on_stop=self._on_mic_stop
        )
        try:
            self._mic_message = await channel.send("🎙 Push-to-talk:", view=view)
        except discord.HTTPException:
            log.warning("could not post the mic button", exc_info=True)

    @commands.command(name="mic")
    async def mic(self, ctx: commands.Context) -> None:
        """Re-post the push-to-talk button at the bottom (handy if it scrolled out of view)."""
        if self._sink is None:
            await ctx.send("Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        await self._post_mic_button(ctx.channel)

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context) -> None:
        """Stop listening and leave the voice channel."""
        vc = ctx.voice_client
        if vc is None:
            await ctx.send("Ich bin in keinem Voice-Channel.")
            return
        if isinstance(vc, voice_recv.VoiceRecvClient) and vc.is_listening():
            vc.stop_listening()
        await vc.disconnect()
        # End the session cleanly: forget this channel's buffered lines + history, drop the sink
        # handle and the per-user counters, so a later !join starts a fresh session (session
        # state is per channel, ADR 003).
        if self._active_vc_id is not None:
            # Persist the world state one last time (it's saved on every change too) so HP/recap
            # survive into the next session, then drop the in-memory handle for this channel.
            state = self._state.pop(self._active_vc_id, None)
            if state is not None:
                try:
                    state.save(self._state_path(self._active_vc_id))
                except OSError:
                    log.exception("could not persist world state on leave")
            # Rotate the conversation autosave (D41) so the record survives but the next session
            # starts fresh (the in-memory history is cleared by reset() just below).
            if self._autosave:
                try:
                    history_store.rotate(
                        self._history_path(self._active_vc_id),
                        stamp=datetime.now().strftime("%Y%m%d-%H%M%S"),
                    )
                except OSError:
                    log.exception("could not rotate the history autosave on leave")
            self._brain.reset(self._active_vc_id)
            self._turn_order.pop(self._active_vc_id, None)
            self._turn_index.pop(self._active_vc_id, None)
        self._active_vc_id = None
        self._sink = None
        self._utterance_counts.clear()
        self._dm_listening = not self._push_to_talk  # reset the routing gate for the next session
        # Clear any pause: stop the animation, drop the flag (the sink is being dropped anyway).
        self._paused = False
        if self._anim_task is not None and not self._anim_task.done():
            self._anim_task.cancel()
        self._text_channel = None
        for msg_attr in ("_mic_message", "_turn_message", "_pause_message"):
            msg = getattr(self, msg_attr)
            if msg is not None:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass
                setattr(self, msg_attr, None)
        await ctx.send("Voice-Channel verlassen.")

    @commands.command(name="vstatus")
    async def vstatus(self, ctx: commands.Context) -> None:
        """Report connection / listening / Opus state."""
        vc = ctx.voice_client
        connected = vc is not None and vc.is_connected()
        listening = isinstance(vc, voice_recv.VoiceRecvClient) and vc.is_listening()
        await ctx.send(
            f"connected={connected} listening={listening} "
            f"opus={discord.opus.is_loaded()} paused={self._paused}"
        )

    @staticmethod
    def _on_listen_done(exc: Exception | None) -> None:
        # Called from the reader thread when listening stops.
        if exc is not None:
            log.error("voice reader stopped with error: %r", exc)
        else:
            log.info("voice reader stopped cleanly")
