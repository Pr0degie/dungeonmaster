"""NPC memory (ADR 044): schema round-trip, prune cap, attitude clamp, lie flip, gossip
propagation, top-K selection, prompt-block rendering and tolerant extractor parsing. All hard
effects (attitude, believed flips, registration) are code — the LLM only proposes (golden
rule #3); the LLM call itself is mocked like the orchestrator tests."""

from __future__ import annotations

import asyncio
import json

from dmbot.memory.npc_memory import (
    EXTRACT_SCHEMA,
    apply_extraction,
    build_extract_user,
    npc_memory_block_de,
    parse_extraction,
    propagate_gossip,
    request_extraction,
    select_top_memories,
)
from dmbot.memory.state import (
    ATTITUDE_SCALE,
    NPC_MEMORY_CAP,
    Combatant,
    NpcMemory,
    WorldState,
    step_attitude,
)
from dmbot.rag.adventure import AdventureNpc


def _npc(name: str = "Grubb", attitude: str = "neutral", faction: str = "") -> Combatant:
    return Combatant(
        name=name, wounds=10, max_wounds=10, is_npc=True, attitude=attitude, faction=faction
    )


# -- schema round-trip -------------------------------------------------------------------------


def test_npc_memory_round_trip_and_omit_when_empty() -> None:
    mem = NpcMemory(about=["pc:Kael"], gist="Kael behauptete, Arbites zu sein.",
                    quote="Ich bin im Auftrag des Ordos hier.", believed=False,
                    importance=5, source="gossip", scene="mud_gate", ts="2026-07-03T20:00:00")
    assert NpcMemory.from_dict(mem.to_dict()) == mem
    # Defaults serialise to nothing (omit-when-empty, like the Combatant extras).
    bare = NpcMemory(about=["party"], gist="Small Talk.")
    assert bare.to_dict() == {"about": ["party"], "gist": "Small Talk."}
    assert NpcMemory.from_dict(bare.to_dict()) == bare


def test_combatant_with_memories_survives_state_round_trip(tmp_path) -> None:
    state = WorldState(session_id="t")
    npc = state.add_or_update_npc("Grubb", attitude="wary", faction="Schmuggler")
    npc.add_memory(NpcMemory(about=["party"], gist="Die Gruppe fragte nach der Route."))
    path = tmp_path / "state.json"
    state.save(path)
    loaded = WorldState.load(path)
    got = loaded.npcs[0]
    assert got.faction == "Schmuggler"
    assert got.memories == npc.memories
    # A memory-less combatant keeps a clean dict (omit-when-empty).
    assert "memories" not in Combatant(name="X", wounds=1, max_wounds=1).to_dict()
    assert "faction" not in Combatant(name="X", wounds=1, max_wounds=1).to_dict()


def test_old_state_without_new_fields_loads_unchanged() -> None:
    state = WorldState.from_dict(
        {"session_id": "old", "npcs": [{"name": "Alecto", "wounds": 8, "max_wounds": 8}]}
    )
    npc = state.npcs[0]
    assert npc.faction == "" and npc.memories == []


# -- prune cap ---------------------------------------------------------------------------------


def test_prune_drops_lowest_importance_then_oldest() -> None:
    npc = _npc()
    for i in range(NPC_MEMORY_CAP):
        npc.add_memory(NpcMemory(about=["party"], gist=f"m{i}", importance=2 if i < 2 else 3))
    npc.add_memory(NpcMemory(about=["party"], gist="neu", importance=4))
    assert len(npc.memories) == NPC_MEMORY_CAP
    gists = [m.gist for m in npc.memories]
    assert "m0" not in gists  # lowest importance (2), oldest of the tie (m0 vs m1)
    assert "m1" in gists and "neu" in gists


def test_prune_protects_lies_and_importance_5() -> None:
    npc = _npc()
    npc.add_memory(NpcMemory(about=["party"], gist="lüge", importance=1, believed=False))
    npc.add_memory(NpcMemory(about=["party"], gist="schwur", importance=5))
    for i in range(NPC_MEMORY_CAP - 1):
        npc.add_memory(NpcMemory(about=["party"], gist=f"m{i}", importance=3))
    assert len(npc.memories) == NPC_MEMORY_CAP
    gists = [m.gist for m in npc.memories]
    assert "lüge" in gists and "schwur" in gists  # protected — m0 went instead
    assert "m0" not in gists


def test_prune_all_protected_drops_oldest_anyway() -> None:
    npc = _npc()
    for i in range(NPC_MEMORY_CAP + 1):
        npc.add_memory(NpcMemory(about=["party"], gist=f"m{i}", importance=5))
    assert len(npc.memories) == NPC_MEMORY_CAP  # hard cap wins
    assert npc.memories[0].gist == "m1"


