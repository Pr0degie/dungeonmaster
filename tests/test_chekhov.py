"""Chekhov list (ADR 050): schema round-trip + atomic write, open-cap eviction, dedupe,
resolved transition, top-3 selection (weight, then age), defensive extraction application
(incl. broken payloads), the extractor-input section, the prompt block, and the wrap-up
variant of the shared ADR-044 extractor call. All list mutations are code — the LLM only
proposes; the LLM call itself is mocked like the other dmbot tests."""

from __future__ import annotations

import asyncio
import json

from dmbot.memory.chekhov import (
    MAX_NEW_PER_EXTRACTION,
    MAX_OPEN,
    MAX_RESOLVED_KEPT,
    ChekhovList,
    ChekhovThread,
    apply_chekhov,
    build_chekhov_section,
    chekhov_block_de,
    is_similar,
)
from dmbot.memory.npc_memory import (
    EXTRACT_SCHEMA_CHEKHOV,
    parse_extraction,
    request_extraction,
)


def _thread(i: int, detail: str = "", *, weight: int = 1, status: str = "open") -> ChekhovThread:
    return ChekhovThread(
        id=f"t{i}", detail=detail or f"Detail Nummer {i} über etwas völlig Eigenes {i}",
        weight=weight, status=status,
    )


# -- schema round-trip + atomic write ---------------------------------------------------------


def test_roundtrip_via_file(tmp_path) -> None:
    path = tmp_path / "sess" / "chekhov.json"
    clist = ChekhovList()
    t = clist.add_thread("Die Münze aus der Bar glüht schwach.", weight=3,
                         origin_scene="bar", created_session="2026-07-04")
    assert t is not None and t.id == "t1"
    clist.resolve("t1")
    clist.save(path)
    loaded = ChekhovList.load(path)
    assert [x.to_dict() for x in loaded.threads] == [x.to_dict() for x in clist.threads]
    assert loaded.threads[0].status == "resolved" and loaded.threads[0].weight == 3
    assert not list(path.parent.glob("*.tmp"))  # atomic write leaves no temp file behind


def test_load_missing_or_broken_file_is_empty(tmp_path) -> None:
    assert ChekhovList.load(tmp_path / "nope.json").threads == []
    broken = tmp_path / "chekhov.json"
    broken.write_text("{kaputt", encoding="utf-8")
    assert ChekhovList.load(broken).threads == []  # never blocks a session


def test_from_dict_clamps_weight_and_status() -> None:
    t = ChekhovThread.from_dict({"id": "t9", "detail": "x", "weight": 99, "status": "quatsch"})
    assert t.weight == 3 and t.status == "open"
    assert ChekhovThread.from_dict({"id": "t1", "detail": "x", "weight": "kaputt"}).weight == 1


# -- cap / eviction ---------------------------------------------------------------------------


def test_open_cap_evicts_oldest_lightest() -> None:
    clist = ChekhovList()
    clist.threads = [_thread(i, weight=1 if i == 3 else 2) for i in range(1, MAX_OPEN + 1)]
    added = clist.add_thread("Ein ganz neues Detail ohne jede Ähnlichkeit.", weight=1)
    assert added is not None
    assert len(clist.open_threads()) == MAX_OPEN
    assert clist.find("t3") is None  # the only weight-1 thread was the victim
    assert clist.find(added.id) is not None


def test_open_cap_falls_back_to_lowest_weight_present() -> None:
    clist = ChekhovList()
    clist.threads = [_thread(i, weight=3 if i == 1 else 2) for i in range(1, MAX_OPEN + 1)]
    clist.add_thread("Noch ein völlig eigenständiges neues Detail.", weight=3)
    assert clist.find("t2") is None   # oldest weight-2 evicted — no weight-1 existed
    assert clist.find("t1") is not None  # the old weight-3 thread survives


