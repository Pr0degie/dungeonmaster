"""ClaudeClient (ADR 061) against a fake SDK — real SDK dataclasses, never a subprocess.

``claude_agent_sdk.query`` is replaced by a scripted async generator, so every test pins what the
client does with the SDK's real message types. One test at the end drives the *real* ``query()``
over a fake transport, to pin the SDK behaviour the early-close path relies on.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import claude_agent_sdk as sdk
import pytest

from dmbot.llm.claude_client import ClaudeClient, _prompt, render_transcript
from dmbot.llm.client import LLMBackendError

_USER = [{"role": "user", "content": "Timo: Ich öffne die Tür."}]
_SCHEMA = {"type": "object", "properties": {"probe": {"type": "string"}}, "required": ["probe"]}


# ---- fake SDK ---------------------------------------------------------------------------------


class _FakeQuery:
    """Stands in for ``claude_agent_sdk.query``: yields the script, records what it was given."""

    def __init__(self, script):
        self.script = list(script)
        self.options: list[sdk.ClaudeAgentOptions] = []
        self.prompts: list[str] = []
        self.systems: list[str] = []
        self.system_paths: list[Path] = []
        self.cwd_listing: list[list[str]] = []
        self.yielded = 0
        self.closed = 0

    def __call__(self, *, prompt, options=None, transport=None):
        self.prompts.append(prompt)
        self.options.append(options)
        path = Path(options.system_prompt["path"])
        self.system_paths.append(path)
        self.systems.append(path.read_text(encoding="utf-8"))
        self.cwd_listing.append([p.name for p in Path(options.cwd).iterdir()])
        return self._messages()

    async def _messages(self):
        try:
            for item in self.script:
                if isinstance(item, BaseException):
                    raise item
                if callable(item):
                    await item()
                    continue
                self.yielded += 1
                yield item
        finally:
            self.closed += 1


@pytest.fixture
def fake(monkeypatch):
    def install(*script) -> _FakeQuery:
        query = _FakeQuery(script)
        monkeypatch.setattr(sdk, "query", query)
        return query

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return install


@pytest.fixture
def client():
    made = ClaudeClient(narration_model="opus", aux_model="haiku", app_version="1.2.3")
    yield made
    asyncio.run(made.aclose())


def _event(payload: dict) -> sdk.StreamEvent:
    return sdk.StreamEvent(uuid="u", session_id="s", event=payload)


def _delta(text: str) -> sdk.StreamEvent:
    return _event({"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


def _start(**usage) -> sdk.StreamEvent:
    return _event({"type": "message_start", "message": {"usage": usage}})


def _stop(reason: str, output_tokens: int) -> sdk.StreamEvent:
    return _event({
        "type": "message_delta",
        "delta": {"stop_reason": reason},
        "usage": {"output_tokens": output_tokens},
    })


def _assistant(*blocks, error=None) -> sdk.AssistantMessage:
    return sdk.AssistantMessage(content=list(blocks), model="claude-x", error=error)


def _result(**kw) -> sdk.ResultMessage:
    base = dict(subtype="success", duration_ms=900, duration_api_ms=700, is_error=False,
                num_turns=1, session_id="s", stop_reason="end_turn",
                usage={"input_tokens": 100, "output_tokens": 20})
    base.update(kw)
    return sdk.ResultMessage(**base)


def _rate_limit(status: str, **kw) -> sdk.RateLimitEvent:
    return sdk.RateLimitEvent(
        rate_limit_info=sdk.RateLimitInfo(status=status, **kw), uuid="u", session_id="s"
    )


_INIT = sdk.SystemMessage(subtype="init", data={})


async def _drain(agen) -> list[str]:
    return [delta async for delta in agen]


# ---- render_transcript ------------------------------------------------------------------------


def test_render_transcript_labels_in_order_with_the_last_user_line_last():
    text = render_transcript([
        {"role": "user", "content": "Timo: Ich klopfe."},
        {"role": "assistant", "content": "Niemand antwortet."},
        {"role": "user", "content": "Timo: Ich trete die Tür ein."},
    ])
    assert text.splitlines()[0] == "Setze die Sitzung fort; antworte nur als Spielleitung."
    assert text.index("[Spieler] Timo: Ich klopfe.") < text.index("[Spielleitung] Niemand antwortet.")
    assert text.endswith("[Spieler] Timo: Ich trete die Tür ein.")


def test_render_transcript_with_empty_history_is_the_instruction_alone():
    assert render_transcript([]) == "Setze die Sitzung fort; antworte nur als Spielleitung."


def test_a_single_instruction_goes_through_verbatim_history_becomes_a_transcript():
    assert _prompt(_USER) == "Timo: Ich öffne die Tür."
    history = [*_USER, {"role": "assistant", "content": "Sie knarrt."}, *_USER]
    assert _prompt(history) == render_transcript(history)


# ---- option mapping ---------------------------------------------------------------------------


def test_narration_call_maps_onto_the_sdk_options(fake, client):
    query = fake(_INIT, _result(result="Die Tür knarrt."))
    asyncio.run(client.chat("PERSONA äöü", _USER, options={"num_predict": 220}))
    options = query.options[0]
    assert options.model == "opus"
    assert options.max_turns == 1
    assert options.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "220"
    assert options.env["CLAUDE_AGENT_SDK_CLIENT_APP"] == "cogitator-dmbot/1.2.3"
    assert options.output_format is None
    assert options.system_prompt["type"] == "file"
    assert query.systems == ["PERSONA äöü"]  # replaces the CLI's prompt, never the preset
    assert query.prompts == ["Timo: Ich öffne die Tür."]
    assert not query.system_paths[0].exists()  # the per-call prompt file is removed afterwards


def test_no_num_predict_means_no_output_cap_env(fake, client):
    query = fake(_INIT, _result(result="x"))
    asyncio.run(client.chat("s", _USER))
    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in query.options[0].env


def test_the_isolation_set_is_complete(fake, client):
    """Every source the CLI would load on its own is switched off (lesson
    isolation-must-enumerate-every-artifact)."""
    query = fake(_INIT, _result(result="x"))
    asyncio.run(client.chat("s", _USER))
    options = query.options[0]
    assert query.cwd_listing == [[]]  # an EMPTY temp dir — no CLAUDE.md / .claude to discover
    assert Path(options.cwd).name == "cwd" and "cogitator-claude-" in str(options.cwd)
    assert options.setting_sources == []
    assert options.skills is None
    assert options.plugins == []
    assert options.mcp_servers == {} and options.strict_mcp_config is True
    assert options.extra_args == {"no-session-persistence": None}
    assert options.tools == [] and options.allowed_tools == []
    assert options.permission_mode == "dontAsk"
    assert options.thinking == {"type": "disabled"}
    assert options.continue_conversation is False and options.resume is None  # stateless


def test_a_schema_call_goes_to_the_aux_tier_with_structured_output(fake, client):
    query = fake(_INIT, _result(structured_output={"probe": "ja"}, result='{"probe":"ja"}',
                                stop_reason="tool_use"))
    raw = asyncio.run(client.chat("ROUTER", _USER, options={"num_predict": 80}, format=_SCHEMA))
    options = query.options[0]
    assert options.model == "haiku"
    assert options.output_format == {"type": "json_schema", "schema": _SCHEMA}
    assert json.loads(raw) == {"probe": "ja"}
    assert client.last_aux_stats["model"] == "haiku" and client.last_aux_stats["truncated"] is False
    # Sized for Claude's tool-call delivery, not Ollama's grammar (see the module constants).
    assert options.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "1024"
    assert options.max_turns == 3
    assert query.systems[0].startswith("ROUTER") and "StructuredOutput" in query.systems[0]


def test_structured_output_keeps_umlauts_and_falls_back_to_the_result_text(fake, client):
    fake(_INIT, _result(structured_output={"name": "Jäger"}))
    assert asyncio.run(client.chat("s", _USER, format=_SCHEMA)) == '{"name": "Jäger"}'
    fake(_INIT, _result(structured_output=None, result=' {"probe": "nein"} '))
    assert asyncio.run(client.chat("s", _USER, format=_SCHEMA)) == '{"probe": "nein"}'


def test_fallback_model_and_cli_path_reach_the_options(fake):
    query = fake(_INIT, _result(result="x"))
    made = ClaudeClient(fallback_model="sonnet", cli_path="C:/bin/claude.exe")
    asyncio.run(made.chat("s", _USER))
    asyncio.run(made.aclose())
    assert query.options[0].fallback_model == "sonnet"
    assert query.options[0].cli_path == "C:/bin/claude.exe"


def test_unmappable_knobs_are_logged_once_not_per_call(fake, client, caplog):
    options = {"temperature": 0.7, "stop": ["\nTimo:"], "repeat_penalty": 1.1, "top_p": 0.9}
    with caplog.at_level(logging.WARNING, logger="dmbot.llm.claude_client"):
        for _ in range(3):
            fake(_INIT, _result(result="x"))
            asyncio.run(client.chat("s", _USER, options=options))
    messages = [r.getMessage() for r in caplog.records]
    assert sum("temperature" in m for m in messages) == 1
    assert sum("stop" in m for m in messages) == 1
    assert len(messages) == 2  # repeat_penalty / top_p are dropped silently


def test_the_model_property_is_the_narration_model(client):
    assert client.model == "opus"
    assert client.last_stats is None


# ---- chat -------------------------------------------------------------------------------------


def test_chat_returns_the_result_text_or_the_assistant_text(fake, client):
    fake(_INIT, _assistant(sdk.TextBlock("Die Tür knarrt.")), _result(result=" Die Tür knarrt. "))
    assert asyncio.run(client.chat("s", _USER)) == "Die Tür knarrt."
    fake(_INIT, _assistant(sdk.ThinkingBlock("hm", "sig"), sdk.TextBlock("Nur Text.")),
         _result(result=None))
    assert asyncio.run(client.chat("s", _USER)) == "Nur Text."


def test_last_stats_arithmetic(fake, client):
    fake(_INIT, _result(result="x", usage={
        "input_tokens": 100, "cache_read_input_tokens": 4000,
        "cache_creation_input_tokens": 300, "output_tokens": 55,
    }))
    asyncio.run(client.chat("s", _USER, options={"num_predict": 220}))
    stats = client.last_stats
    assert stats["prompt_eval_count"] == 4400  # input + cache read + cache creation
    assert stats["eval_count"] == 55
    assert stats["num_ctx"] == 24576  # the nominal budget, equal to Ollama's
    assert stats["cache_read"] == 4000
    assert stats["api_ms"] == 700
    assert stats["model"] == "opus"
    assert stats["truncated"] is False
    assert isinstance(stats["spawn_ms"], int)


# ---- chat_stream ------------------------------------------------------------------------------


def test_stream_yields_only_text_deltas_and_sets_stats_from_the_result(fake, client):
    query = fake(
        _INIT,
        _start(input_tokens=90, cache_read_input_tokens=10),
        _event({"type": "content_block_start", "content_block": {"type": "text", "text": ""}}),
        _event({"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "hm"}}),
        _delta("Die Tür "),
        _event({"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}}),
        _delta("knarrt."),
        _assistant(sdk.TextBlock("Die Tür knarrt.")),
        _stop("end_turn", 12),
        _result(result="Die Tür knarrt.", usage={"input_tokens": 90, "cache_read_input_tokens": 10,
                                                 "output_tokens": 12}),
    )
    deltas = asyncio.run(_drain(client.chat_stream("s", _USER, options={"num_predict": 220})))
    assert deltas == ["Die Tür ", "knarrt."]
    assert client.last_stats["prompt_eval_count"] == 100
    assert client.last_stats["eval_count"] == 12
    assert client.last_stats["truncated"] is False
    assert query.options[0].model == "opus" and query.options[0].include_partial_messages is True
    assert query.closed == 1


def test_stream_ignores_frames_of_a_subagent(fake, client):
    nested = sdk.StreamEvent(uuid="u", session_id="s", parent_tool_use_id="t1", event={
        "type": "content_block_delta", "delta": {"type": "text_delta", "text": "intern"}})
    fake(_INIT, nested, _delta("laut"), _result())
    assert asyncio.run(_drain(client.chat_stream("s", _USER))) == ["laut"]


def test_early_close_closes_the_sdk_stream_and_leaves_fresh_stats(fake, client):
    """The stop-label / pause abort: closing our generator closes the SDK's, nothing further is
    read, and the stats are this call's (not the previous call's)."""
    fake(_INIT, _result(result="alt", usage={"input_tokens": 7, "output_tokens": 7}))
    asyncio.run(client.chat("s", _USER))
    query = fake(_INIT, _start(input_tokens=500), _delta("Eins. "), _delta("Zwei. "),
                 _delta("Drei."), _result())

    async def go():
        agen = client.chat_stream("s", _USER)
        got = []
        async for delta in agen:
            got.append(delta)
            break
        await agen.aclose()
        return got

    assert asyncio.run(go()) == ["Eins. "]
    assert query.closed == 1
    assert query.yielded == 3  # init, message_start, first delta — nothing after the close
    assert not query.system_paths[0].exists()
    assert client.last_stats["prompt_eval_count"] == 500
    assert client.last_stats["eval_count"] is None


def test_a_schema_call_never_writes_the_narration_slot(fake, client):
    """Classifiers run beside the narration on this backend. One that finishes while a narration
    stream is open and then aborted (stop label / pause) must not leave ITS numbers where the
    brain reads the turn's [latency] line and the auto-recap trigger."""
    fake(_INIT, _start(input_tokens=500), _delta("Eins. "), _delta("Zwei."), _result())

    async def go():
        agen = client.chat_stream("s", _USER)
        async for _ in agen:
            break
        # The narration stream is open; a router verdict comes and goes meanwhile.
        fake(_INIT, _start(input_tokens=40), _result(structured_output={"probe": "ja"},
                                                     usage={"input_tokens": 40, "output_tokens": 9}))
        await client.chat("ROUTER", _USER, format=_SCHEMA)
        await agen.aclose()

    asyncio.run(go())
    assert client.last_stats["prompt_eval_count"] == 500 and client.last_stats["model"] == "opus"
    assert client.last_aux_stats["prompt_eval_count"] == 40
    assert client.last_aux_stats["model"] == "haiku"