# -- attitude clamp ----------------------------------------------------------------------------


def test_step_attitude_clamps_to_one_step() -> None:
    npc = _npc(attitude="neutral")
    assert step_attitude(npc, "loyal") == "friendly"  # two steps proposed → one applied
    assert step_attitude(npc, "hostile") == "neutral"
    assert step_attitude(npc, "neutral") == "neutral"  # same value → no move


def test_step_attitude_unknown_proposal_is_a_noop() -> None:
    npc = _npc(attitude="wary")
    assert step_attitude(npc, "ecstatic") == "wary"
    assert step_attitude(npc, "") == "wary"
    assert npc.attitude == "wary"


def test_step_attitude_offscale_current_anchors_at_neutral() -> None:
    npc = _npc(attitude="misstrauisch")  # legacy free-text value
    assert step_attitude(npc, "hostile") == "wary"  # neutral → one step down
    npc2 = _npc(attitude="")
    assert step_attitude(npc2, "loyal") == "friendly"


def test_step_attitude_clamps_at_scale_ends() -> None:
    npc = _npc(attitude="hostile")
    assert step_attitude(npc, "hostile") == "hostile"
    npc.attitude = "loyal"
    assert step_attitude(npc, "loyal") == "loyal"
    assert ATTITUDE_SCALE[0] == "hostile" and ATTITUDE_SCALE[-1] == "loyal"


# -- apply_extraction: new memories -------------------------------------------------------------


def test_apply_adds_memories_and_clamps_fields() -> None:
    state = WorldState()
    state.add_or_update_npc("Grubb", attitude="neutral")
    payload = {"npcs": [{
        "name": "grubb",  # case-insensitive join
        "memories": [
            {"about": ["pc:Kael"], "gist": "Kael behauptete, Arbites zu sein.",
             "quote": "Ich bin im Auftrag des Ordos hier.", "importance": 9},
            {"about": [], "gist": "  " + "x" * 500, "importance": 0},
        ],
        "attitude_proposal": "loyal",
    }]}
    new = apply_extraction(state, payload, scene_id="mud_gate", now="2026-07-03T20:00:00")
    npc = state.npcs[0]
    assert len(new) == 2 and all(n is npc for n, _ in new)
    first, second = npc.memories
    assert first.importance == 5 and first.quote and first.scene == "mud_gate"
    assert second.about == ["party"]  # empty about defaults to the whole group
    assert second.importance == 1
    assert len(second.gist) <= 200
    assert npc.attitude == "friendly"  # loyal proposed from neutral → one step only


def test_apply_dedupes_gists_and_skips_pcs_and_empty() -> None:
    state = WorldState(characters=[Combatant(name="Kael", wounds=10, max_wounds=10)])
    npc = state.add_or_update_npc("Grubb")
    npc.add_memory(NpcMemory(about=["party"], gist="Schon bekannt."))
    payload = {"npcs": [
        {"name": "Grubb", "memories": [
            {"about": ["party"], "gist": "schon bekannt."},  # dup (casefold) → skipped
            {"about": ["party"], "gist": ""},                # empty → skipped
        ]},
        {"name": "Kael", "memories": [{"about": ["party"], "gist": "Nie speichern."}]},
    ]}
    new = apply_extraction(state, payload, scene_id="s")
    assert new == []
    assert len(npc.memories) == 1
    assert state.characters[0].memories == []  # a PC never gets NPC memories


def test_apply_registers_unknown_npc_from_statblock() -> None:
    state = WorldState()
    block = AdventureNpc(name="Wirt Grubb", wounds=7, toughness_bonus=2, armour=1,
                         faction="Unterschacht")
    payload = {"npcs": [{"name": "Wirt Grubb",
                         "memories": [{"about": ["party"], "gist": "Erste Begegnung."}]}]}
    apply_extraction(state, payload, scene_id="s",
                     statblock=lambda name: block if name == "Wirt Grubb" else None)
    npc = state.npcs[0]
    assert npc.wounds == 7 and npc.faction == "Unterschacht" and npc.attitude == "neutral"
    assert npc.memories[0].gist == "Erste Begegnung."


# -- apply_extraction: lie flip -----------------------------------------------------------------


