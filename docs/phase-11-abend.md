# Phase-11-Abend — Beipackzettel zum Mitlesen

Zum Danebenlegen während des Testlaufs: was geprüft wird, wie, und woran du erkennst, dass es
geklappt hat. Die ausführliche Fassung mit allen Begründungen ist
[testabend-ablauf.md §9](testabend-ablauf.md); bei Widerspruch gilt die.

**Die eine Frage des Abends:** Klingt der DM mit Claude (Opus) so viel besser als mit Nemo, dass
sich der Weg lohnt? Alles andere bleibt gleich oder ist aus. Die 17 alten Gates werden heute
**nicht** geprüft.

**Regeln:** Nicht live debuggen. Was hakt: Uhrzeit und Stichwort notieren, weiterspielen. Der Bot
läuft auf Tobis Rechner.

---

## Vor dem Start (einmal)

| Was | Wie | Gut, wenn |
|---|---|---|
| Claude-Login | in `cmd`: `claude -p "hi"` | eine kurze Antwort kommt |
| Kein API-Key | in `cmd`: `echo %ANTHROPIC_API_KEY%` | es steht wörtlich `%ANTHROPIC_API_KEY%` da |
| Ollama | `ollama list` | `mistral-nemo` und `bge-m3` sind da |
| Sandbox leer | in `data/sessions/<channel-id>/` alle Dateien mit `.debug` im Namen löschen, dann `uv run python -m dmbot.rag.ingest_session --wipe-debug <channel-id>` | nichts ohne `.debug` wurde angefasst |
| `.env` | Block aus [§9.2](testabend-ablauf.md) eintragen | `DM_LLM_BACKEND=claude`, `DM_NPC_MEMORY=0`, `DM_CONSISTENCY_GUARD=0`, `DM_DEBUG_OVERLAY=0`, `DM_CLOCKS=0`, `DM_FLAG_CONFIRM=0`, `DM_LOG_FILE=1` |
| Verbrauch | claude.ai → Verbrauchsanzeige | Stand notiert: ______ |

## Beim Start

Bot starten. Im Terminal müssen diese zwei Zeilen stehen:

```
Ollama preflight OK — … model 'mistral-nemo' available.
Claude preflight OK — narration opus: OK · aux haiku: OK (CLI …)
```

Steht dort `FAILED`, `refused` oder `not found`: **nicht spielen**, erst reparieren (die Zeile sagt,
was fehlt; Tabelle in SETUP.md B10). Der Bot würde sonst still mit Nemo laufen, und der Abend
wäre wertlos.

Dann im Discord, direkt nach `!j`:

| Befehl | Soll |
|---|---|
| `!uhren` | „Uhren sind abgeschaltet (`DM_CLOCKS=0`)" |
| `!fäden` | leer |
| `!automatik` | alle fünf **an** (szene, flaggen, fakten, zeit, panel) |
| `!backend` | Primär: claude, nicht degradiert |

---

## Was getestet wird

Reihenfolge so spielen. Durchgang 1 ist der eigentliche Abend, Durchgang 2 und 3 brauchen je
einen Neustart und dauern zusammen etwa zehn Minuten.

### Durchgang 1 — das Spiel (ohne Neustart)

| # | Was wird geprüft | Wie | Bestanden, wenn |
|---|---|---|---|
| 1 | **Läuft wirklich Claude, und passt die Stimme auf die GPU?** | während des Spiels: `nvidia-smi` und `ollama ps` | XTTS liegt auf der GPU; `ollama ps` zeigt **kein** `mistral-nemo` |
| 2 | **Tempo eines Zuges** | `!start`, dann fünf normale gesprochene Züge | fünf Antworten mit Stimme; nach dem Abend stehen fünf `[latency]`-Zeilen im Log |
| 3a | **Würfelknopf von Haiku** | jemand sagt eine Handlung an, die eine Probe braucht (schleichen, überreden, klettern) | ein 🎲-Knopf mit dem Namen der Figur erscheint |
| 3b | **Szenenwechsel von selbst** | die Gruppe geht hörbar an einen anderen Ort der Szenenkarte | der Bot meldet den neuen Ort (mit ↩-Knopf) |
| 3c | **Harter Fakt** | ein NSC übergibt etwas oder die Gruppe nimmt einen Auftrag an | `!fakt` listet ihn danach |
| 7b | **Meldet Opus eine erledigte Gelegenheit?** | die Gruppe erledigt sichtbar etwas, das im Panel unter „noch offen" steht | der Punkt verschwindet aus dem Panel, ohne dass jemand klickt |
| 4 | **Zusammenfassung** | am Ende `!wrap` | `📜 Was bisher geschah:` auf Deutsch, inhaltlich richtig |
| 9 | **Das Urteil des Tisches** — das eigentliche Gate | jeder Spieler sagt drei Sätze zur Erzählqualität | wörtlich aufgeschrieben, siehe unten |

Worauf du beim Zuhören achtest (alles notieren, nichts reparieren):

- Bricht eine Antwort mitten im Satz ab? → abgeschnitten an der Ausgabegrenze.
- Fängt eine Antwort mit „Spielleitung" an, oder steht „Spieler" mitten im Text? → Etikett-Leck.
- Spricht der DM für eine Spielerfigur?
- Erinnert er wiederholt an dasselbe, ohne dass etwas weitergeht?
- Wie lange dauert es von „fertig gesprochen" bis zum ersten Ton, gefühlt?
- Eine ⚠-Zeile im Chat, die du nicht selbst ausgelöst hast → Claude ist ausgefallen, Uhrzeit notieren.

