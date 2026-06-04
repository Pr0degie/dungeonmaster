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
        )
