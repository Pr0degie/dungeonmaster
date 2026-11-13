"""Improvised NPCs join the scene (ADR 062) — the pure half of the post-turn presence classifier.

Live 2026-10-25: Opus invented a "Kettenmann" (later "Brenna"), a "Hakenmann" and four thugs. None
were state, so the attack picker offered Seneschal Kaad from two scenes away and both hits landed
on him. The classifier reports who is physically present; code validates every field.
"""

from __future__ import annotations

import asyncio
import json

from dmbot.llm.npc_router import (
    NpcFailure,
    Sighting,
    card_person,
    classify_present_npcs,
    npc_schema,
    npc_system,
    to_npc_verdict,
)

PARTY = ["Fridolin Feuchtgebietheld", "Rektalus Zerfickus"]
ROSTER = ["Kettenbund-Schläger", "Vosk der Haken", "Seneschall Bramwell Kaad"]


def _verdict(entries, present=()):
    return to_npc_verdict({"npcs": entries}, party=PARTY, roster=ROSTER, present=present, raw="x")


def test_schema_constrains_the_statblock_to_the_roster() -> None:
    s = npc_schema(ROSTER)
    item = s["properties"]["npcs"]["items"]
    assert set(item["properties"]["statblock"]["enum"]) == {*ROSTER, ""}
    assert s["properties"]["npcs"]["maxItems"] == 4


def test_system_prompt_names_party_present_and_roster() -> None:
    sys = npc_system(party=PARTY, roster=ROSTER, present=["Schwester Cassia Vall"])
    for name in (*PARTY, "Schwester Cassia Vall", "Vosk der Haken"):
        assert name in sys


def test_a_new_thug_with_a_statblock_is_accepted() -> None:
    v = _verdict([{"label": "Kettenmann", "statblock": "Kettenbund-Schläger"},
                  {"label": "Hakenmann", "statblock": ""}])
    assert v.failure is None
    assert [(s.label, s.statblock) for s in v.sightings] == [
        ("Kettenmann", "Kettenbund-Schläger"), ("Hakenmann", "")]


def test_player_characters_and_their_first_names_are_dropped() -> None:
    v = _verdict([{"label": "Fridolin", "statblock": ""},
                  {"label": "rektalus zerfickus", "statblock": ""},
                  {"label": "Brenna", "statblock": ""}])
    assert [s.label for s in v.sightings] == ["Brenna"]


def test_already_present_and_duplicate_labels_are_dropped() -> None:
    v = _verdict([{"label": "Schwester Cassia Vall", "statblock": ""},
                  {"label": "Brenna", "statblock": ""}, {"label": "brenna", "statblock": ""}],
                 present=["Schwester Cassia Vall"])
    assert [s.label for s in v.sightings] == ["Brenna"]


def test_narration_and_off_roster_statblocks_are_rejected_field_by_field() -> None:
    v = _verdict([{"label": "Ein Mann, der an der Wand lehnt und eine Kette trägt", "statblock": ""},
                  {"label": "Brenna", "statblock": "Erfundener Block"},
                  {"label": "„Hakenmann“", "statblock": ""}, {"label": 42, "statblock": ""}])
    assert [(s.label, s.statblock) for s in v.sightings] == [("Brenna", "")]


def test_an_empty_list_is_a_clean_verdict_and_garbage_is_a_failure() -> None:
    assert _verdict([]).failure is None and _verdict([]).sightings == ()
    bad = to_npc_verdict({"people": []}, party=PARTY, roster=ROSTER, present=(), raw="x")
    assert bad.failure is NpcFailure.BAD_JSON


def test_classify_fails_open_on_a_broken_call_and_skips_empty_turns() -> None:
    async def boom(*a, **kw):
        raise RuntimeError("backend down")

    v = asyncio.run(classify_present_npcs(boom, answer_text="Ein Kerl tritt vor.", party=PARTY,
                                          roster=ROSTER, present=()))
    assert v.failure is NpcFailure.CALL_FAILED and v.sightings == ()
    v = asyncio.run(classify_present_npcs(boom, answer_text="  ", party=PARTY, roster=ROSTER,
                                          present=()))
    assert v.failure is NpcFailure.NO_INPUT


def test_classify_passes_the_schema_and_parses_the_answer() -> None:
    seen: dict = {}

    async def chat(system, messages, **kw):
        seen.update(kw, system=system, messages=messages)
        return json.dumps({"npcs": [{"label": "Hakenmann", "statblock": "Vosk der Haken"}]})

    v = asyncio.run(classify_present_npcs(chat, answer_text="Der Hakenmann spuckt aus.",
                                          party=PARTY, roster=ROSTER, present=()))
    assert [(s.label, s.statblock) for s in v.sightings] == [("Hakenmann", "Vosk der Haken")]
    assert seen["format"]["properties"]["npcs"]["maxItems"] == 4
    assert "Der Hakenmann spuckt aus." in seen["messages"][0]["content"]


# ---- candidates with their role, and who a sighting is (ADR 062, amendment 2026-11-13) --------

CARD = [("Schwester Cassia Vall", "Schreinschwester der Aschenheiligen"),
        ("Bree Marlok", "Hehlerin, führt die Pfandhalle von Schleusengrund"),
        ("Alter Fenk", "Blinder Vogelhändler am Tor der Pfandhalle")]


def test_the_model_is_given_the_candidates_with_their_roles() -> None:
    """Live 2026-11-13 02:01: "Alter Fenk" was listed as present and came back as a new
    "Blinder Greis" — a bare name says nothing about who he is."""
    seen: dict = {}

    async def chat(system, messages, **kw):
        seen["system"] = system
        return json.dumps({"npcs": []})

    asyncio.run(classify_present_npcs(chat, answer_text="Am Eingang hockt ein blinder Greis.",
                                      party=PARTY, roster=ROSTER, present=["Alter Fenk"],
                                      candidates=CARD))
    for name, role in CARD:
        assert f"{name} — {role}" in seen["system"]
    assert "Nachbarorte" not in npc_system(party=PARTY, roster=ROSTER, present=())


def test_code_decides_which_card_person_a_sighting_is() -> None:
    def who(label, statblock=""):
        return card_person(Sighting(label=label, statblock=statblock), CARD)

    assert who("Schreinschwester") == "Schwester Cassia Vall"    # live 00:40: the role's first word
    assert who("Hehlerin") == "Bree Marlok"                      # the comma in the role is no word
    assert who("Blinder Greis", "Alter Fenk") == "Alter Fenk"    # the verdict's own identification
    assert who("bree marlok") == "Bree Marlok"                   # her name, not yet registered
    assert who("Kettenmann", "Kettenbund-Schläger") == ""        # a statblock off the cards around
    # The verdicts of 01:59 and 02:01 as they came back: no statblock, no role — code cannot know.
    for label in ("Blinder Greis", "Türwächter", "Frau hinter der Sichtklappe"):
        assert who(label) == ""
    twins = [("Schwester Arda", "Schwester der Asche"), ("Schwester Bel", "Schwester des Lichts")]
    assert card_person(Sighting(label="Schwester"), twins) == ""  # fits two: identifies nobody
