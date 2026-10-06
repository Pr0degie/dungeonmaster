"""Boot-time checks for the LLM backends: Ollama reachable + model pulled, and (when
``DM_LLM_BACKEND=claude``) the Claude CLI found, logged in and not about to bill an API key.

Mirrors ``voice/preflight.py`` and ``__main__._ensure_opus``: a loud, clear message at
startup beats a cryptic ``httpx.ConnectError`` mid-game (which is exactly what happens when
Ollama — its own Windows process — simply isn't running; see docs/conventions.md "LLM not answering?").

This only *checks* and warns. It deliberately does **not** start Ollama: the host may be
remote (the 5080 over Tailscale, ADR 002), and starting a local daemon is the launcher's job
(``start_dmbot.bat``), keeping "Ollama runs as its own process" intact.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


def _model_available(model: str, available: set[str]) -> bool:
    """Is ``model`` among the tags Ollama reports? Matches with or without the ``:latest``
    tag (``ollama list`` reports ``mistral-nemo:latest``; the config default is ``mistral-nemo``).
    A pure helper so the matching is unit-testable without a live daemon."""
    if model in available:
        return True
    base = {name.split(":", 1)[0] for name in available}
    return model.split(":", 1)[0] in base


def check_ollama(host: str, model: str, *, timeout: float = 5.0) -> bool:
    """Ping the Ollama host and verify the model is pulled. Returns True if all good.

    Never raises — a preflight must not break boot; on any problem it logs a clear,
    actionable message and returns False so the bot still starts (the turn will fail loudly
    later, but at least the operator saw the reason at startup)."""
    host = host.rstrip("/")
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — any failure means "not usable", report it
        log.error(
            "Ollama not reachable at %s (%s) — DM turns will fail. Start Ollama (the Windows "
            "app / `ollama serve`) and enable its autostart; if the host is remote, check the "
            "machine + Tailscale. See docs/conventions.md 'LLM not answering?'.",
            host, exc.__class__.__name__,
        )
        return False

    available = {m.get("name", "") for m in data.get("models", [])}
    if not _model_available(model, available):
        log.warning(
            "Ollama is up at %s but model '%s' is not pulled (have: %s) — DM turns will fail. "
            "Run `ollama pull %s`.",
            host, model, ", ".join(sorted(available)) or "none", model,
        )
        return False

    log.info("Ollama preflight OK — %s reachable, model '%s' available.", host, model)
    return True


def _find_claude_cli(cli_path: str) -> str | None:
    """The claude executable the backend will use, or ``None``. Mirrors the SDK's own search
    closely enough for a boot message: a configured path, else on Windows a native ``claude.exe``
    — on PATH or at the native installer's default location — and only then whatever ``claude``
    PATH offers. The native exe wins over npm's ``claude.cmd`` even when only the shim is on
    PATH (a terminal not reopened after installing): the SDK finds it there too, so reporting
    the shim would announce a fallback that does not happen."""
    if cli_path:
        return cli_path if Path(cli_path).is_file() else None
    if sys.platform == "win32":
        found = shutil.which("claude.exe")
        if found:
            return found
        default = Path.home() / ".local" / "bin" / "claude.exe"
        if default.is_file():
            return str(default)
    return shutil.which("claude")


async def _claude_ping(config, model: str, timeout: float) -> None:
    """One minimal call on ``model``, through the real client — so the ping exercises the same
    options (isolation, system-prompt file) every DM turn will use. Sent as a prose call on a
    client whose narration model is ``model``: a schema call would cost the aux tier a tool
    round trip just to say OK."""
    from .claude_client import ClaudeClient

    client = ClaudeClient(
        narration_model=model,
        aux_model=model,
        # The same optional Anthropic-side fallback the real client passes, so a value the CLI
        # rejects fails here and not on the first turn.
        fallback_model=getattr(config, "claude_model_fallback", "") or None,
        cli_path=config.claude_cli_path or None,
        allow_api_key=config.claude_allow_api_key,
        timeout=timeout,
    )
    try:
        await client.chat(
            "Antworte nur mit: OK", [{"role": "user", "content": "ping"}], options={"num_predict": 8}
        )
    finally:
        await client.aclose()


async def _claude_pings(config, timeout: float) -> list[tuple[str, str, BaseException | None]]:
    """Ping both tiers side by side → ``[(tier, model, failure or None), …]``. Both, because a
    mistyped ``CLAUDE_MODEL_NARRATION`` passes an aux-only ping and then fails the first turn of
    the evening. One ping when both tiers name the same model."""
    tiers = [("narration", config.claude_model_narration), ("aux", config.claude_model_aux)]
    models = list(dict.fromkeys(model for _, model in tiers))
    outcomes = await asyncio.gather(
        *(_claude_ping(config, model, timeout) for model in models), return_exceptions=True
    )
    failure = dict(zip(models, outcomes))
    return [(tier, model, failure[model]) for tier, model in tiers]


def check_claude(config, *, timeout: float = 60.0) -> bool:
    """Is the Claude backend usable? Returns True if all good. Never raises.

    Three checks, each with its own actionable message: (1) a set ``ANTHROPIC_API_KEY`` is refused
    unless ``CLAUDE_ALLOW_API_KEY=1`` (the CLI ranks the key above the subscription login and would
    bill the API silently); (2) the CLI is found and runs; (3) a minimal call completes on the
    narration model and on the aux model, i.e. the login works and both names are valid. The
    boot line names both outcomes. On False the bot still starts — the failover answers from Ollama, and this
    message is why. Call it before the bot's event loop starts (it runs its own for the ping).
    """
    if os.environ.get("ANTHROPIC_API_KEY", "").strip() and not config.claude_allow_api_key:
        log.error(
            "Claude backend refused: ANTHROPIC_API_KEY is set, and the claude CLI would bill the "
            "API instead of your subscription. Remove the variable from the environment / .env "
            "(or set CLAUDE_ALLOW_API_KEY=1 if that is really intended). DM turns fall back to Ollama."
        )
        return False

    cli = _find_claude_cli(config.claude_cli_path)
    if cli is None:
        log.error(
            "Claude CLI not found (%s) — DM turns fall back to Ollama. Install Claude Code natively "
            "on this machine and log in once; see SETUP.md 'Claude backend'.",
            f"CLAUDE_CLI_PATH={config.claude_cli_path}" if config.claude_cli_path else "not on PATH",
        )
        return False
    if sys.platform == "win32" and cli.lower().endswith((".cmd", ".bat")):
        log.error(
            "Claude CLI at %s is npm's batch shim — the Agent SDK refuses to run it on Windows. "
            "Install the native claude.exe (irm https://claude.ai/install.ps1 | iex) or point "
            "CLAUDE_CLI_PATH at one. DM turns fall back to Ollama.", cli,
        )
        return False
    try:
        version = subprocess.run(
            [cli, "--version"], capture_output=True, text=True, timeout=15, check=True
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001 — any failure means "not usable", report it
        log.error(
            "Claude CLI at %s does not run (%s) — DM turns fall back to Ollama.",
            cli, exc.__class__.__name__,
        )
        return False

    try:
        pings = asyncio.run(_claude_pings(config, timeout))
    except Exception as exc:  # noqa: BLE001 — a preflight must not break boot
        pings = [("narration", config.claude_model_narration, exc), ("aux", config.claude_model_aux, exc)]
    outcome = " · ".join(
        f"{tier} {model}: {'OK' if failure is None else 'FAILED'}" for tier, model, failure in pings
    )
    failures = [(tier, model, failure) for tier, model, failure in pings if failure is not None]
    if failures:
        causes = "; ".join(dict.fromkeys(f"{model}: {failure}" for _, model, failure in failures))
        if len(failures) == len(pings):
            hint = (
                "Check the login from the shell that starts the bot (`claude auth status`, "
                "`claude -p \"hi\"`)."
            )
        else:
            names = " / ".join(
                f"CLAUDE_MODEL_{tier.upper()}={model}" for tier, model, _ in failures
            )
            hint = f"The login works, so check the model name ({names})."
        log.error(
            "Claude preflight FAILED — %s (CLI %s). DM turns fall back to Ollama. %s Cause: %s",
            outcome, version, hint, causes,
        )
        return False

    log.info("Claude preflight OK — %s (CLI %s).", outcome, version)
    return True
