# Evidence — a sighted NPC filed under the scene the group had just left (2026-11-13, 00:40)

**Status:** **fixed 2026-11-13, live-unverified** — ADR 062, amendment 2026-11-13 (D138). The
text below is the evidence as recorded before the fix; "today" and the code references mean
commit `e681702`. Three tests in `tests/test_turn_boundary.py` showed the behaviour and were
marked `xfail(strict=True)` until the fix removed the markers:
`test_a_sighting_lands_in_the_scene_the_group_arrived_in_meanwhile`,
`test_a_sighting_of_a_scene_card_npc_under_another_name_adds_no_second_entry` and, for the
case under *Related* below,
`test_a_sighting_lands_in_the_scene_the_classifier_moved_to_in_the_same_turn`.
**Governing:** ADR 062 (improvised NPCs join the scene), ADR 057 (scene moves), lesson
`snapshot-state-at-event-time`.
**Sources, copied before they rotate:** `logs/debug.log` (session started 00:35:16),
`data/sessions/1343673766487654464/history.debug.jsonl`, `state.debug.json` in the same folder
(read 2026-11-13 around 00:50, the session was still running), adventure `debug-kampagne`.
Code at commit `e681702`.

## What happened

Debug campaign, Claude backend, one player in voice. The pointer stood on `zollhaus`; its only
exit is `schrein`.

| Time | Event |
| --- | --- |
| 00:39:22 | Player: "Ich gehe die Treppen hinunter zum Schrein." The narration ends in front of the half-open portal. Scene classifier: `stay`. |
| 00:40:02 | Player: "Geh rein!" The narration enters the shrine and shows "eine alte Schreinschwester". |
| 00:40:13 | The narration model's `<<ORT>>` marker proposes `schrein`; the post-turn classifiers start with the pointer on `zollhaus`. |
| 00:40:17 | Tobi confirms the proposal: the pointer moves to `schrein`, the scene card's NPC "Schwester Cassia Vall" is registered. The scene classifier returns `schrein` in the same second. |
| 00:40:19 | The presence classifier returns `Schreinschwester` with no statblock. She is registered as a new NPC with default values **in `zollhaus`**. The scene verdict is dropped as stale, correctly. |
| 00:40:32 | The button's own log line, 15 s late: three HTTP 429 on the message edit. One move only — one scene event in the journal, one scene-change time advance (1350 → 1382). |

## What it shows

1. **Wrong scene.** `close_turn` snapshots the pointer before the classifiers run
   (`classified_from`) and files the sightings under that snapshot. The pointer moved while the
   classifier was thinking, and the answer narrated the arrival: the person stands in the new
   scene, the state says the old one. She is therefore not "present" in the shrine — not in the
   prompt's scene roster and not in the target picker.
2. **Second entry for the same person.** "Schreinschwester" is the scene card's
   "Schwester Cassia Vall" (`role_de`: "Schreinschwester der Aschenheiligen"). The classifier was offered the
   adventure's statblock names as roster and still returned an empty statblock;
   `WorldState.place_npc` matches by exact name only, so a second NPC with default values
   (10 wounds instead of 7) was created.

Observation, not a defect: at 00:39:22 the classifier answered `stay` although the narration had
reached the shrine's door. The move came one turn later, when the group went in.

Related, derived from the code and not seen live (the third test): the sightings are applied
before the scene verdict, also under `classified_from`. A turn in which the classifier itself
moves the pointer files the people of an arrival narration under the scene that was just left,
without any race.

## Where in the code

- `dmbot/session/scenes.py`, `close_turn`: `classified_from = state.scene_id` before the
  `await`, then `_apply_npc_sightings(channel, state, npc_verdict, classified_from)`.
- `dmbot/session/scenes.py`, `_classify_turn`: `present=` is built from the scene at
  classification start; `roster=` is every statblock name of the adventure.
- `dmbot/memory/state.py`, `WorldState.place_npc`: a known NPC is found by
  `name.lower() ==` only.

## Evidence

### `logs/debug.log`, 00:39:18–00:40:54

TTS, Whisper, PCM and HTTP lines and table talk that never reached the DM are left out; the
remaining lines are verbatim.

