"""Build the DM system prompt from the layered persona files (Phase 5).

Per ADR 005 the persona is **layered**: a generic GM core (`prompts/dm_core_de.md`) plus a
per-campaign tone/setting overlay (`prompts/campaign_tone_de.md`). The core is system- and
setting-agnostic; swapping campaigns swaps only the overlay (and later the system profile).

Full prompt order (CLAUDE.md) is: GM core → campaign tone → recap → JSON state → RAG hits →
recent history. Phase 5 wires the first two (the system prompt) and the history; recap/state/
RAG join in later phases. Game content stays German; this code/docs stay English.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
_CORE = _PROMPTS_DIR / "dm_core_de.md"
_OVERLAY = _PROMPTS_DIR / "campaign_tone_de.md"


def load_system_prompt(
    core_path: Path = _CORE, overlay_path: Path = _OVERLAY
) -> str:
    """Concatenate the generic GM core and the active campaign tone overlay into one
    system prompt. Read fresh each call so editing the prompt files takes effect on the next
    DM turn without restarting the bot.
    """
    core = core_path.read_text(encoding="utf-8").strip()
    overlay = overlay_path.read_text(encoding="utf-8").strip()
    return f"{core}\n\n--- Kampagne: Ton & Setting ---\n\n{overlay}"
