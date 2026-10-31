"""Dice throw animation (tools/dice_throw.py, tools/generate_dice.py, dmbot/dice_images.py, DiceCog).

Presentation only: a test's button shows the steel "≤target" die; the click resolves through the
engine at once, feeds the DM at once, and only the two cosmetic message edits (throw GIF, then the
static result) wait for the animation. The trajectory comes from a cosmetic generator that never
touches the engine's RNG. Everything is fail-open — a broken animation never loses a result.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from types import SimpleNamespace

import discord
import pytest
from PIL import Image, ImageSequence

from dmbot import dice_images
from dmbot.discord_ui.dice import DICE_FILENAME, TARGET_FILENAME, THROW_FILENAME
from dmbot.rules.profile import load
from dmbot.runtime import SessionRuntime
from dmbot.voice import dicecog
from dmbot.voice.dicecog import DiceCog

_IM = load("imperium_maledictum")
_renderer = dice_images._load_renderer()
throw = _renderer.throw_module()


# --- simulation + seed filter ----------------------------------------------------------------

def test_the_simulation_is_deterministic_per_seed() -> None:
    assert throw.simulate(528) == throw.simulate(528)
    assert throw.simulate(528) != throw.simulate(529)


def _meets_filter(seed: int) -> bool:
    """The filter, restated from the spec, to check good_seed against."""
    states, events = throw.simulate(seed)
    x, _, z, _ = states[-1]
    return ({"L", "R", "top", "bottom"} <= {e for e, _ in events}
            and z < 0.08 and abs(x) < 90 and len(states) <= 32)


def test_the_seed_filter_accepts_a_good_seed_and_rejects_bad_ones() -> None:
    good = next(s for s in range(10_000) if _meets_filter(s))
    assert throw.good_seed(good)
    # A seed that misses an edge, and one that hits all four but ends off-centre / deep / long.
    missing_edge = next(s for s in range(10_000)
                        if not {"L", "R", "top", "bottom"} <= {e for e, _ in throw.simulate(s)[1]})
    assert not throw.good_seed(missing_edge)
    all_edges_but_bad_end = next(
        s for s in range(10_000)
        if {"L", "R", "top", "bottom"} <= {e for e, _ in throw.simulate(s)[1]} and not _meets_filter(s)
    )
    assert not throw.good_seed(all_edges_but_bad_end)


def test_the_pool_is_the_first_25_good_seeds_ascending() -> None:
    seeds = throw.good_seeds()
    assert len(seeds) == 25 and list(seeds) == sorted(seeds)
    assert all(_meets_filter(s) for s in seeds)
    assert not any(_meets_filter(s) for s in range(seeds[0]))  # nothing good was skipped


def test_the_frame_plan_starts_mid_throw_and_settles_on_the_result() -> None:
    plan = throw.throw_frames(528, 23, "gold")
    states, _ = throw.simulate(528)
    # The posted target die is the picture before the GIF: no opening still, no die at rest.
    assert all(f.kind in ("flicker", "final") for f in plan)
    take_off = len(throw.TAKE_OFF)
    assert len(plan) == take_off + (len(states) - 1) + len(throw.SLIDE_IN) + 2
    assert plan[0].scale > plan[1].scale > plan[2].scale > plan[take_off].scale   # shrinks, no jump
    first = plan[take_off]
    assert (first.dx, first.dy) == (states[1][0], states[1][1]) and first.duration_ms == throw.FLICKER_MS
    assert [f.duration_ms for f in plan[-5:]] == [130, 180, 250, 340, 2600]
    assert all(f.kind == "final" and f.value == 23 and f.palette == "gold" for f in plan[-2:])
    assert all(f.palette == "gold" and 1 <= f.value <= 100 for f in plan[take_off:] if f.kind == "flicker")
    # The flicker frames are the cached ones: they don't depend on the result.
    other = throw.throw_frames(528, 99, "gold")
    assert [f for f in plan if f.kind == "flicker"] == [f for f in other if f.kind == "flicker"]
    # Landed = everything before the settle frame; the hold comes after.
    assert throw.landed_ms(plan) == throw.gif_duration_ms(plan[:-2])


# --- rendering ---------------------------------------------------------------------------------

def test_the_target_number_sits_bigger_and_lower_than_a_plain_number() -> None:
    assert all(_renderer.PREFIXED_SIZES[n] > _renderer.NUMBER_SIZES[n] for n in (2, 3, 4))
    assert _renderer.PREFIXED_Y > -0.127


def test_the_target_die_renders_with_the_roll_under_prefix(tmp_path) -> None:
    path = dice_images.get_target_image(100, cache_dir=tmp_path)  # "≤100": the 4-glyph size
    assert path == tmp_path / "steel" / "t_100.png" and path.is_file()
    assert dice_images.get_target_image(100, cache_dir=tmp_path) == path  # cached
    plain = _renderer.shaded_die(45, random.Random(7))
    prefixed = _renderer.shaded_die(45, random.Random(7), "≤")
    assert plain.tobytes() != prefixed.tobytes()
    with pytest.raises(ValueError):
        dice_images.get_target_image(101, cache_dir=tmp_path)


def test_transform_at_rest_leaves_the_die_unchanged() -> None:
    die = _renderer.shaded_die(12, random.Random(7))
    assert _renderer.transform(die, 0, 1, 0, 0).tobytes() == die.tobytes()
    small = _renderer.transform(die, 0, 0.5, 0, 0)
    assert small.getbbox() is not None and small.getbbox()[2] - small.getbbox()[0] <= 601


def test_the_gif_has_every_planned_frame_and_the_planned_play_time(monkeypatch, tmp_path) -> None:
    # Stand-in frames (one solid colour each) — the assembly is under test, not the art.
    def fake_frame(frame):
        shade = (frame.value * 2, frame.texture_seed % 256, int(frame.scale * 200))
        return Image.new("RGB", (_renderer.THUMB, _renderer.THUMB), shade)

    monkeypatch.setattr(_renderer, "render_frame", fake_frame)
    path, landed = dice_images.get_dice_gif(23, "red", 528, cache_dir=tmp_path)
    assert path == tmp_path / "s528_red_r23.gif"           # no target in it: the post shows that
    plan = throw.throw_frames(528, 23, "red")
    with Image.open(path) as gif:
        assert len(gif.getpalette()) // 3 <= _renderer.GIF_COLOURS  # first frame, before seeking
        durations = [f.info["duration"] for f in ImageSequence.Iterator(gif)]
        assert gif.info.get("loop") == 0
    # settle + hold are one picture, so Pillow merges them (durations added)
    assert len(durations) == len(plan) - 1
    assert sum(durations) == throw.gif_duration_ms(plan)
    assert round(landed * 1000) == throw.landed_ms(plan)
    flickers = sum(f.kind == "flicker" for f in plan)
    assert len(list(_renderer.frame_set_dir(tmp_path, 528, "red").glob("f_*.png"))) == flickers

    def no_rebuild(*args, **kwargs):
        raise AssertionError("a cached GIF must not be rebuilt")

    monkeypatch.setattr(_renderer, "build_throw_gif", no_rebuild)
    assert dice_images.get_dice_gif(23, "red", 528, cache_dir=tmp_path) == (path, landed)


def test_preparing_a_throw_renders_the_red_set_so_the_click_only_renders_the_landing(
        monkeypatch, tmp_path) -> None:
    rendered: list[str] = []

    def fake_frame(frame):
        rendered.append(frame.kind)
        return Image.new("RGB", (_renderer.THUMB, _renderer.THUMB), (frame.value, frame.texture_seed % 256, 9))

    monkeypatch.setattr(_renderer, "render_frame", fake_frame)
    monkeypatch.setattr(dice_images, "throw_seeds", lambda **_: (528,))
    assert dice_images.prepare_throw(cache_dir=tmp_path) == 528
    assert rendered and set(rendered) == {"flicker"}
    rendered.clear()
    dice_images.get_dice_gif(23, "red", 528, cache_dir=tmp_path)
    assert rendered == ["final"]                            # settle + hold rendered once


def test_a_real_frame_renders_at_thumbnail_size() -> None:
    frame = throw.throw_frames(528, 23, "green")[5]
    image = _renderer.render_frame(frame)
    assert image.size == (_renderer.THUMB, _renderer.THUMB) and image.mode == "RGB"


def test_a_broken_animation_yields_none_instead_of_an_error(monkeypatch) -> None:
    def broken(target, result, palette, seed=None):
        raise RuntimeError("no font")

    monkeypatch.setattr(dice_images, "_throw", broken)
    assert asyncio.run(dice_images.get_dice_gif_async(45, 23, "red")) is None
    assert asyncio.run(dice_images.get_dice_gif_async(None, 23, "red")) is None
    assert asyncio.run(dice_images.get_dice_gif_async(140, 23, "red")) is None


# --- the cog ------------------------------------------------------------------------------------

class _Msg:
    def __init__(self, log: list, *, gone_after: int | None = None) -> None:
        self.edits: list[dict] = []
        self._log = log
        self._gone_after = gone_after

    async def edit(self, **kwargs) -> None:
        if self._gone_after is not None and len(self.edits) >= self._gone_after:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")
        self.edits.append(kwargs)
        self._log.append(("edit", len(self.edits)))


def _png(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


def _fakes(monkeypatch, tmp_path) -> dict[str, list]:
    """Stand in for the renderers: record what was asked, hand back tiny files at once."""
    asked: dict[str, list] = {"image": [], "gif": [], "target": [], "seed": [], "prepare": []}

    async def image(value, palette="red"):
        asked["image"].append((value, palette))
        return _png(tmp_path, "die.png")

    async def gif(target, result, palette, seed=None):
        asked["gif"].append((target, result, palette))
        asked["seed"].append(seed)
        return _png(tmp_path, "throw.gif"), 0.01

    async def prepare():
        asked["prepare"].append(True)
        return 777

    async def target(value):
        asked["target"].append(value)
        return None if value is None else _png(tmp_path, "target.png")

    monkeypatch.setattr(dicecog, "get_dice_image_async", image)
    monkeypatch.setattr(dicecog, "get_dice_gif_async", gif)
    monkeypatch.setattr(dicecog, "get_target_image_async", target)
    monkeypatch.setattr(dicecog, "prepare_throw_async", prepare)
    monkeypatch.setattr(dicecog, "REVEAL_GRACE_S", 0.0)    # no real waiting in tests
    return asked


def _cog(rng, *, animation: bool = True, images: bool = True):
    log: list = []

    async def run_and_deliver(channel, guild_id):
        log.append(("narrate",))

    async def send(channel, content=None, *, view=None, embed=None, file=None):
        log.append(("send", content, view, embed, file))

    rt = SimpleNamespace(
        _profile=_IM, _rng=rng, _state={}, _brain_channel=lambda ch: 7, _characters=None,
        _dice_images=images, _dice_animation=animation,
        _brain=SimpleNamespace(add_test_result=lambda cid, line: log.append(("fed", line))),
        run_and_deliver=run_and_deliver, _send_with_retry=send,
    )
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    cog._presentations = set()

    async def no_damage_flow(channel, *, attacker, result):  # a hit's damage flow is not under test
        return True

    cog._begin_attack_damage = no_damage_flow
    return cog, log


def _click(cog, log, *, target: int | None = 50, who: str = "Fridolin", gone_after: int | None = None):
    req = SimpleNamespace(skill="Wahrnehmung", target_name=who)
    resolved = SimpleNamespace(target=target, difficulty=None, character=None)
    roll = cog._make_dice_roll(SimpleNamespace(guild=None), req, resolved)
    message = _Msg(log, gone_after=gone_after)

    async def go():
        await roll(SimpleNamespace(message=message))
        await asyncio.gather(*list(cog._presentations))  # let the cosmetic edits finish

    asyncio.run(go())
    return message


def test_a_click_throws_then_reveals_and_the_dm_is_fed_before_the_animation(monkeypatch, tmp_path) -> None:
    asked = _fakes(monkeypatch, tmp_path)
    cog, log = _cog(random.Random(3))
    msg = _click(cog, log, target=50)
    first, second = msg.edits                              # exactly two edits per roll
    assert first["attachments"][0].filename == THROW_FILENAME
    assert first["embed"].image.url == f"attachment://{THROW_FILENAME}"   # big, in the target's place
    assert "view" not in first                             # the locked button stays while it rolls
    assert second["attachments"][0].filename == DICE_FILENAME and second["view"] is None
    assert second["embed"].image.url == f"attachment://{DICE_FILENAME}"  # the result stays big
    fed = next(entry[1] for entry in log if entry[0] == "fed")
    assert second["embed"].description == fed               # the result text only comes with edit 2
    assert fed not in (first["embed"].description or "")
    kinds = [entry[0] for entry in log]
    assert kinds.index("fed") < kinds.index("edit") and kinds.index("narrate") < kinds.index("edit")
    (target, face, _palette), = asked["gif"]
    assert target == 50 and str(face) in fed


def test_with_the_animation_flag_off_no_gif_is_asked_for(monkeypatch, tmp_path) -> None:
    asked = _fakes(monkeypatch, tmp_path)
    cog, log = _cog(random.Random(3), animation=False)
    (edit,) = _click(cog, log).edits
    assert asked["gif"] == [] and edit["attachments"][0].filename == DICE_FILENAME
    assert edit["embed"].image.url == f"attachment://{DICE_FILENAME}"  # still big without the GIF


def test_a_roll_without_a_target_skips_the_animation(monkeypatch, tmp_path) -> None:
    asked = _fakes(monkeypatch, tmp_path)
    cog, log = _cog(random.Random(3))
    _click(cog, log, target=None)
    assert asked["gif"] == [] and len(asked["image"]) == 1


def test_a_failed_gif_goes_straight_to_the_static_result(monkeypatch, tmp_path) -> None:
    _fakes(monkeypatch, tmp_path)

    async def no_gif(target, result, palette, seed=None):
        return None

    monkeypatch.setattr(dicecog, "get_dice_gif_async", no_gif)
    cog, log = _cog(random.Random(3))
    (edit,) = _click(cog, log).edits
    assert edit["attachments"][0].filename == DICE_FILENAME


def test_a_message_deleted_mid_throw_ends_the_animation_quietly(monkeypatch, tmp_path) -> None:
    _fakes(monkeypatch, tmp_path)
    cog, log = _cog(random.Random(3))
    msg = _click(cog, log, gone_after=1)                   # edit 1 lands, then the message is gone
    assert len(msg.edits) == 1
    assert not any(entry[0] == "send" for entry in log)
    assert any(entry[0] == "narrate" for entry in log)     # the DM still narrated the result


def _fate_cog(rng):
    from dmbot.memory.state import WorldState
    from dmbot.rules.characters import CharacterStore

    state = WorldState.seed_from_store(CharacterStore.from_dict({"characters": [
        {"name": "Rektalus", "wounds": 12, "max_wounds": 12},
    ]}))
    state.start_fate_session(default=3)
    cog, log = _cog(rng)
    cog._rt._state = {7: state}
    cog._rt._persist_and_refresh = lambda ch: None
    return cog, log


class _Fixed:
    def __init__(self, *values: int) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


def test_the_fate_choice_appears_with_the_result_not_during_the_throw(monkeypatch, tmp_path) -> None:
    _fakes(monkeypatch, tmp_path)
    cog, log = _fate_cog(_Fixed(95))                       # fails → Rektalus may spend Fate
    first, second = _click(cog, log, target=40, who="Rektalus").edits
    assert "view" not in first
    assert second["view"] is not None and "Neu würfeln" in str(
        [getattr(item, "label", "") for item in second["view"].children])
    assert not any(entry[0] == "narrate" for entry in log)  # narration waits for the Fate choice


def test_a_deleted_message_reposts_a_pending_fate_choice(monkeypatch, tmp_path) -> None:
    _fakes(monkeypatch, tmp_path)
    cog, log = _fate_cog(_Fixed(95))
    _click(cog, log, target=40, who="Rektalus", gone_after=0)
    (send,) = [entry for entry in log if entry[0] == "send"]
    assert send[2] is not None                              # the view rides along — it narrates


def test_the_throw_choice_never_touches_the_engine_rng(monkeypatch, tmp_path) -> None:
    """Same engine seed, animation on vs off → the same results fed to the DM, same RNG state."""
    _fakes(monkeypatch, tmp_path)
    picked: list[int] = []

    def fake_gif(result, palette, seed, *, cache_dir=None):
        picked.append(seed)
        return _png(tmp_path, "throw.gif"), 0.0

    monkeypatch.setattr(dice_images, "throw_seeds", lambda **_: tuple(range(100, 125)))
    monkeypatch.setattr(dice_images, "get_dice_gif", fake_gif)
    monkeypatch.setattr(dicecog, "get_dice_gif_async", dice_images.get_dice_gif_async)  # the real one

    def session(animation: bool):
        rng = random.Random(4242)
        cog, log = _cog(rng, animation=animation)
        for target in (30, 50, 70, 90, 10, 60):
            _click(cog, log, target=target)
        return [entry[1] for entry in log if entry[0] == "fed"], rng.getstate()

    on, off = session(True), session(False)
    assert on == off
    assert len(picked) == 6 and all(100 <= s < 125 for s in picked)


# --- the posted test shows its target ----------------------------------------------------------

async def _noop(*args, **kwargs) -> None:
    return None


def _post(cog, monkeypatch, target: int | None):
    monkeypatch.setattr(dicecog, "resolve_target", lambda *a, **k: SimpleNamespace(
        target=target, difficulty=None, character=None))
    req = SimpleNamespace(skill="Wahrnehmung", target_name="Fridolin", difficulty=None,
                          modifier=None, parsed=True)

    async def go():
        await cog._post_dice_button(SimpleNamespace(guild=None), req)
        await asyncio.gather(*list(cog._presentations))   # the throw preparation, if any

    asyncio.run(go())


def test_a_posted_test_shows_the_steel_target_die(monkeypatch, tmp_path) -> None:
    asked = _fakes(monkeypatch, tmp_path)
    cog, log = _cog(random.Random(3))
    _post(cog, monkeypatch, 45)
    (send,) = [entry for entry in log if entry[0] == "send"]
    _, content, view, embed, file = send
    assert asked["target"] == [45] and content == "🎲 Probe angefordert:" and view is not None
    assert embed.description == "Zielwert **≤45**" and file.filename == TARGET_FILENAME
    assert embed.image.url == f"attachment://{TARGET_FILENAME}"  # big, the 🎲 button below it
    assert embed.thumbnail.url is None


def test_posting_a_test_prepares_its_throw_and_the_click_uses_that_throw(monkeypatch, tmp_path) -> None:
    asked = _fakes(monkeypatch, tmp_path)
    cog, log = _cog(random.Random(3))
    _post(cog, monkeypatch, 45)
    assert asked["prepare"] == [True]
    (send,) = [entry for entry in log if entry[0] == "send"]
    button = send[2]._button

    async def click():
        message = _Msg(log)
        interaction = SimpleNamespace(message=message, response=SimpleNamespace(edit_message=_noop))
        await button.callback(interaction)
        await asyncio.gather(*list(cog._presentations))

    asyncio.run(click())
    assert asked["seed"] == [777]                          # the throw picked when it was posted


def test_nothing_is_prepared_with_the_animation_off(monkeypatch, tmp_path) -> None:
    asked = _fakes(monkeypatch, tmp_path)
    cog, _ = _cog(random.Random(3), animation=False)
    _post(cog, monkeypatch, 45)
    assert asked["prepare"] == [] and asked["target"] == [45]


def test_a_test_without_a_target_or_with_images_off_posts_the_plain_button(monkeypatch, tmp_path) -> None:
    _fakes(monkeypatch, tmp_path)
    cog, log = _cog(random.Random(3))
    _post(cog, monkeypatch, None)
    cog_off, log_off = _cog(random.Random(3), images=False)
    _post(cog_off, monkeypatch, 45)
    for entries in (log, log_off):
        (send,) = [entry for entry in entries if entry[0] == "send"]
        assert send[3] is None and send[4] is None and send[2] is not None


def test_a_failed_send_with_the_target_die_falls_back_to_the_plain_button(monkeypatch, tmp_path) -> None:
    _fakes(monkeypatch, tmp_path)
    cog, _ = _cog(random.Random(3))
    calls: list[dict] = []

    async def flaky(channel, content=None, *, view=None, embed=None, file=None):
        calls.append({"embed": embed, "file": file, "view": view})
        if file is not None:
            raise discord.HTTPException(SimpleNamespace(status=503, reason="busy"), "busy")

    cog._rt._send_with_retry = flaky
    _post(cog, monkeypatch, 45)
    assert [c["file"] is None for c in calls] == [False, True] and calls[1]["view"] is not None


def test_a_send_carrying_a_file_is_not_retried_on_a_5xx() -> None:
    sent: list = []

    class _Channel:
        async def send(self, content, **kwargs):
            sent.append(kwargs)
            raise discord.HTTPException(SimpleNamespace(status=503, reason="busy"), "busy")

    with pytest.raises(discord.HTTPException):
        asyncio.run(SessionRuntime._send_once(None, _Channel(), "x", {"file": object()}))
    assert len(sent) == 1