def test_resolved_kept_capped_fifo() -> None:
    clist = ChekhovList()
    clist.threads = [
        _thread(i, status="resolved") for i in range(1, MAX_RESOLVED_KEPT + 2)
    ]
    clist.add_thread("Ein frisches offenes Detail für den Anstoß.")
    assert len(clist.resolved_threads()) == MAX_RESOLVED_KEPT
    assert clist.find("t1") is None  # oldest resolved trimmed


# -- dedupe ------------------------------------------------------------------------------------


def test_is_similar_substring_and_word_overlap() -> None:
    assert is_similar("Die Münze aus der Bar", "die münze aus der bar glüht schwach")
    assert is_similar("Der Wirt erwähnte eine versteckte Kammer im Keller",
                      "eine versteckte Kammer im Keller erwähnte der Wirt")
    assert not is_similar("Die Münze aus der Bar", "Der Gouverneur schuldet Fridolin einen Gefallen")
    assert not is_similar("", "irgendwas")


def test_add_thread_dedupes_against_open_and_resolved() -> None:
    clist = ChekhovList()
    clist.add_thread("Die Münze aus der Bar glüht schwach.")
    assert clist.add_thread("die Münze aus der Bar glüht schwach") is None
    clist.resolve("t1")
    # a resolved coin must not come back (dedupe spans ALL threads)
    assert clist.add_thread("Die Münze aus der Bar glüht schwach.") is None
    assert len(clist.threads) == 1


# -- resolve / remove / top-3 -------------------------------------------------------------------


def test_resolve_transition_and_unknown_id() -> None:
    clist = ChekhovList()
    clist.add_thread("Ein offenes Versprechen an den Wirt.")
    assert clist.resolve("T1") is not None  # case-insensitive id
    assert clist.find("t1").status == "resolved"
    assert clist.resolve("t1") is None  # already resolved
    assert clist.resolve("t99") is None
    assert clist.remove("t99") is None


def test_top_open_orders_weight_then_older_first() -> None:
    clist = ChekhovList()
    clist.threads = [
        _thread(1, weight=1),
        _thread(2, weight=3),
        _thread(3, weight=2),
        _thread(4, weight=3),
        _thread(5, weight=2, status="resolved"),
    ]
    top = clist.top_open()
    assert [t.id for t in top] == ["t2", "t4", "t3"]  # weight desc, age asc; resolved excluded


# -- apply (defensive) --------------------------------------------------------------------------


def test_apply_resolves_then_adds_capped() -> None:
    clist = ChekhovList()
    clist.add_thread("Die Münze aus der Bar glüht schwach.")
    distinct = [
        "Der Gouverneur schuldet Fridolin einen Gefallen.",
        "Im Keller tropft etwas Grünes aus dem Rohr.",
        "Die Servitorin summte ein verbotenes Kirchenlied.",
        "Auf dem Frachtbrief fehlt eine Unterschrift.",
        "Der blinde Bettler kannte Seskins Namen.",
        "Jemand hat die Lagerhaus-Kamera verdreht.",
        "Das Amulett des Priesters ist plötzlich verschwunden.",
    ]
    payload = {
        "resolved": ["t1", "t42", 7],
        "new": [{"detail": d, "weight": i % 4} for i, d in enumerate(distinct, start=1)],
    }
    n_new, n_resolved = apply_chekhov(clist, payload, origin_scene="bar",
                                      created_session="2026-07-04")
    assert n_resolved == 1 and clist.find("t1").status == "resolved"
    assert n_new == MAX_NEW_PER_EXTRACTION  # the surplus items were never considered
    fresh = clist.open_threads()[0]
    assert fresh.origin_scene == "bar" and fresh.created_session == "2026-07-04"
    assert all(1 <= t.weight <= 3 for t in clist.threads)


def test_apply_is_defensive_about_garbage() -> None:
    clist = ChekhovList()
    assert apply_chekhov(clist, None) == (0, 0)
    assert apply_chekhov(clist, "kaputt") == (0, 0)
    assert apply_chekhov(clist, {"new": "kaputt", "resolved": {"x": 1}}) == (0, 0)
    assert apply_chekhov(clist, {"new": [{"detail": ""}, "kaputt", {"weight": 2}]}) == (0, 0)
    assert clist.threads == []


