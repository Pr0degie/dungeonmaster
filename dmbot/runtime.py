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
from dataclasses import dataclass

import discord

from .config import Config
from .voice.recv import VadSink
from .voice.preflight import check_static
from .stt import Transcriber
from .llm.client import OllamaClient
from .orchestrator import DMBrain
from .tts.piper import PiperTTS
from .tts.textsplit import split_for_discord
from .bridge import BridgeClient
from .rules import profile as profile_mod
from .rules.profile import ProfileError, SystemProfile
from .rules.characters import CharacterStore
from .memory.state import WorldState, world_state_summary_de
from .rag.adventure import Adventure, Scene
from .rag.retrieve import RulebookRetriever

# Repo data dir (data/systems is the profile root; sessions/ sits beside it).
_DATA_DIR = profile_mod.systems_dir().parent

log = logging.getLogger(__name__)

_SR_16K = 16_000

# Context-budget smoke signal: warn once a narration prompt fills more than this fraction of
# num_ctx. Above it, Ollama starts truncating the prompt *head* — which is the persona (the worst
# part to silently lose), since the system prompt leads. The grower is the 20-turn history + the
# recap + the state block, so the fix is to trim those, not raise the cap (KV-cache VRAM).
_CTX_WARN_FRACTION = 0.85

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
        # Per-turn conversation autosave (D41): append every completed turn to
        # data/sessions/<id>/history.jsonl so a crash doesn't lose the evening's thread; restored on
        # !join, rotated on !leave. World state already persists separately (ADR 015).
        self._autosave = config.autosave
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
        # Rules engine (Phase 8): load the active system profile (data/systems/<system>.json). A
        # missing/broken profile must not down the bot — log loudly and run rules-less (no dice).
        self._profile: SystemProfile | None = None
        try:
            self._profile = profile_mod.load(config.system)
            log.info("loaded system profile %r (%s, %s)", self._profile.name,
                     self._profile.dice, self._profile.resolution)
        except ProfileError:
            log.exception("no usable system profile %r — running without the dice engine", config.system)
        # Characters: start from the example party so !test/!roll work out of the box; !join prefers
        # a channel-specific data/sessions/<id>/characters.json if present. Engine rolls (RNG) here.
        self._characters, _ = self._load_characters(None)
        # Adventure compendium (Phase 10a, ADR 019): German scene cards + NPC statblocks under
        # data/adventures/<name>/. The scene pointer lives in WorldState.scene_id; the block is
        # injected via _persist_and_refresh. Missing/broken → run without (logged loudly).
        self._adventure: Adventure | None = None
        if config.adventure:
            self._adventure = Adventure.load(_DATA_DIR / "adventures" / config.adventure)
            if self._adventure is not None:
                log.info("loaded adventure %r (%d scenes, %d NPC statblocks)",
                         self._adventure.title or config.adventure,
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
        # The flag + panel handle live here (shared session state); the pause *control* (set_paused,
        # the animation/Esc tasks) lives in VoiceCog, and DMCog's streaming workers read _paused.
        self._paused = False
        self._pause_message: discord.Message | None = None
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
            OllamaClient(config.ollama_host, config.ollama_model, num_ctx=config.ollama_num_ctx),
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

    # ----- Channel / character / state plumbing --------------------------------------------------

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

    def _state_path(self, channel_id: int):
        """Where this channel's mutable world state lives (data/sessions/<id>/state.json)."""
        return _DATA_DIR / "sessions" / str(channel_id) / "state.json"

    def _history_path(self, channel_id: int):
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
        summary = world_state_summary_de(state)
        for block in (self._psyker_block(state), self._augmetic_block()):
            if block:
                summary = f"{summary}\n\n{block}" if summary else block
        self._brain.set_context(
            cid, recap=state.recap, state_summary=summary, adventure_block=adventure_block,
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
        adventure. The caller persists + refreshes the prompt."""
        if self._adventure is None:
            return None
        scene = self._adventure.get_scene(scene_id)
        if scene is None:
            return None
        state.scene_id = scene.id
        if scene.title_de:
            state.set_location(scene.title_de)  # keep the prose state block in sync
        return scene

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