### Durchgang 2 — setzt Opus den Würfel-Marker selbst? (Punkt 7a)

Bot stoppen, in `.env` `DM_ROLL_ROUTER=0`, starten, `!j`. Drei, vier Züge mit Handlungen, die
eine Probe brauchen.

- **Bestanden, wenn:** ein Würfelknopf erscheint, obwohl der Router aus ist.
- **Notieren:** Ja oder Nein, bei wie vielen von wie vielen Handlungen.
- Danach `DM_ROLL_ROUTER=1` zurücksetzen.

### Durchgang 3 — fällt der Bot sauber auf Nemo zurück? (Punkt 5)

Bot stoppen, in `.env` `CLAUDE_MODEL_NARRATION=opus-gibts-nicht`, starten.

| Schritt | Soll |
|---|---|
| Bootzeile | `Claude preflight FAILED — narration opus-gibts-nicht: FAILED · aux haiku: OK` |
| `!j`, ein Zug | **genau eine** ⚠-Zeile im Chat; Nemo antwortet (erster Zug 10–15 s langsamer) |
| zweiter Zug | Antwort kommt, **keine** zweite ⚠-Zeile |
| `!backend` | zeigt den Grund und bis wann |

Danach `.env` zurück auf `opus`, Neustart, ein Zug: Opus antwortet wieder.

### Nach dem Abend

| # | Was | Wie |
|---|---|---|
| 6 | Verbrauch | Anzeige auf claude.ai, Differenz zum Startwert |
| 8 | Anteil abgeschnittener Antworten | Messung C unten |
| — | Logs sichern, **bevor** der Bot wieder startet | `logs/debug.log`, `logs/transcript.log`, `logs/terminal.log` |

---

## Die drei Messungen (nach dem Abend, in PowerShell im Repo-Ordner)

Nur Züge aus Durchgang 1 werten. Durchgang 3 lief auf Nemo.

**A — Wie schnell ist ein Opus-Zug?**

```
Select-String -Path logs\debug.log -Pattern '\[latency\]' | Select-Object -First 8
```

Aus zwei Zeilen (erster Zug nach `!start`, einer aus der Mitte) ablesen: `spawn=` (Start der
CLI), `first_audio=` (Auslöser bis erster Ton), `cache=` (Prompt-Tokens aus dem Cache).

**B — Wie lange bis zum Würfelknopf?**

```
Select-String -Path logs\debug.log -Pattern '\[classifier\] roll'
```

Drei Zeilen mit einem Urteil (nicht `no test`) notieren, je die Millisekunden.

**C — Wie oft wurde abgeschnitten?**

```
$alle = (Select-String -Path logs\debug.log -Pattern '\[latency\]').Count
$cut  = (Select-String -Path logs\debug.log -Pattern '\[latency\].* cut ').Count
"$cut von $alle"
```

Ist das mehr als eine seltene Ausnahme, sagen 7a und 7b wenig aus: der Marker stand dann dort,
wo geschnitten wird.

---

## Protokoll zum Ausfüllen

| Punkt | Ergebnis |
|---|---|
| 1 GPU / kein Nemo geladen | ☐ ja ☐ nein |
| 2 fünf Züge mit Stimme | ☐ ja ☐ nein |
| 3a Würfelknopf | ☐ ja ☐ nein |
| 3b Szenenwechsel von selbst | ☐ ja ☐ nein |
| 3c harter Fakt | ☐ ja ☐ nein |
| 4 Recap | ☐ ja ☐ nein |
| 5 Failover, genau eine ⚠-Zeile | ☐ ja ☐ nein |
| 6 Verbrauch vorher / nachher | ______ / ______ |
| 7a `<<TEST>>` ohne Router | ☐ ja ☐ nein — ___ von ___ |
| 7b `<<ERLEDIGT>>` angewendet | ☐ ja ☐ nein — ___ von ___ |
| 8 abgeschnitten | ___ von ___ |
| A `spawn` / `first_audio` (kalt) | ______ / ______ |
| A `spawn` / `first_audio` (warm) | ______ / ______ |
| B drei Werte in ms | ______ · ______ · ______ |

**9 — Urteil des Tisches, wörtlich, drei Sätze je Spieler:**

- Spieler 1:
- Spieler 2:
- Spieler 3:
- Spieler 4:

**Was genervt hat (Uhrzeit + Stichwort):**

-

---

## Notgriffe

| Problem | Befehl |
|---|---|
| Claude spinnt, Abend retten | `!backend ollama` (Rest des Abends lokal) |
| Nach einer ⚠-Zeile sofort zurück | `!backend claude` |
| Ein Klassifikator stört | `!automatik fakten aus` bzw. `szene aus` |
| Falscher Szenenwechsel | ↩-Knopf (eine Minute), sonst `!ort <id>` |
| Falscher Fakt | `!fakt weg <Text>` |
| Antwort war Müll | `!redo` |
| Pause | Esc im Bot-Terminal oder ⏸-Knopf |

Jeder Notgriff gehört mit Uhrzeit ins Protokoll: er ändert, was der Abend misst.
