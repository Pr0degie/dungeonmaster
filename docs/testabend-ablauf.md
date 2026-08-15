# Testabend: Ablauf, Prüfpunkte, Nacharbeit

Der zeitliche Faden eines Testabends mit der Debug-Kampagne „Die Mitternachtsfracht" —
von der Vorbereitung am fremden Rechner bis zu dem, was danach ins Repo zurückfließt.

Die Szenen-Referenz (welche Szene welches Gate auslöst, welche Logzeile es beweist, die
Debrief-Greps, der Reset) steht im [Runbook](debug-campaign-runbook.md) und wird hier nicht
wiederholt. Dieses Dokument beantwortet die andere Hälfte: **in welcher Reihenfolge, woran
man am Bildschirm erkennt, dass es geklappt hat, und was danach passiert.**

Die Auflösung der Kampagne steht hier bewusst nicht — wer mitspielt, kann das Dokument lesen.

---

## 1. Was der Abend beweisen soll

Zehn Gates. Acht schließen an einem Abend, zwei brauchen eine kurze zweite Sitzung.

| Gate | Fähigkeit | Szene | 2. Sitzung? |
|---|---|---|---|
| G1 | Regelfrage wird aus dem Regelbuch beantwortet, nicht geraten | `schrein` | nein |
| G2 | Fortschrittsuhren: der DM schlägt Ticks vor, Code führt sie aus | `zollhaus` → `lagerhaus` | nein |
| G3 | Ingame-Zeit läuft, Fristen verstreichen mit Konsequenz | `zollhaus` → `siedehaus` → `pier_neun` | nein |
| G4 | Szenenkarten sind zustandsbehaftet: ein Ausgang bleibt verriegelt | `lagerhaus` | nein |
| G5 | NSCs erinnern sich; eine Lüge fliegt auf, Fraktionen tratschen | `pfandhalle` → `siedehaus` | nein |
| G6 | Konsistenz-Wächter: der DM lässt keinen Toten sprechen | `lagerhaus` → `pier_neun` | nein |
| G7 | NSC-Agenden laufen offscreen weiter | `zollhaus` → `siedehaus` → `pier_neun` | nein |
| G8 | Wunden überleben einen Neustart, der Recap stimmt | `lagerhaus` → `pier_neun` | halb |
| G9 | Chekhov-Fäden: beiläufige Details kommen später zurück | `schrein` + `pfandhalle` → Sitzung 2 | **ja** |
| G10 | Kampagnengedächtnis: der DM erinnert sich an den letzten Abend | Sitzung 2 | **ja** |

Zusätzlich, ohne eigenes Gate, aber der eigentliche Anlass dieses Laufs: **die Sandbox aus
ADR 056 muss halten.** Der letzte Versuch scheiterte daran, dass der Bot den Stand der echten
Kampagne lud. Beweis diesmal: Startszene `zollhaus`, 🧪-Panel beim `!j`, `state.debug.json`
entsteht, und die Live-`state.json` behält ihre Änderungszeit.

---

## 2. Vorbereitung am Zweitrechner (einmalig, vor dem Abend)

**Topologie: beide Bots auf Timos Rechner.** Bot A ist der Musikbot (`Pr0degie/musicbot`,
Branch `dungeon_master` — `main` hat kein `/speak`). Damit bleibt es beim Loopback-Standard,
`DM_BRIDGE_HOST=127.0.0.1` und `DM_BRIDGE_SECRET` leer: die Bots teilen sich die Platte, DMbot
schickt nur den WAV-Pfad, nichts geht über Netz.

Beide Bots müssen **im selben Voice-Channel** sein, sonst sagt der DM nichts und die Bridge
antwortet `bridge /speak refused: HTTP 409 … Bot A is not in the voice channel`. Startreihenfolge:
Ollama → Bot A → DMbot.

> **Zweiter Lauf, getrennt gehostet** (Musikbot bei Tobi, DMbot bei Timo): funktioniert ohne
> Codeänderung, ist aber ein eigener Test — nicht mit dem Gate-Abend vermischen. DMbot schickt
> dann die WAV-**Bytes** statt des Pfades, Bot A muss auf `0.0.0.0` lauschen und
> `DM_BRIDGE_SECRET` auf beiden Seiten identisch sein. Vollständige Anleitung inklusive
> Tailscale und Firewall: `README.md`, Abschnitt „Split hosting". Erwartete Unterschiede: eine
> Handvoll MB pro Turn über die Leitung und entsprechend etwas späterer Sprechbeginn; `401` =
> Secret ungleich, `409` = Bot A nicht im Channel, Timeout = Firewall.