```text
00:39:18 INFO    voice.voicecog | push-to-talk → 🎙 an die Spielleitung
00:39:22 INFO    runtime | 📝 Pr0degie | 2.1s·410ms →DM | Ich gehe die Treppen hinunter zum Schrein.
00:39:22 INFO    voice.voicecog | push-to-talk → ⏸ nur Protokoll
00:39:31 WARNING llm.claude_client | ✂ Antwort an der Ausgabegrenze abgeschnitten (220/220 Tokens)
00:39:31 INFO    orchestrator | 🪵 LLM roh (stream): Staub rieselt noch aus deinem Mantel, Fridolin, während die rostigen Stufen unter deinen Stiefeln im Nebel bergab führen, vorbei an verriegelten Läden und einem Sünder, der in einer Türnische seinen Rausch ausschläft. Drei Gassen tiefer schält sich der Schrein der Aschenheiligen aus dem Dunst, eine kleine Kapelle aus geschwärztem Stein, deren Portal halb offen steht; die gebrochenen Wachssiegel der Arbites, der Gesetzeshüter des Imperiums, hängen in roten Fetzen vom Türrahmen. Drinnen flackert ein einzelnes Lumen, und irgendwo im Inneren schabt Metall über Stein, als würde jemand etwas Schweres verrücken. Oben im Zollhaus steht Kaad noch auf der Schwelle, und sein Blick wandert zu dir, Rektalus, und zu dem Pergament in deiner Hand: „Die N
00:39:31 INFO    voice.delivery | 🎭 Staub rieselt noch aus deinem Mantel, Fridolin, während die rostigen Stufen unter deinen Stiefeln im Nebel bergab führen, vorbei an verriegelten Läden und einem Sünder, der in einer Türnische seinen Rausch ausschläft. Drei Gassen tiefer schält sich der Schrein der Aschenheiligen aus dem Dunst, eine kleine Kapelle aus geschwärztem Stein, deren Portal halb offen steht; die gebrochenen Wachssiegel der Arbites, der Gesetzeshüter des Imperiums, hängen in roten Fetzen vom Türrahmen. Drinnen flackert ein einzelnes Lumen, und irgendwo im Inneren schabt Metall über Stein, als würde jemand etwas Schweres verrücken.
00:39:31 INFO    voice.delivery | ⏱ LLM 8922 ms
00:39:35 INFO    orchestrator | [classifier] roll 3562ms → no test
00:39:36 INFO    orchestrator | [classifier] fact 4219ms → none
00:39:36 INFO    orchestrator | [classifier] scene 4219ms → stay
00:39:38 INFO    orchestrator | [classifier] npcs 5922ms → none
00:39:59 INFO    voice.voicecog | push-to-talk → 🎙 an die Spielleitung
00:40:02 INFO    runtime | 📝 Pr0degie | 0.9s·182ms →DM | Geh rein!
00:40:02 INFO    voice.voicecog | push-to-talk → ⏸ nur Protokoll
00:40:13 INFO    turn_timing | [latency] turn=2 auto stream stt=410ms trigger→llm_done=8922ms ctx=14736/24576 spawn=1906ms cache=0 cut chars=612 first_audio=11313ms tts=11235ms wav=38.9s bridge_wait=39125ms total=50438ms
00:40:13 INFO    orchestrator | 🪵 LLM roh (stream): Das Portal knarrt in seinen Angeln, als du hindurchtrittst, Fridolin, und der Geruch von kaltem Weihrauch und Kerzentalg schlägt dir entgegen. Im flackernden Licht siehst du einen leeren Steinsockel vor dem Altar, auf dem sich ein heller Abdruck in der Asche abzeichnet, groß wie eine Reisetruhe. Daneben kniet eine alte Schreinschwester in grauer Kutte und stemmt mit einer Eisenstange eine Bodenplatte an. Sie fährt herum, die Stange erhoben, und zischt: „Kein Schritt weiter, im Namen des Throns! Wer schickt dich, die Arbites oder die Kettenleute?“ ⏎  ⏎ Und du, Rektalus, stehst noch immer mit Kaads Pergament in der Sakristei, während die Nacht verrinnt. ⏎  ⏎ <<ORT schrein>>
00:40:13 INFO    voice.delivery | 🎭 Das Portal knarrt in seinen Angeln, als du hindurchtrittst, Fridolin, und der Geruch von kaltem Weihrauch und Kerzentalg schlägt dir entgegen. Im flackernden Licht siehst du einen leeren Steinsockel vor dem Altar, auf dem sich ein heller Abdruck in der Asche abzeichnet, groß wie eine Reisetruhe. Daneben kniet eine alte Schreinschwester in grauer Kutte und stemmt mit einer Eisenstange eine Bodenplatte an. Sie fährt herum, die Stange erhoben, und zischt: „Kein Schritt weiter, im Namen des Throns! Wer schickt dich, die Arbites oder die Kettenleute?“
00:40:13 INFO    voice.delivery | ⏱ LLM 10468 ms
00:40:13 INFO    voice.delivery | 📖 Auto-Szenenwechsel vorgeschlagen → schrein (Schrein der Aschenheiligen)
00:40:17 INFO    session.scenes | 👥 Szene 'schrein': Schwester Cassia Vall als anwesend registriert
00:40:17 INFO    session.scenes | scene → schrein (Schrein der Aschenheiligen) [marker]
00:40:17 INFO    orchestrator | [classifier] scene 3547ms → schrein
00:40:17 INFO    orchestrator | [classifier] roll 4141ms → no test
00:40:17 WARNING discord.http | We are being rate limited. PATCH https://discord.com/api/v10/channels/1360964964084486194/messages/1570568173986779317 responded with 429. Retrying in 1.76 seconds.
00:40:18 INFO    orchestrator | [classifier] fact 4922ms → none
00:40:19 INFO    orchestrator | [classifier] npcs 5297ms → Schreinschwester
00:40:19 INFO    session.scenes | 👥 anwesend in 'zollhaus': Schreinschwester (neu, Standardwerte)
00:40:19 INFO    session.scenes | 🗺️ Szenen-Verdikt 'schrein' verworfen — der Zeiger stand bei der Klassifikation auf 'zollhaus' und steht jetzt auf 'schrein'
00:40:20 WARNING discord.http | We are being rate limited. PATCH https://discord.com/api/v10/channels/1360964964084486194/messages/1570568173986779317 responded with 429. Retrying in 5.47 seconds.
00:40:26 WARNING discord.http | We are being rate limited. PATCH https://discord.com/api/v10/channels/1360964964084486194/messages/1570568173986779317 responded with 429. Retrying in 5.56 seconds.
00:40:32 INFO    voice.delivery | scene → schrein (Schrein der Aschenheiligen) [auto, bestätigt]
00:40:54 INFO    turn_timing | [latency] turn=3 auto stream stt=182ms trigger→llm_done=10468ms ctx=15091/24576 gen=428 think=102 spawn=1672ms cache=0 chars=655 first_audio=10812ms tts=12694ms wav=40.8s bridge_wait=41250ms total=52062ms
```

