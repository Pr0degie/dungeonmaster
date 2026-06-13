"""Context-budget logging.

The Ollama client surfaces the response's token counts (``prompt_eval_count`` /
``eval_count``) without changing ``chat()``'s return type, and the per-turn timing record flags
when the prompt nears the ``num_ctx`` cap (the early signal before Ollama truncates the prompt
head — the persona). The network call is faked: these test the pure meta-extraction + threshold
logic, not Ollama itself (that's verified live).
"""

from __future__ import annotations

import asyncio

from dmbot.llm.client import OllamaClient
from dmbot.voice.commands import _TurnTiming


class _FakeResp:
    def __init__(self, data: dict) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class _FakeHTTP:
    """Stand-in for the client's ``httpx.AsyncClient``: returns a canned ``/api/chat`` response."""

    def __init__(self, data: dict) -> None:
        self._data = data
        self.payload: dict | None = None

    async def post(self, url: str, *, json: dict | None = None) -> _FakeResp:
        self.payload = json  # captured so a test could assert on what we send
        return _FakeResp(self._data)

    async def aclose(self) -> None:
        pass


def _client_with(data: dict, *, num_ctx: int | None = None) -> OllamaClient:
    """An OllamaClient whose transport is faked to return ``data`` (the real httpx client, created
    in __init__ but unused here, is closed first so no resource leaks). Pass ``num_ctx`` to
    override the instance default."""
    client = (
        OllamaClient("http://x", "mistral-nemo", num_ctx=num_ctx)
        if num_ctx is not None
        else OllamaClient("http://x", "mistral-nemo")
    )
    asyncio.run(client._client.aclose())
    client._client = _FakeHTTP(data)  # type: ignore[assignment]
    return client


def test_chat_captures_token_meta() -> None:
    client = _client_with(
        {"message": {"content": "  Hallo  "}, "prompt_eval_count": 3100, "eval_count": 180}
    )
    text = asyncio.run(client.chat("sys", [{"role": "user", "content": "hi"}]))
    assert text == "Hallo"  # return type unchanged: still the stripped answer string
    assert client.last_stats == {
        "prompt_eval_count": 3100,
        "eval_count": 180,
        "num_ctx": 24576,  # the instance default we send
    }


def test_chat_meta_missing_counts_is_none() -> None:
    # An older / edge Ollama response without the counts → None, not a KeyError.
    client = _client_with({"message": {"content": "x"}})
    asyncio.run(client.chat("sys", []))
    assert client.last_stats == {"prompt_eval_count": None, "eval_count": None, "num_ctx": 24576}


def test_chat_meta_reflects_num_ctx_option() -> None:
    # A caller-supplied num_ctx is what the budget is measured against.
    client = _client_with({"message": {"content": "y"}, "prompt_eval_count": 10, "eval_count": 5})
    asyncio.run(client.chat("sys", [], options={"num_ctx": 4096}))
    assert client.last_stats["num_ctx"] == 4096


def test_instance_num_ctx_in_request_payload() -> None:
    # The instance num_ctx (OLLAMA_NUM_CTX → config) is what actually goes on the wire, so a
    # raised context window reaches Ollama instead of being silently capped at the old 8192.
    client = _client_with({"message": {"content": "z"}}, num_ctx=12345)
    asyncio.run(client.chat("sys", [{"role": "user", "content": "hi"}]))
    assert client._client.payload["options"]["num_ctx"] == 12345  # type: ignore[attr-defined]


def test_explicit_option_overrides_instance_num_ctx() -> None:
    # An explicit caller option still wins over the instance default (override order preserved).
    client = _client_with({"message": {"content": "z"}}, num_ctx=12345)
    asyncio.run(client.chat("sys", [], options={"num_ctx": 4096}))
    assert client._client.payload["options"]["num_ctx"] == 4096  # type: ignore[attr-defined]


def test_ctx_over_budget_threshold() -> None:
    # 0.85 * 8192 = 6963.2 → 7000 trips it, 6900 doesn't.
    assert _TurnTiming(turn=1, trigger=0.0, prompt_eval=7000, num_ctx=8192).ctx_over_budget()
    assert not _TurnTiming(turn=2, trigger=0.0, prompt_eval=6900, num_ctx=8192).ctx_over_budget()


def test_ctx_over_budget_handles_missing_meta() -> None:
    # No stats yet, or a 0/None num_ctx → never warns (no false alarms when counts are unknown).
    assert not _TurnTiming(turn=3, trigger=0.0).ctx_over_budget()
    assert not _TurnTiming(turn=4, trigger=0.0, prompt_eval=9000, num_ctx=0).ctx_over_budget()