1. **`git pull`.** Die Kampagne selbst kommt mit (drei Dateien unter
   `data/adventures/debug-kampagne/`, seit `7463d5c` getrackt).
2. **`data/vectordb/rag.db` von Hand kopieren.** Die liegt **nicht** in git. Ohne sie fällt
   **G1** aus; der Boot sagt dann
   `no RAG store under data/vectordb/ — rule questions run without the book`.
   G10 ist davon nicht betroffen: der Ingest beim `!leave` legt den Store selbst an, in
   Sitzung 2 stehen die Session-Erinnerungen also auch ohne Regelbuch zur Verfügung.
3. **Ollama:** `ollama pull mistral-nemo` **und** `ollama pull bge-m3`. Ohne das
   Embedding-Modell bleibt Retrieval stumm, der Rest läuft.
4. **Eigenes Discord-Token.** `DISCORD_TOKEN_DMBOT` ist Pflicht und darf nicht Tobis Token
   sein — ein Token ist eine Verbindung. Im Developer-Portal müssen für die Bot-Anwendung
   **Message Content** und **Server Members** aktiv sein.
5. **`.env` auf Stand bringen.** Für diesen Lauf zwingend:

   ```dotenv
   DM_ADVENTURE=debug-kampagne     # NICHT chemical_burn — das liegt nicht in git
   DM_LOG_FILE=1                   # sonst gibt es hinterher keine debug.log
   DM_TRANSCRIPT_FILE=1
   ```

   Anlassen (Defaults, aber prüfen): `DM_SESSION_MEMORY=1` (0 killt G10),
   `DM_DEBUG_OVERLAY=1` (0 killt das 🧪-Panel), `DM_SCENE_MODE=verbunden` (`frei` killt G4),
   `DM_FLAG_CONFIRM=1`. Optional: `DM_DEBUG_CHANNEL=<id>` schiebt das 🧪-Panel in einen
   Nebenchannel — die id muss aus **demselben Server** stammen wie der Spielchannel.

   `SETUP.md` nennt an dieser Stelle noch `DM_ADVENTURE=chemical_burn`. Für den Testabend gilt
   die Zeile oben.

6. **Einmalig auf jedem Rechner, der am 2026-08-15 den Fehlstart hatte:** Damals schrieb der
   Debug-Abend seine Turns noch in die **Live**-Dateien des Channels. Für den Testabend ist
   das egal — die Sandbox greift jetzt —, aber vor der nächsten **echten** Sitzung muss es
   raus, sonst wandert der Fehlabend beim `!leave` ins Kampagnengedächtnis:

   ```
   uv run python tools/cleanup_15aug.py data/sessions/<channel-id>            # nur Bericht
   uv run python tools/cleanup_15aug.py data/sessions/<channel-id> --apply    # ausführen
   ```

   Sichert nach `history.jsonl.bak` und legt das Entfernte außerhalb des Session-Ordners ab.
   Mehrfaches Ausführen schadet nicht. Zeigt der Bericht ein Archiv vom 15.08. **ohne**
   `.debug` im Namen: nicht weitermachen, melden.

7. **`uv run dm-sync` auf beiden Rechnern, Ausgabe diffen.** Übereinstimmen müssen: die
   `repo`-Zeile (gleicher Commit), die drei `sha=`-Werte der `debug-kampagne`-Dateien, sowie
   `model=` und die `chunks:`-Zeile der rag.db. Die `.env`-Zeile vergleicht **nicht** die
   beiden Rechner, sondern nur die lokalen Key-Namen gegen `.env.example` — sie darf abweichen,
   solange keine Keys fehlen. `seeds` muss auf beiden `tracked seed files unmodified` sagen.

---

## 3. Sollbild beim Start

`start_dmbot.bat` (oder `uv run python -m dmbot`). Die Konsole muss diese Zeilen zeigen —
fehlt eine, wird nicht gespielt, sondern repariert:

```
Ollama preflight OK — http://127.0.0.1:11434 reachable, model 'mistral-nemo' available.
voice-stack preflight OK (versions + sink API match the verified set)
loaded system profile 'imperium_maledictum' (1d100, roll_under)
no channel sheet — loaded default party from …\data\sessions\_default\characters.json
loaded adventure 'Die Mitternachtsfracht' (6 scenes, 8 NPC statblocks)
🧪 loaded testplan.json (6 scenes) — debug overlay active
rulebook RAG store found — retrieval is on
```