### Journal (`history.debug.jsonl`)

The turn before the arrival (autosaved 00:40:13) — the classifier's `stay`:

```json
{
  "lines": [
    [
      "Fridolin Feuchtgebietheld",
      "Geh rein!"
    ]
  ],
  "results": [],
  "notes": [],
  "raw": "Staub rieselt noch aus deinem Mantel, Fridolin, während die rostigen Stufen unter deinen Stiefeln im Nebel bergab führen, vorbei an verriegelten Läden und einem Sünder, der in einer Türnische seinen Rausch ausschläft. Drei Gassen tiefer schält sich der Schrein der Aschenheiligen aus dem Dunst, eine kleine Kapelle aus geschwärztem Stein, deren Portal halb offen steht; die gebrochenen Wachssiegel der Arbites, der Gesetzeshüter des Imperiums, hängen in roten Fetzen vom Türrahmen. Drinnen flackert ein einzelnes Lumen, und irgendwo im Inneren schabt Metall über Stein, als würde jemand etwas Schweres verrücken. Oben im Zollhaus steht Kaad noch auf der Schwelle, und sein Blick wandert zu dir, Rektalus, und zu dem Pergament in deiner Hand: „Die N",
  "markers": {
    "tests": [],
    "manifests": [],
    "scenes": [],
    "erledigt": [],
    "uhr": [],
    "zeit": []
  },
  "router": {
    "action": "Ich gehe die Treppen hinunter zum Schrein.",
    "character": "Fridolin Feuchtgebietheld",
    "skills": [
      "Heimlichkeit",
      "Überreden",
      "Wahrnehmung",
      "Nahkampf",
      "Fernkampf",
      "Psi-Meisterschaft",
      "Disziplin (Psi)",
      "WS",
      "BS",
      "Str",
      "Tgh",
      "Ag",
      "Int",
      "Per",
      "Wil",
      "Fel"
    ],
    "raw": "{\"needs_test\": false, \"skill\": \"\", \"difficulty\": \"\"}",
    "decision": null
  },
  "scene_router": {
    "raw": "{\"ziel\": \"nein\"}",
    "verdict": "",
    "failure": null
  },
  "facts": {
    "raw": "{\"art\": \"nichts\", \"sache\": \"Beschreibung: Schrein der Aschenheiligen, Siegel gebrochen, Geräusch im Inneren\", \"an\": \"\", \"von\": \"\"}",
    "verdict": null,
    "failure": null
  },
  "npcs": {
    "raw": "{\"npcs\": []}",
    "verdict": [],
    "failure": null
  },
  "time_minutes": 1350,
  "ts": "2026-11-13T00:40:13",
  "user_msg": "Fridolin Feuchtgebietheld: Ich gehe die Treppen hinunter zum Schrein.",
  "answer": "Staub rieselt noch aus deinem Mantel, Fridolin, während die rostigen Stufen unter deinen Stiefeln im Nebel bergab führen, vorbei an verriegelten Läden und einem Sünder, der in einer Türnische seinen Rausch ausschläft. Drei Gassen tiefer schält sich der Schrein der Aschenheiligen aus dem Dunst, eine kleine Kapelle aus geschwärztem Stein, deren Portal halb offen steht; die gebrochenen Wachssiegel der Arbites, der Gesetzeshüter des Imperiums, hängen in roten Fetzen vom Türrahmen. Drinnen flackert ein einzelnes Lumen, und irgendwo im Inneren schabt Metall über Stein, als würde jemand etwas Schweres verrücken.",
  "redo": false,
  "state_before (pointer and NPCs only)": {
    "scene_id": "zollhaus",
    "npcs": [
      {
        "name": "Seneschall Bramwell Kaad",
        "scene": null
      },
      {
        "name": "Laufbursche",
        "scene": "zollhaus"
      },
      {
        "name": "Gestalt im Schatten",
        "scene": "zollhaus"
      }
    ]
  }
}
```