def test_a_schema_call_before_any_narration_leaves_the_narration_slot_empty(fake, client):
    fake(_INIT, _result(structured_output={"probe": "ja"}))
    asyncio.run(client.chat("ROUTER", _USER, format=_SCHEMA))
    assert client.last_stats is None and client.last_aux_stats["model"] == "haiku"


# ---- truncation (the output cap) --------------------------------------------------------------


def test_narration_is_cut_at_the_first_max_tokens_stop(fake, client, caplog):
    """The CLI would resume after the cap (three times, then fail the run). The client cuts
    instead: text so far, ``truncated``, one WARNING, and the resume frames are never read."""
    query = fake(
        _INIT, _start(input_tokens=600), _delta("Der Gang "), _delta("ist lang"),
        _assistant(sdk.TextBlock("Der Gang ist lang")), _stop("max_tokens", 220),
        _delta(" und geht weiter"), _result(result="nie erreicht"),
    )
    with caplog.at_level(logging.WARNING, logger="dmbot.llm.claude_client"):
        deltas = asyncio.run(_drain(client.chat_stream("s", _USER, options={"num_predict": 220})))
    assert deltas == ["Der Gang ", "ist lang"]
    assert client.last_stats["truncated"] is True
    assert client.last_stats["eval_count"] == 220 and client.last_stats["prompt_eval_count"] == 600
    assert query.closed == 1 and query.yielded == 6
    warnings = [r.getMessage() for r in caplog.records]
    assert warnings == ["✂ Antwort an der Ausgabegrenze abgeschnitten (220/220 Tokens)"]


