"""D131: `!test` without "für" — the caller's own character, or a name at the end; unique first names."""

from __future__ import annotations

from types import SimpleNamespace

from dmbot.rules.characters import CharacterStore
from dmbot.voice.dicecog import DiceCog

_STORE = CharacterStore.from_dict({
    "characters": [{"name": "Fridolin Feuchtgebietheld"}, {"name": "Rektalus Zerfickus"},
                   {"name": "Rene Redo"}, {"name": "Rene Zwei"}],
    "aliases": {"Pr0degie": "Fridolin Feuchtgebietheld", "Sezgin": "Rektalus Zerfickus"},
})


def test_a_unique_first_name_finds_the_character_an_ambiguous_one_does_not() -> None:
    assert _STORE.get("fridolin").name == "Fridolin Feuchtgebietheld"
    assert _STORE.get("Rene") is None                       # two Renes: no guessing


def test_test_rolls_for_the_caller_or_the_character_named_at_the_end() -> None:
    cog = DiceCog.__new__(DiceCog)
    cog._rt = SimpleNamespace(
        _characters=_STORE,
        character_name_for=lambda uid, name: _STORE.get(name).name if _STORE.get(name) else name,
    )
    me = SimpleNamespace(id=1, display_name="Pr0degie")
    assert cog._test_spec_with_name("Heimlichkeit Schwer", me) == "Heimlichkeit Schwer für Fridolin Feuchtgebietheld"
    assert cog._test_spec_with_name("Heimlichkeit Sezgin", me) == "Heimlichkeit für Sezgin"
    assert cog._test_spec_with_name("Athletik Rektalus Zerfickus", me) == "Athletik für Rektalus Zerfickus"
    assert cog._test_spec_with_name("Überreden für Rektalus", me) == "Überreden für Rektalus"
    guest = SimpleNamespace(id=2, display_name="Gast")      # no sheet: rolls without a target, like before
    assert cog._test_spec_with_name("Wahrnehmung", guest) == "Wahrnehmung"
