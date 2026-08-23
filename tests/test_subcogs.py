"""Unit tests for the thin SceneCog / LoreCog split off DMCog (ADR 039).

These commands had no tests while they lived in the turn-pipeline cog — the split is exactly
what gives them a seam testable without a real runtime: `object.__new__(Cog)` + a stub runtime
(the test_autorecap pattern), call `Cog.<cmd>.callback(cog, ctx, ...)` or the helper directly.
No LLM, no TTS, no network. Bot replies are German; assertions match the German strings.
"""
import asyncio
import types
from pathlib import Path

from dmbot.memory.state import WorldState
from dmbot.rules.scene_flow import MoveTrigger
from dmbot.voice.scenecog import SceneCog
from dmbot.voice.lorecog import LoreCog


class _Ctx:
    """Minimal command context: captures ctx.send(...) content + kwargs."""

    def __init__(self, guild_id: int | None = 1) -> None:
        self.sent: list[str] = []
        self.kwargs: list[dict] = []
        self.channel = object()
        self.guild = types.SimpleNamespace(id=guild_id) if guild_id is not None else None

    async def send(self, content: str = "", **kwargs) -> None:
        if content:
            self.sent.append(content)
        if kwargs:
            self.kwargs.append(kwargs)


def _scene_cog(rt) -> SceneCog:
    cog = object.__new__(SceneCog)
    cog._rt = rt
    return cog


def _lore_cog(rt) -> LoreCog:
    cog = object.__new__(LoreCog)
    cog._rt = rt
    return cog


# --- SceneCog (!ort / !szenen / !ortmodus) -------------------------------------------------

def test_ortmodus_no_arg_shows_current_mode() -> None:
    rt = types.SimpleNamespace(_scene_mode="verbunden")
    ctx = _Ctx()
    asyncio.run(SceneCog.ortmodus.callback(_scene_cog(rt), ctx, ""))
    assert rt._scene_mode == "verbunden"  # unchanged
    assert any("verbunden" in m for m in ctx.sent)


def test_ortmodus_sets_valid_mode() -> None:
    rt = types.SimpleNamespace(_scene_mode="verbunden")
    ctx = _Ctx()
    asyncio.run(SceneCog.ortmodus.callback(_scene_cog(rt), ctx, "frei"))
    assert rt._scene_mode == "frei"
    assert any("frei" in m.lower() for m in ctx.sent)


def test_ortmodus_rejects_unknown_mode() -> None:
    rt = types.SimpleNamespace(_scene_mode="verbunden")
    ctx = _Ctx()
    asyncio.run(SceneCog.ortmodus.callback(_scene_cog(rt), ctx, "quatsch"))
    assert rt._scene_mode == "verbunden"  # not mutated by an invalid value
    assert any("Unbekannter Modus" in m for m in ctx.sent)


def test_ort_without_adventure_reports_missing() -> None:
    rt = types.SimpleNamespace(_adventure=None)
    ctx = _Ctx()
    asyncio.run(SceneCog.ort.callback(_scene_cog(rt), ctx, ""))
    assert any("Kein Abenteuer geladen" in m for m in ctx.sent)


def _move_scene_runtime(scene, *, known: str = "s2"):
    """A stub runtime that records the move_scene call !ort makes."""
    calls: dict = {}

    async def _move_scene(channel, scene_id, *, trigger=None, announce=True):
        calls["args"] = (channel, scene_id, trigger, announce)
        return scene if scene_id == known else None

    rt = types.SimpleNamespace(
        _adventure=types.SimpleNamespace(),
        _brain_channel=lambda ch: 7,
        _state={7: types.SimpleNamespace(scene_id="s1")},
        move_scene=_move_scene,
    )
    return rt, calls