**Abbruchkriterien:**

| Was fehlt | Zeile | Folge |
|---|---|---|
| Abenteuer | `no adventure.json under …\chemical_burn` — oder **gar keine** Abenteuer-Zeile | Kein Gate läuft |
| Testplan | die 🧪-Zeile fehlt (Sidecar weg oder `DM_DEBUG_OVERLAY=0`) | Kein Panel am Tisch |
| RAG | `no RAG store under data/vectordb/` | G1 tot (G10 läuft, der Store entsteht beim `!leave`) |
| Ollama-Modell | `Ollama is up … but model 'mistral-nemo' is not pulled` | Jeder DM-Turn scheitert |

Dann `!j` im Voice-Channel. Der Bot postet in dieser Reihenfolge: das 🧪-Panel, den
Beitritts-Text, `👥 **Party:**` mit drei Namen, und
`📖 **Abenteuer:** Die Mitternachtsfracht — Szene: **Die Zoll-Sakristei**`.

**Beim allerersten `!j` eines Debug-Laufs steht keine Zeile `loaded world state from …` da** —
`state.debug.json` existiert ja noch nicht. Das ist richtig so. Erscheint stattdessen
`scene pointer '…' is unknown to adventure 'debug-kampagne' — re-seeding to the start scene
'zollhaus'`, hat der Guard aus ADR 056 gegriffen: ebenfalls in Ordnung, einmal.

Eine ⚠-Warnung über eine Beispiel-Party wäre ein Abbruchgrund — sie erscheint aber nur, wenn
auch die Default-Party fehlt. Auf einem fremden Server lädt `DM_DEFAULT_PARTY=_default` die
echten drei Figuren stillschweigend; entscheidend ist, dass `👥 **Party:**` **Fridolin
Feuchtgebietheld / Gellicus Schulz / Rektalus Zerfickus** nennt.

Die Channel-id aus der Zeile `joined voice '<name>' (id=<channel id>)` notieren — alle
Datei-Pfade für Debrief und Reset hängen daran.

---

## 4. Der Abend, Szene für Szene

Das 🧪-Panel nennt pro Szene die Gates und einen Ein-Zeilen-Hinweis. Es wird an Ort und Stelle
überschrieben, es gibt also immer nur eins. Der DM sieht es nie.

**Vorgeschriebener Weg:** `zollhaus → schrein → pfandhalle → lagerhaus → siedehaus → pier_neun`.
Die Abkürzung `lagerhaus → pier_neun` existiert und ist nach dem Abhaken offen — wer sie nimmt,
überspringt `siedehaus` und damit die Ernte von G5, G7 und G3.

### Szene 1 — `zollhaus`: die Saaten legen

Drei Gates werden hier nur *gesät*, geerntet wird später.

```
!zeit
!uhr neu "Wachsamkeit des Kettenbunds" 6
!frist neu "Mitternachtssirene" +4h
!npc add Arno_Kessel
```

**Die Anführungszeichen bei `!uhr neu` sind Pflicht**, weil der Name mehrere Wörter hat. Ohne
sie stirbt das Kommando still: discord.py versucht „des" als Größe zu lesen, bricht ab, und der
Bot antwortet **gar nicht** — nur die Konsole zeigt `command error in …`. Es entsteht keine
Uhr, auch keine falsch benannte. Kommt keine Zeile `⏱ Neue Uhr: …` zurück, existiert sie nicht;
mit `!uhren` prüfen und wiederholen. (Bei `!frist neu` ist das Label einwortig, dort sind die
Anführungszeichen optional.)

Die id steht in der Antwort (`⏱ Neue Uhr: **…** (`<id>`) ○○○○○○ 0/6`) und wird später für
`!uhr tick <id>` gebraucht: notieren.

`!npc add Arno_Kessel` muss mit `*(Statblock aus dem Abenteuer)*` antworten. Nur dann wurde
sein `goal_de` mitgeladen — ohne das bleibt `!agenden` den ganzen Abend leer und G7 fällt aus.
Kessel ist in dieser Szene nicht anwesend; die frühe Registrierung ist Absicht.

### Szene 2 — `schrein`: Regelfrage und die erste Chekhov-Saat

