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
| `.env` | Block aus [§9.2](testabend-ablauf.md) eintragen | `DM_LLM_BACKEND=claude`, `DM_LLM_ON_FAILURE=pause`, `DM_NPC_MEMORY=0`, `DM_CONSISTENCY_GUARD=0`, `DM_DEBUG_OVERLAY=0`, `DM_CLOCKS=0`, `DM_FLAG_CONFIRM=0`, `DM_LOG_FILE=1` |
| Altes Log weg | Bot aus; in PowerShell im Repo-Ordner: `Rename-Item logs\debug.log "debug-bis-$(Get-Date -Format yyyy-MM-dd).log"` | `logs\debug.log` gibt es nicht mehr; der Bot legt beim Start eine leere an, der Abend beginnt mit einer leeren Datei |
| Verbrauch | claude.ai → Verbrauchsanzeige | Stand notiert: ______ |

## Beim Start

Bot starten. Im Terminal müssen diese zwei Zeilen stehen:

```
Ollama preflight OK — … model 'mistral-nemo' available.
Claude preflight OK — narration opus: OK · aux haiku: OK (CLI …)
```

Steht dort `FAILED`, `refused` oder `not found`: **nicht spielen**, erst reparieren (die Zeile sagt,
was fehlt; Tabelle in SETUP.md B10). Der Bot würde sonst beim ersten Zug pausieren (in der
Stellung `fallback`: still mit Nemo laufen), und der Abend wäre wertlos.

Dann im Discord, direkt nach `!j`:

| Befehl | Soll |
|---|---|
| `!uhren` | „Uhren sind abgeschaltet (`DM_CLOCKS=0`)" |
| `!fäden` | leer |
| `!automatik` | alle sechs **an** (szene, flaggen, fakten, nscs, zeit, panel) |
| `!backend` | Modus: auto (bei Ausfall: Pause) · Primär: claude · kein Ausfall |

---

## Was getestet wird

Reihenfolge so spielen. Durchgang 1 ist der eigentliche Abend. Durchgang 2 braucht einen
Neustart davor und einen danach, Durchgang 3 eine PowerShell als Administrator; zusammen
dauern beide etwa zehn Minuten.

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
- Eine ⏸-Zeile im Chat, die du nicht selbst ausgelöst hast → Claude ist ausgefallen, das Spiel
  pausiert. Uhrzeit notieren, nichts tun: Der Bot meldet sich mit ▶ zurück. Dauert es zu lange,
  siehe Notgriffe.

#### Seit dem 12.11. geändert, am Tisch beobachten

Gebaut und nur durch Tests belegt (D134, D137, D138, `DMBrain`-Befunde Nr. 1–4, 9, 12). Keine Gates des
Abends: nichts davon erzwingen, nur notieren, wenn die Lage eintritt. Diese Punkte stehen nur
hier, nicht in testabend-ablauf.md §9. D135 (Umbau ohne Verhaltensänderung) und D136 (am 13.11.
live belegt: Auto-Recap ohne Schnitt, Neustart danach) brauchen keinen Punkt. Vor dem Start die vier Alteinträge des Laufs vom 13.11.
aus dem Spielstand nehmen: Schreinschwester, Frau hinter der Sichtklappe, Türwächter, Blinder Greis.
Der Schritt „Sandbox leer“ unter „Vor dem Start“ entfernt sie schon; ein eigener Handgriff ist
dafür nicht nötig.