def test_ort_moves_the_pointer_through_the_shared_move_scene() -> None:
    # golden rule #3 (code moves the pointer, never the model) AND the runtime docstring's rule
    # that all four movers share ONE move_scene: persist, NPC registration, NPC-memory mining,
    # travel time, overlay and panel belong to it (covered in tests/test_turn_boundary.py), so
    # !ort contributes only the trigger and its own reply instead of a hand-copied sequence.
    scene = types.SimpleNamespace(id="s2", title_de="Die Brücke", part=2)
    rt, calls = _move_scene_runtime(scene)
    ctx = _Ctx()
    asyncio.run(SceneCog.ort.callback(_scene_cog(rt), ctx, "s2"))
    channel, scene_id, trigger, announce = calls["args"]
    assert (channel, scene_id) == (ctx.channel, "s2")
    assert trigger is MoveTrigger.COMMAND  # a misfiring mover stays attributable (ADR 057)
    assert announce is False  # the cog answers in the channel the command came from
    assert any("Szene gewechselt" in m and "Die Brücke" in m for m in ctx.sent)


def test_ort_may_target_a_scene_the_automation_would_never_propose() -> None:
    # the point of the command: the human at the table is not bound to the current scene's
    # exits, so the raw id goes to move_scene unfiltered (the exit check lives in the
    # classifier path, not here).
    scene = types.SimpleNamespace(id="geheimlabor", title_de="Das Labor", part=4)
    rt, calls = _move_scene_runtime(scene, known="geheimlabor")
    ctx = _Ctx()
    asyncio.run(SceneCog.ort.callback(_scene_cog(rt), ctx, "geheimlabor"))
    assert calls["args"][1] == "geheimlabor"
    assert any("Das Labor" in m for m in ctx.sent)


def test_ort_unknown_scene_reports_and_says_nothing_else() -> None:
    rt, _ = _move_scene_runtime(types.SimpleNamespace())  # every id but "s2" is unknown
    ctx = _Ctx()
    asyncio.run(SceneCog.ort.callback(_scene_cog(rt), ctx, "nope"))
    assert len(ctx.sent) == 1
    assert "Unbekannte Szene" in ctx.sent[0]


# --- SceneCog (!fakt — the ADR-058 retraction) ---------------------------------------------

def _fact_runtime(state: WorldState):
    """Stub runtime with a REAL WorldState: !fakt reads and revokes hard facts, and both
    writers under it (revoke_fact / take_item) had no caller at all before this command."""
    flags: dict = {}

    async def _panel():
        flags["panel"] = True

    rt = types.SimpleNamespace(
        _brain_channel=lambda ch: 7,
        _state={7: state},
        _persist_and_refresh=lambda ch: flags.__setitem__("persisted", True),
        update_player_panel=_panel,
    )
    return rt, flags


def test_fakt_lists_the_open_facts() -> None:
    state = WorldState()
    state.give_item("Zollvollmacht", by="Seneschall Kaad")
    state.record_promise("Freies Geleit", by="Kaad")
    rt, _ = _fact_runtime(state)
    ctx = _Ctx()
    asyncio.run(SceneCog.fakt.callback(_scene_cog(rt), ctx))
    joined = "\n".join(ctx.sent)
    # kind, label, holder, source and the in-game time the code-owned clock stamped (ADR 058)
    assert "Gegenstand: Zollvollmacht → Gruppe (von Seneschall Kaad, Tag 1, 08:00)" in joined
    assert "Zusage: Freies Geleit → Gruppe (von Kaad, Tag 1, 08:00)" in joined
    assert "!fakt weg" in joined  # the listing tells the table how to take one back


def test_fakt_without_any_facts_says_so() -> None:
    rt, _ = _fact_runtime(WorldState())
    ctx = _Ctx()
    asyncio.run(SceneCog.fakt.callback(_scene_cog(rt), ctx))
    assert any("Keine harten Fakten" in m for m in ctx.sent)


