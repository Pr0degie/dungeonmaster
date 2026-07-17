# Debug-Kampagne „Die Mitternachtsfracht“ — Runbook

Stand: 2026-07-17. Die wiederverwendbare Alternative zum One-Shot-Plan in
[live-run-script.md](live-run-script.md): eine eigens gebaute 6-Szenen-Kampagne
(`data/adventures/debug-kampagne/`, **git-ignored, nur lokal**), in der jedes offene
Live-Gate einen natürlichen Story-Trigger hat. Die Spieler sehen ein normales
Imperium-Maledictum-Abenteuer; die Gate-Hinweise kommen ausschließlich über das
🧪-Debug-Overlay (ADR 052, `testplan.json`-Sidecar — erreicht nie das LLM).
Beweis-Logzeilen sind aus [live-run-script.md](live-run-script.md) übernommen (dort
exakt aus dem Code zitiert) und direkt in `logs/debug.log` greppbar.

## Setup (2 min)

- `.env`: `DM_ADVENTURE=debug-kampagne`, `DM_LOG_FILE=1`, `DM_TRANSCRIPT_FILE=1`;
  optional `DM_DEBUG_CHANNEL=<id>` (🧪-Panel in einen Nebenchannel), Kill-Switch
  `DM_DEBUG_OVERLAY=0`.
- Boot-Konsole zeigt: `loaded adventure 'Die Mitternachtsfracht' (6 scenes, 8 NPC
  statblocks)` **und** `🧪 loaded testplan.json (6 scenes) — debug overlay active`.