def test_batch_narration_is_cut_the_same_way(fake, client, caplog):
    fake(_INIT, _start(input_tokens=600), _assistant(sdk.TextBlock("Der Gang ist lang")),
         _stop("max_tokens", 400), _result(result="nie erreicht"))
    with caplog.at_level(logging.WARNING, logger="dmbot.llm.claude_client"):
        answer = asyncio.run(client.chat("s", _USER, options={"num_predict": 400}))
    assert answer == "Der Gang ist lang"
    assert client.last_stats["truncated"] is True
    assert sum("✂" in r.getMessage() for r in caplog.records) == 1


def test_an_answer_below_the_cap_is_not_truncated_and_logs_nothing(fake, client, caplog):
    fake(_INIT, _start(input_tokens=600), _delta("Kurz."), _stop("end_turn", 12),
         _result(result="Kurz.", usage={"input_tokens": 600, "output_tokens": 12}))
    with caplog.at_level(logging.WARNING, logger="dmbot.llm.claude_client"):
        asyncio.run(_drain(client.chat_stream("s", _USER, options={"num_predict": 220})))
    assert client.last_stats["truncated"] is False
    assert caplog.records == []


def test_truncation_from_the_result_stop_reason_and_the_token_fallback(fake, client):
    fake(_INIT, _result(result="x", stop_reason="max_tokens"))
    asyncio.run(client.chat("s", _USER, options={"num_predict": 220}))
    assert client.last_stats["truncated"] is True
    # No stop reason anywhere → fall back to comparing tokens with the cap.
    fake(_INIT, _result(result="x", stop_reason=None, usage={"input_tokens": 1, "output_tokens": 220}))
    asyncio.run(client.chat("s", _USER, options={"num_predict": 220}))
    assert client.last_stats["truncated"] is True
    fake(_INIT, _result(result="x", stop_reason=None, usage={"input_tokens": 1, "output_tokens": 219}))
    asyncio.run(client.chat("s", _USER, options={"num_predict": 220}))
    assert client.last_stats["truncated"] is False