def test_apply_dedupes_new_against_existing() -> None:
    clist = ChekhovList()
    clist.add_thread("Die Münze aus der Bar glüht schwach.")
    n_new, _ = apply_chekhov(clist, {"new": [{"detail": "die münze aus der bar glüht schwach"}]})
    assert n_new == 0 and len(clist.threads) == 1


# -- extractor input + prompt block -------------------------------------------------------------


def test_build_chekhov_section_lists_threads_and_earlier_history() -> None:
    section = build_chekhov_section(
        [ChekhovThread(id="t1", detail="Die Münze aus der Bar.", origin_scene="bar")],
        [{"role": "assistant", "content": "Der Wirt zwinkert."},
         {"role": "user", "content": "Ich stecke die Münze ein."},
         {"role": "user", "content": "   "}],
    )
    assert "[t1] Die Münze aus der Bar. (Szene: bar)" in section
    assert "Früherer Verlauf dieser Sitzung" in section
    assert "Spielleitung: Der Wirt zwinkert." in section
    assert "Spieler: Ich stecke die Münze ein." in section


def test_build_chekhov_section_without_threads_or_earlier() -> None:
    section = build_chekhov_section([], [])
    assert "(keine)" in section and "Früherer Verlauf" not in section


def test_chekhov_block_de_renders_offer_or_empty() -> None:
    assert chekhov_block_de([]) == ""
    block = chekhov_block_de([
        ChekhovThread(id="t1", detail="Die Münze aus der Bar.", weight=3),
        ChekhovThread(id="t2", detail="Das offene Versprechen an den Wirt.", weight=1),
    ])
    assert "Lose Fäden" in block and "nicht erzwingen" in block
    assert "- (wichtig) Die Münze aus der Bar." in block
    assert "- Das offene Versprechen an den Wirt." in block
    assert "t1" not in block  # ids are command-surface, not prompt noise


# -- the wrap-up variant of the shared extractor call --------------------------------------------


class _FakeClient:
    """OllamaClient stand-in (convention: the LLM call is mocked, dmbot tests never hit Ollama)."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    async def chat(self, system, messages, *, options=None, format=None) -> str:
        self.calls.append({"system": system, "messages": messages,
                           "options": options, "format": format})
        return self.answers.pop(0)


def test_request_extraction_with_chekhov_section_switches_schema_and_prompt(tmp_path) -> None:
    npc_prompt = tmp_path / "npc.md"
    npc_prompt.write_text("NPC-SYSTEM", encoding="utf-8")
    chek_prompt = tmp_path / "chekhov.md"
    chek_prompt.write_text("CHEKHOV-REGELN", encoding="utf-8")
    answer = json.dumps({"npcs": [], "chekhov": {"new": [], "resolved": []}})
    client = _FakeClient([answer])
    payload = asyncio.run(request_extraction(
        client, turns=[{"role": "user", "content": "Hi"}], npcs=[], scene_id="s",
        chekhov_section="CHEKHOV-SEKTION",
        prompt_path=npc_prompt, chekhov_prompt_path=chek_prompt,
    ))
    assert payload is not None and payload["chekhov"] == {"new": [], "resolved": []}
    call = client.calls[0]
    assert call["format"] == EXTRACT_SCHEMA_CHEKHOV
    assert "chekhov" in call["format"]["required"]
    assert call["system"] == "NPC-SYSTEM\n\nCHEKHOV-REGELN"
    assert call["messages"][0]["content"].endswith("CHEKHOV-SEKTION")


def test_parse_extraction_tolerates_chekhov_payload() -> None:
    raw = '```json\n{"npcs": [], "chekhov": {"new": [{"detail": "x"}], "resolved": ["t1"]}}\n```'
    payload = parse_extraction(raw)
    assert payload is not None
    assert payload["chekhov"]["resolved"] == ["t1"]