- Party-Check wie im Live-Run-Skript (Pre-Flight #7): Channel `circlejerk`, `!j` stellt
  Fridolin / Gellicus / Rektalus auf — **Fridolin ist der Psioniker**.
- Kein Pre-Flight-Edit nötig: das G4-Gate (`lagerhaus → pier_neun` erfordert
  `verladebrief`) ist fest in der Datei.
- Session-RAG (ADR 054/055): `DM_SESSION_MEMORY` anlassen (Default; `=0` schaltet Ingest
  UND Retrieval ab — dann fällt G10 aus). Debug-Runs laufen in einer **Sandbox**: ihre
  Archive heißen `history.<stamp>.debug.jsonl` und landen in der separaten Source
  `session_debug_<channel-id>` — die Live-Archive und das Live-Kampagnengedächtnis
  bleiben unberührt, in beide Richtungen.

## Szenen → Gates → Beweis

Das 🧪-Panel sagt am Tisch pro Szene, was zu tun ist (Ein-Zeilen-Hinweis). Diese Tabelle
ist die Debrief-Referenz: welche Logzeile hinterher den Beweis liefert.

| Szene | Gates | Beweis-Logzeile / Anzeige |
|---|---|---|
| `zollhaus` — Die Zoll-Sakristei | G2/G3 Saat, G7 Saat | Uhr-Panel `⏱ ○○○○○○ … 0/6`; Frist-Panel `⏳ … — noch ~4 Std`; nach `!npc add Arno_Kessel` zeigt `!agenden` sein Ziel aus `npcs.json` |
| `schrein` — Schrein der Aschenheiligen | G1, G9 Saat 1 | `📚 rulebook:'…' (d=0.xx)` + Embed **📖 Regelauskunft** bei `!rules`; die Münzen-Saat hat KEINE Logzeile — Beweis kommt beim `!wrap` (🧵-Zeile) |
| `pfandhalle` — Die Pfandhalle | G5 Saat (Lüge), G9 Saat 2 | beim nächsten Szenenwechsel: `🧠 NPC-Gedächtnis: N neue Erinnerungen (Szene 'pfandhalle')`; `!npcmem Bree_Marlok` zeigt die Lüge mit wörtlichem Zitat |
| `lagerhaus` — Zwischenlager am Schwarzkanal | G8 (Wunden), G6 Saat (Ohm-3 ✝), G4, G2 Tick | `💥 … = N Wunden → …`; `🚫 Ausgang 'lagerhaus' → 'pier_neun' verriegelt — Bedingung 'verladebrief' nicht erledigt`; `✅ Erledigt vorgeschlagen: …`; `⏱ Tick vorgeschlagen: … (0/6)`; Szenenkarte rendert Ohm-3 `(tot)` |
| `siedehaus` — Das Siedehaus | G5 Ernte + Gossip, G7 Schritt 1, G3 Ernte | `NPC-memory: N Gossip-Einträge verteilt` (Kessel kennt die Lüge als Hörensagen); `NPC-memory: 'Arno Kessel' Agenda-Schritt: …`; `🕐 Zeitfortschritt vorgeschlagen: +N min` |
| `pier_neun` — Pier Neun | G6 Ernte, G9 Ernte, G7 Schritt 2, G3 Frist, G8 | `[consistency] violated (dead:Lastenservitor Ohm-3) — regenerating once`; `⏳ Frist '…' (…) verstrichen — Konsequenz-Hinweis für den nächsten Turn eingereiht`; nach Kill+Neustart: `loaded world state from …`; `!wrap` → `🧵 Chekhov-Liste: N neue Fäden, M aufgelöst` |
| Session 2 (reitet auf der G9-Session) | G10 Kampagnen-Gedächtnis | beim `!leave` von Session 1: `🗂 session memory: ingested history.<stamp>.debug.jsonl (N chunks)`; beim `!j` von Session 2: `🗂 session memory: catch-up — N rotated journal(s) pending`; pro Treffer im Turn: `🗂 Szene 'schrein'/<stamp> (FTS)` bzw. `(d=0.xx)` |

**G9 braucht wie immer eine ZWEITE (kurze) Session:** Saat sind Münze (`schrein`) und
Fenks Hymne (`pfandhalle`) — beide Callbacks sind in `pier_neun` als `secrets_de`
verdrahtet (Kessels Münz-Gegenstück, das Flüstern = Fenks Hymne). Spielt der DM sie in
Session 2 als Wiedererkennen zurück, ist G9 zu. G8s Recap-Hälfte bestätigt der
`📜 Was bisher geschah`-Post beim ersten `!j` von Session 2.

**G10 reitet auf derselben zweiten Session — keine neuen Szenen, keine neuen Saaten:**
die G9-Callbacks sind zugleich die G10-Sonden. In Session 2 fragt ein Spieler (a) in
natürlicher Sprache nach einer der Saaten („Was war das damals im Schrein mit der
Münze?“ — semantische Sonde) und (b) mit einem Eigennamen aus Session 1, mitten im Satz
(„Was hat Fenk in der Pfandhalle gesungen?“ — FTS-Sonde; satz-einleitende Namen verlieren
ihr FTS-Signal, ADR 054). Beweis sind die `🗂`-Zeilen aus der Tabellenzeile oben plus der
Block `## Früher in der Kampagne` im Prompt-Log.

Der (git-ignorierte, nur lokale) `testplan.json`-Eintrag `pier_neun` wurde dafür additiv
erweitert — falls die Datei je neu aufgebaut wird, ist das die exakte Änderung: an `gates`
wird `"G10 Kampagnen-Gedächtnis (Session 2)"` angehängt, und an `hint_de` der Satz
`" Session 2: nach der Münze in natürlicher Sprache fragen UND Fenk beim Namen nennen
(mitten im Satz) — G10."` Bestehende Gates und Hinweise bleiben wörtlich unverändert.

## Debrief in 5 Minuten

Nach dem Abend einmal durchpasten (Git Bash im Repo-Root). Pro Gate EIN Griff; leerer
Output = Gate nicht ausgelöst → Szene/Hinweis in der Tabelle oben nachschlagen.

```bash
# G1 — Regelfrage aus RAG (Treffer + Distanz sichtbar?)
grep -E "📚 rulebook:|📖 !rules" logs/debug.log | tail -5
# G2 — Uhren (Vorschlag UND bestätigter Tick?)
grep -E "⏱ Tick" logs/debug.log | tail -5
# G3 — Zeit & Fristen (Zeitfortschritt + verstrichene Frist?)
grep -E "🕐 Zeitfortschritt|⏳ Frist" logs/debug.log | tail -5
# G4 — Scene-Card-Gate (einmal verriegelt, dann Abhaken?)
grep -E "🚫 Ausgang 'lagerhaus'|✅ Erledigt vorgeschlagen" logs/debug.log | tail -5
# G5 — NPC-Gedächtnis (Extraktion, Gossip, ggf. Lügen-Flip?)
grep -E "🧠 NPC-Gedächtnis|Gossip-Einträge verteilt|Lüge aufgeflogen" logs/debug.log | tail -5
# G6 — Konsistenz-Wächter (genau bei Ohm-3, keine False Positives davor?)
grep -F "[consistency] violated" logs/debug.log | tail -3
# G7 — Agenden (Schritte mit Ingame-Zeitstempel?)
grep -F "Agenda-Schritt" logs/debug.log | tail -5
# G8 — Neustart (State + Autosave wiederhergestellt?)
grep -E "loaded world state from|restored .+ conversation turns" logs/debug.log | tail -3
# G9 — Chekhov (Fäden extrahiert? Auflösung erst Session 2)
grep -F "🧵 Chekhov-Liste" logs/debug.log | tail -3
# G10 — Kampagnen-Gedächtnis (Ingest beim !leave, Catch-up beim !join, Treffer im Turn?)
grep -F "session memory: ingested" logs/debug.log | tail -3
grep -F "session memory: catch-up" logs/debug.log | tail -3
grep -E "🗂 Szene" logs/debug.log | tail -5
# ADR 053 — Szenen-Events im Journal gelandet? (Chunk-Grenzen für den Ingest)
grep '"kind": "scene"' data/sessions/<id>/history*.jsonl | head -3
```

## Reset für einen Re-Run

1. In `data/sessions/<channel-id>/` (live: `1343673766487654464/`) löschen:
   `state.json` (HP, Szene, Flags, Uhren, Zeit, NPC-Gedächtnis, Recap),
   `history.jsonl` (Gesprächs-Autosave) und `chekhov.json` (Fäden).
   Zusätzlich (Session-RAG-Sandbox, ADR 055): alle `history.*.debug.jsonl`
   löschen und die Sandbox-Rows aus dem Store wipen:
   `uv run python -m dmbot.rag.ingest_session --wipe-debug <channel-id>`.
   **Warnung:** Plain-Archive `history.<stamp>.jsonl` sind ECHTE Session-
   Aufzeichnungen dieses geteilten Channels — bei einem Reset **niemals löschen**
   (und `--wipe-debug` rührt ihre Store-Rows nie an).
2. `characters.json` und `sheets/` **behalten** — das sind die Spielerbögen.
3. `logs/debug.log` leeren oder wegrotieren, damit die Debrief-Greps sauber bleiben.
4. Bot neu starten → `!j` seedet frisch auf `zollhaus`; das 🧪-Panel begleitet ab Szene 1.
5. Für einen Normal-Spielabend ohne Overlay: `DM_DEBUG_OVERLAY=0` (Kampagne bleibt spielbar).
