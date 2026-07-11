"""Runtime configuration for DMbot, loaded from the environment / ``.env``.

Single source of truth for the token and hosts. The Ollama host and the bridge address
are *never* hardcoded (CLAUDE.md / ADR 002) — they live here, sourced from the environment,
so switching them is a one-line change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved DMbot configuration. Build it with :meth:`load`."""

    discord_token: str
    ollama_host: str
    ollama_model: str
    ollama_num_ctx: int
    ollama_repeat_penalty: float
    ollama_repeat_last_n: int
    bridge_host: str
    bridge_port: int
    bridge_secret: str
    bot_a_user_id: int | None
    log_level: str
    log_to_file: bool
    transcript_file: bool
    whisper_model: str
    whisper_device: str
    whisper_compute: str
    dump_utterances: bool
    tts_engine: str
    tts_voice: str
    tts_speaker: str
    tts_device: str
    dm_num_predict: int
    dm_intro_num_predict: int
    dm_intro_temperature: float
    dm_max_lines: int
    system: str
    adventure: str
    default_party: str
    push_to_talk: bool
    pause_vad_while_speaking: bool
    button_autosend: bool
    roll_router: bool
    streaming: bool
    autosave: bool
    autorecap: bool
    scene_mode: str
    flag_confirm: bool
    scene_time_advance: int
    npc_memory: bool
    npc_memory_top_k: int
    consistency_guard: bool
    debug_overlay: bool
    debug_channel_id: int
    speech_mode: str
    speech_punct: str
    speech_prebuffer: int

    @classmethod
    def load(cls) -> "Config":
        """Read ``.env`` (if present) and the process environment. Real env vars win.

        Raises ``RuntimeError`` if DMbot's Discord token is missing — there is nothing
        useful to do without it.
        """
        load_dotenv()

        token = os.environ.get("DISCORD_TOKEN_DMBOT", "").strip()
        if not token:
            raise RuntimeError(
                "DISCORD_TOKEN_DMBOT is not set. Copy .env.example to .env and fill in "
                "DMbot's token (never commit .env)."
            )

        bot_a_raw = os.environ.get("BOT_A_USER_ID", "").strip()

        return cls(
            discord_token=token,
            ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip(),
            ollama_model=os.environ.get("OLLAMA_MODEL", "mistral-nemo").strip(),
            # LLM context window (Ollama num_ctx). High by default now that the bot runs on a
            # 16 GB 4080 — 8k silently truncated the system prompt (persona + adventure) mid-session.
            # Lower it if VRAM gets tight (XTTS + Whisper share the GPU).
            ollama_num_ctx=int(os.environ.get("OLLAMA_NUM_CTX", "24576")),
            # Anti-repetition sampling. nemo with no penalty (the old default) loops or drifts into
            # generic filler on a 12B model; a mild penalty curbs it before the post-hoc echo guard
            # has to. 1.1 is gentle — too high frays German fluency / blocks legitimate re-use of a
            # name. repeat_last_n is the look-back window. Tune by ear (1.0 = off).
            ollama_repeat_penalty=float(os.environ.get("DM_REPEAT_PENALTY", "1.1")),
            ollama_repeat_last_n=int(os.environ.get("DM_REPEAT_LAST_N", "256")),
            bridge_host=os.environ.get("DM_BRIDGE_HOST", "127.0.0.1").strip(),
            bridge_port=int(os.environ.get("DM_BRIDGE_PORT", "8765")),
            # Shared secret for the cross-machine bridge. Empty = localhost path mode (no secret).
            # Off-loopback the WAV is sent as bytes and this must match Bot A's DM_BRIDGE_SECRET.
            bridge_secret=os.environ.get("DM_BRIDGE_SECRET", "").strip(),
            bot_a_user_id=int(bot_a_raw) if bot_a_raw else None,
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
            # Debug file logs (logs/terminal.log = plain console mirror; logs/debug.log = fuller,
            # heartbeat-collapsed, pasteable). Off by default — the console stays lean and nothing is
            # written to disk; set DM_LOG_FILE=1 to record a run for later inspection.
            log_to_file=os.environ.get("DM_LOG_FILE", "").strip().lower()
            in ("1", "true", "yes", "on"),
            # Clean session transcript (logs/transcript.log) — just the conversation (player lines
            # + DM answers) with timestamps, including table talk. Separate from the debug log so it
            # stays pasteable as a record of what happened. On by default; DM_TRANSCRIPT_FILE=0 off.
            transcript_file=os.environ.get("DM_TRANSCRIPT_FILE", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # STT (Phase 4). Default to medium (GPU float16) — it clearly out-transcribed
            # small in live German testing and still fits next to Ollama on the 4070. Drop to
            # small via env if VRAM gets tight, or bump to large-v3 for max accuracy.
            whisper_model=os.environ.get("WHISPER_MODEL", "medium").strip(),
            whisper_device=os.environ.get("WHISPER_DEVICE", "cuda").strip(),
            whisper_compute=os.environ.get("WHISPER_COMPUTE", "float16").strip(),
            # Debug aid only: dump each utterance as a WAV to the OS temp dir. Off by default
            # — it clutters the disk; turn on (DM_DUMP_UTTERANCES=1) to inspect a clip.
            dump_utterances=os.environ.get("DM_DUMP_UTTERANCES", "").strip().lower()
            in ("1", "true", "yes", "on"),
            # TTS backend: "xtts" (Coqui XTTS v2, ~58 speakers + cloning — the default, the voice
            # we actually want) or "piper" (fast, fixed voice — the lean fallback if XTTS won't
            # load). torch is a hard dep either way, and XTTS degrades to CPU rather than crashing
            # (tts/xtts.py), so it's a safe default. Phase 6 / ADR 008.
            tts_engine=os.environ.get("TTS_ENGINE", "xtts").strip().lower(),
            # Piper voice .onnx; empty → the wrapper's default (de_DE-thorsten-medium).
            tts_voice=os.environ.get("PIPER_VOICE", "").strip(),
            # XTTS built-in speaker name (see voices/samples/_speakers.txt); empty → default.
            tts_speaker=os.environ.get("TTS_SPEAKER", "").strip(),
            # XTTS device: "cpu" (safe, slower) or "cuda" (fast, needs free VRAM).
            tts_device=os.environ.get("TTS_DEVICE", "cpu").strip(),
            # Hard cap on a DM turn's length (Ollama num_predict, ~tokens). The persona asks for
            # 2–4 sentences; this is the deterministic ceiling against monologues. Back to 220
            # (D43): the 160 squeeze (ADR 016) predates streaming — first audio now plays after the
            # first sentence regardless of turn length, and the praised sessions ran at 220. The
            # speaker-label stops stay as the backstop against scripted-party runaways. The
            # orchestrator trims a capped turn to its last full sentence. Tune by ear.
            dm_num_predict=int(os.environ.get("DM_NUM_PREDICT", "220")),
            # Length cap for the one-time !intro opening monologue (ADR 031). The intro establishes
            # place + mission + how they got here AND gives each player character a personal beat —
            # impossible inside the normal 2–4-sentence cap, so it runs on its own, larger budget.
            # One-off command (not a per-turn cost), so a generous default is safe; tune by ear.
            dm_intro_num_predict=int(os.environ.get("DM_INTRO_NUM_PREDICT", "800")),
            # Sampling temperature for the !intro opening monologue only (D83). The opening turns
            # otherwise run at the model default (~0.8). 0.5 (D83) steadied instruction-following but
            # read flat/formulaic; with the meta-open + quote-wrap now stripped deterministically (D84),
            # the higher-temp downside is caught, so the default is raised to 0.7 for the richer,
            # atmospheric weaving the table liked. Tune by ear: toward 0.8 = more flair, 0.3 = flatter.
            dm_intro_temperature=float(os.environ.get("DM_INTRO_TEMPERATURE", "0.7")),
            # Cap on how many buffered player lines a !dm turn sends. Continuous transcription
            # (no wake word) piles up table talk + jokes between turns; sending all of it drowns
            # the real action, so keep only the most recent N. 0 = unbounded. Lower = snappier
            # focus on the latest intent, higher = more table context per turn.
            dm_max_lines=int(os.environ.get("DM_MAX_LINES", "8")),
            # Active system profile (Phase 8): which data/systems/<name>.json the rules engine
            # applies. IM is the first hand-written profile; other systems are other profiles.
            system=os.environ.get("DM_SYSTEM", "imperium_maledictum").strip(),
            # Active adventure compendium (Phase 10a, ADR 019): which data/adventures/<name>/
            # scene cards + NPC statblocks the DM runs. Empty = no adventure (pre-10a behaviour).
            adventure=os.environ.get("DM_ADVENTURE", "").strip(),
            # Default party (D82): the session sheet loaded for a voice channel that has no own
            # data/sessions/<id>/characters.json — names a data/sessions/<name>/ whose characters.json
            # is used as the fallback. Defaults to the committed "_default" party, so a teammate's
            # clone AND any new/other voice channel load the real party instead of the generic
            # _example one (the party is no longer bound to one channel id). Empty → _example.
            default_party=os.environ.get("DM_DEFAULT_PARTY", "_default").strip(),
            # Push-to-talk: the whole table is always transcribed + logged, but only speech said
            # while the Discord mic button is engaged is routed to the DM (tap before talking to
            # the DM, tap to stop). Keeps the full transcript record while letting the table pick
            # what the DM hears. On by default; DM_PUSH_TO_TALK=0 routes everything to the DM.
            push_to_talk=os.environ.get("DM_PUSH_TO_TALK", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # Layer-2 feedback pause: pause the VAD while Bot A speaks. OFF by default so the table
            # keeps being transcribed during the DM's narration — layer 1 (the Bot-A user-ID filter)
            # still stops the DM transcribing its own voice. Set DM_PAUSE_VAD_WHILE_SPEAKING=1 to
            # restore the pause (e.g. if mic-to-speaker bleed becomes a problem).
            pause_vad_while_speaking=os.environ.get("DM_PAUSE_VAD_WHILE_SPEAKING", "0").strip().lower()
            in ("1", "true", "yes", "on"),
            # Releasing the mic button auto-runs the DM turn (no separate !dm). On by default; the
            # turn first waits for the just-said utterances to transcribe. DM_BUTTON_AUTOSEND=0 off.
            button_autosend=os.environ.get("DM_BUTTON_AUTOSEND", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # Roll-detection router (ADR 014): after the narration turn, a separate constrained-JSON
            # call classifies the player's action → which test (skill + difficulty) and posts the
            # dice button — far more reliable than the model's inline <<TEST>> marker, which stays as
            # a fallback. ON by default (validated live, 2026-06-08); DM_ROLL_ROUTER=0 disables it.
            roll_router=os.environ.get("DM_ROLL_ROUTER", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # Streaming pipeline (ADR 017): stream the LLM answer and speak it sentence-by-sentence,
            # so the first audio plays while the rest is still generating (time-to-first-audio drops
            # from "whole generation + whole synthesis" to "first sentence"). ON by default;
            # DM_STREAMING=0 = the byte-identical batch path (one WAV per turn). Needs a TTS backend.
            streaming=os.environ.get("DM_STREAMING", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # Per-turn conversation autosave (D41): append every completed turn to
            # data/sessions/<id>/history.jsonl so a crash doesn't lose the evening's thread; restored
            # on !join, rotated on !leave. ON by default; DM_AUTOSAVE=0 disables it.
            autosave=os.environ.get("DM_AUTOSAVE", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # Rolling auto-recap / context handoff (D56): when a turn's prompt nears the num_ctx cap
            # (the early signal before Ollama truncates the prompt HEAD — the persona + adventure),
            # auto-summarise the running history into a cumulative recap, persist it like !wrap up,
            # and clear the in-memory history so the next prompt is persona + adventure + recap +
            # state + empty history — safely under budget, persona never truncated. Runs off the hot
            # path (after the turn is spoken). ON by default; DM_AUTORECAP=0 disables it (falls back
            # to the bare context-budget warning).
            autorecap=os.environ.get("DM_AUTORECAP", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # Auto scene transitions (ADR 026): when the DM emits an <<ORT id>> marker, the cog posts
            # a confirm button and, on click, moves the scene pointer. "verbunden" (default) only
            # accepts the current scene's leads_to neighbours; "frei" accepts any known scene id.
            # Switchable live via !ortmodus. An unknown value falls back to "verbunden".
            scene_mode=(os.environ.get("DM_SCENE_MODE", "verbunden").strip().lower()
                        if os.environ.get("DM_SCENE_MODE", "verbunden").strip().lower()
                        in ("verbunden", "frei") else "verbunden"),
            # Stateful scene cards (ADR 043): when the DM emits <<ERLEDIGT id>>, post a confirm
            # button before the element flag is applied (default). DM_FLAG_CONFIRM=0 auto-applies
            # valid flags — lower stakes than the scene pointer, they only change the card render.
            flag_confirm=os.environ.get("DM_FLAG_CONFIRM", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # In-game time (ADR 048): default advance in minutes on a real scene change —
            # travel/regrouping is about half an hour; bigger jumps ride the <<ZEIT>> marker
            # or !zeit. 0 disables the automatic advance.
            scene_time_advance=max(0, int(os.environ.get("DM_SCENE_TIME_ADVANCE", "30") or "30")),
            # NPC memory (ADR 044): at scene change / wrap-up an extra LLM call extracts what the
            # scene's NPCs would remember (incl. player lies); code clamps attitude drift and
            # spreads faction gossip. ON by default; DM_NPC_MEMORY=0 disables the subsystem.
            npc_memory=os.environ.get("DM_NPC_MEMORY", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # How many memories per scene NPC ride in the prompt (ranked importance → recency;
            # revealed lies are always included on top). Floor 1.
            npc_memory_top_k=max(1, int(os.environ.get("DM_NPC_MEMORY_TOP_K", "6") or "6")),
            # Consistency guard (ADR 045): deterministic pre-delivery check of the DM answer
            # against the world state (dead/absent NPC speaking) with max ONE regenerate,
            # strictly fail-open. ON by default; DM_CONSISTENCY_GUARD=0 disables it.
            consistency_guard=os.environ.get("DM_CONSISTENCY_GUARD", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # 🧪 Debug overlay (ADR 052): when the loaded adventure ships a testplan.json sidecar,
            # every scene change posts/edits one compact OOC line (gates under test + hint) —
            # deterministic Discord output only, zero LLM calls, zero prompt bytes. Dormant
            # without the sidecar; DM_DEBUG_OVERLAY=0 disables it entirely.
            debug_overlay=os.environ.get("DM_DEBUG_OVERLAY", "1").strip().lower()
            in ("1", "true", "yes", "on"),
            # Optional channel id for the overlay, to keep OOC test chatter out of the game
            # channel; 0/unset = the game channel. An unresolvable id logs once and falls back.
            debug_channel_id=int(os.environ.get("DM_DEBUG_CHANNEL", "0") or "0"),
            # Spoken-delivery mode (ADR 033), applied to EVERY turn, also switchable live via
            # !sprechmodus. Two orthogonal axes:
            #  - DM_SPEECH_MODE: "stream" (sentence-by-sentence, fast start, small gaps) |
            #    "puffer" (stream, but pre-synthesise DM_SPEECH_PREBUFFER sentences before the first
            #    plays so the buffer cushions CPU synth falling behind → fewer/later gaps, modest
            #    start delay) | "nahtlos" (synth all → one continuous track → one bridge call;
            #    gapless but waits for the whole turn to synthesise — only snappy on a GPU, ADR 002).
            #  - DM_SPEECH_PUNCT: "flach" (strip ALL punctuation — no XTTS babble, flatter) vs
            #    "intoniert" (keep .,!?;:- via the wrapper's normalize_for_tts — sentence/question
            #    intonation, but XTTS may babble on punctuation, D55).
            # Default stream+flach: consistent, gibberish-free, practical on CPU. Unknown → default.
            speech_mode=(os.environ.get("DM_SPEECH_MODE", "stream").strip().lower()
                         if os.environ.get("DM_SPEECH_MODE", "stream").strip().lower()
                         in ("stream", "puffer", "nahtlos") else "stream"),
            speech_punct=(os.environ.get("DM_SPEECH_PUNCT", "flach").strip().lower()
                          if os.environ.get("DM_SPEECH_PUNCT", "flach").strip().lower()
                          in ("flach", "intoniert") else "flach"),
            # Head-start depth for "puffer" mode: how many sentences to synthesise before the first
            # plays. Higher = smoother (gaps later) but a longer start delay. Floor 1 (== "stream").
            speech_prebuffer=max(1, int(os.environ.get("DM_SPEECH_PREBUFFER", "3") or "3")),
        )
