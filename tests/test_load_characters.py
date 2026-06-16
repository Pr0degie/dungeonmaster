"""Unit tests for SessionRuntime._load_characters resolution order (D82 default party).

A voice channel's party is resolved in order: the channel-specific
``data/sessions/<id>/characters.json`` → the configured default party
(``data/sessions/<default>/characters.json``) → the generic ``_example`` party. Only the last,
example-party case sets the loud ``fallback`` flag (D43) — the default party is the *intended*
fallback and loads silently, so a teammate's clone and any new voice channel get the real party
without binding it to one channel id.
"""

from __future__ import annotations

import json
from pathlib import Path

from dmbot.runtime import SessionRuntime


def _write_party(path: Path, *names: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"characters": [{"name": n} for n in names]}), encoding="utf-8")


def _runtime(default_party: str) -> SessionRuntime:
    """A SessionRuntime with __init__ skipped — _load_characters only needs _default_party."""
    rt = object.__new__(SessionRuntime)
    rt._default_party = default_party
    return rt


def _seed(tmp_path: Path, monkeypatch) -> None:
    sessions = tmp_path / "sessions"
    _write_party(sessions / "_example" / "characters.json", "Seskin", "Vask", "Mortn")
    _write_party(sessions / "_default" / "characters.json", "Fridolin", "Gellicus")
    _write_party(sessions / "123" / "characters.json", "ChannelOnly")
    monkeypatch.setattr("dmbot.runtime._DATA_DIR", tmp_path)


def test_channel_sheet_wins(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    store, fallback = _runtime("_default")._load_characters(123)
    assert [c.name for c in store.characters()] == ["ChannelOnly"]
    assert fallback is False


def test_default_party_used_when_no_channel_sheet(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    store, fallback = _runtime("_default")._load_characters(999)  # no sheet for this channel
    assert [c.name for c in store.characters()] == ["Fridolin", "Gellicus"]
    assert fallback is False  # the intended default party — no loud warning


def test_example_fallback_only_without_a_default(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    store, fallback = _runtime("")._load_characters(999)  # default party disabled
    assert [c.name for c in store.characters()] == ["Seskin", "Vask", "Mortn"]
    assert fallback is True  # genuine misconfig → !join warns


def test_missing_default_party_dir_falls_through_to_example(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)
    store, fallback = _runtime("_does_not_exist")._load_characters(999)
    assert [c.name for c in store.characters()] == ["Seskin", "Vask", "Mortn"]
    assert fallback is True


def test_boot_load_none_channel_uses_default_party(tmp_path: Path, monkeypatch) -> None:
    # __init__ calls _load_characters(None) before any !join — it should pick up the default party
    # so !test/!roll work out of the box with the real party, not the example one.
    _seed(tmp_path, monkeypatch)
    store, fallback = _runtime("_default")._load_characters(None)
    assert [c.name for c in store.characters()] == ["Fridolin", "Gellicus"]
    assert fallback is False
