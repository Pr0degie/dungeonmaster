# Draft amendment to ADR 062 — for card figures the card is authoritative (2026-11-15)

**Status:** candidate, not built (Tobi, 2026-11-15). The draft stays in reserve for the case that
the next run shows a presence error D144 does not catch. No decision row exists; the open points
in section 8 were not decided. See "Verification and decision" right below the summary.
**Amends:** [ADR 062](../decisions/062-improvised-npcs-join-the-scene.md), points 2, 6, 8, 9, 10
and 11; decision rows D138 and D144.
**Code references:** commit `9a4f3e1` (HEAD on 2026-11-15). Line numbers are from that commit.
**Evidence:** [npc-sighting-stale-scene-2026-11-13.md](npc-sighting-stale-scene-2026-11-13.md),
`logs/debug-bis-2026-11-14.log` (the sessions of 2026-11-13 start at lines 11844, 11914 and
12256) and `logs/debug-d1.log` (the run of 2026-11-14, 19:04–19:33).

ADR 062 has eleven numbered points: 1–5 in the decision, 6–10 in the amendment of 2026-11-13,
11 in the amendment of 2026-11-14. Points 6, 9 and 11 each estimate how far the narration is
ahead of the scene pointer: "until the next turn boundary", "the scene being left", "two turns
running". This draft replaces the estimates for one group of NPCs with a fixed rule.

## Summary

- **The rule holds for what it covers.** It removes every state write that puts a card figure
  into a scene from a sighting. Points 10 and 11 and the first half of point 9 go completely,
  points 2, 6, 8 and 9b shrink, and one per-channel memory goes (`_neighbour_seen`).
- **Against the logs:** of eight observations on 2026-11-13 and 2026-11-14, the rule prevents
  three (every case in which a card figure or her double was written into the wrong scene), one
  in part, and four not. The four are two doubles that are an identity problem, one transient
  that was no lasting error, and one unclear entry. Today's code (HEAD, with D144) also gets
  these three right in the timing the logs show, two of them only because the second turn at
  the door brought no second sighting of the same figure. The rule gets them right without
  depending on that.
- **The price:** a card figure who really goes with the group is absent from the prompt's scene
  line, the NPC-memory block and the target picker until the game master types a command. Today
  that heals by itself after one turn. In the two logged evenings no card figure travelled, so
  the price was never paid there.
- **Code size stays about the same** (estimate): roughly 55 lines go, and a helper, the card
  check and the command add roughly as many. What shrinks is the rule set, not the line count.

## Verification and decision (2026-11-15)

The draft was checked independently before it went to Tobi. What was checked:

- **The assertion list.** The in-memory patch of section 3 was run again against the whole suite
  at commit `9a4f3e1`: 7 failed, 1558 passed, 4 xfailed, and the seven are the tests section 3
  names. The "after" assertions (89 of 89 on a copy of the test file) were not run again.
- **The log rows of section 6.** Rows 1, 2, 3, 4, 5, 6 and 7 were read in the two logs and stand
  as quoted. Row 6 holds: the man reported at 19:20:54 says "Vosk will wissen, wer nach seiner
  Fracht fragt … bevor er selbst rauskommt" at 19:21:58, and Vosk himself speaks at 19:22:16.
- **The code of section 2.** The lines the draft removes in `dmbot/session/scenes.py` are the
  ones that write a card figure today, and `!npc` has only `add` and `list`.
- **Not checked:** the command of section 4. Nobody prototyped it.

What the check found, and why the rule was not built:

- **No additional prevented error.** Against today's code (D144) the rule prevents none of the
  eight logged observations that D144 does not already get right. Its gain is a smaller rule
  set, not fewer observed errors.
- **The line count stays about the same.** Roughly 55 lines go, and the helper, the card check
  and the command add about as many.
- **The price falls on card figures who travel with the group.** Such a figure stands in the
  prompt as "NICHT anwesend", is missing from the NPC-memory block and from the target picker
  until someone types the command, and the only signal is a log line. Neither logged evening had
  a travelling card figure, so how often this would bite is unknown.
- **A misjudged statblock drops the figure.** An improvised figure the classifier takes for a
  card figure (the chain thug reported as Vosk) gets no entry at all in that turn.

