"""Intro monologue (`!intro`, ADR 031): the campaign-opener director turn that establishes place +
mission + how the party arrived AND gives each player character a personal beat.

Unlike the short `!start` briefing it (a) embeds a character roster into the director instruction and
(b) runs on a larger length budget (`num_predict` override). The audio/Discord half is verified
manually per the phase gate; the decidable, deterministic properties are pinned here:

- the roster block carries each character's flavour (full depth) and tolerates lean sheets;
- the director instruction reads as a GM/director message, asks for one monologue, involves every
  figure, and forbids a dice test;
- the opening path honours a per-turn `num_predict` override (the larger intro budget), while a turn
  with no override still uses the brain's default.
"""

from __future__ import annotations

import asyncio

from dmbot.orchestrator import DMBrain, build_intro_director_msg, build_opening_director_msg
from dmbot.rules import profile as profile_mod
from dmbot.rules.characters import CharacterStore

_IM = profile_mod.load("imperium_maledictum")

# One full-depth sheet (party-JSON shape) + one lean sheet (_example shape, only some flavour).
_STORE = CharacterStore.from_dict(
    {
        "characters": [
            {
                "name": "Fridolin Feuchtgebietheld",
                "concept": "Interrogator & Psioniker",
                "origin": "Schreinwelt",
                "faction": "Inquisition",
                "distinguishing": "Steht plötzlich im Raum, ohne dass jemand die Tür gehen hörte.",
                "goals": "Den Drahtzieher stellen —\nund dabei cool aus dem Schatten treten.",
                "connections": "Inquisitor Aegidius Halikarn — sein Patron.",
                "arc": "Vom prinzipientreuen Diener zum gefährlichen Eiferer.",
            },
            {"name": "Seskin", "goals": "Den Hinterhalt überleben."},  # lean: no concept/origin
        ],
        "aliases": {"Pr0degie": "Fridolin Feuchtgebietheld", "SezBoss69": "Seskin"},
    }
)


# --- the roster block -------------------------------------------------------------------------

def test_intro_roster_carries_full_depth_flavour() -> None:
    roster = _STORE.intro_roster_de()
    # both characters appear, one bullet each
    assert "**Fridolin Feuchtgebietheld**" in roster
    assert "**Seskin**" in roster
    # full-depth fields for the rich sheet (Tobi's choice: goals/connections/arc included)
    assert "Interrogator & Psioniker" in roster      # concept (lead descriptor)
    assert "Herkunft: Schreinwelt" in roster
    assert "Fraktion: Inquisition" in roster
    assert "Ziele: Den Drahtzieher stellen" in roster
    assert "Verbindungen: Inquisitor Aegidius Halikarn" in roster
    assert "Wandel: Vom prinzipientreuen Diener" in roster
    # multi-line sheet fields are collapsed to one line (no embedded newline inside a value)
    assert "stellen —\nund" not in roster


def test_intro_roster_tolerates_lean_sheets() -> None:
    roster = _STORE.intro_roster_de()
    seskin_line = next(line for line in roster.splitlines() if "Seskin" in line)
    # the lean sheet still renders its one present field and never invents the missing ones
    assert "Ziele: Den Hinterhalt überleben." in seskin_line
    assert "Herkunft" not in seskin_line and "Fraktion" not in seskin_line


def test_intro_roster_empty_store_is_blank() -> None:
    assert CharacterStore().intro_roster_de() == ""


# --- the director instruction -----------------------------------------------------------------

def test_intro_director_msg_with_roster() -> None:
    roster = _STORE.intro_roster_de()
    msg = build_intro_director_msg(roster)
    assert msg.startswith("[Regie]")          # a director instruction, not a player line
    assert "Monolog" in msg                    # one coherent opening monologue (not a list)
    assert "Probe" in msg                      # "Verlange keine Probe." — no dice on the auftakt
    assert "folgenden Figuren" in msg          # the character-involvement clause is present
    assert roster in msg                       # the actual party roster is embedded


def test_intro_director_msg_without_roster_degrades() -> None:
    msg = build_intro_director_msg("")
    assert msg.startswith("[Regie]")
    assert "Monolog" in msg and "Probe" in msg
    # with no party loaded, the per-character clause is dropped (nothing to weave in)
    assert "folgenden Figuren" not in msg


# --- the num_predict override on the opening path ---------------------------------------------

class _CaptureClient:
    """Captures the options DMBrain forwards so a test can assert the per-turn num_predict."""

    def __init__(self) -> None:
        self.options: dict | None = None

    async def chat(self, system, messages, options=None) -> str:
        self.options = options
        return "Der Auftakt beginnt."

    async def aclose(self) -> None:
        pass


def test_opening_path_honours_num_predict_override() -> None:
    client = _CaptureClient()
    brain = DMBrain(client, profile=_IM, num_predict=220)
    asyncio.run(brain.respond_opening(1, build_intro_director_msg("- **X**"), num_predict=800))
    assert client.options["num_predict"] == 800   # the larger intro budget reached the request


def test_opening_path_defaults_when_no_override() -> None:
    client = _CaptureClient()
    brain = DMBrain(client, profile=_IM, num_predict=220)
    asyncio.run(brain.respond_opening(2, build_opening_director_msg()))
    assert client.options["num_predict"] == 220   # unchanged default for the short briefing