Eine echte Regelfrage laut im Spiel stellen (der DM zieht sie passiv aus dem Regelbuch), dazu
`!rules <frage>` als Gegenprobe. Beweis ist das Embed **📖 Regelauskunft** mit dem Feld
*Quelle (Regeltexte)* und im Log `📚 rulebook:'…' (d=0.xx)` bzw. `📖 !rules '…' → …`.

Die glattgeschliffene Messingmünze **nur bemerken, nicht verfolgen** — sie ist die G9-Saat und
darf keine Erklärung bekommen.

> Der Psi-Beat dieser Szene gehört Fridolin, also Tobis Figur. Ohne ihn am Tisch geht die Probe
> per `!test Psi-Meisterschaft herausfordernd für Fridolin Feuchtgebietheld`. Der Name nach
> „für" muss der **volle Bogenname oder ein eingetragener Alias** sein (`Tobi`, `Pr0degie`) —
> ein bloßer Vorname wird nicht aufgelöst, und der Wurf fällt still auf ein rohes d100 ohne
> Fertigkeitswert zurück („kein hinterlegter Wert, vergleicht mit eurem Bogen").

### Szene 3 — `pfandhalle`: die Lüge und die zweite Saat

Bree Marlok fragt „In wessen Auftrag?". Dort **markant lügen** — eine falsche Identität, die
später wiedererkennbar ist. Alter Fenks schiefe Hymne registrieren, nicht nachfragen.

Der Beweis kommt erst beim Verlassen der Szene: `🧠 NPC-Gedächtnis: N neue Erinnerungen
(Szene 'pfandhalle')`. Die Extraktion läuft beim Szenenwechsel, nicht währenddessen.

### Szene 4 — `lagerhaus`: Kampf, und die einzige Stelle mit Reihenfolge-Zwang

Vier Gates, und **die Reihenfolge entscheidet**:

1. **`!npc add Lastenservitor_Ohm-3`** *(vor dem Kampf)*. Das ist der Schritt, den man am
   ehesten vergisst — und er scheitert **leise**: Ohne registrierten Gegner bietet ein Treffer
   trotzdem eine Ziel-Auswahl an (`💥 Treffer von **…** — wen trifft es?`), nur stehen darin
   ausschließlich die **eigenen Mitspieler**. Ein Klick verwundet dann einen Spielercharakter
   und verfälscht den G8-Nachweis. Steht Ohm-3 nicht in der Liste: abbrechen, `!npc add`
   nachholen, neu würfeln. Ohne die Registrierung kennt auch der Konsistenz-Wächter ihn
   später nicht — G6 fällt mit aus.
2. **Kämpfen.** Ohm-3 auf 0 Wunden bringen, selbst Wunden kassieren. Beweiszeile:
   `💥 … = N Wunden → …`. Lärm rechtfertigt einen Uhr-Tick.
3. **Erst jetzt: einen Wechsel nach `pier_neun` provozieren, solange der Verladebrief nicht
   abgehakt ist.** Das muss **im Spiel** passieren — die Gruppe redet sich zum Pier, der DM
   setzt den Ortsmarker. `!ort pier_neun` von Hand umgeht die Prüfung vollständig und zerstört
   den Beweis. Erwartete Logzeile:
   `🚫 Ausgang 'lagerhaus' → 'pier_neun' verriegelt — Bedingung 'verladebrief' nicht erledigt`
4. **Danach** den Verladebrief finden und abhaken (`!erledigt verladebrief` oder der
   ✅-Knopf). Ab da ist der Ausgang offen.

Für den Uhr-Tick gilt: G2 will einen **vom DM vorgeschlagenen** Tick
(`⏱ Tick vorgeschlagen: …` → Knopf → `⏱ Tick: … [bestätigt]`). Ein von Hand gesetzter
`!uhr tick <id>` funktioniert, loggt aber `clock tick: <id> → 1/6` und taucht im Debrief-Grep
**nicht** auf.

### Szene 5 — `siedehaus`: die Ernte

Kessel konfrontiert die Gruppe mit ihren eigenen Worten aus der Pfandhalle. Prüfen:

```
!npcmem "Bree Marlok"     ← die Lüge steht drin, mit wörtlichem Zitat
!npcmem "Arno Kessel"     ← dieselbe Lüge als Hörensagen (Gossip über die Fraktion)
!agenden                  ← Kessels Ziel plus sein erster Offscreen-Schritt
!zeit +2h                 ← Richtung Mitternachtssirene
```

**Die Anführungszeichen sind Pflicht.** `!npcmem Bree_Marlok` schlägt fehl — der NSC heißt im
Weltzustand „Bree Marlok" mit Leerzeichen, und nur `!npc add` versteht Unterstriche. Dasselbe
gilt für `!agenda`, `!damage` und `!heal`.

`!zeit +2h` von Hand loggt `time advance (manual): …` statt `🕐 Zeitfortschritt vorgeschlagen`.
Die Fristen-Hälfte von G3 (das Verstreichen) zählt trotzdem — sie hängt nicht am Marker.

### Szene 6 — `pier_neun`: Finale, Konsistenz, Neustart

1. **`!sprechmodus nahtlos`** — zwingend vor der Ohm-3-Probe. Nur der Batch-Pfad kann eine
   Antwort verwerfen und neu erzeugen; im Streaming ist das Audio schon draußen und der
   Wächter kann nur noch protokollieren.
2. Die Gruppe soll den **toten** Ohm-3 gezielt ansprechen. Beweis:
   `[consistency] violated (dead:Lastenservitor Ohm-3) — regenerating once`
3. Die Mitternachtsfrist verstreichen lassen. Beweis:
   `⏳ Frist '…' (…) verstrichen — Konsequenz-Hinweis für den nächsten Turn eingereiht`
4. **Neustart-Test (G8):** Bot hart beenden → neu starten → **beide Bots zurück in den
   Voice-Channel** → **`!j`**. Erst dann `!wrap`.

   Das `!j` ist nicht optional. Ohne aktive Sitzung findet `!wrap` keinen Weltzustand, gibt
   `Noch nichts passiert, das sich zusammenfassen ließe.` zurück, und die 🧵-Zeile für G9
   kommt nie. Nach dem `!j` müssen zwei Zeilen dastehen:

   ```
   loaded world state from …\state.debug.json          ← .debug = die Sandbox hat gehalten
   restored N conversation turns from the autosave
   ```
5. `!wrap` → Beweis `🧵 Chekhov-Liste: N neue Fäden, M aufgelöst` und der Post
   `📜 **Was bisher geschah:**`.
6. **`!leave`** — und das Fenster offen lassen, bis diese Zeile erscheint:

   ```
   🗂 session memory: ingested history.<stamp>.debug.jsonl (N chunks)
   ```

   Der Ingest hängt am Leave-Pfad und läuft im Hintergrund. Wer den Bot vorher hart beendet,
   hat für G10 in Sitzung 2 keine Daten. Ein harter Kill rotiert das Journal nicht.

---

## 5. Sitzung 2 (kurz, 15 Minuten) — G9 und G10

Keine neuen Szenen, keine neuen Saaten. Bot starten, `!j`.

- **G8, zweite Hälfte:** der Post `📜 **Was bisher geschah:**` beim `!j` muss den Abend
  korrekt zusammenfassen.
- **G9:** die beiden Saaten als Wiedererkennen zurückspielen lassen — Kessels Münz-Gegenstück
  und das Flüstern, das Fenks Hymne ist. Spielt der DM sie auf, ist G9 zu.
- **G10, zwei Sonden im Gespräch:**
  1. *semantisch:* „Was war das damals im Schrein mit der Münze?" — natürliche Sprache, kein
     Eigenname.
  2. *wörtlich:* „Was hat **Fenk** in der Pfandhalle gesungen?" — der Eigenname muss **mitten
     im Satz** stehen; satzeinleitende Namen verlieren ihr Signal.

  Beweis pro Treffer: `🗂 Szene 'schrein'/<stamp> (FTS)` bzw. `(d=0.xx)`.

Die Zeile `🗂 session memory: catch-up — N rotated journal(s) pending` beim `!j` ist **kein**
Pflichtbeweis: sie erscheint nur, wenn der Ingest aus Sitzung 1 nicht durchlief.

---

## 6. Übergabe

Nichts davon reist über git — `*.log` und `data/sessions/<id>/` sind ignoriert. Also von Hand,
**bevor der Bot noch einmal gestartet wird**: `logs/terminal.log` wird bei jedem Start
überschrieben.

| Datei | Warum |
|---|---|
| `logs/debug.log` | die Beweiszeilen, Basis aller Debrief-Greps |
| `logs/transcript.log` | Gespräch mit Zeitstempeln — die Qualitätsbewertung |
| `logs/terminal.log` | Konsolen-Spiegel inkl. Boot-Sequenz |
| `data/sessions/<id>/history.<stamp>.debug.jsonl` | das rotierte Journal, Quelle fürs Live-Golden |

Dazu formlos: was am Tisch genervt hat. Das ist der wertvollste Teil — die Gate-Beweise sagen,
ob eine Funktion *läuft*, nicht ob sie sich gut anfühlt.

Das Runbook hat für den Debrief einen fertigen Grep-Block (ein Griff pro Gate, leerer Output =
Gate nicht ausgelöst): [Debrief in 5 Minuten](debug-campaign-runbook.md).

---

## 7. Was wir danach tun

1. **Log in eine `/playtest-triage`-Runde.** Jede Beschwerde bekommt eine Grundursache; die
   Pipeline wird vor dem Modell verdächtigt, ein Code-Guard vor einem Prompt-Hinweis. Pro
   Runde ein Commit, Suite grün.
2. **`progress.md`:** die `VERIFY EVIDENCE`-Felder von Phase 9 und Phase 10 mit den echten
   Logzeilen füllen, die Zeile der offenen Live-Gates kürzen, den Last-session-Block schreiben
   — mit Rotation, die Datei steht bei genau 400 Zeilen.
3. **Frisches Live-Golden ziehen.** Das rotierte Journal nach `tests/golden/live_<datum>.jsonl`
   kopieren, auf einen `{"kind": "session"}`-Header plus eine Handvoll interessanter Turns
   kürzen, `uv run dm-eval tests/golden/live_<datum>.jsonl` muss sofort Exit 0 sein. Ein
   Golden aus der Debug-Kampagne ist committierbar, weil das Abenteuer im Repo liegt.
4. **ADR nur, wenn wirklich abgewogen wurde.** Ein reiner Gate-Nachweis geht in
   `VERIFY EVIDENCE` und ins Decision-Log, nicht in einen ADR. Nächste freie Nummer: 057.
5. **Setup-Pannen werden Preflights.** Was an Timos Rechner schiefging, wird zu einer
   Boot-Prüfung oder einer `dm-sync`-Zeile, nicht nur zu einem Einzelfix.
6. **Gates, die zufielen, heben die WIP-Sperre** — erst danach dürfen wieder Feature-Runden
   starten, die ein neues Live-Gate öffnen.

Und: G9 und G10 bleiben offen, bis die zweite Sitzung gelaufen ist. Nicht vorher abhaken.

---

## 8. Wenn etwas nicht funktioniert

| Symptom | Ursache | Zeile / Griff |
|---|---|---|
| DM antwortet als Text, sagt nichts | Bot A nicht im Channel | `bridge /speak refused: HTTP 409` |
| DM antwortet gar nicht | Ollama weg oder Modell fehlt | `Ollama not reachable at …` |
| Kein 🧪-Panel | Sidecar fehlt oder `DM_DEBUG_OVERLAY=0` | die 🧪-Boot-Zeile fehlt |
| Keine Szenenkarte | falscher `DM_ADVENTURE`-Wert | `no adventure.json under …` |
| `!rules` sagt „Kein RAG-Store" | rag.db nicht kopiert | `no RAG store under data/vectordb/` |
| Kommando antwortet „Keine aktive Sitzung" | `!j` vergessen | — |
| `!npcmem`/`!agenda`/`!damage` findet den NSC nicht | Unterstrich statt Anführungszeichen | `Unbekannter NSC …` |
| Kommando bleibt ohne jede Antwort | Argument falsch geparst (z. B. `!uhr neu` ohne Anführungszeichen) | Konsole: `command error in …` |
| Ziel-Auswahl zeigt nur Mitspieler | Gegner nicht per `!npc add` registriert | keine — abbrechen, nachholen |
| G4 zeigt keine Verriegelung | `!ortmodus frei`, oder `!ort` von Hand benutzt | `🚫 Ausgang …` fehlt |
| Nichts wird transkribiert | Mikrofon-Knopf zu, oder pausiert | `!vstatus` |

Pausieren geht mit **Esc** im DMbot-Terminal oder dem ⏸-Knopf. Ein `!pause`-Kommando gibt es
nicht. Beenden: **zweimal** Strg+C.

---

Nach dem Abend zurücksetzen: [Reset für einen Re-Run](debug-campaign-runbook.md) — dort steht
auch die Warnung, dass alles **ohne** `.debug` im Namen der echten Kampagne gehört.