Decision: not built. The next run checks D144 as it is (checkpoint F7 in
`docs/phase-11-abend.md`). Two smaller levers on the same gap are recorded as candidates in
`progress.md` and are not built either: a persona sentence that puts the `<<ORT>>` marker into
the answer that narrates the arrival, and the turn's player lines for the presence classifier.

## 1. The rule and its scope

**Terms.** A *card figure* is an NPC named in `npcs_here` of at least one scene card of the
loaded adventure, unless her statblock is flagged `generic`. This is the definition
`_card_people` already uses (`dmbot/session/scenes.py:347`), taken over the whole adventure
instead of over the scenes around the pointer, and it includes the dead. An *improvised figure*
is every other NPC in the world state: one the presence classifier registered, an `!npc add`
entry, an entry made from a `generic` statblock ("Kettenbund-Schläger"), a name the NPC-memory
extractor registered.

**The rule.**

1. For a card figure the scene cards decide where she is. She is present in every scene whose
   card lists her, and in no other.
2. A sighting never writes a card figure. It does not register her, does not move her and does
   not file her to follow a move. Sightings count for improvised figures only.
3. A card figure is present in a scene her card does not list only after the game master has
   placed her there with a command (section 4). Only a command takes the placement back.

**Scope, case by case.**

| Case | What happens |
| --- | --- |
| Card figure on one card | Present when the pointer stands on that scene and she is alive. Unchanged. |
| Card figure on several cards (debug campaign: Bree Marlok on `pfandhalle` and `siedehaus`, Arno Kessel on `siedehaus` and `pier_neun`; Chemical Burn: Raguel der Rote on four cards) | Present in each of those scenes while the pointer stands there. There is no "current home" and no first-exit-wins choice as in `_neighbour_homes` today. Only one scene is ever looked at, so being on two cards never shows as being in two places. Unchanged from the card half of `WorldState.present_npcs` (`dmbot/memory/state.py:1030`). |
| The narration shows a card figure in a scene whose card does not list her, and code recognises her | Nothing is written. She is not in "NSCs in der Szene", not in the NPC-memory block, not in the target picker. If she is already registered she stands in the prompt line "NSCs anderswo (NICHT anwesend …)" (`dmbot/memory/state.py:1421`). One log line names her, the label she was reported under and her card scenes. If she is really there, the game master places her. |
| The same, but code does not recognise her | She becomes an improvised entry under the reported label, as today ("Blinder Greis" for Alter Fenk). The rule does not touch identity; see section 6, rows 2–4. |
| How code recognises a card figure | By name over the whole adventure: the label is the name of a card figure, whether registered or not. By statblock, authored alias or role only inside the candidate set of amendment #8, which stays as it is: the cards of the scene the sighting lands in, of every exit reachable right now, and of the scene the turn began in. A statblock of a card figure outside that set stays a template for numbers, as today. |
| Dead card figure | Unchanged: she is no candidate, and a newcomer in her role gets an entry of her own (amendment #8). A sighting under her own name writes nothing. |
| `generic` statblock on a card | No person. Unchanged, the rule does not touch it. |
| No adventure loaded | No cards, so every NPC is improvised. Unchanged. |

**Fixed constraints, kept.** The classifier verdict still only names people; code decides scene,
identity and numbers (golden rule #3). The only new writer of hard state is a command typed by a
human. No call site names an LLM backend; the change adds no LLM call and changes no prompt. The
persona file is not touched.

## 2. What falls away

### Rules

| Point | Today | After |
| --- | --- | --- |
| 1 classifier reports who is present | | stays |
| 2 code validates and writes; "a known NPC is moved into the current scene" | applies to every NPC | **stays for improvised figures.** A known card figure is not moved. |
| 3 presence is the card or `Combatant.scene` | | stays. For a card figure `Combatant.scene` is written by the command only. |
| 4 target picker offers present NPCs only | | stays |
| 5 switch `DM_NPC_ROUTER`, `!automatik nscs` | | stays |
| 6 a sighting lands under the pointer after the verdict and follows a move of the open turn; the flag gate carries nobody | | **stays for improvised figures.** No card figure is ever filed to follow a move. |
| 7 candidates carry role and aliases | | stays unchanged, prompt included. Code needs the recognition to discard the sighting instead of registering a double. |
| 8 code decides identity | a recognised card figure is merged: registered if new, placed where the rule says | **the identity check stays, the write goes.** A recognised card figure is discarded. The clauses on `generic`, templates and the dead stay. |
| 9a a card figure of the scene being left does not follow the move | | **goes completely.** No card figure can be in `_turn_sightings`. |
| 9b the card people of the scene the turn began in are candidates; a sighting recognised as one of them is filed in that scene | | **the candidate half stays** (otherwise "Zöllner" seen during the walk becomes a double in the new scene). **The filing half goes.** |
| 10 entering a scene clears the `scene` field of its card figures | | **goes completely.** It existed to undo sightings. Under the rule the field of a card figure holds only a placement by command, and only a command clears it. See "Open points" for the alternative. |
| 11 a neighbouring scene's card figure seen once stays at home, seen again the next turn is placed | | **goes completely**, with its memory `_neighbour_seen`. |

Decision rows: D124 stays. D138 is narrowed: "code merges a sighting into such a person" becomes
"code recognises such a person and writes nothing", and "follows every move" holds for
improvised figures only. D144 is superseded as a whole. The amendment needs a new row with the
next free number (D147 is the newest on 2026-11-15).

### Code

| Place | Lines | Fate |
| --- | --- | --- |
| `dmbot/session/scenes.py`, `_set_scene`: the loop that clears `npc.scene` of the entered scene's card people | 66–71 | goes completely (#10) |
| `scenes.py`, `_CARRYING_TRIGGERS` | 77–80 | stays for improvised figures |
| `scenes.py`, `_carry_turn_sightings`: `home = self._card_people(left)` and the `continue` for a person on that card | 90, 93–94 | goes completely (#9a). The rest of the method stays for improvised figures; the docstring (83–88) loses its #9 sentence. |
| `scenes.py`, `close_turn`: `self._turn_sightings.pop`, `classified_from`, `began_in=classified_from` | 197, 199, 208–209 | stays (`began_in` now feeds the identity check only) |
| `scenes.py`, `_post_turn_questions`: the `npc` question | 303–310 | stays unchanged |
| `scenes.py`, `_npc_candidates` | 313–329 | stays |
| `scenes.py`, `_neighbour_homes` | 331–345 | goes completely (#11) |
| `scenes.py`, `_card_people` | 347–366 | stays |
| `scenes.py`, `_apply_npc_sightings`: `seen_before = self._neighbour_seen.pop(...)` | 386 | goes completely |
| same: `home` and `candidates` | 392–394 | stays, for the identity check |
| same: `neighbour`, `seen_now` | 395–396 | goes completely |
| same: `known`, `person`, `target`, the player-character guard | 400–404 | stays |
| same: `statblock = person or sighting.statblock` | 405 | becomes `sighting.statblock`: on the path that still writes, `person` is always empty |
| same: `stays`, `elsewhere`, the seen-twice check | 409–416 | goes completely |
| same: `state.place_npc(name, began_in if stays else (elsewhere or scene_id), …, goal=block.goal_de if block and person else "")` | 417–424 | stays for improvised figures with `scene_id` as the scene; the `goal` argument goes (it was only ever set for a recognised card figure) |
| same: the notes "gemeldet als", "bleibt in", "gehört nach … bleibt dort" | 426–431 | goes completely; "gemeldet als" moves into the new log line for a discarded card sighting |
| same: `if not elsewhere:` guard, `self._neighbour_seen[cid] = seen_now` | 433–436 | goes completely; every placed NPC is filed |
| same: `_turn_sightings`, persist, the `👥 anwesend in` log line | 439–442 | stays |
| `dmbot/runtime.py`, `self._neighbour_seen` with its comment | 286–289 | goes completely |
| `dmbot/runtime.py`, `self._turn_sightings` | 283–285 | stays for improvised figures |
| `dmbot/memory/state.py`, `place_npc`, `present_npcs`, `Combatant.scene` | 996–1012, 1030–1034, 263 | stay unchanged. `place_npc` keeps moving a known NPC; the card check sits in the runtime, so `dmbot/tools/aux_parity.py:188` and `dmbot/tools/text_replay.py:218`, which call it directly, are not affected. |
| `dmbot/llm/npc_router.py`, `card_person`, `Candidate`, `npc_question` | 218–238, 75–81, 123–155 | stay unchanged |

### What is new

- A helper in `scenes.py` next to `_card_people`, for example `_card_homes()`: `{casefolded name:
  ids of the scenes whose card lists her}` over all scenes (`self._adventure.scene_overview()`
  gives the ids, `_card_people(sid)` the people). Keys must be built the way `_card_people`
  builds them (stripped name, `casefold()`).
- In `_apply_npc_sightings`, after the player-character guard: if `name` (the recognised person
  or the label) is a key of `_card_homes()`, log and `continue`. Proposed log line:
  `👥 Karten-Figur, Sichtung zählt nicht: Bree Marlok (gemeldet als „Person hinter dem Sehschlitz“;
  Karte: pfandhalle, siedehaus) — Zeiger auf 'schrein'`.
- The `ort` action of `!npc` (section 4).

The loop body as it was run against the suite (see section 3), log line left out:

```python
known = state.find(sighting.label)
person = "" if known is not None else card_person(sighting, candidates)
target = state.find(person) if person else known
if target is not None and not target.is_npc:
    continue
name = person or sighting.label
if name.strip().casefold() in homes:        # a card figure: the card decides, nothing is written
    continue
block = (self._adventure.npc(sighting.statblock)
         if self._adventure is not None and sighting.statblock else None)
npc, new = state.place_npc(
    name, scene_id,
    wounds=block.wounds if block else defaults["wounds"],
    toughness_bonus=block.toughness_bonus if block else defaults["toughness_bonus"],
    armour=block.armour if block else defaults["armour"],
    faction=block.faction if block else "",
)
```

## 3. Assertions that change

**How this list was made.** The rule was patched into `SceneFlowMixin` in memory by a pytest
plugin kept outside the repository (`_set_scene` without lines 66–71, `_carry_turn_sightings`
without the card skip, `_apply_npc_sightings` as sketched above), and the whole suite was run
against it. Baseline: 1565 passed, 4 xfailed. With the rule: **7 failed**, 1558 passed, 4
xfailed. All seven are in `tests/test_turn_boundary.py`. Then the "after" assertions below were
applied to a copy of that file and run against the same patch: 89 of 89 passed. `dm-eval`
exits 0 with and without the patch; `dmbot/tools/eval_replay.py` replays scene moves and element
flags and never touches NPC presence. Keeping #10 instead of dropping it gives the same seven
failures and the same 89 passes.

If any other assertion breaks during the build, this list is wrong: stop and report.

| Test (`tests/test_turn_boundary.py`) | Line | Today | After |
| --- | --- | --- | --- |
| `test_an_improvised_thug_is_registered_in_the_scene_he_was_narrated_in` | 1206 | `state.find("Schwester Vall").scene == "schrein"`: the sighting ("Vall-Double", statblock "Schwester Vall") registers Vall and files her in the shrine | `state.find("Schwester Vall") is None`: the fixture sets the pointer without entering the scene, and the sighting writes nothing |
| same | 1207 | `[n.name for n in rt._scene_npcs(state)] == ["Kettenmann", "Schwester Vall"]` | `== ["Kettenmann"]` |
| helper `_kaad_stayed_behind`, used at 1421, 1432 and 1442 | 1393 | `state.find("Seneschall Kaad").scene == "zollhaus"`: #9b files the recognised Kaad under the scene the turn began in | `.scene == ""`: he is at home through his card, nothing was written. The other three conditions of the helper hold unchanged. |
| `test_a_card_figure_of_the_scene_left_does_not_follow_the_classifiers_move` | 1409 | `state.find("Seneschall Kaad").scene == "zollhaus"` | `.scene == ""`. Lines 1408, 1410 and 1412 hold unchanged ("Narbengesicht", an improvised thug with a `generic` statblock, still goes along). |
| `test_a_card_figure_of_the_scene_left_does_not_follow_a_late_button` | 1421 | fails through the helper only | passes with the helper change |
| `test_a_card_figure_of_the_scene_left_gets_no_entry_in_the_scene_arrived_in` | 1432 | fails through the helper only | passes with the helper change; line 1433 holds unchanged |
| `test_a_card_figure_that_came_along_is_placed_once_the_next_turn_reports_her` | 1442 | helper | passes with the helper change |
| same | 1447 | `state.find("Seneschall Kaad").scene == "schrein"`: a second sighting by name places him | `.scene == ""` |
| same | 1448 | `"Seneschall Kaad" in [n.name for n in rt._scene_npcs(state)]` | `not in`. This test states the price of the rule; rename it and add the placement by command as its second half. |
| `test_entering_a_scene_brings_its_card_figures_home` | 1482–1483 | after two sightings `vall.scene == "zollhaus" and vall in rt._scene_npcs(state)` (#11) | `state.find("Schwester Vall") is None`: two sightings write nothing |
| same | 1490–1491 | `not vall.scene`; `_scene_npcs(state) == ["Seneschall Kaad"]` | both hold if Vall is looked up after the two moves (she is registered on entering the shrine). The test's subject, #10, is gone: delete it or rewrite it around the command. |
| `test_a_neighbouring_card_figure_seen_once_stays_in_her_own_scene` | 1507–1508 | `vall is not None and vall.scene == "schrein"` | `state.find("Schwester Vall") is None` |
| same | 1509 | `[n.name for n in state.npcs].count("Schwester Vall") == 1` | `== 0` |
| same | 1510 | `vall not in rt._scene_npcs(state)` | `rt._scene_npcs(state) == []` |
| same | 1515 | `vall.scene == "schrein"` after a third turn | `state.find("Schwester Vall") is None`. Rewrite as "a neighbouring card figure, seen once or two turns running, is never written". |

Green but describing a rule that is gone (text only, no assertion): the comment at 1203–1204,
the section header at 1375–1377, the docstrings at 1437–1438, 1472–1473 and 1495–1498.

Checked and not affected: the other presence tests in the same file (1189–1560: the kill
switch, the prompt line, the three sighting-follows-the-move tests, the candidate offer, the
template test, the flag gate, the dead card figure, the alias test), `tests/test_npc_router.py`
(verdict validation and `card_person`), `tests/test_memory_state.py:364–387` and
`tests/test_attack_targets.py` (state layer and picker, unchanged), `tests/test_aux_parity.py`
and `tests/aux_parity/log_positives.jsonl` (verdicts only), `tests/test_post_turn.py`,
`tests/test_text_replay.py`, the golden files of `dm-eval`. No test pins a `👥` log string or
the usage text of `!npc`.

New tests the build should add: a known card figure reported by name in another scene is not
moved; a card figure on two cards is present on both and a sighting elsewhere writes nothing;
`!npc ort` places a registered card figure, registers an unregistered one from her statblock,
refuses an unknown scene id, and `heim` takes the placement back; a placed card figure is not
carried by `_carry_turn_sightings`.

## 4. The command that moves a figure

No existing command moves an NPC between scenes. `!npc` (`dmbot/voice/dicecog.py:1045–1104`,
alias `!nsc`) has `add` and `list`; `!ort <szenen-id>` (`dmbot/voice/scenecog.py:47`) moves the
group. The bot has prefix commands only, no slash commands. The smallest fit is a third action
on `!npc`:

```text
!npc ort <Name>               place the figure in the scene the pointer stands on
!npc ort <Name> <szenen-id>   place her in that scene
!npc ort <Name> heim          take the placement back: the card decides again
```

- **Name.** As in `!npc add`: no spaces, underscores are tolerated (`Bree_Marlok`), or the name
  in quotes. Resolve in this order: a registered NPC by name (`WorldState.find`,
  `state.py:690`); a statblock by name (`Adventure.npc`, `rag/adventure.py:414`); exactly one
  card figure of the adventure by authored alias or role (`card_person` over all card people, so
  `!npc ort Kaad` works). Unknown or ambiguous: usage hint, nothing written.
- **Target.** Empty means `state.scene_id`. A scene id must exist (`Adventure.get_scene`);
  otherwise the reply `!ort` gives for an unknown id (`scenecog.py:78`). No reachability check,
  as with `!ort`: the human may place anyone anywhere. Without a loaded adventure the action
  refuses like `!ort` does (`scenecog.py:52–54`).
- **Write.** `WorldState.place_npc` already does what is needed: a registered NPC gets
  `scene = <target>` and keeps her wounds; an unregistered card figure is registered with her
  statblock values (the values `_register_scene_npcs` uses, `scenes.py:124–133`). `heim` sets
  `scene = ""` and is refused for a figure on no card. Then `_persist_and_refresh`, as `!npc add`
  does.
- **Effect.** `present_npcs` stays "on the card or `scene` equals this scene". A placed card
  figure is therefore present in the scene she was placed in and, as before, in her card scenes.
  The placement does not follow the group and does not end by itself.
- **Reply,** in German like the other commands, for example: `📍 **Seneschall Bramwell Kaad**
  ist jetzt in **Schrein der Aschenheiligen** (zusätzlich zu seiner Karte). Zurück: !npc ort Kaad
  heim`. One log line.
- The action also works for improvised figures; it is then the manual repair for a figure filed
  in the wrong scene.
- The usage text at `dicecog.py:1104` and the command's docstring (1050–1057) name the new
  action. The command was not prototyped; only the sighting path in section 2 was run.

## 5. What gets worse

1. **A card figure who really goes with the group is absent until someone types.** Today #9
   and #11 cost one turn and then heal. Table example: Kaad walks the group down to the shrine
   and stands beside them while they question Schwester Vall. For every turn of that scene the
   prompt says "NSCs anderswo (NICHT anwesend — sie sprechen und handeln in dieser Szene
   nicht): Seneschall Bramwell Kaad" while the narration lets him speak; his NPC memories are
   not in the prompt; when Fridolin shoots at him, the picker offers Vall and Rektalus.
2. **Nobody is told.** The only signal is a log line. Tobi plays and runs the table by voice.
   Table example: the same scene, nobody reads the log; the first symptom is the missing name in
   the picker in the middle of a fight, and the fix is a typed command while the fight waits.
3. **An escort needs a command per scene.** The placement does not follow the pointer. Table
   example: Kaad accompanies the group from the shrine to the pawn hall and on to the
   warehouse: `!npc ort Kaad` three times, and he stays listed in the shrine and the pawn hall
   until `heim`.
4. **A figure at the next scene's door is not a target until the pointer moves.** Today the
   second turn at the door places her. Table example from the log: 2026-11-14, 19:12:34, Bree
   Marlok speaks through the slit while the pointer stands on `schrein`. A shot through the slit
   in that turn finds only Schwester Vall and the party in the picker. The cure is the scene
   move itself (confirmed at 19:12:51 that evening).
5. **An improvised figure the classifier takes for a card figure gets no entry at all.** Table
   example from the log: 2026-11-14, 19:20:54, the chain thug at the warehouse gate was reported
   with Vosk's statblock. Under the rule nothing is written, so a shot at him in that turn
   offers Bree Marlok and Alter Fenk as targets. Today's code leaves him without an entry on the
   first turn too, but on a second identical verdict it would place "Vosk der Haken" in the room
   as a stand-in. The repair is `!npc add Kettenmann`.
6. **A roaming figure appears only where the author put her.** Table example, Chemical Burn:
   Raguel der Rote stands on four cards ("überall unterwegs"). If the narration lets him turn up
   in the Thaler-Herberge, whose card does not list him, he is absent there until the command;
   today the second sighting places him because `thaler` leads to `manufactorum`.

Not made worse, to prevent a wrong expectation: the consistency guard reads the card only
(`dmbot/llm/consistency.py:197`), the fact classifier's givers too (`scenes.py:301`), and the
NPC-memory extraction takes every living registered NPC (`dmbot/session/npcs.py:86`). None of
them ever read a sighting.

## 6. The observations of 2026-11-13 and 2026-11-14, one by one

Sources: `logs/debug-bis-2026-11-14.log` (13.11., "bis:" below) and `logs/debug-d1.log` (14.11.,
"d1:" below), line numbers given. The run of 14.11. used the code of D138 (points 6–10); D144
was committed at 20:30 that evening, after the run. "Recognised" means `card_person` returns the
card figure for the verdict as logged.

| # | When | Evidence | What happened | Would the rule have prevented it? |
| --- | --- | --- | --- | --- |
| 1 | 13.11. 00:40:19 | bis:12049–12051; analysis of 2026-11-13 | "Schreinschwester", no statblock, registered with default values in `zollhaus` two seconds after the pointer had moved to `schrein`. She is Schwester Cassia Vall: wrong scene and a second entry. | **Prevented.** The label is the leading word of her role "Schreinschwester der Aschenheiligen", so code recognises her from either scene (she is on the shrine's card, and the shrine is the Zollhaus' exit). A recognised card figure is not written. The recognition is #8 from D138, which the rule keeps. |
| 2 | 13.11. 01:59:57 | bis:12625, 12641–12642, 12650–12651 | "Frau hinter der Sichtklappe", no statblock, registered in `schrein`; the `<<ORT>>` button was confirmed at 02:00:19 and she stayed behind. She is Bree Marlok. | **In part.** The label is neither her name, an alias ("Bree", "Marlok", "die Marlok") nor her role, so code cannot recognise her without a statblock. She becomes an improvised entry and #6, kept for improvised figures, takes her to `pfandhalle`: right room, still a double. With the candidates of #7 the same door scene came back on 14.11. with her statblock (row 5), and then nothing is written. |
| 3 | 13.11. 02:01:07 | bis:12663, 12676–12677 | "Türwächter", default values, in `pfandhalle`. Per ADR 062 this is Bree Marlok again; the narration names no guard. | **Not prevented.** The pointer was right; this is an identity error. Whether it recurs depends on #7, which the rule does not change. |
| 4 | 13.11. 02:01:07 | bis:12663, 12676–12677 | "Blinder Greis", default values, in `pfandhalle`. He is Alter Fenk (role "Blinder Vogelhändler am Tor der Pfandhalle"). | **Not prevented**, same reason. On 14.11. the same entrance ("ein blinder Alter vor verhängten Vogelkäfigen", d1:443) drew no sighting: every verdict in the pawn hall from 19:12:54 to 19:19:41 was `none`. That is one live turn in favour of #7. |
| 5 | 14.11. 19:11:48 | d1:346, 372–373 | "Person hinter dem Sehschlitz", recognised as Bree Marlok, registered as present in `schrein`. The pointer moved to `pfandhalle` at 19:12:51 (d1:405–406). The narration at 19:11:39 showed only the slide moving, no person. | **Prevented.** The log line itself shows the recognition ("Bree Marlok; gemeldet als …"). Nothing is written; the card registers her on entering the pawn hall. |
| 6 | 14.11. 19:20:54 | d1:697, 712–713, 748, 787 | "Mann mit Ketten", recognised as Vosk der Haken, registered as present in `pfandhalle`. Not noted so far: the man was not Vosk. At 19:21:58 he says "Vosk will wissen, wer nach seiner Fracht fragt … bevor er selbst rauskommt", and at 19:22:16 Vosk steps out of the gate. The classifier gave a chain thug the plot NPC's statblock. | **Prevented** as to the state error: Vosk is not placed in the pawn hall, and a misjudged statblock can no longer move a plot NPC at all. The thug gets no entry in that turn (section 5, item 5); he was registered a turn later, as in row 7. |
| 7 | 14.11. 19:22:03 | d1:768–772 | "Kettenmann", statblock "Kettenbund-Schläger", filed in `pfandhalle`. The evening's protocol lists him as "in pfandhalle statt lagerhaus". The log shows he was carried in the same second: `👥 mit der Gruppe nach 'lagerhaus': Kettenmann` (d1:771). | **Not affected.** An improvised figure; #6 stays for him and did its job. No lasting error. |
| 8 | 14.11. 19:22:03 | d1:769–770, 787 | "Kettenmann" beside "Kettenbund-Schläger", which entering `lagerhaus` registered from the card; the protocol says "wohl doppelt". | **Not prevented, and unclear whether it is an error.** `_register_scene_npcs` registers the `generic` card entry as one NPC (`scenes.py:119–135`); the rule leaves `generic` statblocks alone. The narration at 19:22:16 shows two thugs, the one at the gate and "ein zweiter Schläger mit Ketten" inside, so two entries may be correct. |

Count: prevented 3 (rows 1, 5, 6), in part 1 (row 2), not prevented 2 (rows 3, 4), not affected
or unclear 2 (rows 7, 8).

What the logs do not contain: no attack was rolled on 14.11., so no target picker ever showed a
wrong name, and no player line in `logs/transcript-d1.log` between 19:03 and 19:33 remarks on
who is present. No card figure travelled with the group on either evening: Kaad stays on his
threshold or at his desk (bis:12001, d1:88), Vall calls after the group (d1:346), Bree and Fenk
stay in the pawn hall (d1:697).

Derived from the code, not seen live: today a registered card figure reported under her own name
in a scene that is neither hers nor next to hers is moved at once (`scenes.py:400`, 410, 417;
pinned by the test at 1444–1448). With a split party, as on 13.11. when Rektalus stayed with
Kaad while the pointer followed Fridolin to the shrine, one verdict naming Kaad would have put
him in the shrine. Under the rule it writes nothing.

## 7. Checkpoints in `docs/phase-11-abend.md`

| Checkpoint | Change |
| --- | --- |
| F7 "NSCs in der richtigen Szene" (D144) | **Changes.** The proof line `👥 … (gehört nach '<Szene>', bleibt dort)` no longer exists. Good: the new line `👥 Karten-Figur, Sichtung zählt nicht: …`. Bad: any `👥 anwesend in '<Szene>': …` that names a card figure. Add one step: a card figure placed with `!npc ort <Name>` appears in the picker and in the scene line, and `heim` removes her. |
| W3 "Angriff: Zielauswahl, nur Anwesende" | **Stays**, with a rider: a card figure from another scene is offered only after `!npc ort`. |
| N1 "Karten-Figuren ohne Doppelgänger" (D138, list "Seit dem 12.11. geändert") | Stays in substance, it tests #7 and #8. Its proof line `👥 anwesend in 'pfandhalle': Bree Marlok (gemeldet als „…“)` no longer exists; good is `[classifier] npcs … → none` or the new line. |
| N2 "Szenenwechsel über den spät bestätigten Knopf" (D138) | Stays for improvised figures (`👥 mit der Gruppe nach …`); it no longer applies to card figures. |
| F1–F6, F8–F10, W1, W2, W4–W6 | Not affected. |
| "Notgriffe" | New row: a card figure came along or is missing in the picker: `!npc ort <Name>`. |

Other documents the build has to bring in line in the same change: ADR 062 (the amendment
itself), `architecture.md:410–423` ("Who is here"), a new row in `docs/decision-log.md`,
`docs/live-run-script.md:140` (command list), `progress.md`. The two open review findings on
`_turn_sightings` in `progress.md:325–331` (the undo carries the wrong turn's figures; the list
survives `!leave`) remain open: they concern improvised figures, which the rule leaves alone.

## 8. Open points

1. **Keep #10 or drop it?** This draft drops it, because it is an automatic change to a card
   figure and the rule allows only the command. The alternative keeps `scenes.py:66–71` with a
   new meaning: entering a figure's own card scene ends a placement. The existing suite does not
   tell the two apart. Tobi's call.
2. **Should a discarded sighting be shown to the operator?** A line in `DM_DEBUG_CHANNEL`
   (`_operator_channel`, `dmbot/session/panels.py:84`) would answer item 2 of section 5. It
   repeats every turn the figure acts until she is placed, and a throttle would bring back a
   per-channel memory. Not part of this draft.
3. **Should `!npc list` show placements?** Without it a placement is visible only in
   `state.json` and in the prompt. Not part of this draft.
4. **Old state files.** A world state saved before the change can hold a card figure with a
   `scene` value from a sighting; without #10 nothing clears it except `!npc ort <Name> heim`.
   On 2026-11-15 `data/sessions/` holds no `state*.json`, so the debug sandbox is not affected.
   A campaign state on another machine was not checked.
5. **Live-unverified.** Everything here rests on the suite, the two logs and the in-memory
   patch. The session journals of 13.11. and 14.11. no longer exist
   (`data/sessions/1360964964084486194/history.debug.jsonl` holds one line), so the prompt lines
   of the affected turns could not be read back; what the prompt would have said is derived from
   `world_state_summary_de` and `present_npcs`.
6. **Row 8** (Kettenmann beside Kettenbund-Schläger) is not settled either way.
