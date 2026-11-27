""""Was kann ich?" answered from the sheet in code (live run 2026-11-27).

A player asked "Was kann ich?" over push-to-talk and the narration model answered with scene
options: the persona's "what can we do" rule beat the sheet block in the prompt. Code now
recognises the explicit question about the speaker's OWN abilities and posts that character's
sheet as a text message; the narration turn runs on unchanged (golden rule #7: rule/sheet
questions are answered from data).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dmbot.rules.characters import CharacterStore, is_sheet_question
from fakes import make_runtime


# --- the matcher ------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Was kann ich?",
    "was kann ich",
    "Was kann ich eigentlich?",
    "Was kann ich denn?",
    "Äh, was kann ich?",
    "Ähm... was kann ich eigentlich?",
    "Was kann ich alles?",
    "Okay, was kann ich überhaupt?",
    "was kann meine Figur",
    "Was kann mein Charakter?",
    "Welche Fertigkeiten habe ich?",
    "welche Talente hab ich",
    "Welche Fähigkeiten habe ich eigentlich?",
    "Was sind meine Fertigkeiten?",
    "Was sind meine Werte?",
    "Was habe ich für Fertigkeiten?",
    "Was steht auf meinem Bogen?",
])
def test_a_question_about_the_own_sheet_matches(text: str) -> None:
    assert is_sheet_question(text)


@pytest.mark.parametrize("text", [
    "Was kann ich sehen?",
    "Was kann ich tun, um die Tür zu öffnen?",
    "Was kann ich hier machen?",
    "Was kann ich jetzt tun?",
    "Was kann er?",
    "Was kann sie eigentlich?",
    "Kann ich die Tür öffnen?",
    "Was können wir tun?",
    "Ich gehe zur Tür. Was kann ich?",
    "Welche Fertigkeiten hat er?",
    "...",
    "",
    "   ",
])
def test_a_question_about_the_situation_does_not_match(text: str) -> None:
    assert not is_sheet_question(text)


# --- the answer text --------------------------------------------------------------------------

_STORE = CharacterStore.from_dict({"characters": [
    {"name": "Fridolin Feuchtgebietheld", "psyker": True,
     "skills": {"Heimlichkeit": 48, "Überreden": 42, "Psi-Meisterschaft": 51},
     "talents": [{"name": "Leichtfüßig", "effect": "lange Erklärung"}, "Glatte Zunge"],
     "known_powers": ["Smite", "Soulsight"], "fate": 3},
    {"name": "Rektalus Zerfickus", "skills": {"Athletik": 50, "Nahkampf": 39}},
    {"name": "Mortn"},
]})


def test_the_answer_lists_skills_talents_powers_and_fate_of_one_character() -> None:
    answer = _STORE.sheet_answer_de(_STORE.get("Fridolin Feuchtgebietheld"))
    assert answer == (
        "📋 **Fridolin Feuchtgebietheld**\n"
        "Fertigkeiten: Heimlichkeit 48, Überreden 42, Psi-Meisterschaft 51\n"
        "Talente: Leichtfüßig, Glatte Zunge\n"
        "Psychische Kräfte: Smite, Soulsight\n"
        "Schicksalspunkte: 3"
    )
    assert "lange Erklärung" not in answer      # names only, no effects
    assert "Rektalus" not in answer             # ONE character, not the party


def test_the_answer_leaves_out_what_the_sheet_does_not_have() -> None:
    answer = _STORE.sheet_answer_de(_STORE.get("Rektalus Zerfickus"))
    assert answer == "📋 **Rektalus Zerfickus**\nFertigkeiten: Athletik 50, Nahkampf 39"


def test_an_empty_sheet_says_so_instead_of_posting_a_bare_name() -> None:
    answer = _STORE.sheet_answer_de(_STORE.get("Mortn"))
    assert answer.startswith("📋 **Mortn**") and "keine" in answer


def test_a_long_sheet_stays_under_the_cap() -> None:
    store = CharacterStore.from_dict({"characters": [
        {"name": "Vielkönner", "skills": {f"Fertigkeit Nummer {i}": 40 + i for i in range(60)},
         "talents": [f"Talent Nummer {i}" for i in range(60)],
         "psyker": True, "known_powers": ["Smite"], "fate": 2},
    ]})
    answer = store.sheet_answer_de(store.get("Vielkönner"))
    skills, talents, powers, fate = answer.split("\n")[1:]
    assert skills.endswith("…") and talents.endswith("…")    # the long lists are cut ...
    assert powers == "Psychische Kräfte: Smite"                # ... the short lines survive
    assert fate == "Schicksalspunkte: 2"
    assert len(answer) < 2000


def test_the_answer_carries_the_characteristics() -> None:
    # "Was sind meine Werte?" matches — the answer must hold the values it asks for
    store = CharacterStore.from_dict({"characters": [
        {"name": "Rektalus", "characteristics": {"WS": 29, "Wil": 28}, "skills": {"Athletik": 50}},
    ]})
    assert store.sheet_answer_de(store.get("Rektalus")) == (
        "📋 **Rektalus**\nMerkmale: WS 29, Wil 28\nFertigkeiten: Athletik 50")


def test_the_prompt_block_still_reads_the_same_sheet() -> None:
    # the prompt block and the answer share one source — a refactor must not drift them apart
    block = _STORE.sheet_block_de()
    assert ("Fridolin Feuchtgebietheld: Fertigkeiten Heimlichkeit 48, Überreden 42, "
            "Psi-Meisterschaft 51; Talente Leichtfüßig, Glatte Zunge") in block


# --- wiring: a DM-routed line posts the speaker's sheet ----------------------------------------

class _Channel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content or "")
        return SimpleNamespace(content=content)


def _runtime() -> tuple:
    lines: list[tuple[str, str]] = []
    rt = make_runtime()
    rt._characters = _STORE
    rt._char_by_user = {42: "Fridolin Feuchtgebietheld"}
    rt._speaker_names = {}
    rt._speaker_ids = {}
    rt._kick_phrase = False
    rt._text_channel = _Channel()
    rt._post_player_lines = False
    rt._active_vc_id = 7
    rt._last_stt_ms = {}
    rt._brain = SimpleNamespace(add_player_line=lambda cid, name, text: lines.append((name, text)))
    return rt, lines


def _transcribe(rt, speaker: str, text: str, *, for_dm: bool = True) -> None:
    """Feed one STT result the way the worker thread does, then let the loop drain the post."""
    async def run() -> None:
        rt._loop = asyncio.get_running_loop()
        await asyncio.to_thread(rt._on_transcript, speaker, text, 1.0, 100.0, for_dm)
        for _ in range(30):
            await asyncio.sleep(0.01)
            if rt._text_channel.sent:
                break

    asyncio.run(run())


def test_a_routed_sheet_question_posts_the_speakers_sheet_and_still_reaches_the_dm() -> None:
    rt, lines = _runtime()
    rt._speaker_names["Pr0degie"] = rt.character_name_for(42, "Pr0degie")

    _transcribe(rt, "Pr0degie", "Was kann ich eigentlich?")

    assert rt._text_channel.sent == [_STORE.sheet_answer_de(_STORE.get("Fridolin Feuchtgebietheld"))]
    assert lines == [("Fridolin Feuchtgebietheld", "Was kann ich eigentlich?")]  # turn unchanged


@pytest.mark.parametrize("speaker, text, for_dm", [
    ("Gast", "Was kann ich?", True),                 # no character → no post, no error
    ("Pr0degie", "Was kann ich?", False),            # table talk, not routed to the DM
    ("Pr0degie", "Was kann ich sehen?", True),       # a question about the scene
])
def test_no_sheet_post_without_a_character_a_route_or_the_question(
        speaker: str, text: str, for_dm: bool) -> None:
    rt, _lines = _runtime()
    rt._speaker_names["Pr0degie"] = rt.character_name_for(42, "Pr0degie")

    _transcribe(rt, speaker, text, for_dm=for_dm)

    assert rt._text_channel.sent == []
