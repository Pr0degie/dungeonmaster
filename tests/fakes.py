"""Shared, complete test doubles for the runtime and the brain.

The production code accesses its own attributes directly — no ``getattr`` guards for half-built
test objects. These builders are why that works: every double here is *complete by
construction*, so a test sets only what it cares about and the rest is the real default.

- :func:`make_runtime` runs the real ``SessionRuntime.__init__`` with only the heavy edges
  swapped out (voice preflight, STT worker, TTS load thread, LLM client, RAG store, the bridge's
  HTTP client, the party file). Every attribute ``__init__`` sets exists — and stays in sync
  automatically when ``__init__`` grows a new one.
- :class:`FakeBrain` is a real :class:`DMBrain` over a :class:`FakeLLMClient`. Tests subclass it
  and override just the methods they script (``classify_scene_move``, ``take_pending_uhr`` …);
  everything else is the real brain.
- :func:`make_config` is a full :class:`Config` with test defaults: every optional layer that a
  test has to opt into (autosave, panels, dice images, routers, auto-join, kick phrase) is off.
"""

from __future__ import annotations

import dataclasses
import threading
from types import SimpleNamespace
from unittest import mock

from dmbot import runtime as runtime_mod
from dmbot.config import Config
from dmbot.orchestrator import DMBrain
from dmbot.rules.profile import ProfileError, SystemProfile
from dmbot.runtime import SessionRuntime

# Every required Config field, with the value a test runtime should start from. Optional
# layers are off so a test opts into exactly the mechanism it exercises.
_CONFIG_DEFAULTS: dict[str, object] = {
    "discord_token": "test-token",
    "ollama_host": "http://127.0.0.1:11434",
    "ollama_model": "fake",
    "ollama_num_ctx": 8192,
    "ollama_repeat_penalty": 1.0,
    "ollama_repeat_last_n": 64,
    "bridge_host": "127.0.0.1",
    "bridge_port": 8765,
    "bridge_secret": "",
    "bot_a_user_id": None,
    "log_level": "INFO",
    "log_to_file": False,
    "transcript_file": False,
    "whisper_model": "fake",
    "whisper_device": "cpu",
    "whisper_compute": "int8",
    "dump_utterances": False,
    "tts_engine": "piper",
    "tts_voice": "",
    "tts_speaker": "",
    "tts_device": "cpu",
    "dm_num_predict": 220,
    "dm_intro_num_predict": 600,
    "dm_intro_temperature": 0.6,
    "dm_max_lines": 8,
    "system": "",
    "adventure": "",
    "default_party": "",
    "push_to_talk": False,
    "pause_vad_while_speaking": False,
    "button_autosend": False,
    "roll_router": False,
    "streaming": False,
    "autosave": False,
    "session_memory": False,
    "autorecap": False,
    "scene_mode": "verbunden",
    "flag_confirm": True,
    "scene_time_advance": 0,
    "npc_memory": False,
    "npc_memory_top_k": 3,
    "consistency_guard": False,
    "scene_router": False,
    "scene_flag_gate": False,
    "fact_router": False,
    "turn_time_advance": 0,
    "scene_undo_seconds": 0,
    "guidance_every": 1,
    "player_panel": False,
    "debug_overlay": False,
    "debug_channel_id": 0,
    "speech_mode": "stream",
    "speech_punct": "flach",
    "speech_prebuffer": 2,
    # optional Config fields whose production default would switch a layer on
    "npc_router": False,
    "dice_images": False,
    "dice_animation": False,
    "auto_join": False,
    "ready_sound": False,
    "kick_phrase": False,
}


def make_config(**overrides) -> Config:
    """A complete :class:`Config` with the test defaults above; ``overrides`` win."""
    values = {**_CONFIG_DEFAULTS, **overrides}
    known = {f.name for f in dataclasses.fields(Config)}
    unknown = set(values) - known
    if unknown:
        raise TypeError(f"unknown Config field(s): {sorted(unknown)}")
    return Config(**values)


class FakeLLMClient:
    """The full ``LLMClient`` surface (ADR 061) with scripted answers and recorded calls.

    ``replies`` are handed out in order by ``chat`` and ``chat_stream`` (the stream yields the
    whole reply as one piece); once they run out every call answers ``""``."""

    def __init__(self, replies: list[str] | tuple[str, ...] = ()) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.last_stats: dict | None = None

    @property
    def model(self) -> str:
        return "fake"

    def _next(self) -> str:
        return self.replies.pop(0) if self.replies else ""

    async def chat(self, system, messages, *, options=None, format=None) -> str:
        self.calls.append({"system": system, "messages": list(messages),
                           "options": options, "format": format})
        return self._next()

    async def chat_stream(self, system, messages, *, options=None):
        self.calls.append({"system": system, "messages": list(messages),
                           "options": options, "format": None})
        reply = self._next()
        if reply:
            yield reply

    async def aclose(self) -> None:
        return None


