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

Since D107 it also owns the **post-turn boundary** (:meth:`SessionRuntime.close_turn`, ADR
057/058/059): once a turn is narrated the in-game clock ticks, the scene and fact classifiers run
in one shared latency window, a validated verdict moves the code-owned scene pointer (or writes a
hard fact), and the player panel is re-anchored. It lives here rather than in a cog because every
piece of it is shared state — pointer, world state, prompt context, panels — and because all four
scene movers (classifier, flag gate, ``!ort``, the demoted ``<<ORT>>`` marker) must go through the
same :meth:`move_scene`, or NPC registration and the panels drift apart again.

Since ADR 065 the method groups live in ``dmbot/session/`` as mixins of this one class (still one
object, ``self`` is the runtime); this module keeps the constructor and the shared plumbing.

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
from pathlib import Path

import discord

from .config import Config
from .voice.recv import VadSink
from .voice.preflight import check_static, check_tts_speaker
from .voice.kick_phrase import find_culprit, is_kick_master, parse_kick_phrase
from .stt import Transcriber
from .llm import consistency as consistency_mod
from .llm import build_llm_client, recap_cap
from .orchestrator import DMBrain
from .tts.piper import PiperTTS
from .tts.textsplit import split_for_discord, strip_speech_punctuation
from .bridge import BridgeClient
from .rules import profile as profile_mod
from .rules.profile import ProfileError, SystemProfile
from .rules.characters import CharacterStore
from .discord_ui.panel import render_player_panel_de
from .discord_ui.transcript import format_player_line
from .memory import chekhov as chekhov_mod
from .memory.state import (
    WorldState,
    clocks_panel_de,
)
from .rag.adventure import Adventure
from .rag import ingest_session
from .rag.retrieve import RulebookRetriever
from .rag.testplan import Testplan, overlay_line_de
from .session.ingest import SessionIngestMixin
from .session.clocks import ClocksMixin
from .session.npcs import NpcMemoryMixin
from .session.panels import PanelsMixin
from .session.persistence import PersistenceMixin
from .session.seeding import SeedingMixin
from .session.scenes import SceneFlowMixin

# Re-export shim (ADR 034): the per-turn latency record + its ctx-budget threshold moved to
# dmbot/turn_timing.py for context-leanness; keep importing them from here so the cog/dice/tests'
# ``from ..runtime import _TurnTiming`` (and `_CTX_WARN_FRACTION`) keep working unchanged.
from .turn_timing import _CTX_WARN_FRACTION, _TurnTiming  # noqa: F401
# Same for the session journal (ADR 065): its callers moved to dmbot/session/ (scenes, seeding),
# but tests still reach the module as ``runtime_mod.history_store``.
from .memory import history as history_store  # noqa: F401

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


