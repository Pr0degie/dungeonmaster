"""Claude backend behind the :class:`~dmbot.llm.client.LLMClient` seam (ADR 061, Phase 11).

Speaks the same ``chat`` / ``chat_stream`` / ``last_stats`` surface as ``OllamaClient`` through the
``claude-agent-sdk``, which drives the installed ``claude`` CLI on the operator's own subscription
login — no API key anywhere. The SDK is imported lazily, so the Ollama path never pulls it.

**Stateless.** Every call is one ``claude_agent_sdk.query()`` (one turn; a schema call may take
up to three, see ``_AUX_MAX_TURNS``). ``DMBrain`` stays the sole owner of history (redo,
echo-guard pair removal, auto-recap, crash restore); the history is rendered into the prompt
(:func:`render_transcript`), never resumed from an SDK session.

**Tier rule.** A call with a ``format`` is a classifier or extractor → the aux model; every other
call is prose → the narration model. The call sites don't know there are two models.

**Isolation.** The CLI would otherwise load this repo's ``CLAUDE.md``, skills, settings and MCP
servers into the DM's context. Every source is switched off explicitly in :meth:`_options`.

**Not mappable on Claude** (dropped here, the client-side guards above the seam stay in charge):
``temperature`` and server-side ``stop`` (logged once at first use), and the Nemo-specific
``repeat_penalty`` / ``repeat_last_n`` / ``top_p`` / ``num_ctx`` (silent — the caller never asked).

**The output cap is enforced here, not by the CLI.** ``CLAUDE_CODE_MAX_OUTPUT_TOKENS`` caps one
API request, but the CLI then asks the model to resume (up to three times) and finally fails the
run — measured live, not what the PRD assumed. So a narration answer is cut by this client at the
first ``max_tokens`` stop, which restores the hard cut ``num_predict`` means everywhere else.

Where the installed SDK (checked against 0.2.163, CLI 2.1.291) differs from what the PRD assumed,
the code says so at the spot and ADR 061's SDK amendment records it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import LLMBackendError

log = logging.getLogger(__name__)

_TRANSCRIPT_HEADER = "Setze die Sitzung fort; antworte nur als Spielleitung."
_ROLE_LABELS = {"user": "[Spieler]", "assistant": "[Spielleitung]"}

# Floor for the per-request output cap of a schema call. The callers' ``num_predict`` is sized
# for Ollama's grammar-constrained JSON (80 for the roll router); Claude delivers structured
# output as a tool call it may precede with a sentence, and a cap that small made the CLI spend
# four requests on one verdict (measured: 5.4 s instead of one round trip).
_AUX_MIN_OUTPUT_TOKENS = 1024

# Structured output arrives as a ``StructuredOutput`` tool call. When the model answers in plain
# text first, the CLI needs a further turn to demand the call — with ``max_turns=1`` that run
# fails ("Reached maximum number of turns (1)", seen live). There are no other tools, so the
# extra turns can do nothing else. Narration stays at exactly one turn.
_AUX_MAX_TURNS = 3
# Ollama enforces ``format`` by grammar from the first token; here an instruction has to do it.
# Measured on Haiku: with this line the verdict comes in one request (1.5 s) instead of prose
# followed by the call (3 s).
_AUX_SYSTEM_SUFFIX = (
    "\n\nGib deine Antwort ausschließlich über das Werkzeug StructuredOutput ab, ohne Begleittext."
)


def render_transcript(messages: list[dict[str, str]]) -> str:
    """Render role-tagged history into the single prompt string a stateless call needs.

    One German instruction line, then one labelled block per message in order — the newest
    player line is last, so the model answers it. Pure; unknown roles are labelled by name.
    """
    blocks = [_TRANSCRIPT_HEADER]
    for message in messages:
        role = message.get("role", "")
        label = _ROLE_LABELS.get(role, f"[{role}]")
        blocks.append(f"{label} {message.get('content', '')}")
    return "\n\n".join(blocks)


def _prompt(messages: list[dict[str, str]]) -> str:
    """The prompt for one call. A lone user message goes through verbatim: the routers,
    extractors and the recap send exactly one self-contained instruction, and the transcript
    header ("antworte nur als Spielleitung") would contradict it. Deviation from the PRD's
    "always a transcript", recorded in ADR 061's SDK amendment."""
    if len(messages) == 1 and messages[0].get("role") == "user":
        return messages[0].get("content", "")
    return render_transcript(messages)