def test_revealed_lie_flips_entry_and_steps_toward_hostile() -> None:
    state = WorldState()
    npc = state.add_or_update_npc("Grubb", attitude="friendly")
    npc.add_memory(NpcMemory(about=["pc:Kael"], gist="Kael behauptete, Arbites zu sein.",
                             quote="Ich bin im Auftrag des Ordos hier."))
    payload = {"npcs": [{"name": "Grubb", "revealed_lies": [0]}]}
    apply_extraction(state, payload, scene_id="s2", now="2026-07-03T21:00:00")
    lied, flip = npc.memories
    assert lied.believed is False
    assert flip.importance == 5 and flip.believed is True
    assert "Kael" in flip.gist and "belogen" in flip.gist
    assert flip.scene == "s2"
    assert npc.attitude == "neutral"  # friendly → one step toward hostile


def test_revealed_lie_invalid_index_and_repeat_are_safe() -> None:
    state = WorldState()
    npc = state.add_or_update_npc("Grubb", attitude="neutral")
    npc.add_memory(NpcMemory(about=["party"], gist="Angeblich harmlos.", believed=False))
    payload = {"npcs": [{"name": "Grubb", "revealed_lies": [0, 5, "x"]}]}
    apply_extraction(state, payload, scene_id="s")
    # index 0 already flipped → idempotent (no extra entry, no attitude step); 5/"x" ignored.
    assert len(npc.memories) == 1
    assert npc.attitude == "neutral"


def test_lie_flip_and_proposal_combine_in_one_scene() -> None:
    state = WorldState()
    npc = state.add_or_update_npc("Grubb", attitude="friendly")
    npc.add_memory(NpcMemory(about=["pc:Kael"], gist="Kael sei Arbites."))
    payload = {"npcs": [{"name": "Grubb", "revealed_lies": [0],
                         "attitude_proposal": "hostile"}]}
    apply_extraction(state, payload, scene_id="s")
    # friendly → neutral (lie flip) → wary (proposal, clamped to one further step)
    assert npc.attitude == "wary"


# -- gossip -------------------------------------------------------------------------------------


def _gossip_state() -> tuple[WorldState, Combatant, Combatant, Combatant]:
    state = WorldState()
    src = state.add_or_update_npc("Grubb", faction="Schmuggler")
    mate = state.add_or_update_npc("Vex", faction="schmuggler")  # case-insensitive faction join
    outsider = state.add_or_update_npc("Alecto", faction="Arbites")
    return state, src, mate, outsider


def test_gossip_spreads_important_direct_memories_within_the_faction() -> None:
    state, src, mate, outsider = _gossip_state()
    mem = NpcMemory(about=["party"], gist="Die Gruppe sucht die Route.",
                    quote="Wir zahlen gut.", importance=4, scene="s", ts="t")
    src.add_memory(mem)
    planted = propagate_gossip(state, [(src, mem)])
    assert planted == 1
    got = mate.memories[0]
    assert got.source == "gossip" and got.quote == "" and got.importance == 3
    assert got.gist == mem.gist and got.scene == "s"
    assert outsider.memories == [] and len(src.memories) == 1


def test_gossip_respects_threshold_faction_and_duplicates() -> None:
    state, src, mate, _ = _gossip_state()
    low = NpcMemory(about=["party"], gist="Belanglos.", importance=3)
    src.add_memory(low)
    assert propagate_gossip(state, [(src, low)]) == 0  # below the importance threshold
    lonely = state.add_or_update_npc("Solo", faction="")
    big = NpcMemory(about=["party"], gist="Wichtig!", importance=5)
    lonely.add_memory(big)
    assert propagate_gossip(state, [(lonely, big)]) == 0  # empty faction never gossips
    # Duplicate gist at the recipient → skip.
    mate.add_memory(NpcMemory(about=["party"], gist="Grosse Neuigkeit.", source="gossip"))
    news = NpcMemory(about=["party"], gist="grosse neuigkeit.", importance=5)
    src.add_memory(news)
    assert propagate_gossip(state, [(src, news)]) == 0


def test_gossip_does_not_cascade() -> None:
    state, src, mate, _ = _gossip_state()
    heard = NpcMemory(about=["party"], gist="Hörensagen.", importance=5, source="gossip")
    src.add_memory(heard)
    # A gossip-sourced entry never propagates further (no gossip-of-gossip).
    assert propagate_gossip(state, [(src, heard)]) == 0
    assert mate.memories == []


# -- top-K selection + rendering -----------------------------------------------------------------


def test_select_top_memories_ranks_importance_then_recency_and_pins_lies() -> None:
    npc = _npc()
    npc.add_memory(NpcMemory(about=["party"], gist="alt-wichtig", importance=4))
    npc.add_memory(NpcMemory(about=["party"], gist="lüge", importance=1, believed=False))
    npc.add_memory(NpcMemory(about=["party"], gist="klein-alt", importance=2))
    npc.add_memory(NpcMemory(about=["party"], gist="klein-neu", importance=2))
    top = select_top_memories(npc, 3)
    assert [m.gist for m in top] == ["lüge", "alt-wichtig", "klein-neu"]  # lie pinned, then imp/recency