The scene event written by the confirmed move:

```json
{
  "kind": "scene",
  "scene_id": "schrein",
  "ts": "2026-11-13T00:40:17"
}
```

The arrival turn (autosaved 00:40:54). `npcs` is the presence classifier's raw verdict;
`state_before` shows the pointer still on `zollhaus` when the turn began:

```json
{
  "raw": "Das Portal knarrt in seinen Angeln, als du hindurchtrittst, Fridolin, und der Geruch von kaltem Weihrauch und Kerzentalg schlägt dir entgegen. Im flackernden Licht siehst du einen leeren Steinsockel vor dem Altar, auf dem sich ein heller Abdruck in der Asche abzeichnet, groß wie eine Reisetruhe. Daneben kniet eine alte Schreinschwester in grauer Kutte und stemmt mit einer Eisenstange eine Bodenplatte an. Sie fährt herum, die Stange erhoben, und zischt: „Kein Schritt weiter, im Namen des Throns! Wer schickt dich, die Arbites oder die Kettenleute?“\n\nUnd du, Rektalus, stehst noch immer mit Kaads Pergament in der Sakristei, während die Nacht verrinnt.\n\n<<ORT schrein>>",
  "markers": {
    "tests": [],
    "manifests": [],
    "scenes": [
      {
        "scene_id": "schrein",
        "raw": "<<ORT schrein>>",
        "parsed": true
      }
    ],
    "erledigt": [],
    "uhr": [],
    "zeit": []
  },
  "scene_verdict": {
    "requested": "schrein",
    "accepted": true,
    "mode": "verbunden"
  },
  "router": {
    "action": "Geh rein!",
    "character": "Fridolin Feuchtgebietheld",
    "skills": [
      "Heimlichkeit",
      "Überreden",
      "Wahrnehmung",
      "Nahkampf",
      "Fernkampf",
      "Psi-Meisterschaft",
      "Disziplin (Psi)",
      "WS",
      "BS",
      "Str",
      "Tgh",
      "Ag",
      "Int",
      "Per",
      "Wil",
      "Fel"
    ],
    "raw": "{\"needs_test\": false, \"skill\": \"\", \"difficulty\": \"\"}",
    "decision": null
  },
  "scene_router": {
    "raw": "{\"ziel\": \"schrein\"}",
    "verdict": "schrein",
    "failure": null
  },
  "facts": {
    "raw": "{\"art\": \"nichts\", \"sache\": \"Schreinschwester droht mit Eisenstange, fragt nach Auftraggeber; keine Übergabe oder Zusage\", \"an\": \"\", \"von\": \"\"}",
    "verdict": null,
    "failure": null
  },
  "npcs": {
    "raw": "{\"npcs\": [{\"label\": \"Schreinschwester\", \"statblock\": \"\"}]}",
    "verdict": [
      {
        "label": "Schreinschwester",
        "statblock": ""
      }
    ],
    "failure": null
  },
  "time_minutes": 1382,
  "ts": "2026-11-13T00:40:54",
  "user_msg": "Fridolin Feuchtgebietheld: Geh rein!",
  "answer": "Das Portal knarrt in seinen Angeln, als du hindurchtrittst, Fridolin, und der Geruch von kaltem Weihrauch und Kerzentalg schlägt dir entgegen. Im flackernden Licht siehst du einen leeren Steinsockel vor dem Altar, auf dem sich ein heller Abdruck in der Asche abzeichnet, groß wie eine Reisetruhe. Daneben kniet eine alte Schreinschwester in grauer Kutte und stemmt mit einer Eisenstange eine Bodenplatte an. Sie fährt herum, die Stange erhoben, und zischt: „Kein Schritt weiter, im Namen des Throns! Wer schickt dich, die Arbites oder die Kettenleute?“\n\nUnd du, Rektalus, stehst noch immer mit Kaads Pergament in der Sakristei, während die Nacht verrinnt.",
  "redo": false,
  "state_before (pointer and NPCs only)": {
    "scene_id": "zollhaus",
    "npcs": [
      {
        "name": "Seneschall Bramwell Kaad",
        "scene": null
      },
      {
        "name": "Laufbursche",
        "scene": "zollhaus"
      },
      {
        "name": "Gestalt im Schatten",
        "scene": "zollhaus"
      }
    ]
  }
}
```