def _sdk():
    """The lazily imported SDK module (kept out of the Ollama path, like ``xtts``)."""
    try:
        import claude_agent_sdk
    except ImportError as exc:
        raise LLMBackendError(f"claude-agent-sdk is not installed ({exc})") from exc
    return claude_agent_sdk


def _text_delta(event: dict[str, Any]) -> str:
    """The text of one raw stream event, or ``""`` for everything that isn't a text delta
    (thinking deltas, tool-use input deltas, block/message frames)."""
    if event.get("type") != "content_block_delta":
        return ""
    delta = event.get("delta") or {}
    if delta.get("type") != "text_delta":
        return ""
    return delta.get("text") or ""


def _prompt_tokens(usage: dict[str, Any]) -> tuple[int, int]:
    """``(prompt tokens, cache-read tokens)`` from a usage dict. The prompt is what the model
    read: fresh input + cache reads + cache writes (the three are disjoint)."""
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    total = (
        int(usage.get("input_tokens") or 0)
        + cache_read
        + int(usage.get("cache_creation_input_tokens") or 0)
    )
    return total, cache_read


@dataclass
class _Call:
    """Everything one ``query()`` produced, collected while its messages go by."""

    model: str
    cap: int | None
    narration: bool
    started: float
    spawn_ms: int | None = None
    texts: list[str] = field(default_factory=list)
    result: Any = None
    # From the raw stream frames — the only source when the call ends before its result.
    prompt_tokens: int | None = None
    cache_read: int = 0
    output_tokens: int | None = None
    stop_reason: str | None = None
    cut: bool = False  # ended by this client at the output cap


