"""The `!rules` page builder derives the essentials from the active profile (system-agnostic).
Verified against the loaded IM profile so the numbers shown match the engine's source of truth."""

from dmbot.rules import profile as profile_mod
from dmbot.rules.summary import rules_pages_de


def _all_text(pages) -> str:
    return "\n".join(f"{t}\n{b}" for t, b in pages)


def test_im_rules_pages_cover_the_essentials():
    profile = profile_mod.load("imperium_maledictum")
    pages = rules_pages_de(profile)
    assert len(pages) >= 3  # at least: how-to, difficulty, degrees
    text = _all_text(pages)

    # How a test works (roll-under, GM rolls for you)
    assert "1d100" in text
    assert "unter" in text.lower()

    # Difficulty ladder with signed modifiers
    assert "Sehr leicht" in text and "+60" in text
    assert "Schwer" in text and "-20" in text

    # Degrees + auto-bands + crit
    assert "Erfolgsgrade" in text
    assert "01–05" in text
    assert "96–00" in text
    assert "Doppelzahlen" in text


def test_pages_are_title_body_pairs():
    profile = profile_mod.load("imperium_maledictum")
    for page in rules_pages_de(profile):
        assert isinstance(page, tuple) and len(page) == 2
        title, body = page
        assert title and body
