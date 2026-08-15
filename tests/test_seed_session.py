"""Unit tests for SessionRuntime.seed_session (candidate #4 refactor): the !join session-seed
sequence bundled into one runtime method.

These pin the decidable parts of the seed order without the heavy runtime __init__ or Discord:
a fresh state picks up the adventure start scene, a loaded state keeps its stored pointer, a
None adventure leaves the pointer untouched, the turn order is seeded from the voice members and
the index reset, the example-party fallback flag is returned through, and the D41 crash-recovery
restore fires only with autosave on. The brain / character store / persistence are faked — the
real wiring is exercised by the live voice stack and the existing autorecap/history tests.
"""

from __future__ import annotations

from types import SimpleNamespace

from dmbot.runtime import SessionRuntime


# ---- stubs --------------------------------------------------------------------------------

class _FakeStore:
    """Stands in for CharacterStore: only the two hint accessors seed_session calls."""

    def alias_hint_de(self) -> str:
        return "ALIAS_HINT"

    def speaker_labels(self) -> list[str]:
        return ["Mortn", "Seskin", "Vask"]


class _FakeBrain:
    """Records the brain calls seed_session makes; restore_history returns a fixed count."""

    def __init__(self, *, restore_return: int = 0) -> None:
        self.max_history_turns = 20
        self.alias_hints: dict[int, str] = {}
        self.known_speakers: dict[int, list[str]] = {}
        self.restore_calls: list[tuple[int, object]] = []
        self._restore_return = restore_return

    def set_alias_hint(self, channel_id: int, hint: str) -> None:
        self.alias_hints[channel_id] = hint

    def set_known_speakers(self, channel_id: int, names: list[str]) -> None:
        self.known_speakers[channel_id] = names

    def restore_history(self, channel_id: int, turns) -> int:
        self.restore_calls.append((channel_id, turns))
        return self._restore_return

    def history_len(self, channel_id: int) -> int:
        return 0  # seed_session seeds the NPC-memory mark from it (ADR 044)


def _make_runtime(
    *,
    adventure,
    state_obj,
    fallback: bool = False,
    autosave: bool = False,
    restore_return: int = 0,
) -> SessionRuntime:
    """A SessionRuntime with __init__ skipped, wired with only the attributes seed_session
    touches: stub brain + character store, dict-valued per-channel maps, and stubbed loaders /
    persistence as plain lambdas so nothing reaches disk or Discord."""
    rt = SessionRuntime.__new__(SessionRuntime)
    rt._brain = _FakeBrain(restore_return=restore_return)
    rt._adventure = adventure
    rt._autosave = autosave
    rt._active_vc_id = None
    rt._text_channel = None
    rt._characters = None
    rt._state = {}
    rt._turn_order = {}
    rt._turn_index = {}
    rt._npc_mem_marks = {}

    rt._persist_calls: list[object] = []  # recorder for _persist_and_refresh

    rt._load_characters = lambda cid: (_FakeStore(), fallback)
    rt._build_turn_order = lambda voice_channel: ["A", "B", "C"]
    rt._load_or_seed_state = lambda cid: state_obj
    rt._persist_and_refresh = lambda voice_channel: rt._persist_calls.append(voice_channel)
    return rt


def _channels(cid: int = 4242):
    """A (voice, text) channel pair — only .id is read off the voice channel."""
    voice = SimpleNamespace(id=cid, name="Tisch", members=[])
    text = SimpleNamespace(id=cid + 1, name="text")
    return voice, text


# ---- scene pointer ------------------------------------------------------------------------

def _adventure(*, start_scene: str = "szene_01", scenes=("szene_01", "szene_07")):
    """An adventure stub that knows exactly ``scenes`` — enough for the pointer bootstrap, which
    only asks for ``start_scene``, ``id`` and ``get_scene``."""
    return SimpleNamespace(
        id="testabenteuer",
        start_scene=start_scene,
        get_scene=lambda sid: SimpleNamespace(id=sid) if sid in scenes else None,
    )


def test_fresh_state_gets_adventure_start_scene() -> None:
    state = SimpleNamespace(scene_id="")  # fresh: no stored pointer
    rt = _make_runtime(adventure=_adventure(), state_obj=state)
    voice, text = _channels()

    rt.seed_session(voice, text)

    assert rt._state[voice.id] is state
    assert state.scene_id == "szene_01"  # pointed at the start scene


def test_loaded_state_keeps_its_stored_scene() -> None:
    state = SimpleNamespace(scene_id="szene_07")  # a loaded state with a saved position
    rt = _make_runtime(adventure=_adventure(), state_obj=state)
    voice, text = _channels()

    rt.seed_session(voice, text)

    assert state.scene_id == "szene_07"  # the stored pointer survives, not overwritten


def test_foreign_scene_pointer_reseeds_to_start_scene(caplog) -> None:
    # Live 2026-08-15 (ADR 056): DM_ADVENTURE was switched, but the channel's saved state still
    # pointed at the PREVIOUS campaign's scene. Every get_scene() came back None, so the session
    # ran with no scene card and no 🧪 overlay. A pointer the loaded adventure doesn't know must
    # re-seed to the start scene — and say so.
    state = SimpleNamespace(scene_id="rokarth_gasse")  # belongs to another adventure
    rt = _make_runtime(adventure=_adventure(), state_obj=state)
    voice, text = _channels()

    with caplog.at_level("WARNING"):
        rt.seed_session(voice, text)

    assert state.scene_id == "szene_01"
    assert "rokarth_gasse" in caplog.text and "unknown to adventure" in caplog.text