class ClaudeClient:
    """Async Claude client over the Agent SDK. One per bot; close it on shutdown."""

    def __init__(
        self,
        *,
        narration_model: str = "opus",
        aux_model: str = "haiku",
        fallback_model: str | None = None,
        num_ctx: int = 24576,
        cli_path: str | None = None,
        allow_api_key: bool = False,
        timeout: float = 120.0,
        app_version: str = "0.0.0",
    ) -> None:
        self._narration_model = narration_model
        self._aux_model = aux_model
        self._fallback_model = fallback_model or None
        # A nominal budget, not the model's real window: auto-recap (ADR 027) and the [ctx] warning
        # key on prompt_eval / num_ctx, so it stays equal to Ollama's to keep recap cadence identical.
        self._num_ctx = num_ctx
        self._cli_path = cli_path or None
        self._allow_api_key = allow_api_key
        # Batch calls: the whole call. Streaming: only until the first delta — after that the turn
        # is being spoken and the pause/stop path owns a wedged stream, as on Ollama.
        self._timeout = timeout
        self._app = f"cogitator-dmbot/{app_version}"
        # Working area under the system temp dir (never /tmp): `cwd/` stays EMPTY so the CLI finds
        # no CLAUDE.md / .claude there; `prompts/` holds the per-call system-prompt files.
        self._workdir = Path(tempfile.mkdtemp(prefix="cogitator-claude-", dir=tempfile.gettempdir()))
        self._cwd = self._workdir / "cwd"
        self._prompts = self._workdir / "prompts"
        self._cwd.mkdir()
        self._prompts.mkdir()
        self._warned: set[str] = set()
        self._stderr_tail: list[str] = []
        self.last_stats: dict | None = None

    @property
    def model(self) -> str:
        """The narration model — what the table hears. ``last_stats["model"]`` names the tier
        that answered the most recent call."""
        return self._narration_model

    # ---- request building --------------------------------------------------------------

    def _warn_once(self, knob: str, message: str) -> None:
        if knob not in self._warned:
            self._warned.add(knob)
            log.warning(message)

    def _on_stderr(self, line: str) -> None:
        """Keep the CLI's last stderr lines for the error message of a failed call."""
        self._stderr_tail.append(line.rstrip())
        del self._stderr_tail[:-5]

    def _options(self, system_file: Path, options: dict | None, format: dict | str | None):
        """Map one call onto ``ClaudeAgentOptions``. Returns ``(sdk options, model, output cap)``."""
        sdk = _sdk()
        options = options or {}
        if "temperature" in options:
            self._warn_once(
                "temperature",
                "Claude backend: `temperature` is not settable through the Agent SDK — ignored "
                "(the intro temperature of D83 is a no-op here; its retry guard still applies).",
            )
        if options.get("stop"):
            self._warn_once(
                "stop",
                "Claude backend: server-side `stop` sequences are not available through the Agent "
                "SDK — ignored (the client-side speaker-label cut stays the anti-puppeting guard).",
            )
        model = self._narration_model if format is None else self._aux_model
        env = {"CLAUDE_AGENT_SDK_CLIENT_APP": self._app}
        cap = int(options["num_predict"]) if options.get("num_predict") else None
        if cap and format is not None:
            cap = max(cap, _AUX_MIN_OUTPUT_TOKENS)
        if cap:
            # The SDK has no max_tokens field; the CLI reads this env var, per API request. The
            # cut itself (and with it the loss of end-of-answer markers) happens in _run().
            env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(cap)
        sdk_options = sdk.ClaudeAgentOptions(
            # A system prompt of ours REPLACES the CLI's coding prompt (never the preset). Passed as
            # a file, not the plain string the PRD assumed: the SDK puts a string on the command
            # line, and persona + state + RAG outgrows Windows' 32,767-character limit.
            system_prompt={"type": "file", "path": str(system_file)},
            model=model,
            fallback_model=self._fallback_model,
            max_turns=1 if format is None else _AUX_MAX_TURNS,
            # Always on, also for batch calls: the raw frames carry the per-request stop reason
            # and usage, which is how the output cap is detected.
            include_partial_messages=True,
            thinking={"type": "disabled"},
            # No tools this round (Phase 12).
            tools=[],
            allowed_tools=[],
            permission_mode="dontAsk",
            # Isolation — every source the CLI would load on its own, switched off one by one:
            cwd=str(self._cwd),          # an empty dir: no project CLAUDE.md / .claude to discover
            setting_sources=[],          # no user / project / local settings, memory or hooks
            skills=None,                 # no skills (a list here would re-enable setting sources)
            plugins=[],                  # no plugins
            mcp_servers={},              # no MCP servers of ours …
            strict_mcp_config=True,      # … and none from the operator's own Claude Code config
            # The SDK has no field for this (0.2.163); the CLI flag keeps every DM turn from being
            # written to ~/.claude/projects as a session transcript.
            extra_args={"no-session-persistence": None},
            env=env,
            cli_path=self._cli_path,
            stderr=self._on_stderr,
        )
        if isinstance(format, dict):
            sdk_options.output_format = {"type": "json_schema", "schema": format}
        return sdk_options, model, cap

    # ---- one query ---------------------------------------------------------------------

    async def _run(self, call: _Call, sdk_options, prompt: str, *, partial: bool) -> AsyncIterator[str]:
        """Drive one ``query()``: yield text deltas (streaming only), collect the rest into
        ``call``. Every failure leaves as :class:`LLMBackendError`. Closing this generator early
        closes the SDK stream, which ends the CLI subprocess."""
        sdk = _sdk()
        self._stderr_tail.clear()
        deadline: float | None = call.started + self._timeout
        stream = sdk.query(prompt=prompt, options=sdk_options)
        messages = stream.__aiter__()
        try:
            while True:
                try:
                    if deadline is None:
                        message = await messages.__anext__()
                    else:
                        message = await asyncio.wait_for(
                            messages.__anext__(), max(deadline - time.monotonic(), 0.001)
                        )
                except StopAsyncIteration:
                    break
                if call.spawn_ms is None:
                    call.spawn_ms = round((time.monotonic() - call.started) * 1000)
                if isinstance(message, sdk.StreamEvent):
                    if message.parent_tool_use_id is not None:
                        continue
                    self._note_stream_frame(call, message.event)
                    if call.stop_reason == "max_tokens" and call.narration:
                        # The hard cut. Left alone, the CLI would now ask the model to resume and
                        # keep the turn talking past its spoken budget.
                        call.cut = True
                        break
                    delta = _text_delta(message.event)
                    if delta and partial:
                        deadline = None  # speaking has begun — no failover past this point
                        yield delta
                elif isinstance(message, sdk.AssistantMessage):
                    if message.error == "max_output_tokens":
                        # A schema call that never got to its structured answer within the cap
                        # (the CLI's resume attempts are used up). Not a backend failure: the
                        # caller gets the text and fails open, as with a bad verdict from Ollama.
                        call.cut = True
                        break
                    if message.error:
                        # The text of such a message is the CLI's "API Error: …" prose — it must
                        # never reach the table as narration.
                        raise LLMBackendError(f"Claude answered with an error ({message.error})")
                    call.texts.extend(
                        block.text for block in message.content if isinstance(block, sdk.TextBlock)
                    )
                elif isinstance(message, sdk.RateLimitEvent):
                    self._on_rate_limit(message.rate_limit_info)
                elif isinstance(message, sdk.ResultMessage):
                    if message.is_error and message.subtype == "error_max_turns" and not call.narration:
                        # A schema call that used up its turns without the tool call. Like the
                        # spent cap above: this verdict is lost, the backend is not down — an
                        # error here would push the narration onto the fallback for a cooldown.
                        call.cut = True
                        break
                    if message.is_error:
                        detail = "; ".join(message.errors or []) or message.result or message.subtype
                        raise LLMBackendError(f"Claude returned an error result: {detail}")
                    call.result = message
        except LLMBackendError:
            raise
        except TimeoutError as exc:
            raise LLMBackendError(
                f"Claude did not answer within {self._timeout:.0f}s ({call.model})"
            ) from exc
        except Exception as exc:  # noqa: BLE001 — see below
            # Deliberately everything: besides its own error types the SDK raises bare
            # `Exception` (a failed or timed-out initialize handshake), and anything that escaped
            # here unmapped would bypass the failover and leave the table with a silent turn.
            # Task cancellation is a BaseException and passes through untouched.
            tail = " | ".join(self._stderr_tail)
            raise LLMBackendError(
                f"Claude CLI failed ({exc.__class__.__name__}): {exc}" + (f" — {tail}" if tail else "")
            ) from exc
        finally:
            # Also the early-close path (pause, speaker-label abort, the output-cap cut). `query()`
            # does not close its inner generator on an early exit (PEP 533; the SDK only does so
            # one level down), so the subprocess is ended by the event loop finalising that
            # generator: stdin EOF, up to 5 s grace, then terminate. Measured: the CLI process is
            # gone about 5 s after this line, and on an early close this line returns at once —
            # which is what a turn wants. On a timeout or a cancelled task the SDK generator has
            # already run that same shutdown inline, so those two paths do wait for it. Recorded
            # in ADR 061's SDK amendment.
            await stream.aclose()

    def _note_stream_frame(self, call: _Call, event: dict[str, Any]) -> None:
        """Track usage and stop reason from the raw frames. The first ``message_start`` also sets
        provisional ``last_stats``, so an aborted stream (which never reaches its result) doesn't
        leave the previous call's numbers behind."""
        kind = event.get("type")
        if kind == "message_start" and call.prompt_tokens is None:
            usage = (event.get("message") or {}).get("usage") or {}
            call.prompt_tokens, call.cache_read = _prompt_tokens(usage)
            self.last_stats = self._stats(call, truncated=False)
        elif kind == "message_delta":
            call.stop_reason = (event.get("delta") or {}).get("stop_reason")
            output_tokens = (event.get("usage") or {}).get("output_tokens")
            if output_tokens is not None:
                call.output_tokens = output_tokens

    def _stats(self, call: _Call, *, truncated: bool) -> dict:
        """The ``last_stats`` dict: Ollama's three keys plus the Claude extras."""
        result = call.result
        if result is not None and result.usage:
            prompt_tokens, cache_read = _prompt_tokens(result.usage)
            output_tokens = result.usage.get("output_tokens")
        else:
            prompt_tokens, cache_read = call.prompt_tokens, call.cache_read
            output_tokens = call.output_tokens
        return {
            "prompt_eval_count": prompt_tokens,
            "eval_count": output_tokens,
            "num_ctx": self._num_ctx,
            "cache_read": cache_read,
            "spawn_ms": call.spawn_ms,
            "api_ms": result.duration_api_ms if result is not None else None,
            "model": call.model,
            "truncated": truncated,
        }

    def _on_rate_limit(self, info) -> None:
        if info.status == "rejected":
            raise LLMBackendError(
                f"Claude rate limit reached ({info.rate_limit_type or 'unknown'})",
                resets_at=info.resets_at,
            )
        if info.status == "allowed_warning":
            log.warning(
                "Claude rate limit warning — %s at %s, resets at %s",
                info.rate_limit_type or "limit",
                f"{info.utilization:.0%}" if info.utilization is not None else "unknown utilisation",
                time.strftime("%H:%M", time.localtime(info.resets_at)) if info.resets_at else "unknown",
            )

    def _finish(self, call: _Call) -> None:
        """Set ``last_stats`` for a completed call and say so when the output cap cut it."""
        result = call.result
        stop_reason = (result.stop_reason if result is not None else None) or call.stop_reason
        output_tokens = (
            result.usage.get("output_tokens") if result is not None and result.usage
            else call.output_tokens
        )
        # The SDK does expose a stop reason (`ResultMessage.stop_reason`, and per request in the
        # raw frames); the token comparison is only the fallback for a call that carries none.
        if call.cut:
            truncated = True
        elif stop_reason is not None:
            truncated = stop_reason == "max_tokens"
        else:
            truncated = bool(call.cap and output_tokens is not None and output_tokens >= call.cap)
        self.last_stats = self._stats(call, truncated=truncated)
        if not truncated:
            return
        shown = output_tokens if output_tokens is not None else "?"
        if call.narration:
            # Measured, not fixed (ADR 061): every end-of-answer marker sits where the cap cuts.
            log.warning("✂ Antwort an der Ausgabegrenze abgeschnitten (%s/%s Tokens)", shown, call.cap or "?")
        else:
            log.warning(
                "Claude aux call (%s) hit the output cap without a complete answer (%s/%s tokens) "
                "— the caller falls back.", call.model, shown, call.cap or "?",
            )

    def _refuse_api_key(self) -> None:
        """The CLI ranks ``ANTHROPIC_API_KEY`` above the subscription login and would silently
        bill the API. Refusing per call (not only in the preflight) is what makes the failover
        take over when the key is present."""
        if not self._allow_api_key and os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise LLMBackendError(
                "ANTHROPIC_API_KEY is set — the Claude backend refuses to run, it would bill the "
                "API instead of the subscription (unset it, or CLAUDE_ALLOW_API_KEY=1)."
            )

    def _begin(self, system: str, options: dict | None, format: dict | str | None):
        self._refuse_api_key()
        system_file = self._prompts / f"system-{uuid.uuid4().hex}.md"
        sdk_options, model, cap = self._options(system_file, options, format)
        if isinstance(format, dict):
            system += _AUX_SYSTEM_SUFFIX
        system_file.write_text(system, encoding="utf-8")
        call = _Call(model=model, cap=cap, narration=format is None, started=time.monotonic())
        return call, sdk_options, system_file

    # ---- the seam ----------------------------------------------------------------------

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        options: dict | None = None,
        format: dict | str | None = None,
    ) -> str:
        """One finished answer. With a JSON-schema ``format`` the validated object comes back as
        a JSON string, so the callers' ``json.loads`` + validators run unchanged. Raises
        :class:`LLMBackendError` on any failure."""
        call, sdk_options, system_file = self._begin(system, options, format)
        try:
            async for _ in self._run(call, sdk_options, _prompt(messages), partial=False):
                pass
        finally:
            system_file.unlink(missing_ok=True)
        result = call.result
        if result is None and not call.cut:
            raise LLMBackendError("Claude ended the call without a result")
        self._finish(call)
        if isinstance(format, dict) and result is not None and result.structured_output is not None:
            return json.dumps(result.structured_output, ensure_ascii=False)
        text = result.result if result is not None else None
        if text is None:
            text = "".join(call.texts)
        return text.strip()

    async def chat_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        options: dict | None = None,
    ) -> AsyncIterator[str]:
        """Like :meth:`chat`, but yield the answer's text deltas as they arrive. Stopping
        iteration / ``aclose()`` ends the generation (the client-side stop-label abort). An error
        before the first delta raises :class:`LLMBackendError` with nothing yielded, which is
        what lets the failover re-issue the turn; ``last_stats`` is final once the stream ends."""
        call, sdk_options, system_file = self._begin(system, options, None)
        run = self._run(call, sdk_options, _prompt(messages), partial=True)
        try:
            async for delta in run:
                yield delta
        finally:
            await run.aclose()
            system_file.unlink(missing_ok=True)
        if call.result is None and not call.cut:
            raise LLMBackendError("Claude ended the stream without a result")
        self._finish(call)

    async def aclose(self) -> None:
        shutil.rmtree(self._workdir, ignore_errors=True)
