"""Global spoken-delivery mode (ADR 033): the two axes `DM_SPEECH_MODE` (stream|nahtlos) and
`DM_SPEECH_PUNCT` (flach|intoniert), their config parsing, and the runtime helpers that map them
to a per-sentence transform + a seamless flag. The audio dispatch itself is verified live; the
decidable wiring is pinned here.
"""

from __future__ import annotations

from types import SimpleNamespace

from dmbot.config import Config
from dmbot.runtime import SessionRuntime
from dmbot.tts.textsplit import strip_speech_punctuation


def _isolate(monkeypatch):
    """Make Config.load() read ONLY the process env (no real .env), with a dummy token."""
    monkeypatch.setattr("dmbot.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("DISCORD_TOKEN_DMBOT", "test-token")


def test_speech_config_defaults(monkeypatch):
    _isolate(monkeypatch)
    monkeypatch.delenv("DM_SPEECH_MODE", raising=False)
    monkeypatch.delenv("DM_SPEECH_PUNCT", raising=False)
    cfg = Config.load()
    assert cfg.speech_mode == "stream"
    assert cfg.speech_punct == "flach"


def test_speech_config_parses_valid_values(monkeypatch):
    _isolate(monkeypatch)
    monkeypatch.setenv("DM_SPEECH_MODE", "Nahtlos")     # case/space tolerant
    monkeypatch.setenv("DM_SPEECH_PUNCT", " intoniert ")
    cfg = Config.load()
    assert cfg.speech_mode == "nahtlos"
    assert cfg.speech_punct == "intoniert"


def test_speech_config_unknown_falls_back_to_default(monkeypatch):
    _isolate(monkeypatch)
    monkeypatch.setenv("DM_SPEECH_MODE", "turbo")
    monkeypatch.setenv("DM_SPEECH_PUNCT", "schrei")
    cfg = Config.load()
    assert cfg.speech_mode == "stream"
    assert cfg.speech_punct == "flach"


# --- runtime helpers (tested as unbound methods on a stub, no full runtime needed) ----------

def test_speech_transform_maps_punct_axis():
    # flach → strip ALL punctuation; intoniert → None (wrapper keeps punctuation for prosody)
    assert SessionRuntime.speech_transform(SimpleNamespace(_speech_punct="flach")) is strip_speech_punctuation
    assert SessionRuntime.speech_transform(SimpleNamespace(_speech_punct="intoniert")) is None


def test_deliver_seamless_maps_mode_axis():
    assert SessionRuntime.deliver_seamless(SimpleNamespace(_speech_mode="nahtlos")) is True
    assert SessionRuntime.deliver_seamless(SimpleNamespace(_speech_mode="stream")) is False
