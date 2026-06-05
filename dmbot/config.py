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
    bridge_host: str
    bridge_port: int
    bridge_secret: str
    bot_a_user_id: int | None
    log_level: str
    log_to_file: bool
    whisper_model: str
    whisper_device: str
    whisper_compute: str
    dump_utterances: bool
    tts_engine: str
    tts_voice: str
    tts_speaker: str
    tts_device: str
    dm_num_predict: int

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
            bridge_host=os.environ.get("DM_BRIDGE_HOST", "127.0.0.1").strip(),
            bridge_port=int(os.environ.get("DM_BRIDGE_PORT", "8765")),
            # Shared secret for the cross-machine bridge. Empty = localhost path mode (no secret).
            # Off-loopback the WAV is sent as bytes and this must match Bot A's DM_BRIDGE_SECRET.
            bridge_secret=os.environ.get("DM_BRIDGE_SECRET", "").strip(),
            bot_a_user_id=int(bot_a_raw) if bot_a_raw else None,
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
            # Full-detail file log (logs/dmbot.log). Off by default — the console stays lean and
            # nothing is written to disk; set DM_LOG_FILE=1 to record a run for later inspection.
            log_to_file=os.environ.get("DM_LOG_FILE", "").strip().lower()
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
            # Hard cap on a DM turn's length (Ollama num_predict, ~tokens). The persona already
            # asks for 2–5 sentences, but the model overruns into minute-long monologues; this is
            # the deterministic ceiling. ~220 ≈ a few spoken sentences. Tune by ear: lower = snappier
            # turns, higher = more room. The orchestrator trims a capped turn to its last full sentence.
            dm_num_predict=int(os.environ.get("DM_NUM_PREDICT", "220")),
        )
