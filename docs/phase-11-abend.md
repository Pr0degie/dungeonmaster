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
| Sandbox leer | Bot aus; `uv run python -m dmbot.rag.ingest_session --wipe-debug <channel-id>`. Der Befehl verschiebt alle Dateien mit `.debug` im Namen (auch das Replay-Journal `history.debug.jsonl`, das ADR 046/066 brauchen) nach `logs\archive\sandbox\<Zeitstempel>_<channel-id>\` und leert danach die Sandbox im RAG-Speicher | `[OK] archived … sandbox file(s)` und `[OK] wiped … chunks`; nichts ohne `.debug` wurde angefasst. Steht `[!!] … store NOT wiped` da, hält etwas eine Datei offen: schließen, Befehl wiederholen |
| `.env` | Block aus [§9.2](testabend-ablauf.md) eintragen | `DM_LLM_BACKEND=claude`, `DM_LLM_ON_FAILURE=pause`, `DM_NPC_MEMORY=0`, `DM_CONSISTENCY_GUARD=0`, `DM_DEBUG_OVERLAY=0`, `DM_CLOCKS=0`, `DM_FLAG_CONFIRM=0`, `DM_LOG_FILE=1` |
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

### Zwischen Durchgang 1 und 2 — nichts zu sichern

Jeder Bot-Start ist ein eigener Lauf. Startet der Bot für Durchgang 2, wandern die drei Logs von
Durchgang 1 nach `logs\archive\runs\<Startzeit von Durchgang 1>\`; `logs\` beginnt leer. Die
Messungen finden Durchgang 1 über `logruns` (siehe „Die vier Messungen“).

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
| — | Lauf anpinnen, wenn er als Vergleich taugt (die Archivgrenze löscht sonst nach 30 gespielten Läufen) | `uv run python -m dmbot.tools.logruns --pin <N> --name <name>`; `N` aus der Liste von `logruns` |

---

## Die vier Messungen (nach dem Abend, in PowerShell im Repo-Ordner)

Nur Züge aus Durchgang 1 werten. Durchgang 3 ist die Pause-Probe. Jeder Bot-Start hat sein eigenes
Log; zuerst den Ordner von Durchgang 1 nach `$d` holen:

```
uv run python -m dmbot.tools.logruns                    # Liste: Start, Ende, Züge je Lauf
$d = uv run python -m dmbot.tools.logruns --path <N>    # N = die Zeile mit der Startzeit von Durchgang 1
```

`0` ist `logs\` selbst: der laufende oder zuletzt gestoppte Lauf. War Durchgang 1 der letzte Start,
reicht `$d = 'logs'`.

**A — Wie schnell ist ein Opus-Zug?**

```
Select-String -Path "$d\debug.log" -Pattern '\[latency\]' | Select-Object -First 8
```

Aus zwei Zeilen (erster Zug nach `!start`, einer aus der Mitte) ablesen: `spawn=` (Start der
CLI), `first_audio=` (Auslöser bis erster Ton), `cache=` (Prompt-Tokens aus dem Cache).

**B — Wie lange bis zum Würfelknopf?**

```
Select-String -Path "$d\debug.log" -Pattern '\[classifier\] roll'
```

Drei Zeilen mit einem Urteil (nicht `no test`) notieren, je die Millisekunden.

**C — Wie oft wurde abgeschnitten?**

```
$alle = (Select-String -Path "$d\debug.log" -Pattern '\[latency\]').Count
$cut  = (Select-String -Path "$d\debug.log" -Pattern '\[latency\].* cut ').Count
"$cut von $alle"
```

Ist das mehr als eine seltene Ausnahme, sagen 7a und 7b wenig aus: der Marker stand dann dort,
wo geschnitten wird.

**D — Was kosten die Klassifikatoren pro Zug? (ADR 066)**

Jeder Schema-Call auf Claude schreibt eine `[aux]`-Zeile: `in=` (Input-Tokens, Cache mitgezählt),
`cache=`, `out=`, `turns=`, `spawn=`, `api=`, `total=`. `fields=` sagt, welcher Call es war:
`ziel` Szene, `art,sache,an,von` Fakten, `npcs` NSCs, `needs_test,skill,difficulty` Würfel-Router.

```
$aux   = Select-String -Path "$d\debug.log" -Pattern '\[aux\] \S+ fields=(\S+) in=(\d+) cache=(\d+) out=(\d+) turns=(\d+) spawn=(\d+)ms'
$zuege = (Select-String -Path "$d\debug.log" -Pattern '\[latency\]').Count
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
entscheiden. Die Zahl stimmt, weil `$d` genau einen Bot-Start enthält, also allein Durchgang 1.