def test_a_schema_call_is_not_cut_mid_way_and_a_spent_cap_is_not_a_backend_error(fake, client, caplog):
    """A schema call may run past a max_tokens stop (the tool call can still come). When the
    CLI gives up, the caller gets the text and fails open — the failover must not fire."""
    fake(_INIT, _start(input_tokens=50), _assistant(sdk.TextBlock("Also ")), _stop("max_tokens", 1024),
         _result(structured_output={"probe": "ja"}, stop_reason="tool_use"))
    assert json.loads(asyncio.run(client.chat("s", _USER, format=_SCHEMA))) == {"probe": "ja"}
    assert client.last_aux_stats["truncated"] is False

    fake(_INIT, _start(input_tokens=50), _assistant(sdk.TextBlock("Also ich denke")),
         _stop("max_tokens", 1024), _assistant(sdk.TextBlock("API Error"), error="max_output_tokens"),
         _result(is_error=True))
    with caplog.at_level(logging.WARNING, logger="dmbot.llm.claude_client"):
        raw = asyncio.run(client.chat("s", _USER, options={"num_predict": 80}, format=_SCHEMA))
    assert raw == "Also ich denke"
    assert client.last_aux_stats["truncated"] is True
    assert ["aux call" in r.getMessage() for r in caplog.records] == [True]