class FakeBrain(DMBrain):
    """A real :class:`DMBrain` driving a :class:`FakeLLMClient`.

    Subclass it and override only what the test scripts; call ``super().__init__()`` first so
    the brain's own state (buffers, pending markers, replay capture) exists."""

    def __init__(self, *, client: FakeLLMClient | None = None,
                 profile: SystemProfile | None = None, **kwargs) -> None:
        super().__init__(client if client is not None else FakeLLMClient(), profile=profile,
                         **kwargs)


def make_brain(*, client: FakeLLMClient | None = None, profile: SystemProfile | None = None,
               **overrides) -> FakeBrain:
    """A :class:`FakeBrain` with ``overrides`` set as attributes — a scripted method
    (``take_pending_scenes=lambda cid: [...]``) or brain state (``last_router={...}``)."""
    brain = FakeBrain(client=client, profile=profile)
    for key, value in overrides.items():
        setattr(brain, key, value)
    return brain


class _FakeTranscriber:
    """Stands in for the faster-whisper worker: nothing is loaded, nothing transcribed."""

    def __init__(self, on_text, **kwargs) -> None:
        self.on_text = on_text
        self.submitted: list[tuple] = []

    def start(self) -> None:
        return None

    def submit(self, *args, **kwargs) -> None:
        self.submitted.append((args, kwargs))

    def wait_idle(self, timeout: float = 3.0) -> bool:
        return True

    def stop(self) -> None:
        return None


class _FakeRetriever:
    """No RAG store: ``available()`` is False, so the brain runs without retrieval."""

    def __init__(self, db_path, **kwargs) -> None:
        self._db_path = db_path

    def available(self) -> bool:
        return False

    async def fetch_block(self, *args, **kwargs) -> str:
        return ""

    def lookup(self, *args, **kwargs) -> list:
        return []

    async def aclose(self) -> None:
        return None


class _FakeBridge:
    """The bridge without its httpx client — tests replace it when they assert on /speak."""

    def __init__(self, host, port, *, secret: str = "", timeout: float = 300.0) -> None:
        self.spoken: list = []

    async def health(self) -> dict | None:
        return None

    async def speak(self, *args, **kwargs) -> None:
        self.spoken.append((args, kwargs))

    async def aclose(self) -> None:
        return None


class _NoThread:
    """``threading.Thread`` for the TTS load: never started (no TTS backend in tests)."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        return None


def make_runtime(*, brain: DMBrain | None = None, profile: SystemProfile | None = None,
                 config: Config | None = None, **overrides) -> SessionRuntime:
    """A real :class:`SessionRuntime`, built through its own ``__init__``.

    ``config`` defaults to :func:`make_config`; ``profile`` is what the profile load returns
    (``None`` = no dice engine, as with a missing profile); ``brain`` replaces the built brain
    (default: a :class:`FakeBrain` with the same profile). The party starts empty
    (``_characters`` is ``None``) and no TTS backend is loaded (text-only). ``overrides`` are
    set as attributes afterwards — runtime state (``_autosave=True``) or a method replaced by a
    recorder (``_persist_and_refresh=lambda ch: ...``)."""
    config = config if config is not None else make_config()

    def _load_profile(name):
        if profile is None:
            raise ProfileError("no profile in this test")
        return profile

    fake_threading = SimpleNamespace(Thread=_NoThread, Event=threading.Event)
    with mock.patch.multiple(
        runtime_mod,
        check_static=lambda: None,
        check_tts_speaker=lambda *a, **k: None,
        Transcriber=_FakeTranscriber,
        RulebookRetriever=_FakeRetriever,
        BridgeClient=_FakeBridge,
        build_llm_client=lambda cfg: FakeLLMClient(),
        threading=fake_threading,
    ), mock.patch.object(runtime_mod.profile_mod, "load", _load_profile), \
            mock.patch.object(runtime_mod.log, "exception", lambda *a, **k: None), \
            mock.patch.object(SessionRuntime, "_load_characters",
                              lambda self, channel_id: (None, False)):
        rt = SessionRuntime(config)
    rt._brain = brain if brain is not None else FakeBrain(profile=profile)
    rt._tts_enabled = False
    rt._tts_ready.set()
    for key, value in overrides.items():
        setattr(rt, key, value)
    return rt