### World state after the turn (`state.debug.json`)

```json
{
  "scene_id": "schrein",
  "time_minutes": 1382,
  "npcs": [
    {
      "name": "Seneschall Bramwell Kaad",
      "wounds": 8,
      "max_wounds": 8,
      "toughness_bonus": 2,
      "attitude": "neutral"
    },
    {
      "name": "Laufbursche",
      "wounds": 10,
      "max_wounds": 10,
      "toughness_bonus": 3,
      "attitude": "neutral",
      "scene": "zollhaus"
    },
    {
      "name": "Gestalt im Schatten",
      "wounds": 10,
      "max_wounds": 10,
      "toughness_bonus": 3,
      "attitude": "neutral",
      "scene": "zollhaus"
    },
    {
      "name": "Schwester Cassia Vall",
      "wounds": 7,
      "max_wounds": 7,
      "toughness_bonus": 2,
      "attitude": "neutral"
    },
    {
      "name": "Schreinschwester",
      "wounds": 10,
      "max_wounds": 10,
      "toughness_bonus": 3,
      "attitude": "neutral",
      "scene": "zollhaus"
    }
  ]
}
```

### The adventure

```json
{
  "zollhaus": {
    "title_de": "Die Zoll-Sakristei",
    "npcs_here": [
      "Seneschall Bramwell Kaad"
    ],
    "leads_to": [
      "schrein"
    ]
  },
  "schrein": {
    "title_de": "Schrein der Aschenheiligen",
    "npcs_here": [
      "Schwester Cassia Vall"
    ],
    "leads_to": [
      "pfandhalle"
    ]
  },
  "statblock": {
    "name": "Schwester Cassia Vall",
    "role_de": "Schreinschwester der Aschenheiligen",
    "wounds": 7,
    "toughness_bonus": 2,
    "armour": 0
  }
}
```
