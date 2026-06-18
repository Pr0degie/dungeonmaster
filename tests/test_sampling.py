"""Sampling options on the wire.

nemo's anti-repetition is off by default (only ``temperature``/``top_p`` were sent), so a 12B
model loops or drifts into generic filler; the post-hoc echo guard only catches it after the fact.
The client now carries a per-instance ``repeat_penalty`` (+ ``repeat_last_n``) — like ``num_ctx``,
it is an instance default that rides on every call (batch and streaming) so all narration turns get
it, while a caller can still override per call. Config-driven (``DM_REPEAT_PENALTY`` /
``DM_REPEAT_LAST_N``) so it stays live-tunable. The network call is faked: this pins what we send,
not Ollama itself.
"""

from __future__ import annotations

import asyncio

from dmbot.llm.client import OllamaClient


class _FakeResp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": "ok"}}


class _FakeHTTP:
    """Captures the JSON payload of the next ``/api/chat`` POST (batch or stream)."""

    def __init__(self) -> None:
        self.payload: dict | None = None

    async def post(self, url: str, *, json: dict | None = None) -> _FakeResp:
        self.payload = json
        return _FakeResp()

    def stream(self, method: str, url: str, *, json: dict | None = None, timeout=None):
        self.payload = json
        return _FakeStream()

    async def aclose(self) -> None:
        pass


class _FakeStream:
    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *exc) -> None:
        pass

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        yield '{"message": {"content": "ok"}, "done": true, "eval_count": 1}'


def _faked(**kwargs) -> OllamaClient:
    client = OllamaClient("http://x", "mistral-nemo", **kwargs)
    asyncio.run(client._client.aclose())
    client._client = _FakeHTTP()  # type: ignore[assignment]
    return client


def test_repeat_penalty_rides_on_the_batch_payload() -> None:
    client = _faked(repeat_penalty=1.1, repeat_last_n=256)
    asyncio.run(client.chat("sys", [{"role": "user", "content": "hi"}]))
    opts = client._client.payload["options"]  # type: ignore[attr-defined]
    assert opts["repeat_penalty"] == 1.1
    assert opts["repeat_last_n"] == 256


def test_repeat_penalty_rides_on_the_stream_payload() -> None:
    # Streaming is the live path — the anti-repetition setting must reach it too, not just batch.
    client = _faked(repeat_penalty=1.15, repeat_last_n=128)

    async def _drain() -> None:
        async for _ in client.chat_stream("sys", [{"role": "user", "content": "hi"}]):
            pass

    asyncio.run(_drain())
    opts = client._client.payload["options"]  # type: ignore[attr-defined]
    assert opts["repeat_penalty"] == 1.15
    assert opts["repeat_last_n"] == 128


def test_no_repeat_keys_when_unset() -> None:
    # Default construction (e.g. tests / callers that don't tune it) sends no repeat keys, so the
    # model default applies and existing payload expectations are unchanged.
    client = _faked()
    asyncio.run(client.chat("sys", []))
    opts = client._client.payload["options"]  # type: ignore[attr-defined]
    assert "repeat_penalty" not in opts
    assert "repeat_last_n" not in opts


def test_caller_options_override_instance_repeat_penalty() -> None:
    # A per-call option still wins over the instance default (parity with how num_ctx behaves).
    client = _faked(repeat_penalty=1.1)
    asyncio.run(client.chat("sys", [], options={"repeat_penalty": 1.3}))
    assert client._client.payload["options"]["repeat_penalty"] == 1.3  # type: ignore[attr-defined]


def test_roll_router_call_disables_repeat_penalty() -> None:
    # The constrained-JSON classifier (ADR 014 / golden rule #2) must stay deterministic: B1's
    # narration default must NOT ride on it, or the penalty fights the very skill/difficulty enum
    # the router has to pick (its system prompt lists them all inside the look-back window).
    from dmbot.orchestrator import DMBrain
    from dmbot.rules import profile as profile_mod

    client = _faked(repeat_penalty=1.1, repeat_last_n=256)
    brain = DMBrain(client, profile=profile_mod.load("imperium_maledictum"))
    asyncio.run(brain.classify_test(action="Ich schleiche an der Wache vorbei",
                                    character="Seskin", skills=["Heimlichkeit"]))
    opts = client._client.payload["options"]  # type: ignore[attr-defined]
    assert opts["repeat_penalty"] == 1.0   # explicitly neutralised for the verdict
    assert opts["repeat_last_n"] == 0