# ---- errors -----------------------------------------------------------------------------------


@pytest.mark.parametrize("failure", [
    sdk.CLIConnectionError("no pipe"),
    sdk.CLINotFoundError("Claude Code not found"),
    sdk.ProcessError("boom", exit_code=1),
    OSError("[WinError 206] The filename or extension is too long"),
])
def test_sdk_failures_become_the_one_backend_error(fake, client, failure):
    fake(failure)
    with pytest.raises(LLMBackendError) as caught:
        asyncio.run(client.chat("s", _USER))
    assert caught.value.__cause__ is failure
    with pytest.raises(LLMBackendError):
        asyncio.run(_drain(client.chat_stream("s", _USER)))


def test_the_sdks_bare_exceptions_are_backend_errors_too(fake, client):
    """The SDK raises plain ``Exception`` for a failed or timed-out initialize handshake; left
    unmapped it would bypass the failover and the turn would simply be silent."""
    failure = Exception("Control request timeout: initialize")
    fake(failure)
    with pytest.raises(LLMBackendError, match="initialize") as caught:
        asyncio.run(client.chat("s", _USER))
    assert caught.value.__cause__ is failure
    with pytest.raises(LLMBackendError):
        asyncio.run(_drain(client.chat_stream("s", _USER)))


def test_a_cancelled_call_stays_cancelled(fake, client):
    async def hang():
        await asyncio.sleep(30)

    query = fake(_INIT, hang)

    async def go():
        task = asyncio.create_task(client.chat("s", _USER))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert query.closed == 1 and not query.system_paths[0].exists()


