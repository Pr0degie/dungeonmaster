"""Throw GIFs stored once in Discord (ADR 064, dmbot/dice_assets.py) and the click that uses them.

The 75 flight-only GIFs go into a storage channel once, ten per message; later starts only re-fetch
those messages for fresh links. A click then edits the message to point at the stored GIF (no
upload) and starts the result upload early by the learnt upload time. Everything is fail-open:
no channel / not ready → the per-roll upload path.
"""

from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace

import discord
from PIL import Image, ImageSequence

from dmbot import dice_assets, dice_images
from dmbot.dice_assets import DiceAssetStore, asset_name
from dmbot.discord_ui.dice import DICE_FILENAME
from dmbot.rules.profile import load
from dmbot.voice import dicecog
from dmbot.voice.dicecog import DiceCog

_IM = load("imperium_maledictum")
_renderer = dice_images._load_renderer()
throw = _renderer.throw_module()


# --- the flight-only GIF -----------------------------------------------------------------------

def test_the_flight_is_the_throw_without_its_landing_ending_on_a_blank_face() -> None:
    flight = throw.flight_frames(528, "red")
    full = throw.throw_frames(528, 23, "red")
    flickers = [f for f in full if f.kind == "flicker"]
    assert len(flight) == len(flickers) and flight[:-1] == flickers[:-1]
    assert (flight[-1].kind, flight[-1].value) == ("blank", 0)
    assert not any(f.kind == "final" for f in flight)


def test_the_flight_gif_plays_once_and_rests_on_the_blank_die(monkeypatch, tmp_path) -> None:
    rendered: list[str] = []

    def fake_frame(frame):
        rendered.append(frame.kind)
        return Image.new("RGB", (_renderer.THUMB, _renderer.THUMB), (frame.value, frame.texture_seed % 256, 9))

    monkeypatch.setattr(_renderer, "render_frame", fake_frame)
    path, seconds = dice_images.get_flight_gif(528, "red", cache_dir=tmp_path)
    plan = throw.flight_frames(528, "red")
    with Image.open(path) as gif:
        assert "loop" not in gif.info                      # no loop: it stops on the blank die
        durations = [f.info["duration"] for f in ImageSequence.Iterator(gif)]
    assert len(durations) == len(plan) and sum(durations) == round(seconds * 1000)
    assert rendered.count("blank") == 1


def test_a_blank_face_draws_no_number() -> None:
    blank = _renderer.shaded_die(None, random.Random(7))
    numbered = _renderer.shaded_die(23, random.Random(7))
    assert blank.tobytes() != numbered.tobytes()


def test_the_side_faces_carry_fixed_numbers_never_the_shown_value() -> None:
    for value in (1, 23, 88, 100):
        numbers = _renderer.face_numbers(value)
        assert numbers == _renderer.face_numbers(value)          # same value → same picture
        assert len(set(numbers)) == 9 and value not in numbers
        assert all(1 <= n <= 100 for n in numbers)
    assert _renderer.face_numbers(23) != _renderer.face_numbers(24)


def test_the_side_numbers_are_drawn_on_the_die(monkeypatch) -> None:
    with_faces = _renderer.shaded_die(23, random.Random(7))
    monkeypatch.setattr(_renderer, "face_numbers", lambda number: [])
    without = _renderer.shaded_die(23, random.Random(7))
    assert with_faces.tobytes() != without.tobytes()


# --- the store -----------------------------------------------------------------------------------

class _Msg:
    def __init__(self, mid: int, files: list) -> None:
        self.id = mid
        self.attachments = [SimpleNamespace(filename=f.filename, url=f"https://cdn/{mid}/{f.filename}")
                            for f in files]


class _Channel:
    def __init__(self, cid: int, name: str) -> None:
        self.id, self.name = cid, name
        self.sent: list[_Msg] = []
        self.deleted: set[int] = set()
        self.fetched: list[int] = []

    async def send(self, content, *, files):
        assert len(files) <= dice_assets.PER_MESSAGE
        msg = _Msg(1000 + len(self.sent), files)
        self.sent.append(msg)
        return msg

    async def fetch_message(self, mid: int):
        self.fetched.append(mid)
        if mid in self.deleted:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")
        return next(m for m in self.sent if m.id == mid)


def _guild(*channels):
    return SimpleNamespace(id=42, name="g", text_channels=list(channels))


def _store(monkeypatch, tmp_path, seeds=(1, 2, 3), spec="botcommands"):
    gif = tmp_path / "f.gif"
    gif.write_bytes(b"GIF89a")
    monkeypatch.setattr(dice_images, "throw_seeds", lambda **_: tuple(seeds))
    monkeypatch.setattr(dice_images, "get_flight_gif", lambda seed, palette, **_: (gif, 2.0))
    return DiceAssetStore(spec, state_file=tmp_path / "assets.json")


def test_the_storage_channel_is_found_by_name_or_id(tmp_path) -> None:
    general, bots = _Channel(1, "general"), _Channel(7, "🤖-bot-commands")
    guild = _guild(general, bots)
    assert DiceAssetStore("botcommands", state_file=tmp_path / "a").resolve_channel(guild) is bots
    assert DiceAssetStore("7", state_file=tmp_path / "a").resolve_channel(guild) is bots
    assert DiceAssetStore("nope", state_file=tmp_path / "a").resolve_channel(guild) is None


