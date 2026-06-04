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
    bridge_host: str
    bridge_port: int
    bot_a_user_id: int | None
    log_level: str
    whisper_model: str
    whisper_device: str
    whisper_compute: str
    dump_utterances: bool

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
            bridge_host=os.environ.get("DM_BRIDGE_HOST", "127.0.0.1").strip(),
            bridge_port=int(os.environ.get("DM_BRIDGE_PORT", "8765")),
            bot_a_user_id=int(bot_a_raw) if bot_a_raw else None,
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
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
        )