def test_a_schema_call_out_of_turns_loses_its_verdict_not_the_backend(fake, client, caplog):
    fake(_INIT, _assistant(sdk.TextBlock("Ich denke, ja.")),
         _result(is_error=True, subtype="error_max_turns", result=None))
    with caplog.at_level(logging.WARNING, logger="dmbot.llm.claude_client"):
        assert asyncio.run(client.chat("s", _USER, format=_SCHEMA)) == "Ich denke, ja."
    assert client.last_aux_stats["truncated"] is True and len(caplog.records) == 1
    # Narration has exactly one turn by design — there the same subtype is a real error.
    fake(_INIT, _result(is_error=True, subtype="error_max_turns", result=None))
    with pytest.raises(LLMBackendError):
        asyncio.run(client.chat("s", _USER))


def test_an_error_result_raises(fake, client):
    fake(_INIT, _result(is_error=True, subtype="error_during_execution", errors=["model not found"]))
    with pytest.raises(LLMBackendError, match="model not found"):
        asyncio.run(client.chat("s", _USER))


def test_an_assistant_error_never_becomes_narration(fake, client):
    fake(_INIT, _assistant(sdk.TextBlock("API Error: 529 overloaded"), error="server_error"),
         _result(result="API Error: 529 overloaded"))
    with pytest.raises(LLMBackendError, match="server_error"):
        asyncio.run(client.chat("s", _USER))


def test_a_rejected_rate_limit_raises_with_the_reset_time(fake, client):
    fake(_INIT, _rate_limit("rejected", resets_at=1791290400, rate_limit_type="five_hour"),
         _result(result="x"))
    with pytest.raises(LLMBackendError) as caught:
        asyncio.run(client.chat("s", _USER))
    assert caught.value.resets_at == 1791290400


def test_a_rate_limit_warning_is_logged_and_the_call_succeeds(fake, client, caplog):
    fake(_INIT, _rate_limit("allowed"),
         _rate_limit("allowed_warning", utilization=0.91, resets_at=1791290400,
                     rate_limit_type="five_hour"),
         _result(result="Weiter."))
    with caplog.at_level(logging.WARNING, logger="dmbot.llm.claude_client"):
        assert asyncio.run(client.chat("s", _USER)) == "Weiter."
    assert len(caplog.records) == 1
    assert "91%" in caplog.records[0].getMessage() and "five_hour" in caplog.records[0].getMessage()


def test_a_call_without_a_result_raises(fake, client):
    fake(_INIT)
    with pytest.raises(LLMBackendError, match="without a result"):
        asyncio.run(client.chat("s", _USER))


def test_stream_error_before_the_first_delta_raises_with_nothing_yielded(fake, client):
    """What the failover needs: a failure before any text surfaces as the error itself."""
    fake(_INIT, _rate_limit("rejected"), _delta("zu spät"))

    async def go():
        got = []
        with pytest.raises(LLMBackendError):
            async for delta in client.chat_stream("s", _USER):
                got.append(delta)
        return got

    assert asyncio.run(go()) == []