def test_npc_memory_block_renders_tags_quotes_and_attitude() -> None:
    npc = _npc(attitude="wary")
    npc.add_memory(NpcMemory(about=["pc:Kael"], gist="Kael behauptete, Arbites zu sein.",
                             quote="Ich bin im Auftrag des Ordos hier.", importance=5))
    npc.add_memory(NpcMemory(about=["party"], gist="Die Gruppe fragte nach der Route.",
                             importance=3, source="gossip"))
    npc.add_memory(NpcMemory(about=["party"], gist="Angeblich Händler.", believed=False))
    block = npc_memory_block_de([npc], top_k=6)
    assert "[NPC-Gedächtnis: Grubb — Haltung: misstrauisch]" in block
    assert "- (wichtig) Kael behauptete, Arbites zu sein. Zitat: „Ich bin im Auftrag des Ordos hier.“" in block
    assert "- (Hörensagen) Die Gruppe fragte nach der Route." in block
    assert "- (als Lüge aufgeflogen) Angeblich Händler." in block
    assert block.startswith("## NPC-Gedächtnis")


def test_npc_memory_block_empty_cases() -> None:
    assert npc_memory_block_de([]) == ""
    assert npc_memory_block_de([_npc()]) == ""  # an NPC without memories renders nothing


def test_npc_memory_block_respects_top_k() -> None:
    npc = _npc()
    for i in range(10):
        npc.add_memory(NpcMemory(about=["party"], gist=f"m{i}"))
    block = npc_memory_block_de([npc], top_k=2)
    assert block.count("\n- ") == 2


# -- extractor input + parsing -------------------------------------------------------------------


def test_build_extract_user_numbers_existing_memories() -> None:
    npc = _npc(attitude="wary")
    npc.add_memory(NpcMemory(about=["pc:Kael"], gist="Kael sei Arbites.", quote="Ordos!"))
    npc.add_memory(NpcMemory(about=["party"], gist="Alte Lüge.", believed=False))
    user = build_extract_user(
        [{"role": "user", "content": "Kael: Wir sind harmlos."},
         {"role": "assistant", "content": "Grubb nickt."},
         {"role": "user", "content": "   "}],
        [npc], "mud_gate",
    )
    assert "Szene: mud_gate" in user
    assert "- Grubb (Haltung: misstrauisch)" in user
    assert "[0] Kael sei Arbites. Zitat: „Ordos!“" in user
    assert "[1] Alte Lüge. [als Lüge aufgeflogen]" in user
    assert "Spieler: Kael: Wir sind harmlos." in user
    assert "Spielleitung: Grubb nickt." in user


def test_parse_extraction_tolerates_fences_and_rejects_junk() -> None:
    payload = {"npcs": [{"name": "Grubb"}]}
    assert parse_extraction(json.dumps(payload)) == payload
    assert parse_extraction(f"```json\n{json.dumps(payload)}\n```") == payload
    assert parse_extraction("kein json") is None
    assert parse_extraction("[1, 2]") is None          # not a dict
    assert parse_extraction('{"npcs": "nope"}') is None  # npcs not a list
    assert parse_extraction("") is None


class _FakeClient:
    """OllamaClient stand-in (convention: the LLM call is mocked, dmbot tests never hit Ollama)."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    async def chat(self, system, messages, *, options=None, format=None) -> str:
        self.calls.append({"system": system, "messages": messages,
                           "options": options, "format": format})
        return self.answers.pop(0)


def test_request_extraction_returns_parsed_payload(tmp_path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("SYSTEM", encoding="utf-8")
    client = _FakeClient(['{"npcs": []}'])
    payload = asyncio.run(request_extraction(
        client, turns=[{"role": "user", "content": "Hi"}], npcs=[_npc()],
        scene_id="s", prompt_path=prompt,
    ))
    assert payload == {"npcs": []}
    call = client.calls[0]
    assert call["system"] == "SYSTEM"
    assert call["format"] == EXTRACT_SCHEMA
    assert call["options"]["repeat_penalty"] == 1.0  # deterministic side-band call (ADR 042)


def test_request_extraction_retries_once_then_skips(tmp_path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("SYSTEM", encoding="utf-8")
    client = _FakeClient(["kaputt", "immer noch kaputt"])
    payload = asyncio.run(request_extraction(
        client, turns=[], npcs=[], scene_id="s", prompt_path=prompt,
    ))
    assert payload is None
    assert len(client.calls) == 2  # exactly one retry, then skip — never raises