def test_every_flight_gif_is_uploaded_once_ten_per_message(monkeypatch, tmp_path) -> None:
    store = _store(monkeypatch, tmp_path, seeds=range(12))  # 12 × 3 palettes = 36 GIFs
    bots = _Channel(7, "botcommands")
    guild = _guild(bots)
    assert store.url(guild, 0, "red") is None               # not stored yet → the upload path
    assert asyncio.run(store.ensure(guild)) is True
    assert len(bots.sent) == 4
    assert store.url(guild, 5, "gold") == f"https://cdn/{bots.sent[1].id}/{asset_name(5, 'gold')}"

    # A restart: a fresh store reads the saved message ids and only fetches them — no upload.
    again = _store(monkeypatch, tmp_path, seeds=range(12))
    assert asyncio.run(again.ensure(guild)) is True
    assert len(bots.sent) == 4 and len(bots.fetched) == 4
    assert again.url(guild, 11, "green") is not None


def test_a_deleted_storage_message_gets_its_gifs_uploaded_again(monkeypatch, tmp_path) -> None:
    store = _store(monkeypatch, tmp_path)                    # 3 × 3 = 9 GIFs, one message
    bots = _Channel(7, "botcommands")
    guild = _guild(bots)
    asyncio.run(store.ensure(guild))
    bots.deleted.add(bots.sent[0].id)
    again = _store(monkeypatch, tmp_path)
    assert asyncio.run(again.ensure(guild)) is True
    assert len(bots.sent) == 2 and again.url(guild, 1, "red").startswith(f"https://cdn/{bots.sent[1].id}/")


def test_without_a_storage_channel_nothing_is_stored(monkeypatch, tmp_path) -> None:
    store = _store(monkeypatch, tmp_path, spec="botcommands")
    guild = _guild(_Channel(1, "general"))
    assert asyncio.run(store.ensure(guild)) is False
    assert store.url(guild, 1, "red") is None


# --- the click with a stored GIF ------------------------------------------------------------------

class _Edited:
    def __init__(self) -> None:
        self.edits: list[dict] = []

    async def edit(self, **kwargs) -> None:
        self.edits.append(kwargs)


def _cog(monkeypatch, tmp_path, *, link: str | None):
    png = tmp_path / "die.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    async def image(value, palette="red"):
        return png

    async def gif(target, result, palette, seed=None):
        (tmp_path / "throw.gif").write_bytes(b"GIF89a")
        return tmp_path / "throw.gif", 0.0

    slept: list[float] = []

    async def no_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(dicecog, "get_dice_image_async", image)
    monkeypatch.setattr(dicecog, "get_dice_gif_async", gif)
    monkeypatch.setattr(dicecog, "flight_seconds", lambda seed, palette: 2.4)
    monkeypatch.setattr(dicecog.asyncio, "sleep", no_sleep)
    log: list = []

    async def run_and_deliver(channel, guild_id):
        log.append("narrate")

    rt = SimpleNamespace(
        _profile=_IM, _rng=random.Random(3), _state={}, _brain_channel=lambda ch: 7,
        _dice_images=True, _dice_animation=True,
        _brain=SimpleNamespace(add_test_result=lambda cid, line: log.append(line)),
        run_and_deliver=run_and_deliver,
    )
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    cog._presentations = set()
    cog._upload_lead_s = 1.0
    cog._assets = SimpleNamespace(url=lambda guild, seed, palette: link)
    return cog, slept


def _click(cog):
    req = SimpleNamespace(skill="Wahrnehmung", target_name="Fridolin")
    resolved = SimpleNamespace(target=50, difficulty=None, character=None)

    async def prepared():
        return 528

    async def go():
        prep = asyncio.ensure_future(prepared())
        roll = cog._make_dice_roll(SimpleNamespace(guild=SimpleNamespace(id=42)), req, resolved, prep=prep)
        message = _Edited()
        await roll(SimpleNamespace(message=message))
        await asyncio.gather(*list(cog._presentations))
        return message

    return asyncio.run(go())


def test_a_stored_gif_is_shown_by_link_without_an_upload(monkeypatch, tmp_path) -> None:
    cog, slept = _cog(monkeypatch, tmp_path, link="https://cdn/stored.gif")
    first, second = _click(cog).edits
    assert first["attachments"] == [] and first["embed"].image.url == "https://cdn/stored.gif"
    assert second["attachments"][0].filename == DICE_FILENAME   # the result stays an attachment
    assert second["embed"].image.url == f"attachment://{DICE_FILENAME}"
    # The result upload starts early by the learnt upload time (1.0 s) to land with the die.
    assert slept == [2.4 + dicecog.CLIENT_START_S - 1.0]


def test_without_a_stored_gif_the_click_uploads_it_like_before(monkeypatch, tmp_path) -> None:
    cog, _ = _cog(monkeypatch, tmp_path, link=None)
    first, _second = _click(cog).edits
    assert first["attachments"][0].filename == "dice.gif"
