"""Dice result thumbnails (dmbot/dice_images.py, tools/generate_dice.py).

Presentation only: the die picture shows the raw face the engine rolled, in a palette picked from
the engine's critical/fumble flags. The result line, what the DM is fed and the replay journal
stay untouched. Rendering is fail-open — a broken thumbnail never loses a dice result.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from dmbot import dice_images
from dmbot.dice_images import (
    get_dice_image,
    get_dice_image_async,
    palette_for,
    roll_image_value,
)
from dmbot.discord_ui.dice import DICE_FILENAME
from dmbot.rules import engine
from dmbot.rules.profile import load
from dmbot.voice import dicecog
from dmbot.voice.dicecog import DiceCog

_IM = load("imperium_maledictum")


class _Seq:
    def __init__(self, *values: int) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


def _test(face: int, target: int, skill: str) -> engine.TestResult:
    """A test resolved by the engine under the IM profile, crit scope applied like the cog does."""
    return engine.scope_doubles(_IM, engine.resolve_test(_IM, target, _Seq(face)), skill)


# --- cache ---------------------------------------------------------------------------------------

def test_the_first_call_renders_the_image_and_the_second_returns_the_cached_file(tmp_path) -> None:
    first = get_dice_image(42, "red", cache_dir=tmp_path)
    assert first == tmp_path / "red" / "d_42.png" and first.is_file()
    mtime = first.stat().st_mtime_ns
    second = get_dice_image(42, "red", cache_dir=tmp_path)
    assert second == first and second.stat().st_mtime_ns == mtime
    assert [p.name for p in (tmp_path / "red").iterdir()] == ["d_42.png"]  # no temp file left


def test_each_palette_gets_its_own_cache_folder(tmp_path) -> None:
    gold = get_dice_image(100, "gold", cache_dir=tmp_path)
    assert gold == tmp_path / "gold" / "d_100.png" and gold.is_file()
    assert not (tmp_path / "red").exists()


def test_values_outside_the_die_and_unknown_palettes_are_refused(tmp_path) -> None:
    for bad in (0, 101):
        with pytest.raises(ValueError):
            get_dice_image(bad, cache_dir=tmp_path)
    with pytest.raises(ValueError):
        get_dice_image(5, "blue", cache_dir=tmp_path)


def test_a_render_failure_yields_no_image_instead_of_an_error(monkeypatch) -> None:
    def broken(value, palette):
        raise FileNotFoundError("no number (bold) font found")

    monkeypatch.setattr(dice_images, "get_dice_image", broken)
    assert asyncio.run(get_dice_image_async(20, "red")) is None


# --- palette from the engine ---------------------------------------------------------------------

def test_a_critical_attack_is_gold_a_fumbled_attack_green_and_a_plain_result_red() -> None:
    crit = _test(22, 50, "Nahkampf")
    fumble = _test(77, 50, "Fernkampf")
    plain = _test(23, 50, "Nahkampf")
    assert crit.critical and fumble.fumble and not (plain.critical or plain.fumble)
    assert palette_for(crit) == "gold"
    assert palette_for(fumble) == "green"
    assert palette_for(plain) == "red"
    assert palette_for(_test(80, 50, "Nahkampf")) == "red"  # a plain failure is not a fumble


def test_the_profile_decides_whether_a_double_counts() -> None:
    # IM: doubles are critical/fumble on attack tests only (crit_scope "attack") — the engine
    # drops the flag on a skill test, so the picture stays red.
    assert palette_for(_test(22, 50, "Heimlichkeit")) == "red"
    assert palette_for(_test(77, 50, "Heimlichkeit")) == "red"


def test_an_unresolved_roll_is_red() -> None:
    assert palette_for(None) == "red"


# --- !roll ---------------------------------------------------------------------------------------

def test_a_free_roll_shows_its_total_only_while_a_die_image_exists_for_it() -> None:
    assert roll_image_value(engine.roll("2d10+3", _Seq(4, 9))) == 16
    assert roll_image_value(engine.roll("1d100", _Seq(100))) == 100
    assert roll_image_value(engine.roll("2d100", _Seq(60, 70))) is None   # 130 > 100
    assert roll_image_value(engine.roll("1d5-10", _Seq(3))) is None       # -7: no such face
    assert asyncio.run(get_dice_image_async(roll_image_value(engine.roll("2d100", _Seq(60, 70))))) is None


# --- the cog posts the die as a thumbnail --------------------------------------------------------

class _Msg:
    def __init__(self) -> None:
        self.edits: list[dict] = []

    async def edit(self, **kwargs) -> None:
        self.edits.append(kwargs)


class _Ctx:
    def __init__(self) -> None:
        self.sent: list[tuple[tuple, dict]] = []

    async def send(self, *args, **kwargs) -> None:
        self.sent.append((args, kwargs))


def _fake_images(monkeypatch, tmp_path, *, broken: bool = False) -> list[tuple]:
    """Stand in for the renderer: record what was asked, hand back a tiny PNG (or nothing)."""
    asked: list[tuple] = []
    png = tmp_path / "die.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    async def fake(value, palette="red"):
        asked.append((value, palette))
        return None if broken or value is None else png

    monkeypatch.setattr(dicecog, "get_dice_image_async", fake)
    return asked


def _cog(rng, *, images: bool = True):
    narrated: list[int] = []
    fed: list[str] = []

    async def run_and_deliver(channel, guild_id):
        narrated.append(1)

    rt = SimpleNamespace(
        _profile=_IM, _rng=rng, _state={}, _brain_channel=lambda ch: 7, _dice_images=images,
        _brain=SimpleNamespace(add_test_result=lambda cid, line: fed.append(line)),
        run_and_deliver=run_and_deliver,
    )
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt

    async def no_damage_flow(channel, *, attacker, result):  # a hit's damage flow is not under test
        return True

    cog._begin_attack_damage = no_damage_flow
    return cog, fed


def _click(cog, *, face_skill: str, target: int | None = 50):
    req = SimpleNamespace(skill=face_skill, target_name="Fridolin")
    resolved = SimpleNamespace(target=target, difficulty=None, character=None)
    roll = cog._make_dice_roll(SimpleNamespace(guild=None), req, resolved)
    interaction = SimpleNamespace(message=_Msg())
    asyncio.run(roll(interaction))
    return interaction.message


def test_a_dice_button_result_shows_the_raw_face_as_the_big_image(monkeypatch, tmp_path) -> None:
    asked = _fake_images(monkeypatch, tmp_path)
    cog, fed = _cog(_Seq(22))  # a double on an attack: critical
    msg = _click(cog, face_skill="Fernkampf", target=50)
    assert asked == [(22, "gold")]
    (edit,) = msg.edits
    embed = edit["embed"]
    assert edit["content"] is None
    assert embed.image.url == f"attachment://{DICE_FILENAME}"
    assert embed.thumbnail.url is None                  # a button test is big: target, throw, result
    (file,) = edit["attachments"]
    assert file.filename == DICE_FILENAME
    assert embed.description == fed[0]                  # the same line the DM is fed
    assert "kritischer Erfolg" in embed.description


def test_a_roll_without_a_sheet_value_still_shows_its_die(monkeypatch, tmp_path) -> None:
    asked = _fake_images(monkeypatch, tmp_path)
    cog, _ = _cog(_Seq(64))
    _click(cog, face_skill="Wahrnehmung", target=None)
    assert asked == [(64, "red")]


def test_a_failed_render_posts_the_result_without_a_thumbnail(monkeypatch, tmp_path) -> None:
    _fake_images(monkeypatch, tmp_path, broken=True)
    cog, fed = _cog(_Seq(23))
    (edit,) = _click(cog, face_skill="Wahrnehmung").edits
    assert edit["attachments"] == [] and edit["embed"].image.url is None
    assert edit["embed"].description == fed[0]


def test_with_dice_images_off_the_result_stays_plain_text(monkeypatch, tmp_path) -> None:
    asked = _fake_images(monkeypatch, tmp_path)
    cog, fed = _cog(_Seq(23), images=False)
    (edit,) = _click(cog, face_skill="Wahrnehmung").edits
    assert edit == {"content": fed[0], "view": None} and asked == []


def test_bang_roll_shows_the_total_as_a_thumbnail_up_to_100(monkeypatch, tmp_path) -> None:
    asked = _fake_images(monkeypatch, tmp_path)
    cog, _ = _cog(_Seq(4, 9))
    ctx = _Ctx()
    asyncio.run(DiceCog.roll.callback(cog, ctx, dice="2d10+3"))
    (_, kwargs), = ctx.sent
    assert asked == [(16, "red")]
    assert kwargs["embed"].thumbnail.url == f"attachment://{DICE_FILENAME}"  # !roll stays small
    assert kwargs["embed"].image.url is None
    assert kwargs["embed"].description == "🎲 `2d10+3` → **16** (4+9+3)"


def test_bang_roll_above_100_is_posted_as_plain_text(monkeypatch, tmp_path) -> None:
    asked = _fake_images(monkeypatch, tmp_path)
    cog, _ = _cog(_Seq(60, 70))
    ctx = _Ctx()
    asyncio.run(DiceCog.roll.callback(cog, ctx, dice="2d100"))
    assert ctx.sent == [(("🎲 `2d100` → **130** (60+70)",), {})] and asked == []


def test_the_renderer_resolves_a_font_or_names_what_it_tried(tmp_path) -> None:
    renderer = dice_images._load_renderer()
    with pytest.raises(FileNotFoundError, match="no mono \\(ASCII\\) font"):
        renderer.resolve_font((tmp_path / "nope.ttf",), "mono (ASCII)")
    assert Path(renderer.resolve_font(renderer.BOLD_FONT_CANDIDATES, "number (bold)")).is_file()


def _fate_cog(rng):
    from dmbot.memory.state import WorldState
    from dmbot.rules.characters import CharacterStore

    state = WorldState.seed_from_store(CharacterStore.from_dict({"characters": [
        {"name": "Rektalus", "wounds": 12, "max_wounds": 12},
    ]}))
    state.start_fate_session(default=3)
    cog, fed = _cog(rng)
    cog._rt._state = {7: state}
    cog._rt._persist_and_refresh = lambda ch: None
    return cog, fed


def _fate_decide(cog, spend: bool) -> _Msg:
    resolved = SimpleNamespace(target=40, difficulty="Herausfordernd")
    first, line = cog._roll_test(resolved, "Heimlichkeit", "Rektalus")
    msg = _Msg()
    decide = cog._make_fate_decision(object(), None, msg, resolved, "Heimlichkeit", "Rektalus",
                                     first, line)
    asyncio.run(decide(None, spend))
    return msg


def test_a_fate_reroll_shows_the_die_of_the_result_that_stands(monkeypatch, tmp_path) -> None:
    asked = _fake_images(monkeypatch, tmp_path)
    cog, _ = _fate_cog(_Seq(75, 12))                     # fails, the reroll succeeds
    (edit,) = _fate_decide(cog, True).edits
    assert asked == [(12, "red")]
    assert "75" in edit["embed"].description and "12 — Erfolg" in edit["embed"].description
    assert len(edit["attachments"]) == 1 and edit["view"] is None
    assert edit["embed"].image.url == f"attachment://{DICE_FILENAME}"  # same message, still big


def test_accepting_the_failure_keeps_the_first_die_and_only_drops_the_buttons(monkeypatch, tmp_path) -> None:
    asked = _fake_images(monkeypatch, tmp_path)
    cog, _ = _fate_cog(_Seq(75))
    (edit,) = _fate_decide(cog, False).edits
    assert edit == {"view": None} and asked == []
