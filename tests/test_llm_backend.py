"""Backend selection (ADR 061): the config knobs, the client factory, ``check_claude`` and
``!backend``. Proves every knob is wired (lesson unwired-knobs-and-silent-fallbacks): the client
is built from the environment and asserted on. No subprocess, no network.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import types

import claude_agent_sdk as sdk
import pytest

from dmbot import config as config_mod
from dmbot.config import Config
from dmbot.llm import build_llm_client, preflight
from dmbot.llm.claude_client import ClaudeClient
from dmbot.llm.client import LLMBackendError, OllamaClient
from dmbot.llm.failover import FailoverClient
from dmbot.voice.dmcog import DMCog

_CLAUDE_ENV = (
    "DM_LLM_BACKEND", "CLAUDE_MODEL_NARRATION", "CLAUDE_MODEL_AUX", "CLAUDE_MODEL_FALLBACK",
    "CLAUDE_NUM_CTX", "CLAUDE_CLI_PATH", "CLAUDE_ALLOW_API_KEY", "DM_LLM_FAILOVER_COOLDOWN_S",
    "ANTHROPIC_API_KEY",
)


def _load(monkeypatch, **env) -> Config:
    """``Config.load()`` from exactly this environment (the developer's ``.env`` stays out)."""
    monkeypatch.setattr(config_mod, "load_dotenv", lambda: None)
    for name in _CLAUDE_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DISCORD_TOKEN_DMBOT", "token")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Config.load()


# ---- config -----------------------------------------------------------------------------------


def test_the_default_backend_is_ollama_with_the_documented_claude_defaults(monkeypatch):
    config = _load(monkeypatch)
    assert config.llm_backend == "ollama"
    assert (config.claude_model_narration, config.claude_model_aux) == ("opus", "haiku")
    assert config.claude_model_fallback == "" and config.claude_cli_path == ""
    assert config.claude_num_ctx == 24576 == config.ollama_num_ctx
    assert config.claude_allow_api_key is False
    assert config.llm_failover_cooldown_s == 600


def test_an_unknown_backend_is_a_boot_error_not_a_silent_default(monkeypatch):
    with pytest.raises(RuntimeError, match="DM_LLM_BACKEND"):
        _load(monkeypatch, DM_LLM_BACKEND="cluade")


def test_the_backend_name_is_case_and_space_tolerant(monkeypatch):
    assert _load(monkeypatch, DM_LLM_BACKEND=" Claude ").llm_backend == "claude"


# ---- factory ----------------------------------------------------------------------------------


def test_ollama_backend_builds_the_plain_ollama_client(monkeypatch):
    client = build_llm_client(_load(monkeypatch, OLLAMA_MODEL="mistral-nemo", OLLAMA_NUM_CTX="16384",
                                    DM_REPEAT_PENALTY="1.2", DM_REPEAT_LAST_N="128"))
    assert type(client) is OllamaClient  # not wrapped — the pre-round bot
    assert client.model == "mistral-nemo" and client._num_ctx == 16384
    assert client._repeat_penalty == 1.2 and client._repeat_last_n == 128
    asyncio.run(client.aclose())


def test_claude_backend_builds_the_failover_pair_from_every_knob(monkeypatch):
    client = build_llm_client(_load(
        monkeypatch,
        DM_LLM_BACKEND="claude",
        CLAUDE_MODEL_NARRATION="sonnet",
        CLAUDE_MODEL_AUX="haiku-x",
        CLAUDE_MODEL_FALLBACK="opus-old",
        CLAUDE_NUM_CTX="32000",
        CLAUDE_CLI_PATH="C:/tools/claude.exe",
        CLAUDE_ALLOW_API_KEY="1",
        DM_LLM_FAILOVER_COOLDOWN_S="45",
        OLLAMA_MODEL="nemo-local",
    ))
    assert isinstance(client, FailoverClient)
    claude, ollama = client._primary, client._fallback
    assert isinstance(claude, ClaudeClient) and type(ollama) is OllamaClient
    assert claude._narration_model == "sonnet" and claude._aux_model == "haiku-x"
    assert claude._fallback_model == "opus-old"
    assert claude._num_ctx == 32000
    assert claude._cli_path == "C:/tools/claude.exe"
    assert claude._allow_api_key is True
    assert client._cooldown_s == 45
    assert ollama.model == "nemo-local"
    status = client.status()
    assert (status.primary, status.fallback) == ("claude", "ollama")
    assert (status.primary_model, status.fallback_model) == ("sonnet", "nemo-local")
    asyncio.run(client.aclose())


def test_claude_backend_defaults_leave_the_optional_knobs_unset(monkeypatch):
    client = build_llm_client(_load(monkeypatch, DM_LLM_BACKEND="claude"))
    claude = client._primary
    assert claude._fallback_model is None and claude._cli_path is None
    assert claude._allow_api_key is False and claude._num_ctx == 24576
    asyncio.run(client.aclose())


# ---- check_claude -----------------------------------------------------------------------------


def _preflight_config(**kw):
    base = dict(claude_model_narration="opus", claude_model_aux="haiku", claude_cli_path="",
                claude_allow_api_key=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


class _Ping:
    """Fake ``claude_agent_sdk.query`` for the preflight pings. ``failure`` is raised for every
    model, or only for the ones in ``failing``."""

    def __init__(self, failure: BaseException | None = None, failing: tuple[str, ...] = ()) -> None:
        self.failure = failure
        self.failing = failing
        self.options: list = []

    def __call__(self, *, prompt, options=None, transport=None):
        self.options.append(options)
        return self._messages(options.model)

    async def _messages(self, model):
        if self.failure is not None and (not self.failing or model in self.failing):
            raise self.failure
        yield sdk.ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                                num_turns=1, session_id="s", result="OK", stop_reason="end_turn",
                                usage={"input_tokens": 5, "output_tokens": 1})


@pytest.fixture
def cli(monkeypatch):
    """A found, runnable CLI and a working ping; tests break one piece at a time."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(preflight, "_find_claude_cli", lambda path: "C:/bin/claude.exe")
    monkeypatch.setattr(
        preflight.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout="2.1.291 (Claude Code)\n"),
    )
    ping = _Ping()
    monkeypatch.setattr(sdk, "query", ping)
    return ping


def test_preflight_ok_pings_both_tiers_and_names_both_results(cli, caplog):
    with caplog.at_level(logging.INFO, logger="dmbot.llm.preflight"):
        assert preflight.check_claude(_preflight_config()) is True
    assert "Claude preflight OK — narration opus: OK · aux haiku: OK" in caplog.text
    assert sorted(o.model for o in cli.options) == ["haiku", "opus"]
    for options in cli.options:
        assert options.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "8"
        assert options.tools == [] and options.setting_sources == []
        assert options.output_format is None  # a prose ping, no tool round trip


def test_preflight_catches_a_wrong_narration_model_at_boot(cli, monkeypatch, caplog):
    """The aux ping alone would pass; the first turn of the evening would then fail over."""
    monkeypatch.setattr(sdk, "query", _Ping(sdk.ProcessError("model not found"), failing=("opux",)))
    with caplog.at_level(logging.ERROR, logger="dmbot.llm.preflight"):
        assert preflight.check_claude(_preflight_config(claude_model_narration="opux")) is False
    assert "narration opux: FAILED · aux haiku: OK" in caplog.text
    assert "CLAUDE_MODEL_NARRATION=opux" in caplog.text and "model not found" in caplog.text
    assert "claude auth status" not in caplog.text  # the login is fine — don't send him there


def test_preflight_pings_once_when_both_tiers_share_a_model(cli, caplog):
    with caplog.at_level(logging.INFO, logger="dmbot.llm.preflight"):
        assert preflight.check_claude(_preflight_config(claude_model_aux="opus")) is True
    assert [o.model for o in cli.options] == ["opus"]
    assert "narration opus: OK · aux opus: OK" in caplog.text


def test_preflight_refuses_a_set_api_key_before_anything_runs(cli, monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with caplog.at_level(logging.ERROR, logger="dmbot.llm.preflight"):
        assert preflight.check_claude(_preflight_config()) is False
    assert "ANTHROPIC_API_KEY" in caplog.text and cli.options == []


def test_preflight_accepts_an_api_key_when_explicitly_allowed(cli, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert preflight.check_claude(_preflight_config(claude_allow_api_key=True)) is True


def test_preflight_fails_when_the_cli_is_missing(cli, monkeypatch, caplog):
    monkeypatch.setattr(preflight, "_find_claude_cli", lambda path: None)
    with caplog.at_level(logging.ERROR, logger="dmbot.llm.preflight"):
        assert preflight.check_claude(_preflight_config()) is False
    assert "not found" in caplog.text and cli.options == []


def test_preflight_explains_the_npm_shim_on_windows(cli, monkeypatch, caplog):
    monkeypatch.setattr(preflight.sys, "platform", "win32")
    monkeypatch.setattr(preflight, "_find_claude_cli", lambda path: "C:/npm/claude.CMD")
    with caplog.at_level(logging.ERROR, logger="dmbot.llm.preflight"):
        assert preflight.check_claude(_preflight_config()) is False
    assert "batch shim" in caplog.text and cli.options == []


def test_preflight_fails_when_the_cli_does_not_run(cli, monkeypatch):
    def boom(*a, **kw):
        raise subprocess.CalledProcessError(1, "claude")

    monkeypatch.setattr(preflight.subprocess, "run", boom)
    assert preflight.check_claude(_preflight_config()) is False


def test_preflight_fails_when_the_ping_fails_and_never_raises(cli, monkeypatch, caplog):
    monkeypatch.setattr(sdk, "query", _Ping(sdk.CLIConnectionError("not logged in")))
    with caplog.at_level(logging.ERROR, logger="dmbot.llm.preflight"):
        assert preflight.check_claude(_preflight_config()) is False
    assert "not logged in" in caplog.text and "claude auth status" in caplog.text


def test_find_claude_cli_honours_the_configured_path(tmp_path, monkeypatch):
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"")
    assert preflight._find_claude_cli(str(exe)) == str(exe)
    assert preflight._find_claude_cli(str(tmp_path / "missing.exe")) is None
    monkeypatch.setattr(preflight.sys, "platform", "linux")
    monkeypatch.setattr(preflight.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert preflight._find_claude_cli("") == "/usr/bin/claude"


def test_find_claude_cli_prefers_the_native_exe_over_a_shim_on_path(tmp_path, monkeypatch):
    """Only npm's claude.cmd is on PATH, the native exe sits at the installer's default place
    (terminal not reopened). The SDK uses the exe — the boot message must not cry 'batch shim'."""
    native = tmp_path / ".local" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_bytes(b"")
    monkeypatch.setattr(preflight.sys, "platform", "win32")
    monkeypatch.setattr(preflight.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(preflight.shutil, "which",
                        lambda name: "C:/npm/claude.CMD" if name == "claude" else None)
    assert preflight._find_claude_cli("") == str(native)
    native.unlink()
    assert preflight._find_claude_cli("") == "C:/npm/claude.CMD"  # only the shim: say so


def test_the_ping_carries_the_configured_fallback_model(cli):
    assert preflight.check_claude(_preflight_config(claude_model_fallback="sonnet")) is True
    assert {o.fallback_model for o in cli.options} == {"sonnet"}


# ---- !backend + the table notice ------------------------------------------------------------------


class _Ctx:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str = "", **kwargs) -> None:
        self.sent.append(content)


class _Stub:
    """A minimal LLMClient side for the pair behind ``!backend``."""

    def __init__(self, model: str, fail: BaseException | None = None) -> None:
        self.model = model
        self.fail = fail
        self.last_stats = None

    async def chat(self, system, messages, *, options=None, format=None):
        if self.fail is not None:
            raise self.fail
        self.last_stats = {}
        return self.model

    async def aclose(self) -> None:
        pass


def _cog(client) -> DMCog:
    cog = object.__new__(DMCog)
    cog._rt = types.SimpleNamespace(_brain=types.SimpleNamespace(client=client), _text_channel=None)
    return cog


def _backend(cog: DMCog, arg: str = "") -> str:
    ctx = _Ctx()
    asyncio.run(DMCog.backend.callback(cog, ctx, arg=arg))
    assert len(ctx.sent) == 1
    return ctx.sent[0]


def test_backend_command_on_the_plain_ollama_path():
    text = _backend(_cog(_Stub("mistral-nemo")))
    assert "ollama" in text and "mistral-nemo" in text and "DM_LLM_BACKEND=ollama" in text


def test_backend_command_shows_the_pair_and_the_last_answer():
    pair = FailoverClient(_Stub("opus"), _Stub("mistral-nemo"))
    asyncio.run(pair.chat("s", []))
    text = _backend(_cog(pair))
    assert "auto" in text and "**claude** (opus)" in text and "**ollama** (mistral-nemo)" in text
    assert "kein Ausfall" in text and "Letzte Antwort von: claude" in text


def test_backend_command_shows_a_degraded_pair_with_its_cause():
    pair = FailoverClient(_Stub("opus", LLMBackendError("rate limit reached")), _Stub("mistral-nemo"))
    asyncio.run(pair.chat("s", []))
    text = _backend(_cog(pair))
    assert "ausgefallen" in text and "rate limit reached" in text
    assert "Letzte Antwort von: ollama" in text


def test_backend_command_forces_and_restores():
    pair = FailoverClient(_Stub("opus"), _Stub("mistral-nemo"))
    cog = _cog(pair)
    assert "fest auf ollama" in _backend(cog, "ollama")
    assert pair.status().mode == "fallback"
    assert "fest auf claude" in _backend(cog, " Claude ")
    assert pair.status().mode == "primary"
    assert "auto" in _backend(cog, "auto")
    assert pair.status().mode == "auto"


def test_backend_command_rejects_an_unknown_name_without_changing_anything():
    pair = FailoverClient(_Stub("opus"), _Stub("mistral-nemo"))
    text = _backend(_cog(pair), "gemini")
    assert text.startswith("❓") and pair.status().mode == "auto"


def test_the_table_gets_exactly_one_line_per_switch():
    """Story 7: a dead Claude posts ONE ⚠ line, not one per turn — and one ✅ on recovery."""
    primary = _Stub("opus", LLMBackendError("down"))
    now = [1_000_000.0]
    pair = FailoverClient(primary, _Stub("mistral-nemo"), clock=lambda: now[0])
    cog = _cog(pair)
    channel = _Ctx()
    cog._rt._text_channel = channel

    async def go():
        watcher = asyncio.create_task(cog._watch_backend(pair))
        for _ in range(3):  # three turns while Claude is down
            await pair.chat("s", [])
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)
        after_outage = list(channel.sent)
        now[0] += 600
        primary.fail = None
        await pair.chat("s", [])
        await asyncio.sleep(0.01)
        watcher.cancel()
        return after_outage

    after_outage = asyncio.run(go())
    assert len(after_outage) == 1 and after_outage[0].startswith("⚠")
    assert len(channel.sent) == 2 and channel.sent[1].startswith("✅")


def test_a_notice_before_any_channel_is_joined_is_logged_not_lost_silently(caplog):
    pair = FailoverClient(_Stub("opus", LLMBackendError("down")), _Stub("mistral-nemo"))
    cog = _cog(pair)

    async def go():
        watcher = asyncio.create_task(cog._watch_backend(pair))
        await pair.chat("s", [])
        await asyncio.sleep(0.01)
        watcher.cancel()

    with caplog.at_level(logging.WARNING, logger="dmbot.voice.dmcog"):
        asyncio.run(go())
    assert "no channel joined yet" in caplog.text