| # | Was | Wie | Gut, wenn | Beweis im Log |
|---|---|---|---|---|
| N1 | **Karten-Figuren ohne Doppelgänger** (D138) | Prüfszene Pfandhalle: mit Alter Fenk am Eingang („Fenk") und Bree Marlok hinter der Sichtklappe reden | beide bleiben je ein Eintrag; kein „Blinder Greis", „Türwächter", „Frau hinter der Sichtklappe" | `👥 anwesend in 'pfandhalle': Bree Marlok (gemeldet als „…“)` oder `[classifier] npcs … → none`. Schlecht: `… (neu, Standardwerte)` für eine der beiden |
| N2 | **Szenenwechsel über den spät bestätigten Knopf** (D138) | die Erzählung zeigt bei der Ankunft jemand Neuen; den Ortswechsel-Knopf erst danach bestätigen | die Person steht in der neuen Szene, nicht in der verlassenen | `👥 mit der Gruppe nach '<szene>': <Name>` |
| N3 | **`!redo` nach zwei gleichen Zeilen** (Befund 1) | nur wenn der DM zweimal die Spielerzeile wiederholt und der Zug stumm bleibt: dann `!redo` | der Zug **davor** ist danach noch im Verlauf (der DM weiß noch, was davor geschah) | `echo guard: the retry misfired again — suppressing the turn`, danach der Redo-Zug |
| N4 | **Ein Zug während des Auto-Recaps** (Befund 2, 3) | wenn `🧵 … Auto-Recap` läuft, normal weitersprechen | der DM kennt diesen Zug im nächsten noch | zwischen `🧵 Kontext bei … — Auto-Recap` und `🧵 Auto-Recap fertig` steht eine `[latency]`-Zeile |
| N5 | **Antworten enden auf ganzen Sätzen** (D137) | zuhören und im Chat mitlesen | kein halber Satz, auch nicht nach einem Schnitt; Stimme und Chat enden gleich | `✂ Antwort an der Ausgabegrenze abgeschnitten (220/220 Tokens), … Zeichen am Ende weggefallen` |
| N6 | **Wörtliche Rede klingt am Satzende natürlich** (Befund 9, 12) | auf NSC-Sätze achten, die auf `?“`, `!“` oder `.“` enden | der Satz wird gesprochen und steht im Chat; keine Pause oder Betonung an der falschen Stelle | keine Logzeile, nur Ohr und Chat |
| N7 | **Opening mitten in der Sitzung** (Befund 4) | nur falls nötig: `!start` oder `!intro` nach einem Spielerzug | das Opening bringt keinen 🎲-Knopf mit | keine Logzeile |
| N8 | **Sprachbefehl „… war ein sehr böser Junge"** (D134) | nur wenn Tobi es am Abend will; braucht „Mitglieder verschieben" | der Genannte fliegt aus dem Voice-Kanal, der DM hört die Zeile nicht | `⚡ <Name> war ein sehr böser Junge — vom Voice-Kanal getrennt` |

### Zwischen Durchgang 1 und 2 — Logs von Durchgang 1 sichern

Bot stoppen und, **bevor** er für Durchgang 2 wieder startet, in PowerShell im Repo-Ordner:

```
Copy-Item logs\debug.log    logs\debug-d1.log
Copy-Item logs\terminal.log logs\terminal-d1.log
```

`terminal.log` wird bei jedem Start geleert, `debug.log` läuft weiter und bekommt die Züge von
Durchgang 2 und 3 dazu. Alle vier Messungen laufen deshalb auf `debug-d1.log`.

### Durchgang 2 — setzt Opus den Würfel-Marker selbst? (Punkt 7a)

Bot stoppen, in `.env` `DM_ROLL_ROUTER=0`, starten, `!j`. Drei, vier Züge mit Handlungen, die
eine Probe brauchen.

- **Bestanden, wenn:** ein Würfelknopf erscheint, obwohl der Router aus ist.
- **Notieren:** Ja oder Nein, bei wie vielen von wie vielen Handlungen.
- Danach `DM_ROLL_ROUTER=1` zurücksetzen.

### Durchgang 3 — pausiert der Bot sauber, wenn Claude ausfällt? (Punkt 5)

Nach Durchgang 2 läuft der Bot wieder mit `DM_ROLL_ROUTER=1`; `!j`, ein Zug auf Opus zur
Kontrolle. Der Ausfall wird ohne Neustart erzeugt und wieder aufgehoben: eine Firewall-Regel
sperrt `claude.exe` das Netz. Dafür vorher eine **PowerShell als Administrator** öffnen. Die
Regel trennt auch offene Claude-Code-Sitzungen auf dem Rechner, solange sie steht.

```
New-NetFirewallRule -DisplayName "dm-claude-aus" -Direction Outbound -Action Block -Program "$env:USERPROFILE\.local\bin\claude.exe"
Remove-NetFirewallRule -DisplayName "dm-claude-aus"
```

Die erste Zeile ist der Ausfall, die zweite die Rückkehr. Liegt `claude.exe` woanders: Pfad aus
`where.exe claude` einsetzen.

| Schritt | Soll |
|---|---|
| Regel setzen, dann ein Zug (Mikro oder `!dm …`) | **genau eine** ⏸-Zeile im Chat und ein gesprochener Satz („Die Spielleitung ist gerade nicht erreichbar, das Spiel pausiert.“); **keine** Erzählantwort, kein „(Der Spielleiter schweigt …)“. Zeit vom Zug bis zur ⏸-Zeile notieren (bis zu zwei Minuten sind möglich) |
| `ollama ps` in einem zweiten Terminal | **kein** `mistral-nemo` (nur `bge-m3` darf dort stehen) |
| `!backend` | „bei Ausfall: Pause“, „Spiel pausiert seit …, nächster Versuch …“ |
| Regel löschen — **innerhalb etwa einer Minute nach der ⏸-Zeile** — und warten | **genau eine** ▶-Zeile („… es geht weiter.“) und ein gesprochener Satz; gleich danach beantwortet der DM **von selbst** die Zeile aus dem ersten Schritt, auf Opus |
| ein normaler Zug | Opus antwortet; keine weitere ⏸- oder ▶-Zeile |

Der Bot versucht es 30 s nach der ⏸-Zeile wieder, dann mit wachsendem Abstand (60 s, 120 s, …).
Kommt die ▶-Zeile erst nach mehr als drei Minuten Pause, lautet sie „… darum warte ich auf eure
nächste Zeile“ und der DM antwortet nicht von selbst. Dann eine Zeile sprechen: Die Antwort muss
die Zeile aus dem ersten Schritt mit beantworten. Auch das ist bestanden; im Protokoll vermerken,
welcher der beiden Fälle es war.

Zum Schluss prüfen, dass die Regel weg ist: `Get-NetFirewallRule -DisplayName "dm-claude-aus"`
muss einen Fehler melden („keine … gefunden“).

### Nach dem Abend

| # | Was | Wie |
|---|---|---|
| 6 | Verbrauch | Anzeige auf claude.ai, Differenz zum Startwert |
| 6b | Was die Klassifikatoren davon kosten (ADR 066) | Messung D unten; dazu: kam eine ⏸-Zeile wegen eines Verbrauchslimits („Limit bis etwa …“), und nach wie vielen Zügen? |
| 8 | Anteil abgeschnittener Antworten | Messung C unten |
| — | Logs sichern, **bevor** der Bot wieder startet | `logs/debug.log`, `logs/transcript.log`, `logs/terminal.log` |

---

## Die vier Messungen (nach dem Abend, in PowerShell im Repo-Ordner)

Nur Züge aus Durchgang 1 werten. Durchgang 3 ist die Pause-Probe. Alle vier Messungen laufen auf
der Kopie `logs\debug-d1.log` (Schritt zwischen Durchgang 1 und 2), nicht auf dem Gesamt-Log.

**A — Wie schnell ist ein Opus-Zug?**

```
Select-String -Path logs\debug-d1.log -Pattern '\[latency\]' | Select-Object -First 8
```

Aus zwei Zeilen (erster Zug nach `!start`, einer aus der Mitte) ablesen: `spawn=` (Start der
CLI), `first_audio=` (Auslöser bis erster Ton), `cache=` (Prompt-Tokens aus dem Cache).

**B — Wie lange bis zum Würfelknopf?**

```
Select-String -Path logs\debug-d1.log -Pattern '\[classifier\] roll'
```

Drei Zeilen mit einem Urteil (nicht `no test`) notieren, je die Millisekunden.

**C — Wie oft wurde abgeschnitten?**

```
$alle = (Select-String -Path logs\debug-d1.log -Pattern '\[latency\]').Count
$cut  = (Select-String -Path logs\debug-d1.log -Pattern '\[latency\].* cut ').Count
"$cut von $alle"
```

Ist das mehr als eine seltene Ausnahme, sagen 7a und 7b wenig aus: der Marker stand dann dort,
wo geschnitten wird.

**D — Was kosten die Klassifikatoren pro Zug? (ADR 066)**

Jeder Schema-Call auf Claude schreibt eine `[aux]`-Zeile: `in=` (Input-Tokens, Cache mitgezählt),
`cache=`, `out=`, `turns=`, `spawn=`, `api=`, `total=`. `fields=` sagt, welcher Call es war:
`ziel` Szene, `art,sache,an,von` Fakten, `npcs` NSCs, `needs_test,skill,difficulty` Würfel-Router.

```
$aux   = Select-String -Path logs\debug-d1.log -Pattern '\[aux\] \S+ fields=(\S+) in=(\d+) cache=(\d+) out=(\d+) turns=(\d+) spawn=(\d+)ms'
$zuege = (Select-String -Path logs\debug-d1.log -Pattern '\[latency\]').Count
$aux | Group-Object { $_.Matches[0].Groups[1].Value } | ForEach-Object {
  $in    = ($_.Group | ForEach-Object { [int]$_.Matches[0].Groups[2].Value } | Measure-Object -Sum).Sum
  $cache = ($_.Group | ForEach-Object { [int]$_.Matches[0].Groups[3].Value } | Measure-Object -Sum).Sum
  $spawn = ($_.Group | ForEach-Object { [int]$_.Matches[0].Groups[6].Value } | Measure-Object -Average).Average
  "{0}: {1} Calls, in je Call {2:N0}, davon Cache {3:N0}, spawn {4:N0} ms" -f $_.Name, $_.Count, ($in / $_.Count), ($cache / $_.Count), $spawn
}
$summe = ($aux | ForEach-Object { [int]$_.Matches[0].Groups[2].Value } | Measure-Object -Sum).Sum
"alle: {0} Calls in {1} Zuegen, {2:N0} Input-Tokens je Zug" -f $aux.Count, $zuege, ($summe / $zuege)
```

Notieren: die Zeile je Call-Art und die Summenzeile. Der Vergleichswert aus ADR 066 ist eine
Schätzung: Szene, Fakten und NSCs zusammen 3800–4900 Input-Tokens je Zug. Liegt die Messung
deutlich darüber oder kam am Abend ein Verbrauchslimit, ist das der Anlass, ADR 066 neu zu
entscheiden. Die Zahl stimmt nur, wenn die Kopie allein Durchgang 1 enthält — dafür sorgt der
Schritt „Altes Log weg“ unter „Vor dem Start“.

---

## Ergebnis vom 14.11.2026 (Durchgang 1, 19:04–19:33, Tobi + Sezgin, mit Bot A)

Durchgang 2 und 3 nicht gespielt; D139 (Pause statt Nemo) bleibt live-unverifiziert. Logs: `logs/debug-d1.log`,
`terminal-d1.log`, `transcript-d1.log`.

| Punkt | Ergebnis |
|---|---|
| 1 GPU / kein Nemo | `ollama ps` ohne `mistral-nemo` ✅; XTTS-Gerät nicht geprüft |
| 2 Züge mit Stimme | ✅ 33 |
| 3a Würfelknopf | ✅ (8 Router-Urteile, 7 Würfel-GIFs, zweimal Schicksalspunkt-Neuwurf) |
| 3b Szenenwechsel | ✅ dreimal, alle über Opus' `<<ORT>>`-Marker (schrein, pfandhalle, lagerhaus) |
| 3c harter Fakt | ✅ Auftragspergament mit Inquisitionssiegel (19:04:36) |
| 4 Recap | ☐ kein `!wrap`; Auto-Recap 19:20:32–19:20:40 lief |
| 6 Verbrauch | ca. 7 % des Session-Kontingents, parallel lief eine Claude-Code-Sitzung |
| 6b Verbrauchslimit | nein |
| 7a `<<TEST>>` ohne Router | nicht geprüft (Router an) — aber Opus setzte von sich aus 15 Marker in 33 Zügen |
| 7b `<<ERLEDIGT>>` | ✅ `vall-gestaendnis` (19:11:40) |
| 8 / C abgeschnitten | **8 von 33** |
| A kalt / warm | `spawn` 563 ms, `first_audio` 13,3 s / ~580 ms, 8–11 s — **`cache=0` in jedem Zug** |
| B Würfelknopf | 3313 · 4391 · 3687 ms (Ausreißer 6062) |
| D Szene `ziel` | 2189 / 740 / 719 ms (33 Calls) |
| D Fakten | 2079 / 985 / 720 ms (33) |
| D NSCs | 2451 / 1317 / 718 ms (33) |
| D Würfel-Router | 2020 / 1197 / 680 ms (29) |
| D alle Aux-Calls | ~8500 Input-Tokens je Zug (128 Calls); Szene+Fakten+NSCs ≈ 6700 — über der Schätzung 3800–4900 aus ADR 066 |
| N1 / N2 | ⚠️ Bree Marlok um 19:11:48 in der Szene **schrein** registriert, eine Minute bevor der Zeiger auf pfandhalle ging; Vosk und „Kettenmann“ in pfandhalle statt lagerhaus, „Kettenmann“ neben „Kettenbund-Schläger“ wohl doppelt |
| N4 | nicht eingetreten (kein Zug während des Auto-Recaps) |
| N5 | 8 Schnitte, s. Punkt 8 |

**9 — Urteil des Tisches:** Tobi: Die Texte waren früher besser; man muss hundertmal sagen, was passiert, bevor sich
etwas tut, oft dasselbe; die Proben sind immer zu schwer. Sezgin (19:29, als es hing): „Dann würde ich sagen, in
Fable reingeben.“ Tobi (19:29:50): „Das bewegt sich einfach nicht weiter.“

**Befunde aus dem Log:**

- **Hängeschleife durch verworfene Marker (Hauptbefund):** 19:25–19:31 schrieb Opus neunmal
  `<<TEST Überreden Schwierig für Fridolin>>`; jedes Mal `Inline-Marker verworfen — der Router entscheidet (D43)`, der
  Router sagte `no test` (einmal `Nahkampf` für eine Bestechung). Opus erzählte den offenen Moment immer neu.
- **Immer „Herausfordernd“:** jedes Router-Urteil des Abends; Opus' Schwierigkeit fiel mit dem Marker weg
  (19:08:47 wollte Opus *Leicht* = Ziel 82, gewürfelt wurde auf 42, die 72 wurde ein Fehlschlag).
- **Lange Züge:** bis 742 Zeichen = 48 s Audio; viel Atmosphäre, wenig Fortschritt pro Zug.
- **Kein Prompt-Cache bei der Erzählung** (`cache=0`), die Haiku-Calls treffen ihn.
- **NSCs in der Szene, die die Gruppe gerade verlässt** (N1/N2 oben).

Folgerunde: D140 (Opus-Marker zählt auf Claude), D141 (Fortschritt statt Atmosphäre, Kommas fürs Vorlesen,
Komma-Pausen im Code, Budget 280), D142 (Cache), D143 (ADR 066 B, Schalter aus).

## Nächster Lauf — die Folgerunde vom 14.11. prüfen

Alles darin ist nur durch Tests belegt. Ablauf wie Durchgang 1 (Sandbox leer, altes Log weg, Bot neu). Normal
spielen, nichts erzwingen außer einer Verhandlung mit Probe.

| # | Was | Gut, wenn | Beweis im Log |
|---|---|---|---|
| F1 | **Opus' Probe zählt** (D140) | Würfelknopf mit Opus' Fertigkeit und Schwierigkeit; eine eingeschüchterte oder bestochene Figur wird *Leicht* oder *Routine* | `🎲 Marker entscheidet: <Name> — <Fertigkeit> (<Schwierigkeit>)`; kein `Inline-Marker verworfen` mehr auf Claude |
| F2 | **Keine Hängeschleife** (D140, D141) | kein zweiter Zug, der denselben offenen Moment neu beschreibt; bleibt ein Wurf liegen, kommt der Knopf wieder oder die Welt handelt | höchstens einmal `🎲 Sicherheitsnetz: …` |
| F3 | **Fortschritt pro Zug** (D141) | jeder Zug bringt etwas Neues; Sätze dürfen lang sein, aber mit Kommas | 8 von 33 gekappt am 14.11. → jetzt deutlich weniger `✂` |
| F4 | **Die Stimme atmet an Kommas** (D141, `DM_TTS_COMMA_SPLIT=120`) | lange Sätze mit kurzen Pausen, keine abgehackten Mini-Stücke, kein Gebrabbel am Stückende | nur Ohr; zum Vergleich `DM_TTS_COMMA_SPLIT=0` |
| F5 | **Prompt-Cache greift** (D142) | erster Ton schneller als 8–13 s | ab dem zweiten Zug `cache=` deutlich über 0 in `[latency]`; nach einem Auto-Recap einmal wieder `cache_w=` hoch |
| F6 | **Zusatzanfrage der CLI?** (D142, offen) | — | im Verbrauch: kostet jeder Zug eine zweite kleine Opus-Anfrage (Sitzungsname)? Nur wenn auffällig |
| F7 | **NSCs in der richtigen Szene** (D144) | Eine Karten-Figur der nächsten Szene, gesehen bevor der Zeiger dort ist, bleibt in ihrer Szene | `👥 … (gehört nach '<Szene>', bleibt dort)`; schlecht: eine Karten-Figur `anwesend in '<alte Szene>'` |

ADR 066 B (ein Haiku-Call statt drei) ist gebaut, aber `DM_AUX_COMBINED=0`: der Abgleich gegen 35 Züge stimmte in
95 von 105 Urteilen überein, zwei Calls liefen ins 20-s-Timeout. Vor dem Einschalten: drei Abgleich-Läufe (ADR 066
Schritt 4), dann ein Lauf mit dem Schalter als einziger Änderung.

## Protokoll zum Ausfüllen

| Punkt | Ergebnis |
|---|---|
| 1 GPU / kein Nemo geladen | ☐ ja ☐ nein |
| 2 fünf Züge mit Stimme | ☐ ja ☐ nein |
| 3a Würfelknopf | ☐ ja ☐ nein |
| 3b Szenenwechsel von selbst | ☐ ja ☐ nein |
| 3c harter Fakt | ☐ ja ☐ nein |
| 4 Recap | ☐ ja ☐ nein |
| 5 Pause: genau eine ⏸-Zeile, keine Nemo-Antwort, `ollama ps` ohne `mistral-nemo` | ☐ ja ☐ nein — Zeit bis ⏸: ____ s |
| 5 Rückkehr: genau eine ▶-Zeile, die Spielerzeile wird beantwortet | ☐ ja ☐ nein — ☐ von selbst ☐ nach der nächsten Zeile |
| 6 Verbrauch vorher / nachher | ______ / ______ |
| 7a `<<TEST>>` ohne Router | ☐ ja ☐ nein — ___ von ___ |
| 7b `<<ERLEDIGT>>` angewendet | ☐ ja ☐ nein — ___ von ___ |
| 8 abgeschnitten | ___ von ___ |
| A `spawn` / `first_audio` (kalt) | ______ / ______ |
| A `spawn` / `first_audio` (warm) | ______ / ______ |
| B drei Werte in ms | ______ · ______ · ______ |
| 6b Verbrauchslimit erreicht | ☐ nein ☐ ja, nach ___ Zügen |
| D Szene (`ziel`): in je Call / Cache / spawn | ______ / ______ / ______ |
| D Fakten (`art,…`): in je Call / Cache / spawn | ______ / ______ / ______ |
| D NSCs (`npcs`): in je Call / Cache / spawn | ______ / ______ / ______ |
| D Würfel-Router: in je Call / Cache / spawn | ______ / ______ / ______ |
| D alle Aux-Calls: Input-Tokens je Zug | ______ |
| N1 Karten-Figuren ohne Doppelgänger | ☐ ja ☐ nein ☐ nicht eingetreten |
| N2 Wechsel über späten Knopf | ☐ ja ☐ nein ☐ nicht eingetreten |
| N3 `!redo` nach zwei gleichen Zeilen | ☐ ja ☐ nein ☐ nicht eingetreten |
| N4 Zug während des Auto-Recaps | ☐ ja ☐ nein ☐ nicht eingetreten |
| N5 ganze Sätze am Ende | ☐ ja ☐ nein — Uhrzeiten: ______ |
| N6 wörtliche Rede am Satzende | ☐ ja ☐ nein — Uhrzeiten: ______ |
| N7 Opening mitten in der Sitzung | ☐ ja ☐ nein ☐ nicht eingetreten |
| N8 Sprachbefehl | ☐ ja ☐ nein ☐ nicht probiert |

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
| ⏸-Pause dauert zu lange, Abend lokal retten | `!backend ollama` (Nemo erzählt, auch die vorgemerkten Zeilen) |
| Nach einer ⏸-Zeile sofort neu versuchen | `!backend claude` |
| Ein Klassifikator stört | `!automatik fakten aus` bzw. `szene aus` |
| Falscher Szenenwechsel | ↩-Knopf (eine Minute), sonst `!ort <id>` |
| Falscher Fakt | `!fakt weg <Text>` |
| Antwort war Müll | `!redo` |
| Pause | Esc im Bot-Terminal oder ⏸-Knopf |

Jeder Notgriff gehört mit Uhrzeit ins Protokoll: er ändert, was der Abend misst.
