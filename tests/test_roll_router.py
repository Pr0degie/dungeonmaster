"""Roll-detection router (ADR 014) — pure prompt/schema/parse helpers. The live classification is
verified offline against Ollama (nemo 8/8); here we lock the constrained schema + the JSON→TestRequest
mapping, which is what makes the verdict safe to trust without re-checking the model each turn."""

from dmbot.llm.roll_router import (
    classifier_schema,
    classifier_system,
    is_continuation_fragment,
    roll_button_source,
    superseded_by_manifest,
    to_test_request,
)


def test_schema_constrains_skill_and_difficulty_to_the_allowed_sets():
    s = classifier_schema(["Heimlichkeit", "Wahrnehmung"], ["Schwer", "Routine"])
    assert "Heimlichkeit" in s["properties"]["skill"]["enum"]
    assert "" in s["properties"]["skill"]["enum"]  # "" = no test
    assert "Schwer" in s["properties"]["difficulty"]["enum"]
    assert set(s["required"]) == {"needs_test", "skill", "difficulty"}


def test_system_prompt_lists_the_skills_and_demands_json():
    sys = classifier_system(["Heimlichkeit"], ["Schwer"], "Imperium Maledictum")
    assert "Heimlichkeit" in sys and "Imperium Maledictum" in sys and "JSON" in sys


def test_maps_a_positive_verdict_to_a_test_request():
    req = to_test_request(
        {"needs_test": True, "skill": "Heimlichkeit", "difficulty": "Schwer"}, character="Seskin"
    )
    assert req is not None
    assert req.skill == "Heimlichkeit" and req.difficulty == "Schwer"
    assert req.target_name == "Seskin" and req.parsed


def test_none_when_no_test_or_blank_skill():
    assert to_test_request({"needs_test": False, "skill": "", "difficulty": ""}, character="Seskin") is None
    assert to_test_request({"needs_test": True, "skill": "", "difficulty": "Schwer"}, character="X") is None


def test_none_on_garbage_input():
    assert to_test_request("not a dict", character=None) is None
    assert to_test_request({}, character=None) is None


def test_blank_difficulty_becomes_none():
    req = to_test_request({"needs_test": True, "skill": "Athletik", "difficulty": ""}, character="Vask")
    assert req is not None and req.difficulty is None  # engine then uses the profile default


# --- dedupe: the router wins when it's on (D43, flips D40) — the constrained classifier picks
# reliable skills, the narration model's inline markers don't (seen live: <<TEST Heimlichkeit>>
# for an attack). Markers are the fallback only when the router is off. One button per action.

def test_roll_button_source_router_wins_the_dedupe():
    # router on → the router decides, with or without inline markers (markers are discarded)
    assert roll_button_source(True, 0) == "router"
    assert roll_button_source(True, 1) == "router"
    assert roll_button_source(True, 3) == "router"
    # router off → inline <<TEST>> markers are the only trigger
    assert roll_button_source(False, 2) == "marker"
    assert roll_button_source(False, 0) == "none"


# --- 2026-10-25 run --------------------------------------------------------------------------------

def test_a_reported_speech_fragment_is_not_an_action():
    """Live: Sezgin's whole turn was "dass wir das Osadium suchen." — the tail of what he told the
    Arbites. The classifier read "suchen" as a search and asked Rektalus for Wahrnehmung."""
    assert is_continuation_fragment("dass wir das Osadium suchen.")
    assert is_continuation_fragment("  Daß wir nichts Böses wollen")
    assert is_continuation_fragment("weil sie etwas verbirgt.")


def test_a_declared_action_is_not_a_fragment():
    assert not is_continuation_fragment("Ich untersuche den Schrein nach Spuren.")
    assert not is_continuation_fragment("Wenn er sich umdreht, schleiche ich vorbei.")
    assert not is_continuation_fragment("")


def test_any_router_test_is_dropped_when_the_psyker_already_manifests():
    """Live 2026-10-25, twice: one psi action posted a Manifest *and* a router test — first
    "Psi-Meisterschaft (Schwierig)", in the next run "Fel (Herausfordernd)" for Dread Presence.
    Both were rolled and narrated. The Manifest Test is that character's roll for the action."""
    manifesting = {"fridolin feuchtgebietheld"}
    assert superseded_by_manifest("Fridolin Feuchtgebietheld", manifesting=manifesting)
    assert superseded_by_manifest("  fridolin feuchtgebietheld ", manifesting=manifesting)


def test_other_characters_are_not_superseded():
    assert not superseded_by_manifest("Rektalus Zerfickus", manifesting={"fridolin feuchtgebietheld"})
    assert not superseded_by_manifest("Fridolin Feuchtgebietheld", manifesting=set())
    assert not superseded_by_manifest(None, manifesting={"fridolin feuchtgebietheld"})


def test_the_classifier_defaults_to_the_middle_difficulty():
    """Live 2026-10-25: "Ich schieße ihm ins Gesicht" (gun already at his head) came back
    Fernkampf *Schwierig* with no reason in the action — the prompt now pins the default."""
    sys = classifier_system(["Fernkampf"], ["Leicht", "Herausfordernd", "Schwierig"], "IM")
    assert "Standard ist die mittlere" in sys and "Im Zweifel die mittlere" in sys
    assert "nächster Nähe" in sys
