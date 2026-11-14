"""LLM: Ollama client (host from OLLAMA_HOST, never hardcoded) + prompt building
(generic GM core -> campaign tone overlay -> recap -> JSON state -> RAG -> history). Phase 5.

:func:`build_llm_client` is the one place a backend is chosen (ADR 061)."""

from __future__ import annotations

import logging
from importlib import metadata

from .client import LLMClient, OllamaClient

log = logging.getLogger(__name__)


def _app_version() -> str:
    try:
        return metadata.version("cogitator")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def build_llm_client(config) -> LLMClient:
    """The LLM client for this bot, from ``config.llm_backend``.

    ``ollama`` → the ``OllamaClient`` alone, built exactly as before the seam existed.
    ``claude`` → ``FailoverClient(ClaudeClient, OllamaClient)``: Claude answers. What happens
    when it cannot is ``config.llm_on_failure``: ``pause`` (the game waits, nothing is sent to
    Ollama) or ``fallback`` (Ollama takes over loudly). The Claude modules are imported only on
    that branch, so the Ollama path never touches them (or the SDK).
    """
    ollama = OllamaClient(
        config.ollama_host,
        config.ollama_model,
        num_ctx=config.ollama_num_ctx,
        repeat_penalty=config.ollama_repeat_penalty,
        repeat_last_n=config.ollama_repeat_last_n,
    )
    if config.llm_backend != "claude":
        return ollama
    from .claude_client import ClaudeClient
    from .failover import FailoverClient

    claude = ClaudeClient(
        narration_model=config.claude_model_narration,
        aux_model=config.claude_model_aux,
        fallback_model=config.claude_model_fallback or None,
        num_ctx=config.claude_num_ctx,
        cli_path=config.claude_cli_path or None,
        allow_api_key=config.claude_allow_api_key,
        app_version=_app_version(),
    )
    # Said at boot, so the position the evening runs on is a fact in the log, not an assumption.
    if config.llm_on_failure == "pause":
        log.info("LLM backend: claude; when it fails the game pauses (DM_LLM_ON_FAILURE=pause, "
                 "first retry after %s s, own turn after a return within %s s).",
                 config.llm_pause_retry_s, config.llm_pause_auto_turn_s)
    else:
        log.info("LLM backend: claude; when it fails %s takes over for %s s "
                 "(DM_LLM_ON_FAILURE=fallback).", config.ollama_model, config.llm_failover_cooldown_s)
    return FailoverClient(
        claude, ollama,
        cooldown_s=config.llm_failover_cooldown_s,
        on_failure=config.llm_on_failure,
        pause_retry_s=config.llm_pause_retry_s,
        pause_auto_turn_s=config.llm_pause_auto_turn_s,
    )


def recap_cap(config, client):
    """The recap call's output-cap hook for this bot's backend (ADR 061, amendment 2026-11-13) —
    what ``DMBrain(recap_num_predict=…)`` takes.

    ``ollama`` → ``None``: the brain's own number applies, as it always has. ``claude`` → a
    function asked before each recap call. It answers the Claude client's larger number while the
    failover pair would try Claude (the same text costs Opus far more tokens, and a recap cut at
    the cap loses its newest events), and ``None`` while the pair is degraded or pinned to Ollama,
    so Nemo keeps its own cap. Chosen here, next to :func:`build_llm_client`, so no call site
    names a model. ``client`` is what :func:`build_llm_client` returned."""
    if config.llm_backend != "claude":
        return None
    from .claude_client import RECAP_OUTPUT_TOKENS

    return lambda: RECAP_OUTPUT_TOKENS if client.on_primary else None


def post_turn_combined(config, client):
    """The combined post-turn classifier hook (ADR 066, option B) — what
    ``DMBrain(combine_post_turn=…)`` takes.

    ``None`` on ``ollama`` and while ``DM_AUX_COMBINED`` is off: the scene, fact and presence
    classifiers stay three separate calls, as they always were. On ``claude`` with the flag on, a
    function asked before each turn's classification: ``True`` while the failover pair would try
    Claude, so Haiku gets one call instead of three; ``False`` while the pair is degraded, paused
    or pinned to Ollama, so Nemo keeps the separate calls it has been answering. Same pattern and
    same known gap as :func:`recap_cap`: the one call during which Claude fails reaches the
    fallback as it was issued — combined — and a malformed answer from there falls back to the
    separate calls. ``client`` is what :func:`build_llm_client` returned."""
    if config.llm_backend != "claude" or not getattr(config, "aux_combined", False):
        return None
    return lambda: bool(client.on_primary)