class SessionRuntime(SessionIngestMixin, ClocksMixin, NpcMemoryMixin, PanelsMixin,
                     PersistenceMixin, SeedingMixin, SceneFlowMixin):
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
        # The configured XTTS speaker must exist (B13: the live run spoke in a random voice
        # because TTS_SPEAKER carried the value meant for TTS_DEVICE). Loud, never fatal — TTS is
        # an optional layer, and this runs before the torch import so the message is early.
        check_tts_speaker(config.tts_speaker, engine=config.tts_engine)
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
        # Consequence clocks (ADR 047/059): off = not seeded, not rendered, <<UHR>> ignored, !uhr
        # answers with a hint. Saved clocks are only hidden, never deleted. Read through
        # ``clocks_enabled`` everywhere.
        self._clocks = config.clocks
        self._post_player_lines = config.post_player_lines
        # The table's running gag as a voice command ("Der Timo war ein sehr böser Junge." →
        # Timo is disconnected from voice). DM_KICK_PHRASE=0 off; DM_KICK_MASTER limits who may say it.
        self._kick_phrase = config.kick_phrase
        self._kick_master = config.kick_master
        self._speaker_ids: dict[str, int] = {}  # display name → Discord user id (written per utterance)
        self._voice_channel = None  # the joined voice channel (seed_session); its members are live
        self._loop: asyncio.AbstractEventLoop | None = None  # captured by seed_session (STT → loop)
        if not self._clocks:
            log.info("⏱ Uhren aus (DM_CLOCKS=0) — nicht angelegt, nicht angezeigt, <<UHR>> wird "
                     "ignoriert; gespeicherte Uhren bleiben erhalten.")
        # --- the post-turn machinery of D107 (ADR 057/058/059). Every block below is switchable
        # on its own, live via !automatik, because the evening must survive a misfiring mechanism.
        # Scene-move classifier (ADR 057 #1) + the model-free flag gate (#2): the two movers that
        # replace the <<ORT>> marker, which fired zero times in 22 live turns. The marker itself
        # stays wired in the delivery pipeline as an opportunistic fallback.
        self._scene_router = config.scene_router
        self._scene_flag_gate = config.scene_flag_gate
        # Fact classifier (ADR 058): runs on the SAME turn boundary as the scene one, in one
        # asyncio.gather — one latency window for both, as the ADR requires.
        self._fact_router = config.fact_router
        self._npc_router = config.npc_router
        self._fate_wait_seconds = config.fate_wait_seconds
        self._dice_images = config.dice_images  # dice result thumbnails (dmbot/dice_images.py)
        self._dice_animation = config.dice_animation  # throw GIF between click and result
        self._dice_asset_channel = config.dice_asset_channel  # stored throw GIFs (ADR 064)
        self._auto_join = config.auto_join  # any command joins voice first (D130)
        # In-game minutes a narrated turn costs (ADR 059 #2); the bigger scene-change advance
        # stays _scene_time_advance above.
        self._turn_time_advance = config.turn_time_advance
        # How long the ↩ control under an automatic scene change stays live (ADR 057 #4).
        self._scene_undo_seconds = config.scene_undo_seconds
        # Cadence of the scene's standing guidance (PRD block 3): injected on the first turn in a
        # scene and every Nth turn after, as an impulse rather than the standing order that made
        # the seneschal repeat "die Zeit läuft uns davon" in eight of ten answers.
        self._guidance_every = config.guidance_every
        self._scene_turns: dict[int, int] = {}  # turns narrated since entering the current scene
        # The open <<ORT>> proposal per channel: (message, proposed scene id). Any real move retires
        # it, so its "Wechseln" button cannot linger after the classifier already moved (2026-10-25).
        self._scene_proposals: dict[int, tuple] = {}
        self._last_narration: dict[int, str] = {}  # the previous answer, the scene router's context
        # The NPCs the presence classifier filed in the turn that is still open (ADR 062,
        # amendment 2026-11-13): they follow the pointer until the next turn boundary begins.
        self._turn_sightings: dict[int, tuple[str, ...]] = {}
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
        # Player panel (PRD stories 14-17): one message the table reads — place, goal, time,
        # deadline, whose turn it is, what is still open here — edited in place and re-anchored at
        # the bottom after every turn. Deliberately NOT a replacement for the 🧪 overlay: that one
        # is the operator's line (gate codes + command hints) and belongs in DM_DEBUG_CHANNEL,
        # while this one is in players' language and belongs in the game channel.
        self._player_panel_enabled = config.player_panel
        self._player_panel: discord.Message | None = None
        self._player_panel_lock = asyncio.Lock()  # two quick updates must not post two panels
        # Channels already swept this run (once per channel): old player panels adopted/deduped,
        # and the separate pressure panels of earlier runs deleted (D132/D133).
        self._panel_swept_channels: set = set()
        self._pressure_swept_channels: set = set()
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
        # Identity (PRD "Identity", findings A4/B4): Discord user id → character name, captured
        # from the voice-channel members at !join. The id is the stable key — a nickname change
        # mid-session cannot break it, which display-name resolution could. ``_speaker_names``
        # memoises the resolution per display name, because the STT callback only carries the
        # name (the utterance callback, which has the id, fills it in).
        self._char_by_user: dict[int, str] = {}
        self._speaker_names: dict[str, str] = {}
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
        self._retriever = RulebookRetriever(
            _DATA_DIR / "vectordb" / "rag.db", host=config.ollama_host,
            session_memory=config.session_memory,
            # Debug-run sandbox (ADR 055): a debug campaign reads back only its own
            # session_debug_<id> memories — never the live campaign's, and vice versa.
            debug_sessions=self.is_debug_run,
        )
        if self._retriever.available():
            log.info("rulebook RAG store found — retrieval is on")
        else:
            log.info("no RAG store under data/vectordb/ — rule questions run without the book")
        # Ollama alone, or Claude with Ollama as the loud fallback (DM_LLM_BACKEND, ADR 061).
        # The retriever above keeps embedding through Ollama on both.
        llm_client = build_llm_client(config)
        self._brain = DMBrain(
            llm_client,
            profile=self._profile,
            num_predict=config.dm_num_predict,
            max_buffer_lines=config.dm_max_lines,
            retriever=self._retriever if self._retriever.available() else None,
            recap_num_predict=recap_cap(config, llm_client),  # per answering backend (ADR 061)
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
        # Identity (PRD "Identity"): resolve who this is NOW, while the Discord user id is still
        # in hand — the STT callback below only gets the display name back. One plain dict write;
        # the STT thread reads it (GIL-atomic, like _last_stt_ms).
        self._speaker_names[name] = self.character_name_for(user_id, name)
        self._speaker_ids[name] = user_id
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
        if self._maybe_kick(name, text):
            return  # a table command, not a line for the DM
        # Buffer the line for the next DM turn (triggered by !dm) only when routed. Runs on the STT
        # thread; the brain's buffer is lock-guarded.
        if for_dm and self._active_vc_id is not None:
            # Under the CHARACTER's name, not the Discord one (PRD "Identity", findings A4/B4):
            # the prompt used to read "Sezgin: …", so the DM answered "Sezgin, ich kann leider
            # nicht …" and treated four players as one. The log line above keeps the Discord name
            # — that is the operator's record of who actually spoke.
            speaker = self.prompt_speaker_name(name)
            self._brain.add_player_line(self._active_vc_id, speaker, text)
            # Remember this utterance's transcribe ms as the turn's stt stage (reuse, don't
            # re-measure). A plain int write; the consuming turn pops it on the event loop.
            self._last_stt_ms[self._active_vc_id] = round(latency_ms)
            self._echo_player_line(speaker, text)

    def _echo_player_line(self, speaker: str, text: str) -> None:
        """Post a DM-routed player line to the text channel (``DM_POST_PLAYER_LINES``), so the
        channel holds both halves of the story. Called on the STT thread: the send is handed to
        the event loop captured at ``seed_session``. Fire-and-forget — a failed post is logged,
        never blocks the turn. The line lands before the DM's answer because the turn waits for
        STT to go idle and then spends seconds in the LLM."""
        loop = self._loop
        channel = self._text_channel
        if not self._post_player_lines or loop is None or channel is None:
            return
        if not text.strip() or loop.is_closed():
            return
        content = format_player_line(speaker, text)

        async def _post() -> None:
            try:
                await self._send_with_retry(channel, content)
            except Exception:
                log.exception("posting the player line failed")

        asyncio.run_coroutine_threadsafe(_post(), loop)

    # ----- "Der Timo war ein sehr böser Junge." (voice command → disconnect) -----------------------

    def _maybe_kick(self, speaker: str, text: str) -> bool:
        """If ``text`` is the kick phrase, disconnect the named member from the voice channel.
        Returns True when the line was a command (handled or refused), so the caller keeps it
        away from the DM. Runs on the STT thread: the move itself is scheduled on the loop."""
        if not self._kick_phrase:
            return False
        culprit_name = parse_kick_phrase(text)
        if not culprit_name:
            return False
        master = self._kick_master
        if not is_kick_master(master, speaker, self._speaker_ids.get(speaker)):
            log.info("⚡ %s said the kick phrase about %r — only %s may (DM_KICK_MASTER)",
                     speaker, culprit_name, master)
            return True
        vc = self._voice_channel
        loop = self._loop
        if vc is None or loop is None or loop.is_closed():
            log.info("⚡ kick phrase about %r, but no voice channel/loop to act on", culprit_name)
            return True
        member = find_culprit(culprit_name, getattr(vc, "members", []) or [],
                              self._char_by_user, self._bot_a_user_id)
        if member is None:
            log.info("⚡ kick phrase about %r — nobody in the voice channel matches", culprit_name)
            return True
        asyncio.run_coroutine_threadsafe(self._kick_member(member, speaker), loop)
        return True

    async def _kick_member(self, member, by: str) -> None:
        """``move_to(None)`` = drop the member from voice (needs the Move Members permission),
        then tell the text channel. Errors are logged, never raised into the loop."""
        name = getattr(member, "display_name", "?")
        try:
            await member.move_to(None, reason=f"Sprachbefehl von {by}: war ein sehr böser Junge")
        except Exception:
            log.exception("⚡ disconnecting %s failed (Move Members permission?)", name)
            return
        log.info("⚡ %s war ein sehr böser Junge — vom Voice-Kanal getrennt (gesagt von %s)", name, by)
        channel = self._text_channel
        if channel is None:
            return
        try:
            await self._send_with_retry(
                channel, f"⚡ **{discord.utils.escape_markdown(name)}** war ein sehr böser Junge "
                         f"und wurde vom Server getrennt.")
        except Exception:
            log.exception("posting the kick line failed")

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
                               embed: discord.Embed | None = None,
                               file: discord.File | None = None):
        """Send a message, retrying once on a transient Discord 5xx (e.g. the 503 seen mid-session).
        Discord caps message ``content`` at 2000 chars (HTTP 400, code 50035), so a longer answer
        (the `!intro` monologue, a long DM turn) is split into several messages; any ``view``/``embed``/
        ``file`` rides on the **last** one so the dice button / turn-order view sits after the full text.
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
            if on_last and file is not None:
                kwargs["file"] = file
            last = await self._send_once(channel, piece, kwargs)
        return last

    async def _send_once(self, channel, content: str | None, kwargs: dict):
        """One ``channel.send``, retried once on a transient 5xx. A <500 error is re-raised (the
        caller's command handler logs it); a 5xx is retried after 1 s, then dropped (returns None)."""
        try:
            return await channel.send(content, **kwargs)
        except discord.HTTPException as exc:
            if (getattr(exc, "status", 0) or 0) < 500 or "file" in kwargs:
                raise  # (a sent discord.File is closed — it can't ride a retry; the caller falls back)
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

    # ----- Identity: which character a speaker is (PRD "Identity", ADR 003) ----------------------

    def character_name_for(self, user_id: int | None, display_name: str) -> str:
        """The character name a speaker's line enters the prompt under.

        Resolution order, and the order is the point: the Discord **user id** first (captured
        from the voice-channel members at ``!join``, so a nickname change mid-session cannot
        break it — story 24), then the display name through the same alias map (a player who
        joined the channel after ``!join``), then the display name itself. The last step is not a
        fallback bug but the guest case: someone at the table without a sheet keeps their own
        name and nothing raises."""
        if user_id is not None:
            resolved = self._char_by_user.get(user_id)
            if resolved:
                return resolved
        char = self._characters.get(display_name) if self._characters else None
        return char.name if char is not None else display_name

    def prompt_speaker_name(self, display_name: str) -> str:
        """The memoised resolution for ``display_name`` (written by :meth:`_on_utterance`, which
        still has the user id). Unknown speaker → the display name, unchanged."""
        return self._speaker_names.get(display_name) or self.character_name_for(None, display_name)

    def _seed_speaker_identities(self, voice_channel) -> None:
        """Map every human member of the joined voice channel from their Discord user id to their
        character name (``!join``). Bots and Bot A are skipped, an unmapped member simply gets no
        entry — :meth:`character_name_for` then falls back to the display name."""
        self._char_by_user = {}
        self._speaker_names = {}
        for member in getattr(voice_channel, "members", []) or []:
            if getattr(member, "bot", False) or (
                self._bot_a_user_id and member.id == self._bot_a_user_id
            ):
                continue
            char = self._characters.get(member.display_name) if self._characters else None
            if char is not None:
                self._char_by_user[member.id] = char.name
        if self._char_by_user:
            log.info("identity: %d player(s) resolved to character names by Discord id",
                     len(self._char_by_user))

    def session_file(self, channel_id: int, stem: str, ext: str) -> Path:
        """One per-session artifact under ``data/sessions/<channel_id>/``, sandboxed by run mode
        (ADR 056). A debug-campaign run plays in the SAME channel as live play, so it writes
        ``<stem>.debug.<ext>`` beside the live file instead of into it — the live campaign's
        state, thread, recap and loose ends survive a test evening untouched, and the debug run
        starts from its own clean slate. Mirrors how the rotated archives already split
        (``history.<stamp>.debug.jsonl``, ADR 055); the mode comes from :attr:`is_debug_run`."""
        marker = ".debug" if self.is_debug_run else ""
        return _DATA_DIR / "sessions" / str(channel_id) / f"{stem}{marker}.{ext}"

    def _state_path(self, channel_id: int):
        """Where this channel's mutable world state lives (data/sessions/<id>/state.json)."""
        return self.session_file(channel_id, "state", "json")

    def _history_path(self, channel_id: int):
        """Where this channel's append-only conversation autosave lives (D41)."""
        return self.session_file(channel_id, "history", "jsonl")

    def _chekhov_path(self, channel_id: int):
        """Where this channel's Chekhov list lives (ADR 050), beside the other session files."""
        return self.session_file(channel_id, "chekhov", "json")

    # --- campaign memory: session-transcript ingest (ADR 054) -----------------------------------

    @property
    def is_debug_run(self) -> bool:
        """True iff a ``testplan.json`` sits next to the loaded adventure (ADR 055) — a pure
        path check, deliberately independent of the DM_DEBUG_OVERLAY kill-switch (the overlay
        may be off while the debug campaign is still being played). Only the file's *presence*
        is used; its content never reaches any prompt or RAG path (ADR 052 invariant)."""
        return self._adventure_dir is not None and (self._adventure_dir / "testplan.json").is_file()

    def _session_ingest_source(self, channel_id: int) -> str | None:
        """The RAG source this channel's played sessions are ingested under, or ``None`` to skip
        ingest entirely (feature off, DM_SESSION_MEMORY=0). Debug-campaign runs (ADR 052/055)
        play in the SAME channel as live play, so channel isolation doesn't cover them: they
        route into the sandboxed ``session_debug_<channel_id>`` source instead — the live
        campaign's memory stays untouched, and the debug run still exercises the full
        ingest/retrieval path (gate G10)."""
        if not self._session_memory:
            return None
        if self._adventure_dir is not None and (self._adventure_dir / "testplan.json").is_file():
            return ingest_session.session_source(channel_id, debug=True)
        return ingest_session.session_source(channel_id)

    # ----- 🧪 Debug overlay (ADR 052) ---------------------------------------------------------

    async def update_debug_overlay(self) -> None:
        """(Re)render the 🧪 testplan overlay for the current scene (ADR 052) — edit-in-place
        (the clock-panel pattern), called by every scene-change path. Fully dormant without a
        loaded testplan; zero LLM calls, zero prompt bytes — the DM never learns a test run is
        happening. Best-effort: a send/edit failure logs, never breaks a turn."""
        plan = self._testplan
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

    # ----- Player panel (PRD stories 14-17) ---------------------------------------------------

    def _panel_text(self) -> str:
        """Render the current player panel, or ``""`` when there is nothing to render.

        The gate labels come from the 🧪 sidecar and are read HERE, in the runtime — the panel
        renderer never learns the sidecar exists (the ADR-052 LLM-invisibility invariant is
        structural and pinned by ``tests/test_debug_overlay.py``)."""
        cid = self._active_vc_id
        state = self._state.get(cid) if cid is not None else None
        if state is None:
            return ""
        scene = self._adventure.get_scene(state.scene_id) if self._adventure is not None else None
        plan = self._testplan
        entry = plan.entry_for(state.scene_id) if plan is not None else None
        order = self._turn_order.get(cid, [])
        active = order[self._turn_index.get(cid, 0) % len(order)] if order else ""
        text = render_player_panel_de(
            state, scene, entry.gates if entry is not None else (), active_player=active
        )
        if text and self.clocks_enabled and state.clocks:  # the pressure panel's clocks (D133)
            text = f"{text}\n{clocks_panel_de(state.clocks)}"
        return text

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
        # Scope the *presence* check to the campaign's named NPCs (D107). Registering a scene's
        # NPCs on entry is what finally gives this guard data — but the NPC-memory extractor also
        # registers whatever name it reads out of a transcript, so without this scoping one
        # invented extra ("Kaads Laufbursche") would become a permanent registered NPC and cost a
        # regeneration every time the DM let a bystander speak in another scene.
        named = self._adventure.npc_names() if self._adventure is not None else None
        return lambda text: consistency_mod.check(text, state, scene, named_only=named)

    def replay_note(self, channel, key: str, value) -> None:
        """Record one replay-journal fact for the turn in flight (ADR 046) — the delivery
        pipeline notes the pre-marker world state + scene/flag verdicts, the dice cog notes the
        router verdict. Drained into the turn's autosave record by :meth:`take_replay_notes`."""
        if not self._autosave:
            return
        self._replay_notes.setdefault(self._brain_channel(channel), {})[key] = value

    def take_replay_notes(self, channel) -> dict:
        """Return and clear the turn's replay notes (ADR 046) — called by the autosave."""
        if not self._replay_notes:
            return {}
        return self._replay_notes.pop(self._brain_channel(channel), {})
