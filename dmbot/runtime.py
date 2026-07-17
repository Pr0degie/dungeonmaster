"""SessionRuntime — the shared session state + services injected into every DMbot cog.

The voice cog grew to ~2300 lines owning voice wiring, dice, memory, TTS delivery, scenes,
auto-recap and all Discord UI. This module holds the state that used to live as cog attributes —
the LLM brain, STT/TTS, the bridge, the rules profile + characters, the RAG retriever, the
adventure compendium, the per-channel world state, and the push-to-talk/pause/mute flags — built
once in ``__main__`` from the :class:`~dmbot.config.Config` and passed into each cog
(``Cog(bot, runtime)``). The cogs (VoiceCog/DiceCog/DMCog) stay thin command/flow layers and reach
everything shared through this object; **no cog reaches into another cog** (no ``bot.get_cog``).
Cross-cog calls (a dice roll → DM narration, the delivery → dice/mic buttons) go through the few
registered hooks below. See ADR 029.

Docs and code are English; game content (what the DM says) stays German (CLAUDE.md).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import discord

from .config import Config
from .voice.recv import VadSink
from .voice.preflight import check_static
from .stt import Transcriber
from .llm import consistency as consistency_mod
from .llm.client import OllamaClient
from .orchestrator import DMBrain
from .tts.piper import PiperTTS
from .tts.textsplit import split_for_discord, strip_speech_punctuation
from .bridge import BridgeClient
from .rules import profile as profile_mod
from .rules.profile import ProfileError, SystemProfile
from .rules.characters import CharacterStore
from .memory import chekhov as chekhov_mod
from .memory import history as history_store
from .memory import npc_memory as npc_memory_mod
from .memory.gametime import deadline_note_de, render_time_de
from .memory.state import (
    Clock,
    Combatant,
    WorldState,
    clock_full_note_de,
    pressure_panel_de,
    world_state_summary_de,
)
from .rag.adventure import Adventure, Scene
from .rag import ingest_session
from .rag.retrieve import RulebookRetriever
from .rag.testplan import Testplan, overlay_line_de

# Re-export shim (ADR 034): the per-turn latency record + its ctx-budget threshold moved to
# dmbot/turn_timing.py for context-leanness; keep importing them from here so the cog/dice/tests'
# ``from ..runtime import _TurnTiming`` (and `_CTX_WARN_FRACTION`) keep working unchanged.
from .turn_timing import _CTX_WARN_FRACTION, _TurnTiming  # noqa: F401

# Repo data dir (data/systems is the profile root; sessions/ sits beside it).
_DATA_DIR = profile_mod.systems_dir().parent

log = logging.getLogger(__name__)

_SR_16K = 16_000

# Ceiling for the first spoken line to wait on the background TTS load before degrading to
# text-only (a normal XTTS/Coqui load is a few seconds; this guards a hung load).
_TTS_LOAD_TIMEOUT_S = 90


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


class SessionRuntime:
    """Shared session state + services, built once from :class:`Config` and injected into every cog.

    Holds the LLM brain, STT/TTS, bridge, rules profile + characters, RAG retriever, adventure
    compendium, per-channel world state, and the push-to-talk/pause/mute flags. Exposes the
    state-mutating helpers (``_persist_and_refresh``, ``_set_scene``, ``_load_*``) and the STT/VAD
    callbacks (the transcriber is built here with ``_on_transcript``; ``!join`` wires the VadSink to
    ``_on_utterance``). Cross-cog flow goes through the five registered hooks at the bottom — no cog
    looks up another cog. Phase 10b (profile bootstrap, ADR 005) will hang off this object too.
    """

    def __init__(self, config: Config) -> None:
        # Preflight the version-sensitive voice stack at boot, so a drift surfaces as a loud
        # warning here instead of as a silent garbage transcript mid-session (ADR 006).
        check_static()
        self._bot_a_user_id = config.bot_a_user_id
        self._dump_utterances = config.dump_utterances
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
        self._push_to_talk = config.push_to_talk
        # Push-to-talk DM-routing gate: the whole table is always transcribed + logged, but only
        # utterances captured while this is True are buffered for the DM. The mic button flips it.
        # With push-to-talk off it's always True (legacy: everything reaches the DM).
        self._dm_listening = not config.push_to_talk
        # Layer-2 feedback pause (opt-in, off by default): pause the VAD while Bot A speaks. Off so
        # the table keeps being transcribed during narration; layer 1 still blocks self-hearing.
        self._pause_vad_while_speaking = config.pause_vad_while_speaking
        # Release the mic button → auto-run the DM turn (no separate !dm). On by default; the turn
        # waits for the just-said utterances to transcribe first. DM_BUTTON_AUTOSEND=0 disables it.
        self._button_autosend = config.push_to_talk and config.button_autosend
        # Roll-detection router (ADR 014): classify the player's action in a separate constrained call
        # and post the dice button, instead of relying on the model's inline <<TEST>> (kept as fallback).
        self._roll_router = config.roll_router
        # Streaming pipeline (ADR 017): stream the LLM answer and speak it sentence-by-sentence so
        # the first audio plays while the rest is still generating. Off (DM_STREAMING=0) = the
        # byte-identical batch path. Only engages when a TTS backend loaded (else nothing to stream).
        self._streaming = config.streaming
        # Length budget for the one-time !intro opening monologue (ADR 031) — larger than the normal
        # per-turn cap so the auftakt can cover place + mission + how they arrived AND a personal beat
        # for each player character. Read by DMCog's !intro command; the normal turn cap is unchanged.
        self._intro_num_predict = config.dm_intro_num_predict
        # Fixed (lower) sampling temperature for !intro only (D83), so the opening monologue
        # reliably follows the director brief instead of wandering into a short generic turn.
        self._intro_temperature = config.dm_intro_temperature
        # Global spoken-delivery mode (ADR 033), applied to every turn, switchable live via
        # !sprechmodus. _speech_mode: "stream" | "puffer" (stream with a head-start buffer) |
        # "nahtlos" (continuous one-track playback). _speech_punct: "flach" (strip all punctuation)
        # vs "intoniert" (keep it for prosody). _speech_prebuffer: head-start depth for "puffer".
        self._speech_mode = config.speech_mode
        self._speech_punct = config.speech_punct
        self._speech_prebuffer = config.speech_prebuffer
        # Per-turn conversation autosave (D41): append every completed turn to
        # data/sessions/<id>/history.jsonl so a crash doesn't lose the evening's thread; restored on
        # !join, rotated on !leave. World state already persists separately (ADR 015).
        self._autosave = config.autosave
        # Campaign memory (ADR 054): rotated session journals are chunked per scene and embedded
        # into the RAG store on !leave (plus a !join catch-up scan for anything missed), so the
        # DM can recall episodic detail from earlier evenings. DM_SESSION_MEMORY=0 turns ingest
        # and retrieval off together.
        self._session_memory = config.session_memory
        self._ollama_host = config.ollama_host
        self._session_tasks: set = set()  # strong refs — bare create_task results can be GC'd
        # Replay-journal notes for the turn in flight (ADR 046): per channel, facts the cogs and
        # the delivery pipeline record (state_before, scene/flag verdicts, the router verdict);
        # the autosave drains them into the turn record so dm-eval can replay the session.
        self._replay_notes: dict[int, dict] = {}
        # Rolling auto-recap / context handoff (D56): when a turn's prompt nears the num_ctx cap (the
        # early signal before Ollama silently truncates the prompt HEAD — the persona + adventure), we
        # compact the running history into a cumulative recap and clear the in-memory history, so the
        # persona/adventure are never the truncated head mid-session (the first-session complaint:
        # "wenn der Kontext eng wird, übergib an eine neue Sitzung"). Runs OFF the hot path. ON by
        # default; DM_AUTORECAP=0 falls back to the bare context-budget warning.
        self._autorecap = config.autorecap
        # Per-channel "compaction in progress" guard so two quick turns don't both compact and the
        # next player turn doesn't read half-cleared history. A plain set, mutated only on the event
        # loop (where the turn-finalize and the deferred compaction both run).
        self._compacting: set[int] = set()
        # Auto scene transitions (ADR 026): which targets an <<ORT id>> marker may move to.
        # "verbunden" = only the current scene's leads_to neighbours; "frei" = any known scene.
        # Switchable live via !ortmodus; an unknown value degrades to "verbunden".
        self._scene_mode = config.scene_mode if config.scene_mode in ("verbunden", "frei") else "verbunden"
        # Scene-element flags (ADR 043): True → a valid <<ERLEDIGT id>> posts a confirm button
        # (human-in-the-loop, like the scene-change button); False → apply immediately (flags only
        # change what the card renders — lower stakes than the scene pointer).
        self._flag_confirm = config.flag_confirm
        # In-game time (ADR 048): default advance (minutes) applied on a real scene change —
        # travel/regrouping time. 0 = off. The <<ZEIT>> marker and !zeit carry bigger jumps.
        self._scene_time_advance = config.scene_time_advance
        # NPC memory (ADR 044): extract at scene exit / wrap-up what the scene's NPCs would
        # remember; code clamps attitude drift and spreads faction gossip. _npc_mem_marks tracks
        # per channel how many history messages were already mined (the extraction window seam —
        # approximate around compaction, deduped at apply); _npc_mem_running is the per-channel
        # reentrancy guard (two quick scene changes must not extract concurrently).
        self._npc_memory = config.npc_memory
        self._npc_memory_top_k = config.npc_memory_top_k
        # Consistency guard (ADR 045): deterministic pre-delivery check (dead/absent NPC
        # speaking) with max one regenerate on the batch path; the streaming path logs only.
        self._consistency_guard = config.consistency_guard
        self._npc_mem_marks: dict[int, int] = {}
        self._npc_mem_running: set[int] = set()
        # Chekhov list (ADR 050): per-channel unresolved threads, extracted at wrap-up inside
        # the ADR-044 call, code-managed (cap/dedupe/status), lazily loaded from chekhov.json.
        self._chekhov_lists: dict[int, chekhov_mod.ChekhovList] = {}
        # Rules engine (Phase 8): load the active system profile (data/systems/<system>.json). A
        # missing/broken profile must not down the bot — log loudly and run rules-less (no dice).
        self._profile: SystemProfile | None = None
        try:
            self._profile = profile_mod.load(config.system)
            log.info("loaded system profile %r (%s, %s)", self._profile.name,
                     self._profile.dice, self._profile.resolution)
        except ProfileError:
            log.exception("no usable system profile %r — running without the dice engine", config.system)
        # Default party (D82): which data/sessions/<name>/characters.json a channel WITHOUT its own
        # sheet falls back to. The committed "_default" party makes the real party travel to a
        # teammate's clone and load in every voice channel — instead of the generic _example one
        # (the party was previously bound to one channel id, so a new channel got the example party).
        self._default_party = config.default_party
        # Characters: start from the default/example party so !test/!roll work out of the box; !join
        # prefers a channel-specific data/sessions/<id>/characters.json if present. Engine rolls here.
        self._characters, _ = self._load_characters(None)
        # Adventure compendium (Phase 10a, ADR 019): German scene cards + NPC statblocks under
        # data/adventures/<name>/. The scene pointer lives in WorldState.scene_id; the block is
        # injected via _persist_and_refresh. Missing/broken → run without (logged loudly).
        self._adventure: Adventure | None = None
        self._adventure_dir = _DATA_DIR / "adventures" / config.adventure if config.adventure else None
        if config.adventure:
            self._adventure = Adventure.load(_DATA_DIR / "adventures" / config.adventure)
            if self._adventure is not None:
                log.info("loaded adventure %r (%d scenes, %d NPC statblocks)",
                         self._adventure.title or config.adventure,
                         len(self._adventure.scene_overview()), self._adventure.npc_count())
        # 🧪 Debug overlay (ADR 052): the testplan.json sidecar is loaded HERE, next to but never
        # into the Adventure — no prompt/persona/RAG path can reach it (LLM-invisibility, pinned
        # by tests). No sidecar → dormant; DM_DEBUG_OVERLAY=0 → not even loaded.
        self._testplan: Testplan | None = None
        if self._adventure is not None and config.debug_overlay:
            self._testplan = Testplan.load(_DATA_DIR / "adventures" / config.adventure)
            if self._testplan is not None:
                log.info("🧪 loaded testplan.json (%d scenes) — debug overlay active",
                         len(self._testplan))
        self._debug_panel: discord.Message | None = None
        self._debug_channel_id = config.debug_channel_id
        self._debug_channel_warned = False
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
        # The flag + panel handle live here (shared session state); the pause *control* (set_paused,
        # the animation/Esc tasks) lives in VoiceCog, and DMCog's streaming workers read _paused.
        self._paused = False
        self._pause_message: discord.Message | None = None
        # Consequence-clock panel (ADR 047): edit-in-place like the pause panel, no spam.
        self._clock_panel: discord.Message | None = None
        self._text_channel: discord.abc.Messageable | None = None  # where panels are posted (set on join)
        # Rulebook retriever (stage 3, ADR 019): only wired in when an ingested store exists
        # (data/vectordb/rag.db, built offline via `python -m dmbot.rag.ingest`). Without it the
        # brain runs exactly as before — retrieval is additive.
        self._retriever = RulebookRetriever(_DATA_DIR / "vectordb" / "rag.db", host=config.ollama_host)
        if self._retriever.available():
            log.info("rulebook RAG store found — retrieval is on")
        else:
            log.info("no RAG store under data/vectordb/ — rule questions run without the book")
        self._brain = DMBrain(
            OllamaClient(
                config.ollama_host,
                config.ollama_model,
                num_ctx=config.ollama_num_ctx,
                repeat_penalty=config.ollama_repeat_penalty,
                repeat_last_n=config.ollama_repeat_last_n,
            ),
            profile=self._profile,
            num_predict=config.dm_num_predict,
            max_buffer_lines=config.dm_max_lines,
            retriever=self._retriever if self._retriever.available() else None,
        )
        self._bridge = BridgeClient(config.bridge_host, config.bridge_port, secret=config.bridge_secret)
        # Load the TTS backend OFF the boot path so the bot is ready fast (ADR 020 made shutdown
        # fast; this does the same for startup). The XTTS/Coqui load is several seconds of torch +
        # GPU; a daemon thread builds it while Discord connects, and the synth paths wait on
        # _tts_ready *in their worker thread* (never blocking the event loop). on_ready fires
        # immediately and the model is virtually always loaded before anyone !joins and speaks.
        # xtts is imported lazily so Piper users don't pull torch; a load failure → text-only.
        self._tts = None
        self._tts_enabled = True            # a backend is configured; flips False if the load fails
        self._tts_ready = threading.Event()  # set once the load thread finishes (success or failure)

        def _load_tts() -> None:
            log.info("loading TTS backend '%s' in the background …", config.tts_engine)
            t0 = time.perf_counter()
            try:
                if config.tts_engine == "xtts":
                    from .tts.xtts import XttsTTS  # heavy import (torch) — only when selected

                    self._tts = XttsTTS(config.tts_speaker, device=config.tts_device)
                else:
                    self._tts = PiperTTS(config.tts_voice) if config.tts_voice else PiperTTS()
                log.info("TTS backend '%s' ready in %.1fs.", config.tts_engine, time.perf_counter() - t0)
            except Exception:
                self._tts_enabled = False  # graceful: run text-only, but make the failure LOUD
                log.exception("TTS backend '%s' FAILED to load — running text-only (answers post "
                              "but aren't spoken).", config.tts_engine)
            finally:
                self._tts_ready.set()

        threading.Thread(target=_load_tts, name="tts-load", daemon=True).start()
        # STT worker (Phase 4): loads faster-whisper in its own thread, transcribes off the
        # audio path. Started here so a broken cuDNN surfaces at boot, not on first utterance.
        self._transcriber = Transcriber(
            self._on_transcript,
            model=config.whisper_model,
            device=config.whisper_device,
            compute_type=config.whisper_compute,
        )
        self._transcriber.start()

        # ----- Cross-cog hooks (ADR 029) -------------------------------------------------------
        # Registered by the owning cog in its __init__ (runtime.<hook> = self._<method>). They bind
        # the turn pipeline across cog boundaries without bot.get_cog. All are first called only
        # after !join, so registration order doesn't matter.
        self.run_and_deliver = None   # ← DMCog._run_and_deliver  (called by DiceCog roll callbacks)
        self.auto_dm_turn = None      # ← DMCog._auto_dm_turn      (called by VoiceCog mic release)
        self.speak = None             # ← DMCog delivery._speak    (called by LoreCog !lore tts)
        self.handle_dice = None       # ← DiceCog._handle_dice     (called by DMCog delivery)
        self.reanchor_mic = None      # ← VoiceCog._post_mic_button (called by DMCog delivery end)
        self.post_turn_order = None   # ← DiceCog._post_turn_order (called by VoiceCog !join)

    # ----- STT / VAD callbacks (the transcriber is built above with _on_transcript; VadSink in
    # ----- !join is wired to _on_utterance). Both touch only runtime state, run off the event loop.

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

    # ----- Shared Discord send util --------------------------------------------------------------

    async def clear_panel(self, attr: str) -> None:
        """Delete the bottom-pinned panel message stored at self.<attr> (mic / turn-order /
        pause) if one exists, and null the handle. Best-effort: a panel already gone is
        ignored. Shared by the re-post paths so a fresh panel replaces the old one."""
        msg = getattr(self, attr)
        if msg is not None:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass
            setattr(self, attr, None)

    async def _send_with_retry(self, channel, content: str | None = None, *,
                               view: discord.ui.View | None = None,
                               embed: discord.Embed | None = None):
        """Send a message, retrying once on a transient Discord 5xx (e.g. the 503 seen mid-session).
        Discord caps message ``content`` at 2000 chars (HTTP 400, code 50035), so a longer answer
        (the `!intro` monologue, a long DM turn) is split into several messages; any ``view``/``embed``
        rides on the **last** one so the dice button / turn-order view sits after the full text.
        Returns the last message sent."""
        pieces = split_for_discord(content) if content else [None]
        last = None
        for i, piece in enumerate(pieces):
            on_last = i == len(pieces) - 1
            kwargs: dict = {}
            if on_last and view is not None:
                kwargs["view"] = view
            if on_last and embed is not None:
                kwargs["embed"] = embed
            last = await self._send_once(channel, piece, kwargs)
        return last

    async def _send_once(self, channel, content: str | None, kwargs: dict):
        """One ``channel.send``, retried once on a transient 5xx. A <500 error is re-raised (the
        caller's command handler logs it); a 5xx is retried after 1 s, then dropped (returns None)."""
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

    # ----- Spoken-delivery mode (ADR 033) --------------------------------------------------------

    def speech_transform(self):
        """The per-sentence text transform for the current intonation axis, applied before synthesis
        (chat text is never touched). ``flach`` → strip ALL punctuation (no XTTS babble, flatter);
        ``intoniert`` → ``None`` so the wrapper's ``normalize_for_tts`` keeps ``.,!?;:-`` for prosody."""
        return strip_speech_punctuation if self._speech_punct == "flach" else None

    def deliver_seamless(self) -> bool:
        """True when the delivery axis is ``nahtlos`` — synth the whole turn, join into one continuous
        track, play in a single bridge call (gapless, but waits for the full synthesis)."""
        return self._speech_mode == "nahtlos"

    def prebuffer_count(self) -> int:
        """How many sentences the streaming path synthesises before the first plays: the configured
        head-start in ``puffer`` mode (cushions CPU synth falling behind → gaps later), else 1
        (plain ``stream`` — play as soon as the first sentence is ready)."""
        return self._speech_prebuffer if self._speech_mode == "puffer" else 1

    # ----- Channel / character / state plumbing --------------------------------------------------

    def _brain_channel(self, channel) -> int:
        """The id the brain/turn-state are keyed by — the active voice channel, text channel as
        fallback (matches the existing !dm/!redo convention)."""
        return self._active_vc_id if self._active_vc_id is not None else channel.id

    def _load_characters(self, channel_id: int | None) -> tuple[CharacterStore, bool]:
        """Load the party JSON: a channel-specific sheet if present, else the configured default
        party (D82), else the example party. Returns ``(store, fallback)`` — ``fallback`` is True
        ONLY when the *example* party was loaded (the real misconfig: no channel sheet AND no
        default party), so ``!join`` warns loudly (D43: a wrong-channel session silently ran the
        example party, wrong names + sheet values, unnoticed until the DM felt broken). The committed
        ``_default`` party is the *intended* fallback and loads silently — so a teammate's clone and
        every voice channel get the real party without binding it to one channel id. A missing file
        yields an empty store (the engine then rolls without a target)."""
        sessions = _DATA_DIR / "sessions"
        if channel_id is not None:
            specific = sessions / str(channel_id) / "characters.json"
            if specific.is_file():
                log.info("loaded characters from %s", specific)
                return CharacterStore.load(specific), False
        if self._default_party:
            default = sessions / self._default_party / "characters.json"
            if default.is_file():
                log.info("no channel sheet — loaded default party from %s", default)
                return CharacterStore.load(default), False
        return CharacterStore.load(sessions / "_example" / "characters.json"), True

    def _state_path(self, channel_id: int):
        """Where this channel's mutable world state lives (data/sessions/<id>/state.json)."""
        return _DATA_DIR / "sessions" / str(channel_id) / "state.json"

    def _history_path(self, channel_id: int):
        """Where this channel's append-only conversation autosave lives (D41)."""
        return _DATA_DIR / "sessions" / str(channel_id) / "history.jsonl"

    def _chekhov_path(self, channel_id: int):
        """Where this channel's Chekhov list lives (ADR 050), beside the other session files."""
        return _DATA_DIR / "sessions" / str(channel_id) / "chekhov.json"

    def chekhov_list(self, channel_id: int) -> chekhov_mod.ChekhovList:
        """This channel's Chekhov list, lazily loaded (a missing/broken file is an empty list)."""
        if channel_id not in self._chekhov_lists:
            self._chekhov_lists[channel_id] = chekhov_mod.ChekhovList.load(
                self._chekhov_path(channel_id)
            )
        return self._chekhov_lists[channel_id]

    def save_chekhov(self, channel_id: int) -> None:
        """Persist this channel's Chekhov list (atomic, like state.json); best-effort."""
        try:
            self.chekhov_list(channel_id).save(self._chekhov_path(channel_id))
        except OSError:
            log.exception("could not persist the chekhov list for channel %s", channel_id)

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
            adventure_block = self._adventure.adventure_block_de(
                state.scene_id,
                resolved_ids=state.resolved_ids(state.scene_id),
                dead_npcs=[n.name for n in state.npcs if n.wounds <= 0],
            )
        summary = world_state_summary_de(state)
        chekhov_block = chekhov_mod.chekhov_block_de(self.chekhov_list(cid).top_open())
        for block in (self._psyker_block(state), self._augmetic_block(), chekhov_block):
            if block:
                summary = f"{summary}\n\n{block}" if summary else block
        npc_block = ""
        if self._npc_memory:
            npc_block = npc_memory_mod.npc_memory_block_de(
                self._scene_npcs(state), top_k=self._npc_memory_top_k
            )
        self._brain.set_context(
            cid, recap=state.recap, state_summary=summary, adventure_block=adventure_block,
            npc_memory_block=npc_block,
        )

    def _psyker_block(self, state: WorldState) -> str:
        """A compact German block listing each psyker's known powers, Psi-Meisterschaft value, Warp
        Threshold and current Warp Charge — so the DM knows what can be manifested and how close the
        psyker is to Perils (ADR 022). Empty if the profile has no psyker rules or nobody is a psyker.
        Powers are static (the sheet); Warp Charge is the live value from the world state."""
        if self._profile is None or not self._profile.psyker_enabled() or self._characters is None:
            return ""
        lines: list[str] = []
        for char in self._characters.characters():
            if not char.psyker:
                continue
            psi = self._characters.skill_value(char, self._profile.psyker_test_skill())
            wil = self._characters.skill_value(char, self._profile.threshold_characteristic())
            threshold = self._profile.warp_threshold(wil)
            combatant = state.find(char.name)
            warp = combatant.warp_charge if combatant is not None else 0
            stats = [f"Psi-Meisterschaft {psi}" if psi is not None else "Psi-Meisterschaft ?",
                     f"Warp-Schwelle {threshold}", f"aktuell Warp {warp}"]
            powers = ", ".join(char.known_powers) if char.known_powers else "—"
            lines.append(f"{char.name} ({', '.join(stats)}): {powers}")
        if not lines:
            return ""
        return (
            "## Psioniker (psychische Kräfte — wirke sie per `<<MANIFEST Kraft für Name>>`)\n"
            + "\n".join(lines)
        )

    def _augmetic_block(self) -> str:
        """A compact German block listing each character's augmetics + a short effect, so the DM
        narrates with them in mind (ADR 023). Augmetics are passive: the engine already applies
        their armour + characteristic bonuses to rolls; the listed effects remind the DM of the
        situational ones (Auspex, Mechadendrites, …). Static (from the sheet) — empty if the profile
        has no augmetics rules or nobody has an implant."""
        if self._profile is None or not self._profile.augmetics_enabled() or self._characters is None:
            return ""
        lines: list[str] = []
        for char in self._characters.characters():
            if not char.augmetics:
                continue
            parts: list[str] = []
            for name in char.augmetics:
                stats = self._profile.augmetic(name)
                text = (stats or {}).get("text", "")
                parts.append(f"{name} — {text}" if text else name)
            lines.append(f"{char.name}: " + "; ".join(parts))
        if not lines:
            return ""
        return (
            "## Augmetik/Implantate (dauerhaft, kein Wurf — Rüstung/Merkmals-Boni rechnet die "
            "Engine bereits dazu; situative Effekte erzählst du)\n" + "\n".join(lines)
        )

    def _set_scene(self, state: WorldState, scene_id: str) -> Scene | None:
        """Move the code-owned scene pointer (golden rule #3): set ``state.scene_id`` and sync the
        prose location. The single deterministic move shared by ``!ort`` and the auto-transition
        path (ADR 026). Returns the Scene moved to, or None if ``scene_id`` is unknown to the
        adventure. The caller persists + refreshes the prompt. A real move (pointer actually
        changes) is journaled as a ``{"kind": "scene"}`` event (ADR 053)."""
        if self._adventure is None:
            return None
        scene = self._adventure.get_scene(scene_id)
        if scene is None:
            return None
        changed = state.scene_id != scene.id
        state.scene_id = scene.id
        if scene.title_de:
            state.set_location(scene.title_de)  # keep the prose state block in sync
        if changed:
            self._journal_scene_event(state)
        return scene

    def _journal_scene_event(self, state: WorldState) -> None:
        """Append a ``{"kind": "scene", "scene_id", "ts"}`` record to the session journal
        (ADR 053): rotated transcripts carry their own scene boundaries for the upcoming
        session-transcript ingest. ``load_recent`` skips it (no ``user_msg``/``answer``,
        ADR 046). getattr-guarded like :meth:`replay_note` — journaling must never break a
        scene move on a partially-built runtime."""
        if not getattr(self, "_autosave", False):
            return
        cid = next((c for c, st in getattr(self, "_state", {}).items() if st is state), None)
        if cid is None:
            return
        try:
            history_store.append_event(self._history_path(cid), {
                "kind": "scene",
                "scene_id": state.scene_id,
                "ts": datetime.now().isoformat(timespec="seconds"),
            })
        except OSError:
            log.exception("could not journal the scene event for channel %s", cid)

    # --- campaign memory: session-transcript ingest (ADR 054) -----------------------------------

    def _session_ingest_source(self, channel_id: int) -> str | None:
        """The RAG source this channel's played sessions are ingested under, or ``None`` to skip
        ingest entirely. Skipped when the feature is off (DM_SESSION_MEMORY=0) — and for
        debug-campaign runs (ADR 052): those play in the SAME channel as live play, so channel
        isolation doesn't cover them; a ``testplan.json`` next to the loaded adventure marks the
        run as debug (pure path check, independent of the DM_DEBUG_OVERLAY kill-switch). This
        method is the seam for the debug-campaign follow-up, which will return a sandboxed debug
        source here instead of skipping."""
        if not self._session_memory:
            return None
        if self._adventure_dir is not None and (self._adventure_dir / "testplan.json").is_file():
            log.info("session ingest skipped — debug-campaign run (testplan.json present)")
            return None
        return ingest_session.session_source(channel_id)

    def schedule_session_ingest(self, channel_id: int, rotated: Path | None) -> None:
        """Ingest one just-rotated journal in the background (the !leave trigger). Degrades
        silently: any failure only logs; !leave never waits on it."""
        if rotated is None or self._session_ingest_source(channel_id) is None:
            return
        self._spawn_session_ingest([Path(rotated)], channel_id)

    def schedule_session_catchup(self, channel_id: int) -> None:
        """Ingest every rotated journal whose stamp isn't in the store yet, in the background
        (the !join trigger). Self-healing: covers crashes, shutdown-during-ingest — and the
        first !join after the feature lands backfills all existing rotated sessions."""
        if self._session_ingest_source(channel_id) is None:
            return
        session_dir = self._history_path(channel_id).parent
        db_path = self._retriever._db_path

        def _scan_and_ingest() -> None:
            for path in ingest_session.pending_files(session_dir, db_path=db_path):
                self._ingest_one(path, channel_id)

        self._spawn_session_task(_scan_and_ingest)

    def _ingest_one(self, path: Path, channel_id: int) -> None:
        """One journal into the store (worker thread). Failures log and skip the file — the
        catch-up retries it on the next !join because its stamp was never recorded."""
        try:
            n = ingest_session.ingest_session_file(
                path, channel_id=channel_id,
                db_path=self._retriever._db_path, host=self._ollama_host,
            )
            log.info("🗂 session memory: ingested %s (%d chunks)", path.name, n)
        except Exception:
            log.exception("session ingest failed for %s — skipped", path.name)

    def _spawn_session_ingest(self, paths: list[Path], channel_id: int) -> None:
        def _work() -> None:
            for path in paths:
                self._ingest_one(path, channel_id)

        self._spawn_session_task(_work)

    def _spawn_session_task(self, work) -> None:
        """Run ``work`` (sync, does its own error logging) off the event loop as a fire-and-forget
        background task. Without a running loop (unit tests) it degrades to a no-op."""
        try:
            task = asyncio.get_running_loop().create_task(asyncio.to_thread(work))
        except RuntimeError:
            log.debug("no running event loop — session ingest not scheduled")
            return
        tasks = getattr(self, "_session_tasks", None)
        if tasks is not None:  # stub runtimes in tests may lack the set
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    def _set_scene_flag(self, state: WorldState, element_id: str, *, resolved: bool) -> str | None:
        """Deterministically flag an element of the CURRENT scene resolved/open (ADR 043, golden
        rule #3) — the single mutator shared by ``!erledigt``/``!offen`` and the ``<<ERLEDIGT>>``
        auto path. Validates ``element_id`` against the current scene card; returns the element's
        German text on success (for the reply), None for an unknown/foreign id or no adventure.
        Idempotent. The caller persists + refreshes the prompt."""
        if self._adventure is None:
            return None
        scene = self._adventure.get_scene(state.scene_id)
        if scene is None:
            return None
        text = scene.element_text(element_id)
        if text is None:
            return None
        if resolved:
            state.mark_resolved(scene.id, element_id)
        else:
            state.mark_open(scene.id, element_id)
        return text

    # ----- Consequence clocks (ADR 047) -----------------------------------------------------

    def _tick_clock(self, channel, clock_id: str) -> Clock | None:
        """Deterministically advance a clock one segment (golden rule #3) — the single mutator
        shared by ``!uhr tick`` and the ``<<UHR>>`` confirm/auto path. Rejects unknown ids and
        already-full clocks (returns ``None``). A fresh fill queues the one-shot ``[Regie]``
        consequence note for the next DM turn (ADR 047 #8). The caller persists + refreshes the
        prompt + updates the panel."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return None
        clock = state.tick_clock(clock_id)
        if clock is None:
            return None
        if clock.full:
            self._brain.add_gm_note(cid, clock_full_note_de(clock))
            log.info("⌛ Uhr '%s' (%s) ist voll — Konsequenz-Hinweis für den nächsten Turn "
                     "eingereiht", clock.name, clock.id)
        return clock

    def _untick_clock(self, channel, clock_id: str) -> Clock | None:
        """Take one segment back (``!uhr zurück``). Unticking a *full* clock retracts a
        still-queued consequence note — an accidental fill must not fire (ADR 047 #8)."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return None
        clock = state.find_clock(clock_id)
        if clock is None:
            return None
        if clock.full and self._brain.discard_gm_notes(cid, containing=f"„{clock.name}“"):
            log.info("⏱ Uhr '%s': eingereihter Konsequenz-Hinweis zurückgezogen", clock.name)
        return state.untick_clock(clock_id)

    async def update_clock_panel(self) -> None:
        """(Re)render the pressure panel (time + deadlines + clocks, ADR 047/048) in the
        session's text channel — edit-in-place (the pause-panel pattern), so ticks/advances
        update one message instead of spamming. No clocks AND no deadlines → the panel is
        removed (`!zeit` shows the bare time on demand). Best-effort: a send/edit failure
        logs, never breaks a turn/command."""
        if self._text_channel is None:
            return
        state = self._state.get(self._active_vc_id) if self._active_vc_id is not None else None
        if state is None or not (state.clocks or state.deadlines):
            await self.clear_panel("_clock_panel")
            return
        content = pressure_panel_de(state)
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

    # ----- 🧪 Debug overlay (ADR 052) ---------------------------------------------------------

    def _debug_overlay_channel(self):
        """The overlay's target: the DM_DEBUG_CHANNEL channel when set and resolvable (one
        loud line + game-channel fallback otherwise), else the session's text channel."""
        if self._debug_channel_id:
            guild = getattr(self._text_channel, "guild", None)
            ch = guild.get_channel(self._debug_channel_id) if guild is not None else None
            if ch is not None:
                return ch
            if not self._debug_channel_warned:
                log.warning("🧪 DM_DEBUG_CHANNEL=%s not resolvable — overlay falls back to "
                            "the game channel", self._debug_channel_id)
                self._debug_channel_warned = True
        return self._text_channel

    async def update_debug_overlay(self) -> None:
        """(Re)render the 🧪 testplan overlay for the current scene (ADR 052) — edit-in-place
        (the clock-panel pattern), called by every scene-change path. Fully dormant without a
        loaded testplan; zero LLM calls, zero prompt bytes — the DM never learns a test run is
        happening. Best-effort: a send/edit failure logs, never breaks a turn."""
        plan = getattr(self, "_testplan", None)  # getattr: stub runtimes stay dormant
        if plan is None:
            return
        state = self._state.get(self._active_vc_id) if self._active_vc_id is not None else None
        if state is None or not state.scene_id:
            return
        channel = self._debug_overlay_channel()
        if channel is None:
            return
        scene = self._adventure.get_scene(state.scene_id) if self._adventure else None
        content = overlay_line_de(state.scene_id, scene.title_de if scene else "",
                                  plan.entry_for(state.scene_id))
        if self._debug_panel is not None:
            try:
                await self._debug_panel.edit(content=content)
                return
            except discord.HTTPException:
                self._debug_panel = None  # message gone — fall through and re-post
        try:
            self._debug_panel = await channel.send(content)
        except discord.HTTPException:
            log.warning("could not post the debug overlay", exc_info=True)

    # ----- In-game time + deadlines (ADR 048) -----------------------------------------------

    async def _advance_time(self, channel, minutes: int) -> int:
        """Deterministically advance the in-game clock (golden rule #3) — the single mutator
        shared by ``!zeit``, the ``<<ZEIT>>`` confirm/auto path and the scene-change default
        advance. Queues the one-shot ``[Regie]`` note for each newly expired deadline
        (ADR 048 #8), persists, refreshes the prompt and the pressure panel. Returns the
        applied minutes (0 = no session or a non-positive amount)."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None or minutes <= 0:
            return 0
        expired = state.advance_time(minutes)
        for dl in expired:
            self._brain.add_gm_note(cid, deadline_note_de(dl.label))
            log.info("⏳ Frist '%s' (%s) verstrichen — Konsequenz-Hinweis für den nächsten "
                     "Turn eingereiht", dl.label, dl.id)
        self._persist_and_refresh(channel)
        await self.update_clock_panel()
        return minutes

    async def advance_scene_time(self, channel) -> int:
        """The default time cost of a *real* scene change (ADR 048 #10) — called by the two
        move paths (``!ort``, confirmed ``<<ORT>>``) after a successful move to a different
        scene. ``DM_SCENE_TIME_ADVANCE=0`` disables it. Returns the applied minutes."""
        return await self._advance_time(channel, self._scene_time_advance)

    # ----- Consistency guard (ADR 045) ------------------------------------------------------

    def consistency_checker(self, channel):
        """The consistency check for this channel's turn, or ``None`` when the guard is off or
        no world state exists yet (both mean: don't check). Closes over the channel's live
        world state + active scene card; passed into ``DMBrain.respond``/``redo`` (batch path,
        regenerate-once) and run log-only at the end of a streamed turn (ADR 045)."""
        if not self._consistency_guard:
            return None
        state = self._state.get(self._brain_channel(channel))
        if state is None:
            return None
        scene = self._adventure.get_scene(state.scene_id) if self._adventure is not None else None
        return lambda text: consistency_mod.check(text, state, scene)

    # ----- NPC memory (ADR 044) -------------------------------------------------------------

    def _scene_npcs(self, state: WorldState, scene_id: str | None = None) -> list[Combatant]:
        """The *living, registered* NPCs of a scene (default: the current one) — whose memories
        ride in the prompt. With an adventure loaded the card's ``npcs_here`` filters the
        registered list (case-insensitive, like ``WorldState.find``); without one, every living
        registered NPC counts (there is no scene notion to scope by)."""
        living = [n for n in state.npcs if n.wounds > 0]
        if self._adventure is None:
            return living
        scene = self._adventure.get_scene(scene_id if scene_id is not None else state.scene_id)
        if scene is None:
            return living
        here = {n.strip().lower() for n in scene.npcs_here}
        return [n for n in living if n.name.lower() in here]

    def schedule_npc_memory_extraction(self, channel, scene_id: str) -> None:
        """Fire-and-forget NPC-memory extraction for the scene just left (ADR 044) — called by
        the scene-change seams (!ort, the confirmed <<ORT>> move) right after the pointer moved.
        Off the hot path by design: the scene change never waits for the LLM."""
        if not self._npc_memory:
            return
        try:
            asyncio.get_running_loop().create_task(
                self.extract_npc_memories(channel, scene_id)
            )
        except RuntimeError:  # no running loop (sync/test context) — extraction is best-effort
            log.debug("NPC-memory: no running event loop — extraction skipped")

    async def extract_npc_memories(self, channel, scene_id: str, *, include_chekhov: bool = False) -> int:
        """Mine the history since the last extraction for what ``scene_id``'s NPCs would remember
        and apply it (memories + clamped attitude drift + lie flips + faction gossip — all hard
        effects in code, golden rule #3). Best-effort end to end: any failure logs and returns 0,
        never blocks the caller. Returns the number of new direct memories.

        ``include_chekhov`` (the ``!wrap`` call, ADR 050): the same call additionally maintains
        the Chekhov list — its input gains the open threads + the session history *before* the
        scene window (threads are session-granularity; the window alone only covers the last
        scene), and the ``chekhov`` output section is applied code-side (cap/dedupe/status)."""
        if not self._npc_memory:
            return 0
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None or cid in self._npc_mem_running:
            if cid in self._npc_mem_running:
                log.info("NPC-memory: extraction already running for channel %s — skipped", cid)
            return 0
        mark = min(self._npc_mem_marks.get(cid, 0), self._brain.history_len(cid))
        turns = self._brain.history_messages(cid, mark)
        chekhov_section = ""
        if include_chekhov:
            earlier = self._brain.history_messages(cid, 0)[:mark]
            if turns or earlier:  # anything at all this session the thread pass could mine
                chekhov_section = chekhov_mod.build_chekhov_section(
                    self.chekhov_list(cid).open_threads(), earlier
                )
        # Candidates: every living registered NPC (incl. off-card !npc add spawns of this scene)
        # plus the departed scene card's npcs_here — the latter may be unregistered talk-only
        # NPCs; a dummy carrier lets the extractor name them, apply registers on first memory.
        # The extractor prompt binds memories to what actually happened in the transcript.
        candidates = [n for n in state.npcs if n.wounds > 0]
        known = {n.name.lower() for n in candidates}
        if self._adventure is not None:
            scene = self._adventure.get_scene(scene_id)
            for name in scene.npcs_here if scene else []:
                if name.strip().lower() not in known:
                    candidates.append(Combatant(name=name.strip(), wounds=1, max_wounds=1, is_npc=True))
        if (not turns or not candidates) and not chekhov_section:
            self._npc_mem_marks[cid] = mark + len(turns)
            return 0
        self._npc_mem_running.add(cid)
        try:
            now_ingame = render_time_de(state.time_minutes)
            payload = await npc_memory_mod.request_extraction(
                self._brain.client, turns=turns, npcs=candidates, scene_id=scene_id,
                now_ingame=now_ingame, chekhov_section=chekhov_section,
            )
            # The window is consumed even when extraction failed (skip, don't re-mine it against
            # a different scene later); the gist-dedup in apply covers the overlap cases.
            self._npc_mem_marks[cid] = mark + len(turns)
            if payload is None:
                return 0
            new_entries = npc_memory_mod.apply_extraction(
                state, payload, scene_id=scene_id,
                now=datetime.now().isoformat(timespec="seconds"),
                now_ingame=now_ingame,
                statblock=self._adventure.npc if self._adventure is not None else None,
            )
            npc_memory_mod.propagate_gossip(state, new_entries)
            if chekhov_section:
                n_new, n_resolved = chekhov_mod.apply_chekhov(
                    self.chekhov_list(cid), payload.get("chekhov"),
                    origin_scene=scene_id,
                    created_session=datetime.now().date().isoformat(),
                )
                if n_new or n_resolved:
                    self.save_chekhov(cid)
                    log.info("🧵 Chekhov-Liste: %d neue Fäden, %d aufgelöst", n_new, n_resolved)
            self._persist_and_refresh(channel)
            log.info("🧠 NPC-Gedächtnis: %d neue Erinnerungen (Szene '%s')", len(new_entries), scene_id or "—")
            return len(new_entries)
        except Exception:
            log.exception("NPC-memory extraction failed for scene '%s' — skipped", scene_id)
            return 0
        finally:
            self._npc_mem_running.discard(cid)

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

    def seed_session(self, voice_channel, text_channel) -> bool:
        """Seed all per-session state for a fresh !join in the right order: active + text
        channel, party (+ alias/speaker hints), turn order from the voice members, world
        state (seeded from the sheet on first join, else loaded), the start-scene pointer for
        a fresh state (a loaded state keeps its stored pointer), persist+refresh, and the D41
        crash-recovery history restore. Returns the example-party fallback flag."""
        cid = voice_channel.id
        self._active_vc_id = cid  # buffer transcripts + answer for this channel
        self._text_channel = text_channel  # where the pause panel (and other panels) are posted
        # Phase 8: load this channel's party (else the example), wire the "who plays whom" alias
        # hint into the prompt (open item F), and seed the turn order from the voice members.
        self._characters, char_fallback = self._load_characters(cid)
        self._brain.set_alias_hint(cid, self._characters.alias_hint_de())
        # All table names → cut-labels/stop sequences, so a puppeted "Seskin: …" script is truncated.
        self._brain.set_known_speakers(cid, self._characters.speaker_labels())
        self._turn_order[cid] = self._build_turn_order(voice_channel)
        self._turn_index[cid] = 0
        # Memory (Phase 9): load this channel's world state (or seed it from the sheet on first join),
        # then inject the stored recap + current state into the prompt so the DM picks up where it
        # left off — the "next session opens with a correct recap" half of the gate.
        self._state[cid] = self._load_or_seed_state(cid)
        # Adventure (Phase 10a): point a fresh session at the start scene; a loaded state keeps
        # its stored pointer (the plot position survives restarts like HP does).
        if self._adventure is not None and not self._state[cid].scene_id:
            self._state[cid].scene_id = self._adventure.start_scene
        self._persist_and_refresh(voice_channel)
        # Crash recovery (D41): restore the conversation thread from the autosave if the in-memory
        # history is empty (a fresh process after a crash). A clean !leave rotates the file away, so
        # this only fires when the previous session didn't shut down cleanly.
        if self._autosave:
            try:
                turns = history_store.load_recent(
                    self._history_path(cid), self._brain.max_history_turns
                )
            except OSError:
                log.exception("could not read the history autosave for channel %s", cid)
                turns = []
            restored = self._brain.restore_history(cid, turns)
            if restored:
                log.info("restored %d conversation turns from the autosave (!redo unavailable for the last)", restored)
        # NPC memory (ADR 044): don't re-mine restored/pre-join history — extraction starts at
        # the join point (the previous session's tail was covered by its own wrap-up/scene exits).
        self._npc_mem_marks[cid] = self._brain.history_len(cid)
        # Replay journal header (ADR 046): the session context dm-eval needs to rebuild the
        # pipeline (profile, adventure, scene mode). One line per !join; load_recent skips it.
        if self._autosave:
            profile = getattr(self, "_profile", None)
            adventure = getattr(self, "_adventure", None)
            try:
                history_store.append_event(self._history_path(cid), {
                    "kind": "session",
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "profile": profile.name if profile else "",
                    "adventure": adventure.id if adventure else "",
                    "scene_mode": getattr(self, "_scene_mode", "verbunden"),
                })
            except OSError:
                log.exception("could not write the session header for channel %s", cid)
            # Scene journal event (ADR 053): open every session's journal with the current scene
            # — the fresh start-scene seed above or a restored pointer — so the first chunk of a
            # session has a scene even before the first transition.
            if self._state[cid].scene_id:
                self._journal_scene_event(self._state[cid])
        return char_fallback

    def replay_note(self, channel, key: str, value) -> None:
        """Record one replay-journal fact for the turn in flight (ADR 046) — the delivery
        pipeline notes the pre-marker world state + scene/flag verdicts, the dice cog notes the
        router verdict. Drained into the turn's autosave record by :meth:`take_replay_notes`.
        getattr-guarded: recording must never break a turn on a partially-built runtime."""
        if not getattr(self, "_autosave", False):
            return
        notes = getattr(self, "_replay_notes", None)
        if notes is None:
            notes = self._replay_notes = {}
        notes.setdefault(self._brain_channel(channel), {})[key] = value

    def take_replay_notes(self, channel) -> dict:
        """Return and clear the turn's replay notes (ADR 046) — called by the autosave."""
        notes = getattr(self, "_replay_notes", None)
        if not notes:
            return {}
        return notes.pop(self._brain_channel(channel), {})
