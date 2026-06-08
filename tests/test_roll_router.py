"""Roll-detection router (ADR 014) — pure prompt/schema/parse helpers. The live classification is
verified offline against Ollama (nemo 8/8); here we lock the constrained schema + the JSON→TestRequest
mapping, which is what makes the verdict safe to trust without re-checking the model each turn."""

from dmbot.llm.roll_router import classifier_schema, classifier_system, to_test_request


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
