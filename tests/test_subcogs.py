"""Unit tests for the thin SceneCog / LoreCog split off DMCog (ADR 039).

These commands had no tests while they lived in the turn-pipeline cog — the split is exactly
what gives them a seam testable without a real runtime: `object.__new__(Cog)` + a stub runtime
(the test_autorecap pattern), call `Cog.<cmd>.callback(cog, ctx, ...)` or the helper directly.
No LLM, no TTS, no network. Bot replies are German; assertions match the German strings.
"""
import asyncio
import types
from pathlib import Path

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


def test_ort_moves_pointer_via_code_not_llm() -> None:
    # golden rule #3: the command moves the plot pointer deterministically through _set_scene
    # + _persist_and_refresh — the model is never consulted here.
    flags = {}
    scene = types.SimpleNamespace(id="s2", title_de="Die Brücke", part=2)
    rt = types.SimpleNamespace(
        _adventure=types.SimpleNamespace(),
        _brain_channel=lambda ch: 7,
        _state={7: types.SimpleNamespace(scene_id="s1")},
        _set_scene=lambda st, sid: scene if sid == "s2" else None,
        _persist_and_refresh=lambda ch: flags.__setitem__("persisted", True),
    )
    ctx = _Ctx()
    asyncio.run(SceneCog.ort.callback(_scene_cog(rt), ctx, "s2"))
    assert flags.get("persisted") is True
    assert any("Szene gewechselt" in m and "Die Brücke" in m for m in ctx.sent)


def test_ort_unknown_scene_does_not_persist() -> None:
    flags = {}
    rt = types.SimpleNamespace(
        _adventure=types.SimpleNamespace(),
        _brain_channel=lambda ch: 7,
        _state={7: types.SimpleNamespace(scene_id="s1")},
        _set_scene=lambda st, sid: None,  # unknown id
        _persist_and_refresh=lambda ch: flags.__setitem__("persisted", True),
    )
    ctx = _Ctx()
    asyncio.run(SceneCog.ort.callback(_scene_cog(rt), ctx, "nope"))
    assert "persisted" not in flags
    assert any("Unbekannte Szene" in m for m in ctx.sent)


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