def test_no_adventure_leaves_scene_untouched() -> None:
    state = SimpleNamespace(scene_id="")
    rt = _make_runtime(adventure=None, state_obj=state)
    voice, text = _channels()

    rt.seed_session(voice, text)

    assert state.scene_id == ""  # no adventure → nothing to point at


# ---- turn order + active/text channel -----------------------------------------------------

def test_turn_order_seeded_and_index_reset() -> None:
    state = SimpleNamespace(scene_id="x")
    rt = _make_runtime(adventure=None, state_obj=state)
    voice, text = _channels()

    rt.seed_session(voice, text)

    assert rt._turn_order[voice.id] == ["A", "B", "C"]  # from _build_turn_order(voice_channel)
    assert rt._turn_index[voice.id] == 0
    assert rt._active_vc_id == voice.id
    assert rt._text_channel is text
    # alias + speaker hints wired into the brain for this channel
    assert rt._brain.alias_hints[voice.id] == "ALIAS_HINT"
    assert rt._brain.known_speakers[voice.id] == ["Mortn", "Seskin", "Vask"]
    assert rt._persist_calls == [voice]  # persisted + refreshed once, with the voice channel


# ---- fallback flag passthrough ------------------------------------------------------------

def test_char_fallback_flag_returned_through() -> None:
    state = SimpleNamespace(scene_id="x")
    rt_fb = _make_runtime(adventure=None, state_obj=state, fallback=True)
    rt_ok = _make_runtime(adventure=None, state_obj=SimpleNamespace(scene_id="x"), fallback=False)
    voice, text = _channels()

    assert rt_fb.seed_session(voice, text) is True
    assert rt_ok.seed_session(voice, text) is False


# ---- D41 crash-recovery restore -----------------------------------------------------------

def test_autosave_on_calls_restore_history(monkeypatch) -> None:
    state = SimpleNamespace(scene_id="x")
    rt = _make_runtime(adventure=None, state_obj=state, autosave=True, restore_return=3)
    voice, text = _channels()

    # Stub the module-level history_store.load_recent so nothing touches disk.
    import dmbot.runtime as runtime_mod

    sentinel_turns = [("user", "Timo: Wir gehen."), ("assistant", "Ihr steht im Schacht.")]
    rt._history_path = lambda cid: f"/fake/history/{cid}.jsonl"
    monkeypatch.setattr(
        runtime_mod.history_store, "load_recent", lambda path, n: sentinel_turns
    )
    headers: list[dict] = []  # the replay-journal session header (ADR 046) — no disk in tests
    monkeypatch.setattr(
        runtime_mod.history_store, "append_event", lambda path, record: headers.append(record)
    )

    rt.seed_session(voice, text)

    assert rt._brain.restore_calls == [(voice.id, sentinel_turns)]
    # One header per !join (ADR 046) + the opening scene event (ADR 053) — here the state's
    # *restored* pointer, so a rotated-fresh journal still opens with a scene.
    assert [h["kind"] for h in headers] == ["session", "scene"]
    assert headers[1]["scene_id"] == "x"


def _stub_journal(rt, monkeypatch) -> list[dict]:
    """Route the seed's journal writes into a list — no disk in tests."""
    import dmbot.runtime as runtime_mod

    events: list[dict] = []
    rt._history_path = lambda cid: f"/fake/history/{cid}.jsonl"
    monkeypatch.setattr(runtime_mod.history_store, "load_recent", lambda path, n: [])
    monkeypatch.setattr(
        runtime_mod.history_store, "append_event", lambda path, record: events.append(record)
    )
    return events


def test_join_start_scene_assignment_is_journaled(monkeypatch) -> None:
    """ADR 053: the initial start-scene seed on !join writes a scene event, so the first chunk
    of a fresh session has a scene."""
    state = SimpleNamespace(scene_id="")  # fresh: the seed assigns the start scene
    adventure = SimpleNamespace(start_scene="szene_01", id="abenteuer")  # header reads .id
    rt = _make_runtime(adventure=adventure, state_obj=state, autosave=True)
    voice, text = _channels()
    events = _stub_journal(rt, monkeypatch)

    rt.seed_session(voice, text)

    assert [e["kind"] for e in events] == ["session", "scene"]
    assert events[1]["scene_id"] == "szene_01"


def test_join_without_scene_writes_no_scene_event(monkeypatch) -> None:
    state = SimpleNamespace(scene_id="")  # no adventure → the pointer stays empty
    rt = _make_runtime(adventure=None, state_obj=state, autosave=True)
    voice, text = _channels()
    events = _stub_journal(rt, monkeypatch)

    rt.seed_session(voice, text)

    assert [e["kind"] for e in events] == ["session"]  # header only, no empty scene event


def test_autosave_off_skips_restore_history() -> None:
    state = SimpleNamespace(scene_id="x")
    rt = _make_runtime(adventure=None, state_obj=state, autosave=False)
    voice, text = _channels()

    rt.seed_session(voice, text)

    assert rt._brain.restore_calls == []  # autosave off → no crash-recovery restore
