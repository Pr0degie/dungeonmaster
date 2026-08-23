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
from .voice.preflight import check_static, check_tts_speaker
from .stt import Transcriber
from .llm import consistency as consistency_mod
from .llm.client import OllamaClient
from .llm.director_msgs import scene_rejected_note_de
from .llm.scene_router import SceneExit
from .orchestrator import DMBrain
from .tts.piper import PiperTTS
from .tts.textsplit import split_for_discord, strip_speech_punctuation
from .bridge import BridgeClient
from .rules import profile as profile_mod
from .rules.profile import ProfileError, SystemProfile
from .rules.characters import CharacterStore
from .rules.scene_flow import (
    MoveTrigger,
    apply_scene_undo,
    capture_scene_undo,
    is_scene_exhausted,
    next_scene_on_exhaustion,
    reachable_exits,
    resolve_exit,
)
from .discord_ui.panel import render_player_panel_de
from .discord_ui.undo import SceneUndoView
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
        # Identity (PRD "Identity"): resolve who this is NOW, while the Discord user id is still
        # in hand — the STT callback below only gets the display name back. One plain dict write;
        # the STT thread reads it (GIL-atomic, like _last_stt_ms).
        self._speaker_names[name] = self.character_name_for(user_id, name)
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
            # Under the CHARACTER's name, not the Discord one (PRD "Identity", findings A4/B4):
            # the prompt used to read "Sezgin: …", so the DM answered "Sezgin, ich kann leider
            # nicht …" and treated four players as one. The log line above keeps the Discord name
            # — that is the operator's record of who actually spoke.
            self._brain.add_player_line(self._active_vc_id, self.prompt_speaker_name(name), text)
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
        scene = self._adventure.get_scene(state.scene_id) if self._adventure is not None else None
        if self._adventure is not None:
            adventure_block = self._adventure.adventure_block_de(
                state.scene_id,
                resolved_ids=state.resolved_ids(state.scene_id),
                dead_npcs=[n.name for n in state.npcs if n.wounds <= 0],
                include_guidance=self._guidance_due(cid),
            )
        # Which registered NPCs are actually HERE (D107). Once scene NPCs are registered on entry
        # the roster keeps growing, and an unscoped "NSCs in der Szene" line would hand the model
        # the seneschal from scene one as present in scene four — the contradiction of 2026-08-22.
        summary = world_state_summary_de(
            state, present=scene.npcs_here if scene is not None else None
        )
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

    def _guidance_due(self, channel_id: int) -> bool:
        """Whether the current scene's standing GM guidance rides in the next prompt.

        ADR 019 put ``guidance_de`` in *every* turn's card. Live (2026-08-22, findings A5/B6) the
        model treated it as a standing order and made the seneschal say the deadline line in eight
        of ten answers — the guidance was also the only characterisation input it had. The loader
        now renders it as a one-off impulse and leaves the WHEN to the caller: first turn in a
        scene, then every ``DM_GUIDANCE_EVERY``-th turn. 1 = every turn (pre-D107), 0 = never."""
        if self._guidance_every <= 0:
            return False
        return self._scene_turns.get(channel_id, 0) % self._guidance_every == 0

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
        # Entering a scene registers its NPCs as present (PRD block 3, story 21) — the single
        # switch that finally feeds NPC memory (ADR 044), agendas (ADR 049) and the consistency
        # guard (ADR 045), none of which ever ran because state.npcs was always empty. Done here,
        # in the one deterministic pointer mover, so all four movers get it.
        self._register_scene_npcs(state, scene)
        if changed:
            self._journal_scene_event(state)
            turns = getattr(self, "_scene_turns", None)  # getattr: stub runtimes stay dormant
            cid = next((c for c, st in getattr(self, "_state", {}).items() if st is state), None)
            if turns is not None and cid is not None:
                turns[cid] = 0  # the guidance impulse fires again on the first turn here
        return scene

    def _register_scene_npcs(self, state: WorldState, scene: Scene | None) -> list[str]:
        """Register the scene card's NPCs in the world state as present, with their statblock
        values (ADR 044's ``!npc add`` shape). Returns the names newly added.

        Only *named campaign* NPCs are registered — the card's ``npcs_here``. Incidental figures
        the DM invents (a runner, a bystander) are never registered here, and the consistency
        guard's presence check is additionally scoped to :meth:`Adventure.npc_names` in
        :meth:`consistency_checker`, so an accidental registration by the NPC-memory extractor
        cannot turn the DM's extras into violations either (the trap named in the PRD).

        Idempotent: an already-registered NPC keeps its drifted attitude, wounds and memories —
        ``attitude=""`` on the update path means "don't touch". A name belonging to a player
        character is skipped."""
        # getattr: a partially-built state (tests) has no roster to register into — stay dormant.
        if self._adventure is None or scene is None or not hasattr(state, "add_or_update_npc"):
            return []
        players = {c.name.strip().lower() for c in getattr(state, "characters", [])}
        known = {n.name.strip().lower() for n in getattr(state, "npcs", [])}
        added: list[str] = []
        for raw in scene.npcs_here:
            name = raw.strip()
            key = name.lower()
            if not name or key in players:
                continue
            block = self._adventure.npc(name)
            state.add_or_update_npc(
                name,
                wounds=block.wounds if block and key not in known else None,
                toughness_bonus=block.toughness_bonus if block else 0,
                armour=block.armour if block else 0,
                attitude="" if key in known else "neutral",
                faction=block.faction if block else "",
                goal=block.goal_de if block else "",
            )
            if key not in known:
                added.append(name)
        if added:
            log.info("👥 Szene '%s': %s als anwesend registriert", scene.id, ", ".join(added))
        return added

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
        debug = self.is_debug_run  # captured now — the scan sees only this mode's archives

        def _scan_and_ingest() -> None:
            pending = ingest_session.pending_files(session_dir, db_path=db_path, debug=debug)
            if pending:
                # gate-G10 evidence: the catch-up half of the ingest story is greppable too
                log.info("🗂 session memory: catch-up — %d rotated journal(s) pending",
                         len(pending))
            for path in pending:
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
        plan = getattr(self, "_testplan", None)
        entry = plan.entry_for(state.scene_id) if plan is not None else None
        order = self._turn_order.get(cid, [])
        active = order[self._turn_index.get(cid, 0) % len(order)] if order else ""
        return render_player_panel_de(
            state, scene, entry.gates if entry is not None else (), active_player=active
        )

    async def update_player_panel(self, *, reanchor: bool = False) -> None:
        """(Re)render the player panel in the session's text channel.

        Edit-in-place by default (the clock-panel pattern, no spam); ``reanchor=True`` deletes and
        re-posts it so it sits at the BOTTOM again — story 17, the same treatment the mic button
        gets after every turn. On 2026-08-22 the only comparable message was posted once and
        scrolled away, because its single refresh trigger was a scene change that never came.
        Best-effort: a send/edit failure logs and never breaks a turn."""
        # getattr: a partially-built runtime (tests) stays dormant, like the 🧪 overlay above.
        if not getattr(self, "_player_panel_enabled", False) or self._text_channel is None:
            return
        content = self._panel_text()
        if not content:
            return
        if reanchor:
            await self.clear_panel("_player_panel")
        elif self._player_panel is not None:
            try:
                await self._player_panel.edit(content=content)
                return
            except discord.HTTPException:
                self._player_panel = None  # message gone — fall through and re-post
        try:
            self._player_panel = await self._text_channel.send(content)
        except discord.HTTPException:
            log.warning("could not post the player panel", exc_info=True)

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
        await self.update_player_panel()  # the panel shows the clock + the deadline (D107)
        return minutes

    async def advance_scene_time(self, channel) -> int:
        """The default time cost of a *real* scene change (ADR 048 #10 / ADR 059 #2, the larger of
        the two increments) — called by every move path after a successful move to a different
        scene. ``DM_SCENE_TIME_ADVANCE=0`` disables it. Returns the applied minutes."""
        return await self._advance_time(channel, self._scene_time_advance)

    async def advance_turn_time(self, channel) -> int:
        """The per-turn heartbeat of the in-game clock (ADR 059 #2).

        Small and unconditional: through the whole live run of 2026-08-22 the clock read "Tag 1,
        08:00, Morgen" while the fiction played the night before midnight, because time only moved
        when the model emitted a ``<<ZEIT>>`` marker and it emitted none in 22 turns. The marker
        keeps its job (deliberate jumps, ADR 059 #3) — it is now an accelerator on a clock that
        already runs. ``DM_TURN_TIME_ADVANCE=0`` disables it."""
        return await self._advance_time(channel, self._turn_time_advance)

    # ----- The post-turn boundary: scene, facts, clock (ADR 057/058/059) ---------------------

    async def close_turn(self, channel, answer: str) -> None:
        """Everything code decides once a turn has been narrated — the seam the whole D107 round
        hangs on. Called by the delivery pipeline concurrently with playback (like the dice
        button), so its latency is hidden behind the DM's own voice.

        In order: the clock ticks (ADR 059), the two classifiers run in ONE ``gather`` — one
        latency window for both, as ADR 058 requires — the fact verdict goes through the world
        state's validating writers, the scene verdict (or the model-free flag gate) moves the
        pointer, and the player panel is re-anchored at the bottom. Best-effort end to end: a
        failure here logs and never breaks a turn."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return
        try:
            self._scene_turns[cid] = self._scene_turns.get(cid, 0) + 1
            await self.advance_turn_time(channel)
            classified_from = state.scene_id     # snapshot: the classifier call takes seconds
            scene_verdict, fact_verdict = await self._classify_turn(channel, state, answer)
            self._apply_commitment(channel, state, fact_verdict)
            if scene_verdict is not None and state.scene_id != classified_from:
                # Someone moved the pointer while the classifier was thinking (``!ort``, the
                # ``<<ORT>>`` button, an undo). The verdict was built against the *old* scene's
                # exits, so it is stale — drop it silently rather than reject it loudly and tell
                # the model the group did NOT go where it just went
                # (docs/lessons/snapshot-state-at-event-time.md).
                log.info("🗺️ Szenen-Verdikt '%s' verworfen — der Zeiger stand bei der "
                         "Klassifikation auf '%s' und steht jetzt auf '%s'",
                         getattr(scene_verdict, "target_id", ""), classified_from, state.scene_id)
                scene_verdict = None
            await self._apply_scene_verdict(channel, state, scene_verdict)
            await self.update_player_panel(reanchor=True)
        except Exception:
            log.exception("post-turn boundary failed — the turn itself is unaffected")

    async def _classify_turn(self, channel, state: WorldState, answer: str):
        """Run the scene (ADR 057) and fact (ADR 058) classifiers on the same turn boundary.

        Both are optional layers and fail open: a switched-off block, a missing brain method (a
        stub in tests) or a degenerate verdict yields ``None`` and changes nothing. Returns
        ``(scene_verdict | None, fact_verdict | None)``."""
        scene = self._adventure.get_scene(state.scene_id) if self._adventure is not None else None
        jobs: list[tuple[str, object]] = []
        if self._scene_router and scene is not None:
            classify = getattr(self._brain, "classify_scene_move", None)
            exits = self._exit_labels(scene, state)
            if classify is not None and exits:
                jobs.append(("scene", classify(
                    turn_text=answer, exits=exits, current_title=scene.title_de,
                )))
        if self._fact_router:
            classify = getattr(self._brain, "classify_commitment", None)
            if classify is not None:
                givers = list(scene.npcs_here) if scene is not None else []
                jobs.append(("fact", classify(
                    answer_text=answer,
                    recipients=self._characters.character_names() if self._characters else [],
                    givers=givers,
                )))
        if not jobs:
            return None, None
        results = await asyncio.gather(*(coro for _, coro in jobs), return_exceptions=True)
        out: dict[str, object] = {}
        for (kind, _), result in zip(jobs, results):
            if isinstance(result, BaseException):
                log.exception("%s classifier raised — ignored (fail-open)", kind,
                              exc_info=result)
                continue
            out[kind] = result
        # Replay journal (ADR 046): the raw verdicts, exactly like the roll router's.
        for key, attr in (("scene_router", "last_scene_router"), ("facts", "last_facts")):
            note = getattr(self._brain, attr, None)
            if note is not None:
                self.replay_note(channel, key, note)
        return out.get("scene"), out.get("fact")

    def _exit_labels(self, scene: Scene | None, state: WorldState) -> dict[str, str]:
        """``{scene_id: title}`` for the exits reachable from ``scene`` right now (ADR 057 #6).

        The title is what lets the model map "zum Hafen" onto ``pier_neun``; a gated exit whose
        element isn't resolved yet is simply not offered."""
        if scene is None or self._adventure is None:
            return {}
        labels: dict[str, str] = {}
        for sid in reachable_exits(scene, state.resolved_ids(scene.id)):
            target = self._adventure.get_scene(sid)
            labels[sid] = target.title_de if target is not None else ""
        return labels

    def _apply_commitment(self, channel, state: WorldState, verdict) -> None:
        """Write a validated commitment into the world state (ADR 058 #2).

        Code decides what the verdict *means*: ``record_commitment`` re-validates the kind and
        the label and returns ``None`` for anything it won't accept, so a malformed verdict
        changes nothing. The write is logged because a prompt-resident wrong fact is worse than a
        forgotten right one and the operator must be able to see (and ``!fakt weg``) it."""
        commitment = getattr(verdict, "commitment", None)
        if commitment is None:
            return
        written = state.record_commitment(commitment.kind, **commitment.record_kwargs())
        if written is None:
            return
        self._persist_and_refresh(channel)
        log.info("📌 Fakt aufgenommen (%s): %s → %s%s", commitment.kind, commitment.text,
                 commitment.to or "Gruppe",
                 f" (von {commitment.by})" if commitment.by else "")

    async def _apply_scene_verdict(self, channel, state: WorldState, verdict) -> None:
        """Turn the classifier verdict — or, failing that, the flag gate — into a pointer move.

        The classifier wins when it saw an arrival: it read the narration, the gate only counts
        flags. The gate (ADR 057 #2) then covers the other failure the run showed, a room squeezed
        empty with nobody moving on, and only when the answer is unambiguous (exactly one open
        exit). Both proposals are re-checked by ``scene_flow.resolve_exit`` before anything is
        written, and a rejection is loud (ADR 057 #5)."""
        if self._adventure is None:
            return
        scene = self._adventure.get_scene(state.scene_id)
        resolved = state.resolved_ids(scene.id) if scene is not None else []
        target, trigger = "", None
        if verdict is not None and getattr(verdict, "moved", False):
            target, trigger = verdict.target_id, MoveTrigger.CLASSIFIER
        elif self._scene_flag_gate and is_scene_exhausted(scene, resolved):
            choice = next_scene_on_exhaustion(scene, resolved)
            if choice.auto_target:
                target, trigger = choice.auto_target, MoveTrigger.FLAG_GATE
                log.info("🔓 Szene '%s' ist ausgespielt — Flag-Zwang schiebt weiter nach '%s'",
                         scene.id if scene else "—", target)
            elif choice.candidates:
                log.info("🔓 Szene '%s' ist ausgespielt, aber %d Ausgänge offen — kein Automatik-"
                         "Wechsel", scene.id if scene else "—", len(choice.candidates))
        if not target:
            return
        await self.request_scene_move(channel, target, trigger=trigger)

    async def request_scene_move(self, channel, target_id: str, *, trigger=None) -> Scene | None:
        """Validate a proposed move and perform it, or report the rejection loudly.

        The single gate every automatic mover goes through (classifier, flag gate, and the demoted
        ``<<ORT>>`` marker). Returns the Scene moved to, or ``None``."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None or self._adventure is None:
            return None
        scene = self._adventure.get_scene(state.scene_id)
        verdict = resolve_exit(
            scene, target_id,
            resolved_ids=state.resolved_ids(scene.id) if scene is not None else [],
            known_scene_ids=[sid for _, sid, _ in self._adventure.scene_overview()],
        )
        self.replay_note(channel, "scene_move", {
            "requested": target_id,
            "trigger": getattr(trigger, "value", trigger),
            "accepted": verdict.permitted,
            "reason": getattr(verdict.reason, "value", verdict.reason),
        })
        if not verdict.permitted:
            await self.report_rejected_move(channel, verdict)
            return None
        return await self.move_scene(channel, verdict.target_id, trigger=trigger)

    async def report_rejected_move(self, channel, verdict) -> None:
        """Make a refused scene change loud (ADR 057 #5) — a director note for the next turn AND
        an operator-visible line, never the single ``log.info`` of 2026-08-22.

        Spoiler discipline decides where each half lands: the ``[Regie]`` note (model-facing) and
        the log carry the reachable exits and the element that would unlock a gated one, and the
        operator line goes to ``DM_DEBUG_CHANNEL`` *only*. Without one configured there is no
        channel line at all — a scene id like ``pier_neun`` in the game channel names a locked
        finale to the players, which is exactly what this docstring claims not to do."""
        cid = self._brain_channel(channel)
        labels = [SceneExit(sid, self._scene_title(sid)).label()
                  for sid in verdict.reachable_exits]
        note = scene_rejected_note_de(verdict.target_id, verdict.reason, labels)
        self._brain.add_gm_note(cid, note)
        log.warning("🚫 Szenenwechsel '%s' abgelehnt (%s)%s — erreichbar: %s; Regie-Hinweis für "
                    "den nächsten Zug eingereiht", verdict.target_id,
                    getattr(verdict.reason, "value", verdict.reason),
                    f", Bedingung '{verdict.required_element_id}' offen"
                    if verdict.required_element_id else "",
                    ", ".join(verdict.reachable_exits) or "—")
        target = self._operator_channel()
        if target is None:
            return          # no operator channel — log + [Regie] note are the whole delivery
        name = self._scene_title(verdict.target_id) or verdict.target_id
        try:
            await target.send(
                f"🚫 Szenenwechsel nach „{name}“ abgelehnt — die Gruppe bleibt, wo "
                f"sie ist. (Grund im Log; die Spielleitung bekommt einen Hinweis.)"
            )
        except discord.HTTPException:
            log.warning("could not post the rejected-move line", exc_info=True)

    def _scene_title(self, scene_id: str) -> str:
        scene = self._adventure.get_scene(scene_id) if self._adventure is not None else None
        return scene.title_de if scene is not None else ""

    async def move_scene(self, channel, scene_id: str, *, trigger=None,
                         announce: bool = True) -> Scene | None:
        """Move the scene pointer and do everything a *real* move entails, in one place.

        Deterministic pointer + NPC registration (``_set_scene``), persist + prompt refresh, NPC
        memory mining for the scene just left (ADR 044), the scene-change time cost (ADR 048 #10),
        the 🧪 overlay and the player panel — plus, when ``announce``, the channel line and the
        one-minute ↩ control of ADR 057 #4. The change happens FIRST and is undone on click: the
        evening proved that a confirmation nobody knows about is the same as no mechanism."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return None
        undo = capture_scene_undo(state, scene_id, trigger=trigger)
        old_scene = state.scene_id
        moved = self._set_scene(state, scene_id)
        if moved is None:
            return None
        self._persist_and_refresh(channel)
        log.info("scene → %s (%s) [%s]", moved.id, moved.title_de,
                 getattr(trigger, "value", trigger) or "auto")
        if old_scene and old_scene != moved.id:
            self.schedule_npc_memory_extraction(channel, old_scene)
            await self.advance_scene_time(channel)
        await self.update_debug_overlay()
        await self.update_player_panel()
        if announce:
            await self._announce_scene_change(channel, moved, undo)
        return moved

    async def _announce_scene_change(self, channel, scene: Scene, undo) -> None:
        """Say in the channel that the scene moved, with a ↩ control that stays live for about a
        minute (ADR 057 #4). ``DM_SCENE_UNDO_SECONDS=0`` posts the line without the button."""
        text = f"📖 Szene gewechselt: **{scene.title_de}** (Teil {scene.part})."
        view = None
        if self._scene_undo_seconds > 0:
            view = SceneUndoView(self._make_scene_undo(channel, undo),
                                 timeout=float(self._scene_undo_seconds))
        try:
            message = await self._send_with_retry(channel, text, view=view)
        except discord.HTTPException:
            log.warning("could not announce the scene change", exc_info=True)
            return
        if view is not None:
            view.message = message  # so the view can grey its button out when the minute is up

    def _make_scene_undo(self, channel, undo):
        """Build the ↩ callback for one scene change: restore pointer + in-game time, refresh the
        prompt and the panels, and edit the announcement. ``apply_scene_undo`` refuses (and writes
        nothing) when the pointer has moved on since — which also makes a second click a no-op."""
        async def _undo(interaction: discord.Interaction) -> None:
            cid = self._brain_channel(channel)
            state = self._state.get(cid)
            if state is None:
                return
            if not apply_scene_undo(undo, state):
                await interaction.edit_original_response(
                    content="Nicht mehr aktuell — die Szene ist inzwischen weitergezogen."
                )
                return
            self._persist_and_refresh(channel)
            self._scene_turns[cid] = 0
            log.info("scene ↩ zurückgenommen → %s (%s)", state.scene_id,
                     getattr(undo.trigger, "value", undo.trigger) or "auto")
            await self.update_debug_overlay()
            await self.update_player_panel()
            await self.update_clock_panel()
            scene = self._adventure.get_scene(state.scene_id) if self._adventure else None
            title = scene.title_de if scene is not None else state.scene_id
            await interaction.edit_original_response(
                content=f"↩ Szenenwechsel zurückgenommen — ihr seid weiter in **{title}**."
            )
        return _undo

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

    def _seed_adventure_state(self, state) -> None:
        """Seed what the adventure ships into a fresh world state: start time, deadlines and
        consequence clocks (ADR 059 #1), the scene's NPCs as present (PRD block 3) and the
        campaign objective as the mission quest (ADR 058 #3).

        All three are idempotent — ``seed_time_from_adventure`` latches ``time_seeded``,
        ``set_mission`` replaces rather than appends and NPC registration keeps existing values —
        so a re-join or a restart mid-session neither resets the clock nor duplicates a deadline.
        Every step is ``getattr``-guarded: a partially-built state (tests) simply skips it."""
        adv = self._adventure
        if adv is None:
            return
        start_time = getattr(adv, "start_time_de", "")
        deadlines = getattr(adv, "deadlines", []) or []
        clocks = getattr(adv, "clocks", []) or []
        seed_time = getattr(state, "seed_time_from_adventure", None)
        if seed_time is not None and (start_time or deadlines or clocks):
            seed_time(start_time=start_time or None, deadlines=deadlines, clocks=clocks)
        mission = getattr(adv, "mission", None) or {}
        set_mission = getattr(state, "set_mission", None)
        title = str(mission.get("title_de", "") or "").strip()
        if set_mission is not None and title:
            set_mission(title,
                        detail=str(mission.get("detail_de", "") or ""),
                        given_by=str(mission.get("given_by", "") or ""))
        if hasattr(state, "npcs") and getattr(state, "scene_id", ""):
            self._register_scene_npcs(state, adv.get_scene(state.scene_id))

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
        # Identity (PRD "Identity"): who is who, by Discord user id, before anything is buffered.
        self._seed_speaker_identities(voice_channel)
        # With the resolution real, the prompt no longer carries the display-name → character
        # mapping the model had to apply itself — every player line already arrives under its
        # character name. The party boundary half of the hint stays either way.
        self._brain.set_alias_hint(
            cid, self._characters.alias_hint_de(with_mapping=not self._char_by_user)
        )
        # All table names → cut-labels/stop sequences, so a puppeted "Seskin: …" script is truncated.
        self._brain.set_known_speakers(cid, self._characters.speaker_labels())
        self._turn_order[cid] = self._build_turn_order(voice_channel)
        self._turn_index[cid] = 0
        # Memory (Phase 9): load this channel's world state (or seed it from the sheet on first join),
        # then inject the stored recap + current state into the prompt so the DM picks up where it
        # left off — the "next session opens with a correct recap" half of the gate.
        self._state[cid] = self._load_or_seed_state(cid)
        # Adventure (Phase 10a): point a fresh session at the start scene; a loaded state keeps
        # its stored pointer (the plot position survives restarts like HP does) — unless that
        # pointer names a scene the loaded adventure doesn't have. That happened live (2026-08-15,
        # ADR 056): the stored pointer belonged to the previous campaign, every get_scene() came
        # back None, and the evening ran with no scene card and no 🧪 overlay (it only fires on a
        # scene change, which never came). A foreign pointer re-seeds to the start scene, loudly.
        if self._adventure is not None:
            stored = self._state[cid].scene_id
            if stored and self._adventure.get_scene(stored) is None:
                log.warning("scene pointer %r is unknown to adventure %r — re-seeding to the start "
                            "scene %r (stale pointer from another campaign?)",
                            stored, self._adventure.id, self._adventure.start_scene)
                self._state[cid].scene_id = ""
            if not self._state[cid].scene_id:
                self._state[cid].scene_id = self._adventure.start_scene
            # The campaign's own clock and its objective (ADR 059 #1 / ADR 058 #3), seeded from
            # the adventure file instead of typed at the table. Both are idempotent — a resumed
            # session keeps its time and its mission — so this may run on every !join.
            self._seed_adventure_state(self._state[cid])
        self._scene_turns[cid] = 0
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