def test_a_silent_cli_times_out_into_a_backend_error(fake):
    async def hang():
        await asyncio.sleep(30)

    query = fake(_INIT, hang, _result(result="x"))
    made = ClaudeClient(timeout=0.05)
    with pytest.raises(LLMBackendError, match="did not answer"):
        asyncio.run(made.chat("s", _USER))
    assert query.closed == 1
    asyncio.run(made.aclose())


def test_the_stream_timeout_ends_with_the_first_delta(fake):
    async def pause():
        await asyncio.sleep(0.15)

    fake(_INIT, _delta("Erster Satz. "), pause, _delta("Zweiter."), _result())
    made = ClaudeClient(timeout=0.05)
    assert asyncio.run(_drain(made.chat_stream("s", _USER))) == ["Erster Satz. ", "Zweiter."]
    asyncio.run(made.aclose())


def test_a_set_api_key_is_refused_unless_allowed(fake, monkeypatch):
    query = fake(_INIT, _result(result="x"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    made = ClaudeClient()
    with pytest.raises(LLMBackendError, match="ANTHROPIC_API_KEY"):
        asyncio.run(made.chat("s", _USER))
    with pytest.raises(LLMBackendError, match="ANTHROPIC_API_KEY"):
        asyncio.run(_drain(made.chat_stream("s", _USER)))
    assert query.options == []  # refused before anything is spawned
    asyncio.run(made.aclose())
    allowed = ClaudeClient(allow_api_key=True)
    assert asyncio.run(allowed.chat("s", _USER)) == "x"
    asyncio.run(allowed.aclose())


def test_aclose_removes_the_working_directory(fake):
    query = fake(_INIT, _result(result="x"))
    made = ClaudeClient()
    asyncio.run(made.chat("s", _USER))
    workdir = Path(query.options[0].cwd).parent
    assert workdir.is_dir()
    asyncio.run(made.aclose())
    assert not workdir.exists()


# ---- the real SDK over a fake transport ---------------------------------------------------------


class _FakeTransport(sdk.Transport):
    """A CLI that answers the handshake, streams two deltas and then never finishes."""

    def __init__(self):
        self._frames: asyncio.Queue = asyncio.Queue()
        self.closed = asyncio.Event()

    async def connect(self) -> None:
        pass

    def is_ready(self) -> bool:
        return not self.closed.is_set()

    async def end_input(self) -> None:
        pass

    async def close(self) -> None:
        self.closed.set()
        self._frames.put_nowait(None)

    async def write(self, data: str) -> None:
        message = json.loads(data)
        if message.get("type") == "control_request":
            self._frames.put_nowait({"type": "control_response", "response": {
                "subtype": "success", "request_id": message["request_id"], "response": {}}})
        elif message.get("type") == "user":
            self._frames.put_nowait({"type": "system", "subtype": "init", "session_id": "s"})
            for text in ("Eins. ", "Zwei. "):
                self._frames.put_nowait({
                    "type": "stream_event", "uuid": "u", "session_id": "s", "parent_tool_use_id": None,
                    "event": {"type": "content_block_delta",
                              "delta": {"type": "text_delta", "text": text}},
                })

    async def read_messages(self):
        while True:
            frame = await self._frames.get()
            if frame is None:
                return
            yield frame


def test_early_close_reaches_the_transport_of_the_real_sdk(monkeypatch):
    """Pins what the abort path relies on in the installed SDK: after our generator is closed,
    the SDK closes its transport (= ends the CLI process) without anyone awaiting it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    transport = _FakeTransport()
    real_query = sdk.query
    monkeypatch.setattr(
        sdk, "query", lambda *, prompt, options: real_query(prompt=prompt, options=options,
                                                            transport=transport))
    made = ClaudeClient()

    async def go():
        agen = made.chat_stream("s", _USER)
        first = await agen.__anext__()
        await agen.aclose()
        await asyncio.wait_for(transport.closed.wait(), timeout=5)
        return first

    assert asyncio.run(go()) == "Eins. "
    asyncio.run(made.aclose())