def test_fakt_weg_revokes_the_fact_and_refreshes_prompt_and_panel() -> None:
    state = WorldState()
    state.give_item("Zollvollmacht", by="Kaad")
    rt, flags = _fact_runtime(state)
    ctx = _Ctx()
    asyncio.run(SceneCog.fakt_weg.callback(_scene_cog(rt), ctx, text="  zollvollmacht  "))
    assert state.open_facts() == []  # matched case-insensitively, on the trimmed label
    assert state.facts[0].status == "revoked"
    assert flags.get("persisted") is True  # gone from the next prompt (ADR 058)
    assert flags.get("panel") is True
    assert any("Fakt zurückgenommen" in m and "Zollvollmacht" in m for m in ctx.sent)


def test_fakt_weg_unknown_label_changes_nothing() -> None:
    state = WorldState()
    state.give_item("Zollvollmacht", by="Kaad")
    rt, flags = _fact_runtime(state)
    ctx = _Ctx()
    asyncio.run(SceneCog.fakt_weg.callback(_scene_cog(rt), ctx, text="Ossarium"))
    assert len(state.open_facts()) == 1
    assert "persisted" not in flags
    assert any("Kein offener Fakt" in m for m in ctx.sent)


def test_fakt_weg_without_a_label_prints_its_usage() -> None:
    state = WorldState()
    state.give_item("Zollvollmacht", by="Kaad")
    rt, flags = _fact_runtime(state)
    ctx = _Ctx()
    asyncio.run(SceneCog.fakt_weg.callback(_scene_cog(rt), ctx, text=""))
    assert len(state.open_facts()) == 1 and "persisted" not in flags
    assert any("Nutzung: `!fakt weg <Text>`" in m for m in ctx.sent)


def test_fakt_without_a_session_reports_instead_of_crashing() -> None:
    rt = types.SimpleNamespace(_brain_channel=lambda ch: 7, _state={})
    ctx = _Ctx()
    asyncio.run(SceneCog.fakt.callback(_scene_cog(rt), ctx))
    assert any("Keine aktive Sitzung" in m for m in ctx.sent)


# --- LoreCog (!lore) -----------------------------------------------------------------------

def test_lore_question_without_rag_store_reports() -> None:
    rt = types.SimpleNamespace(_retriever=types.SimpleNamespace(available=lambda: False))
    ctx = _Ctx()
    asyncio.run(_lore_cog(rt)._lore_question(ctx, "wer ist der Imperator?"))
    assert any("Kein RAG-Store" in m for m in ctx.sent)


def test_lore_question_no_hits_reports() -> None:
    async def _lookup(question, sources=None):
        return []

    rt = types.SimpleNamespace(
        _retriever=types.SimpleNamespace(available=lambda: True, lookup=_lookup),
    )
    ctx = _Ctx()
    asyncio.run(_lore_cog(rt)._lore_question(ctx, "irgendwas erfundenes"))
    assert any("Dazu steht nichts im Weltwissen" in m for m in ctx.sent)


def test_lore_question_renders_hits_as_embed() -> None:
    async def _lookup(question, sources=None):
        return [("lore_imperium", "Der Imperator", "Er sitzt auf dem Goldenen Thron.", 0.2)]

    embeds = []

    async def _send_with_retry(channel, **kwargs):
        embeds.append(kwargs.get("embed"))

    rt = types.SimpleNamespace(
        _retriever=types.SimpleNamespace(available=lambda: True, lookup=_lookup),
        _send_with_retry=_send_with_retry,
    )
    asyncio.run(_lore_cog(rt)._lore_question(_Ctx(), "wer ist der Imperator?"))
    assert embeds and embeds[0] is not None
    embed = embeds[0]
    assert "Weltwissen" in embed.title
    assert "Goldenen Thron" in embed.description
    assert "Imperium" in embed.description  # source label mapped via _LORE_SOURCE_NAMES


def test_lore_tts_without_voice_reports() -> None:
    rt = types.SimpleNamespace(_tts_enabled=False)
    ctx = _Ctx()
    asyncio.run(_lore_cog(rt)._lore_speak(ctx, Path("."), "imperium"))
    assert any("Keine TTS-Stimme" in m for m in ctx.sent)