---

## Ergebnis vom 14.11.2026 (Durchgang 1, 19:04–19:33, Tobi + Sezgin, mit Bot A)

Durchgang 2 und 3 nicht gespielt; D139 (Pause statt Nemo) bleibt live-unverifiziert. Logs (angepinnt):
`logs/archive/pinned/2026-11-14_d1/` mit `debug.log`, `terminal.log`, `transcript.log`.

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

## Ergebnis vom 27.11.2026 (16:00–16:44, Tobi + Timo + Sezgin, mit Bot A)

Der ganze Lauf, beendet mit `!wrap` um 16:44:02 (die Zeit stammt aus dem Änderungsdatum von `recap.debug.md`; im
Log steht der Befehl nicht, s. unten). Teil B nicht gespielt; D139 bleibt live-unverifiziert. Lauf 0: Start
16:00:27, Opening 16:03:32, letzte Erzählantwort 16:35:55, 18 Erzählantworten, Code `60c7983`, Opus
`claude-opus-5-5`, Haiku `claude-haiku-5-5`. Nach dem `!wrap` lief der Bot weiter (beim Auswerten reichte das Log bis
17:05, nur Mitschrift, kein Zug mehr); gezählt ist bis zum `!wrap`. Lauf 1 (15:54:42–16:00:07, 0 Züge) war nur der Neustart, um Gellicus
(Timo) in die lokale Party-Datei zu nehmen. Logs: bis zum nächsten Bot-Start in `logs\`, danach
`logs/archive/runs/2026-11-27_160027/`.

**Hauptbefund — zwei Erzählzüge gleichzeitig (neu als Prüfpunkt F11).** Zweimal liefen zwei Erzählanfragen
nebeneinander, beide Antworten wurden gesprochen, Satz für Satz ineinander:

- **16:17:06** — erstes Sprechfenster 16:16:36–16:16:56 (Timo, Tobi), zweites 16:16:57–16:16:58 (Timo: „Perfekt.“,
  ein versehentlicher Tastendruck). Zwei `LLM roh` in derselben Sekunde (9610 ms und 7625 ms), `[latency]` turn=10
  vor turn=9, turn=8 fehlt. Die zweite Antwort beschreibt denselben Moment noch einmal.
- **16:22:19 / 16:22:21** — Timo und Tobi hatten im selben Zug je eine Probe (F8). Jeder Schicksals-Neuwurf
  (16:22:10 Gellicus, 16:22:14 Fridolin) löste eine eigene Erzählung aus (turn=15, turn=16). Die beiden widersprechen
  sich: in der einen drückt der Wächter Gellicus gegen den Käfig und Fridolins Tanz erntet einen kalten Blick, in der
  anderen ist der Wächter abgelenkt und Opus verlangt `<<TEST Nahkampf Leicht für Gellicus>>`. Zu diesem Marker steht
  keine `🎲`-Zeile im Log, ein Knopf ist nicht belegt.

Nach 16:25 kein weiterer Fall: `[latency]` turn=17, 18, 19 kommen in Reihenfolge.

Tobis Wunsch am Tisch (16:23:11): bei zwei Proben erst beide Ergebnisse abwarten, dann eine Erzählung. In
`logs/archive/pinned/bis-2026-11-14/` gibt es einen früheren Fall (21:37:56 turn=49, 21:38:09 turn=48 `roll`); im
Zwei-Spieler-Lauf vom 14.11. keinen.

**Weitere Befunde nach 16:25:**

- **16:34:34 — Smite macht keinen Schaden.** Fridolin manifestiert Smite (16:34:26 `🌀 … 05 — Erfolg, 0 EG · Warp
  2/4.`), die Erzählung lässt den Blitz den Torwächter in die Brust treffen und gegen einen Pfandkäfig schleudern.
  Der Zustand führt den Torwächter danach weiter bei 10/10 Wunden, obwohl das Profil für Smite „2 + WillkürB + EG
  Schaden“ angibt: eine Schadenskraft wendet keinen Schaden an.
- **16:35:49 — „Was kann ich?“ wird nicht aus dem Bogen beantwortet.** Tobi fragt, im selben Sprechfenster geht ein
  „...“ von Timo mit an die Spielleitung. Die Antwort um 16:35:55 ist Szenenerzählung mit Vorschlägen („Fridolin, du
  könntest ihr eine glaubwürdige Geschichte auftischen …“), ohne Fertigkeit und ohne Wert aus dem Bogen. Tobi um
  16:36:05: „Okay, das hat schon mal nicht funktioniert.“
- **16:35:49 — Hintergrundton als Spielerzeile.** Timos Mikrofon nahm englischen Videoton auf (16:35:58 „... was
  $64.000, almost four times my salary …“, 16:36:09 „...dollars. In 2026, the average new car now cost...“); ein
  „...“ davon ging als Timos Zeile an die Spielleitung. Dazu drei `🚫 Whisper-Halluzination verworfen` (16:30:06,
  16:31:18, 16:36:05).
- **16:44:02 — der `!wrap` hinterlässt keine Spur im Log.** Recap und Zustand sind geschrieben (s. Zeile „Recap /
  `!wrap`“), aber weder `debug.log` noch `terminal.log` hat eine Zeile dazu: kein Befehl, kein Recap-Text, keine
  Dauer.

| Punkt | Urteil | Beleg |
|---|---|---|
| F1 | bestanden | 16:10:51 `🎲 Marker entscheidet: Fridolin Feuchtgebietheld — Überreden (Leicht)`, 16:19:53 Nahkampf (Schwierig), 16:21:50 Nahkampf (Herausfordernd); kein `Inline-Marker verworfen` |
| F2 | bestanden für die Hängeschleife | kein `🎲 Sicherheitsnetz`; die doppelte Beschreibung von 16:17:06 hat eine andere Ursache (Hauptbefund) |
| F3 | bestanden | kein `✂` in 18 Antworten (14.11.: 8 von 33) |
| F4 | nur am Tisch prüfbar | — |
| F5 | bestanden (Cache), erster Ton nicht schneller | `cache=11022` in 16 von 17 Zügen ab turn=2; einmal `cache=0 cache_w=15326` um 16:36:32 (turn=19), der erste Zug nach dem Auto-Recap — erwartet; `first_audio` Median 10,3 s (14.11.: 10,2 s), Spanne 6,2–17,8 s |
| F6 | nur am Tisch prüfbar | Verbrauch auf claude.ai |
| F7 | nicht eingetreten | kein `gehört nach` |
| F8 | bestanden | 16:21:50 `🎲 Marker entscheidet: Gellicus Schulz …`, 16:21:56 `🎲 router: Fridolin Feuchtgebietheld … → Überreden (Herausfordernd)` |
| F9 | nur am Tisch prüfbar | im Text: NSCs nennen Charakternamen, die niemand gesagt hat (16:10:51 „Fridolin, so heißt ihr doch“, 16:15:35 „Gellicus, Rektalus, oder wie eure Namen auch lauten mögen“) |
| F10 | nur am Tisch prüfbar | 16:19:27 Tobi: „Boah, also die Antwort gefällt mir“ |
| W1 | bestanden | 8 × `🎲 throw gif (stored)`, auch nach den drei Neuwürfen (16:20:20, 16:22:13, 16:22:17) und beim Psionik-Wurf (16:34:30) |
| W2 | nur am Tisch prüfbar | Knopfdrücke stehen nicht im Log |
| W3 | nicht eingetreten | beide Nahkampf-Proben von Gellicus misslangen, auch nach dem Neuwurf (16:20:15, 16:22:10); die Zielauswahl kommt erst nach einem Treffer |
| W4 | nicht bestanden | 16:35:49 „Was kann ich?“ → 16:35:55 Szenenerzählung mit Vorschlägen, keine Fertigkeit und kein Wert aus dem Bogen |
| W5 | bestanden | 16:20:15, 16:22:10, 16:22:14 `🙏 … gibt einen Schicksalspunkt aus …` je nach einem Fehlschlag |
| W6 | erster Teil bestanden; Schicksal nach Fehlschlag nicht eingetreten | 16:34:17 `<<MANIFEST Smite für Fridolin Feuchtgebietheld>>`, 16:34:22 `🎲 router: Fridolin Feuchtgebietheld — Psi-Meisterschaft verworfen, die Manifestation deckt die Handlung ab`, 16:34:26 `🌀 Fridolin Feuchtgebietheld manifestiert Smite (Ziel 41): 05 — Erfolg, 0 EG · Warp 2/4.`, 16:34:30 `🎲 throw gif (stored)`; danach `warp_charge` 2 im Zustand. Der Wurf gelang, also kamen keine Schicksal-Buttons |
| N1 | bestanden | Bree Marlok und Alter Fenk je ein Eintrag; 16:15:39 `[classifier] npcs … → none` nach dem Zug mit dem „blinden Alten“ |
| N2 (D138) | bestanden | 16:12:36 `scene → pfandhalle … [marker]`, 16:12:38 `👥 anwesend in 'pfandhalle': Torwächter (neu, Standardwerte)` — die neue Figur steht in der neuen Szene |
| N3, N7, N8 | nicht eingetreten | kein `echo guard`, kein `⚡ … böser Junge`, nur das eine Opening von 16:03:32 |
| N4 | nicht eingetreten | Auto-Recap 16:34:45–16:34:53 (`🧵 Kontext bei 21881/24576`, `🧵 Auto-Recap fertig`), dazwischen keine `[latency]`-Zeile: kein Zug während des Auto-Recaps |
| N5 | bestanden | kein `✂`, alle 18 Antworten enden auf einem ganzen Satz |
| N6 | nur am Tisch prüfbar | — |
| Recap / `!wrap` | geschrieben, Text stimmt, nicht im Log | 16:44:02 `recap.debug.md` und `recap` in `state.debug.json` (beide 1144 Zeichen): Zollhaus, Schrein, Pfandhalle, endet auf Brees offener Frage. Die widersprüchliche zweite Fassung des Doppelzugs von 16:22, die das Auto-Recap von 16:34:53 (1214 Zeichen) noch trug („Fridolin lenkte den Wächter ab“), ist weg. Keine Zeile in `debug.log` oder `terminal.log` |
| Teil B | nicht gespielt | — |

| Messung | 27.11. | Vergleich |
|---|---|---|
| Würfe je Probenanforderung des Erzählers | 3 von 3 `Marker entscheidet` gewürfelt; dazu der Marker von 16:22:21 ohne Logzeile und ohne Wurf. Router: 2 Zeilen, 1 gewürfelt (16:22:05), 1 verworfen, weil die Manifestation die Handlung abdeckt (16:34:22). `🌀`: 1 von 1 gewürfelt (16:34:26) | 4 von 15 am 14.11. |
| Zeichen je Zug / je Satz | 595 / 142 (18 Antworten, 75 Sätze; `chars=` im Mittel 595) | 555 / 166 am 14.11. |
| Schnitte | 0 von 18 | 8 von 33 |
| `cache=` ab Zug 2 | 11022 in 16 von 17 Zügen, einmal 0 (16:36:32, turn=19, erster Zug nach dem Auto-Recap, `cache_w=15326`); `cache_w=` steigt davor von 4353 auf 10857 | immer 0 |
| Doppelte oder falsch platzierte Figuren | keine; neu: „Torwächter“ (steht nicht auf der Abenteuerkarte) | drei am 14.11. |

Sonst: kein `Traceback`, kein `ERROR`, keine Pause. Die Spieluhr stand beim `!wrap` auf Tag 1, 23:06 (Start
21:00, Frist 24:00), im Log stehen aber nur zwei `🕐`-Zeilen mit je +15 min. `logs/archive/LAYOUT` und
`logs/archive/sandbox/` sind nicht git-ignoriert.

---

## Nächster Lauf — die Folgerunden vom 14.11. und 27.11. und die Zerlegung prüfen

Alles darin ist nur durch Tests belegt. **Stand 27.11., abends:** Der Bot muss vorher neu starten. Der laufende
Stand (Start 27.11., 16:00) kennt weder D151–D155 noch die Zerlegung von `memory/state.py`, `orchestrator.py` und
`voice/dicecog.py` ([Plan](plans/split-state-dicecog-orchestrator.md)). Die Sandbox hält den Stand vom 27.11.
(Pfandhalle, Tag 1, 23:06, Recap vom `!wrap`): darauf weiterspielen, dann prüft `!j` gleich das Laden eines
bestehenden Spielstands. `characters.local.json` enthält Fridolin, Gellicus und Rektalus.

**Ablauf:** `!j` → die vier Kontrollbefehle aus „Beim Start“ → `!start` → spielen (Teil A) → `!wrap` → Teil B
(Pause-Probe, zehn Minuten) → Bot stoppen, mir Bescheid geben („werte den letzten Lauf aus“). Zu sichern ist nichts:
die Logs bleiben bis zum nächsten Start in `logs\` und wandern dann nach `logs\archive\runs\`.

### Checkliste — alles, was dieser Lauf zeigen muss

Eine Zeile je Handgriff, in Spielreihenfolge. Die rechte Spalte nennt, was der Handgriff prüft; die Einzelheiten
und Beweis-Logzeilen stehen in den Tabellen von Teil A und B darunter. Wer diese Liste abarbeitet, hat alles
Offene berührt.

| # | Was du tust | Was es prüft |
|---|---|---|
| 1 | Bot neu starten; beide Preflight-Zeilen stehen auf OK | der Bot fährt mit den zerlegten Modulen hoch |
| 2 | `!j` auf dem bestehenden Spielstand, dann die vier Kontrollbefehle | Zerlegung `state.py`: der Spielstand wird geladen; das Spieler-Panel bleibt eine Nachricht (W2) |
| 3 | `!start` oder `!intro` | Zerlegung `orchestrator.py`: das Opening |
| 4 | ein normaler erzählter Zug, danach `!redo` | Zerlegung `orchestrator.py`: Zug und Wiederholung; die Stimme atmet an Kommas (F4); wörtliche Rede klingt am Satzende natürlich (N6); kein Regeltext als Spielerrede, Wunden und Gegenstände stimmen (F9) |
| 5 | zwei Spieler handeln im selben Zug, beide mit Probe; nach einem Fehlschlag „🙏 Neu würfeln“ | **eine** Erzählung für beide Proben, nichts wird ineinander gesprochen (F11, D152); Zerlegung `dicecog.py`: Probe mit Schicksals-Neuwurf, bei eingeschalteter Wurf-Animation erscheint ein zweiter Wurf |
| 6 | Angriff mit genanntem Ziel („Ich greife den Torwächter an“), der Wurf gelingt | der Treffer geht ohne Auswahl auf den Genannten (W7, D151); Zerlegung `state.py`: der Treffer wird gebucht; Waffenschaden verliert nur die Rüstung des Ziels (W8, D155) |
| 7 | Angriff, ohne ein Ziel zu nennen, der Wurf gelingt | die Zielauswahl zeigt nur Anwesende (W3) |
| 8 | Fridolin wirkt Smite auf einen genannten NSC; misslingt der Wurf, einen Schicksalspunkt nehmen | Psi-Schaden wird gebucht (W8, D153); Schicksal nach einem Psi-Fehlschlag (W6); Zerlegung `dicecog.py`: Manifestation mit Schaden und mit Neuwurf |
| 9 | „Was kann ich?“ sagen | der eigene Bogen erscheint im Textkanal (W4, D154) |
| 10 | Ortswechsel mit Ankunft bei jemandem; ein NSC übergibt etwas oder sagt etwas zu | Karten-Figuren stehen in der richtigen Szene (F7, D144); Zerlegung `state.py`: ein erzählter Fakt wird notiert |
| 11 | `!rules` mit einer Frage | Zerlegung `orchestrator.py`: die Regelantwort |
| 12 | `!npc add`, `!npc list`, `!agenda`, `!agenden`, `!npcmem`, `!help` | Zerlegung `dicecog.py`: die vier NSC-Kommandos laufen und stehen in `!help` unter `NpcCog` |
| 13 | `!wrap` | Zerlegung `orchestrator.py`: der Recap; er steht jetzt auch im Log (D152) |
| 14 | Teil B: Pause-Probe mit der Firewall-Regel, danach die Regel wieder aufheben | Pause statt Nemo (D139), noch nie gespielt |
| 15 | zum Schluss: jeder sagt drei Sätze; Verbrauch auf claude.ai ansehen | Urteil des Tisches (F10); Zusatzanfrage der CLI (F6) |

**Nur wenn die Lage von selbst eintritt:** `!redo` nach zwei gleichen Zeilen (N3), ein Zug während des
Auto-Recaps (N4), ein Opening mitten in der Sitzung (N7), der Sprachbefehl (N8), kein zweiter Zug zum selben
offenen Moment (F2).

**Am 27.11. schon bestanden, läuft nur mit:** Opus' Probe zählt (F1), keine abgeschnittene Antwort (F3, N5), der
Cache greift (F5), zwei Spieler mit einer Probe von Opus (F8), Würfel-Post und GIF (W1), Schicksal-Buttons nach
einem Fehlschlag (W5), Karten-Figuren ohne Doppelgänger (N1), Ankunft in der neuen Szene (N2).

Zeigt der Würfelablauf einen Fehler, sind die Änderungen D151–D153 und der Umzug von `dicecog.py` beide
verdächtig. Jeder Umzug ist ein eigener Commit und lässt sich einzeln zurücknehmen.

### Teil A — im Spiel, Prüfpunkte der Folgerunde

Normal spielen; herbeiführen: eine Verhandlung oder Bestechung mit Probe, zwei Spieler handeln im selben Zug,
ein Ortswechsel mit Ankunft bei jemandem.

| # | Was | Gut, wenn | Beweis im Log |
|---|---|---|---|
| F1 | **Opus' Probe zählt** (D140) | Würfelknopf mit Opus' Fertigkeit und Schwierigkeit; eine eingeschüchterte oder bestochene Figur wird *Leicht* oder *Routine* | `🎲 Marker entscheidet: <Name> — <Fertigkeit> (<Schwierigkeit>)`; kein `Inline-Marker verworfen` mehr auf Claude |
| F2 | **Keine Hängeschleife** (D140, D141) | kein zweiter Zug, der denselben offenen Moment neu beschreibt; bleibt ein Wurf liegen, kommt der Knopf wieder oder die Welt handelt | höchstens einmal `🎲 Sicherheitsnetz: …` |
| F3 | **Fortschritt pro Zug** (D141) | jeder Zug bringt etwas Neues; Sätze dürfen lang sein, aber mit Kommas | 8 von 33 gekappt am 14.11. → jetzt deutlich weniger `✂` |
| F4 | **Die Stimme atmet an Kommas** (D141, `DM_TTS_COMMA_SPLIT=120`) | lange Sätze mit kurzen Pausen, keine abgehackten Mini-Stücke, kein Gebrabbel am Stückende | nur Ohr; zum Vergleich `DM_TTS_COMMA_SPLIT=0` |
| F5 | **Prompt-Cache greift** (D142) | erster Ton schneller als 8–13 s | ab dem zweiten Zug `cache=` deutlich über 0 in `[latency]`; nach einem Auto-Recap einmal wieder `cache_w=` hoch |
| F6 | **Zusatzanfrage der CLI?** (D142, offen) | — | im Verbrauch: kostet jeder Zug eine zweite kleine Opus-Anfrage (Sitzungsname)? Nur wenn auffällig. Hintergrund: die CLI schickt vor unserem Prompt einen Systemhinweis mit der Account-E-Mail und eine Umgebungsnachricht mit Temp-Ordner und Datum mit; die Sitzungsnamen-Anfrage wurde bisher nur bei einer absichtlich scheiternden Anfrage gesehen |
| F7 | **NSCs in der richtigen Szene** (D144) | Eine Karten-Figur der nächsten Szene, gesehen bevor der Zeiger dort ist, bleibt in ihrer Szene | `👥 … (gehört nach '<Szene>', bleibt dort)`; schlecht: eine Karten-Figur `anwesend in '<alte Szene>'` |
| F8 | **Zwei Spieler, eine Probe von Opus** (D140, Review) | wer keinen Marker bekam, bekommt seinen Knopf vom Router | `🎲 Marker entscheidet: A …` und `🎲 router: B …` im selben Zug |
| F9 | **Kontext ohne Überschrift** (D142, offen) | Opus verwechselt Regelbuch-/Abenteuertext nicht mit Spielerrede, hält den Zustand (Wunden, Gegenstände) ein | nur Ohr; Verdacht mit Uhrzeit notieren. Scheitert der Punkt, ist die Abhilfe eine Kopfzeile vor dem Block (ändert den Prompt, braucht `dm-eval` und einen Lauf) |
| F10 | **Urteil des Tisches** | jeder sagt drei Sätze: besser als am 14.11.? | wörtlich aufschreiben |
| F11 | **Ein Erzählzug zur Zeit** (D152, Befund vom 27.11.) | zwei Proben im selben Zug ergeben **eine** Erzählung, wenn beide gewürfelt sind (Log `🎲 Erzählung wartet auf 1 weitere Probe(n)`); zwei Sprechfenster kurz nacheinander ergeben zwei Antworten nacheinander, nie ineinander gesprochen; eine Würfel-Erzählung beginnt erst, wenn die Antwort davor zu Ende gesprochen ist | keine zwei `🪵 LLM roh` näher beieinander als die `⏱ LLM`-Dauer der ersten; `[latency]` turn= in steigender Reihenfolge (Lücken sind erlaubt: ein Tastendruck, der nichts an die Spielleitung schickt, verbraucht eine Zugnummer ohne Zeile) |

### Teil A — dabei mitprüfen, noch offen aus früheren Runden

| # | Was | Gut, wenn |
|---|---|---|
| W1 | Würfel: Zielwert-Post, GIF, Ergebnis, auch nach „🙏 Neu würfeln“ | alles erscheint; Log `🎲 throw gif (stored)` |
| W2 | Spieler-Panel | bleibt eine Nachricht und wird nur bearbeitet |
| W3 | Angriff: Zielauswahl | nur Anwesende; kein „Wechseln“ nach einem Auto-Wechsel |
| W4 | „Was kann ich?“ (D154) | im Textkanal erscheint der eigene Bogen (📋 Name, Merkmale, Fertigkeiten mit Werten, Talente, Kräfte, Schicksalspunkte), Log `📋 Bogen-Antwort für <Name>`; die Erzählung läuft normal weiter. „Was kann ich sehen?“ löst nichts aus |
| W5 | Schicksal-Buttons | erscheinen nach Fehlschlägen |
| W6 | **Psionik** (Würfel-GIF, D145) | der 🌀-Knopf zeigt den Wurf wie eine Probe; nach einem Fehlschlag kommen die Schicksal-Buttons, und die Warp-Aufladung im Panel gilt für das Ergebnis, das stehen bleibt (`🙏 … dieses Ergebnis gilt: 🌀 …`) |
| W7 | **Angriff mit genanntem Ziel** (D151) | „Ich greife den Torwächter an“ und der Wurf gelingt: der Treffer geht ohne Auswahl auf ihn (Log `🎯 Ziel aus der Ansage: Torwächter`). Zwei Genannte, niemand genannt, eine Verneinung („nicht auf den Wächter“) oder nur ein Mitspieler genannt: die Auswahl kommt, genannte NSCs stehen oben, Mitspieler unten |
| W8 | **Psi-Schaden** (D153, D155) | Fridolin wirkt Smite auf einen genannten NSC und der Wurf gelingt: der Schaden ist 2 + Willenskraftbonus + Erfolgsgrade ohne Abzug; auch Waffentreffer verlieren nur noch die Rüstung des Ziels, keine Zeile nennt mehr einen „Soak“ bei einem Ziel ohne Rüstung. Nach der 🌀-Zeile kommt eine Schadenszeile (`💥 Fridolin … trifft … mit Smite: … Wunden`), die Wunden im Panel sinken, danach eine Erzählung. Ohne genanntes Ziel kommt die Auswahl „🌀 … wen trifft es?“ mit dem Eintrag „Niemand davon — nur erzählen“; steht kein NSC in der Szene, wird nur erzählt |
| N3–N8 | die Beobachtungspunkte von oben („Seit dem 12.11. geändert“) | nur wenn die Lage eintritt |

### Teil B — Pause statt Nemo (D139), nach `!wrap`

Genau wie Durchgang 3 oben (PowerShell als Administrator, Firewall-Regel auf `claude.exe`): eine ⏸-Zeile, kein
Nemo, eine ▶-Zeile, der liegengebliebene Zug wird beantwortet; zum Schluss die Regel wieder weg.

### Danach — wertet Claude aus dem Log aus

Messungen A–D wie oben (A: `cache=` > 0 ab Zug 2 = F5), Anteil `✂`, Zahl der `Marker entscheidet` / `Sicherheitsnetz` /
`router`, NSC-Zeilen `gehört nach …`, Verbrauch vorher/nachher auf claude.ai.

ADR 066 B (ein Haiku-Call statt drei) ist am 15.11. nach dem Abgleich verworfen und wieder entfernt worden (D148,
ADR 066, Nachtrag 2026-11-15): der Abgleich gegen 35 Züge stimmte in 95 von 105 Urteilen überein, zwei Calls liefen
ins 20-s-Timeout, beide in Zügen, in denen jemand Neues auftaucht. Szene, Fakten und NSCs bleiben drei Calls; am
Tisch ändert sich dadurch nichts. Das Journal des 14.11. (`history.debug.jsonl`) ist beim Vorbereiten am 14.11.,
20:40 gelöscht worden.

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
