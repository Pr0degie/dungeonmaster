# Testabend: Ablauf, Prüfpunkte, Nacharbeit

Der zeitliche Faden eines Testabends mit der Debug-Kampagne „Die Mitternachtsfracht" —
von der Vorbereitung am fremden Rechner bis zu dem, was danach ins Repo zurückfließt.

Die Szenen-Referenz (welche Szene welches Gate auslöst, welche Logzeile es beweist, die
Debrief-Greps, der Reset) steht im [Runbook](debug-campaign-runbook.md) und wird hier nicht
wiederholt. Dieses Dokument beantwortet die andere Hälfte: **in welcher Reihenfolge, woran
man am Bildschirm erkennt, dass es geklappt hat, und was danach passiert.**

> ⏸ **Stand 2026-10-06: §0–§8 beschreiben den geparkten Nemo-Abend** (zehn Gates plus die
> sieben aus D107–D115; ADR 061, Nachtrag). **Der nächste Abend ist der Phase-11-Abend und
> läuft nach §9 ganz unten.** §2 (Topologie), §6 (Übergabe) und §8 (Fehlersuche) gelten dort
> weiter, soweit §9 nichts anderes sagt.

Die Auflösung der Kampagne steht hier bewusst nicht — wer mitspielt, kann das Dokument lesen.

---

## 0. Was sich seit dem letzten Abend geändert hat (D107–D114)

Der Lauf vom 22.08. blieb 22 Züge in Szene eins hängen. Fünf Dinge sind seitdem anders, und
alle fünf ändern, worauf du am Bildschirm achtest:

- **Der Ortswechsel passiert von selbst.** Ein Klassifikator prüft nach jedem Zug, ob die Gruppe
  einen der echten Ausgänge betreten hat, und wechselt sofort — mit einem ↩-Knopf, der den
  Wechsel eine Minute lang zurücknimmt. Zusätzlich schiebt der Flag-Zwang weiter, sobald alle
  Gelegenheiten einer Szene abgehakt sind. `!ort` bleibt dein Notnagel und darf mehr als die
  Automatik: es setzt jede Szene, auch eine unerreichbare.
- **Ein abgelehnter Wechsel ist sichtbar** — aber nur, wenn `DM_DEBUG_CHANNEL` gesetzt ist.
  Ohne den Kanal steht er nur im Log. **Vor dem Abend setzen.**
- **Uhr und Fristen kommen aus dem Abenteuer** und laufen pro Zug weiter. Nichts von Hand
  anlegen (siehe Szene 1).
- **Harte Fakten.** Übergibt ein NSC etwas, nimmt die Gruppe einen Auftrag an oder gibt jemand
  ein Versprechen, landet das im Weltzustand und steht ab dann in jedem Prompt. `!fakt` listet
  sie, `!fakt weg <Text>` nimmt einen falschen zurück — **das ist der Knopf, den du brauchst,
  wenn der Klassifikator Unsinn einträgt.**
- **Ein Spieler-Panel im Chat** zeigt Szene, Auftrag, Uhrzeit, Frist und was hier noch offen
  ist. Es aktualisiert sich selbst und verankert sich am Ende des Kanals neu.

Dazu vier Nachzügler, die den gesprochenen Text und die Würfel betreffen:

- **Ein Würfelknopf je ansagender Figur (D111).** Bisher wurde nur die letzte Pufferzeile eines
  Zuges geprüft — sagten zwei Spieler etwas an, verschwand die eine Ansage spurlos. Jetzt bekommt
  jede Figur ihren eigenen, namentlich beschrifteten Knopf. Die Figur kommt vom **Sprecher**, nicht
  vom Klickenden: du darfst den Knopf eines abwesenden Mitspielers drücken, ohne seine Probe zu
  stehlen. Erwartete Logzeile: `🎲 router: Gellicus Schulz — '…' → Überreden (Herausfordernd)`.
- **Meta-Sätze werden nicht mehr vorgelesen (D112).** Entschuldigungen im Sie-Register, „In diesem
  Fall würde ich als Spielleitung antworten:" und das „Damit übergibt er wieder an die Gruppe" am
  Ende. War eine Antwort *nur* Meta, sagt der DM stattdessen eine neutrale Zeile — hörst du
  „Ich habe das nicht mitbekommen — sagt es noch einmal.", hat der Filter eine ganze Antwort
  kassiert; das ist ein Befund fürs Debriefing, kein Bedienfehler.
- **Der DM spricht nur noch NSCs (D113).** Legt er einer Spielerfigur wörtliche Rede in den Mund,
  fliegt der Satz. Handlungen von Spielerfiguren bleiben absichtlich stehen — wenn euch *das*
  stört, ist es ein neuer Befund, kein Bug.
- **Whisper-Abspänne landen nicht mehr im Puffer (D114).** „Das war's für heute, tschüss" wird
  inhaltlich geblockt, einzelne Floskeln überleben. Sichtbar als
  `🚫 Whisper-Halluzination verworfen (Name): …` — die Zeile ist der Beweis, dass der Filter greift.

Zwei Einstellungen vorher prüfen: `DM_DEBUG_CHANNEL` (sonst sind Ablehnungen unsichtbar) und
`OLLAMA_NUM_PARALLEL` ≥ 2 — sonst serialisiert Ollama die zwei Klassifikatoren, die auf einer
Zugnaht laufen, und der zweite kippt in seinen Timeout, statt zu antworten.

Der Sprechmodus-Vergleich aus [speech-mode-comparison.md](speech-mode-comparison.md) gehört an
den Anfang des Abends: er dauert fünf Minuten und entscheidet, wie der ganze Rest klingt.

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
echten vier Figuren stillschweigend; entscheidend ist, dass `👥 **Party:**` **Fridolin
Feuchtgebietheld / Gellicus Schulz / Rektalus Zerfickus / Rene Redo** nennt.

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
!zeit                     ← muss „Tag 1, 21:00 (Abend)" zeigen
!uhren                    ← beide Uhren müssen schon da sein
!fristen                  ← die Mitternachtssirene muss schon da sein
!npc add Arno_Kessel
```

**Uhr und Frist NICHT mehr von Hand anlegen (seit D107 / ADR 059).** Die Kampagne bringt
Startzeit, Mitternachtsfrist und beide Uhren selbst mit; sie werden beim Sitzungsstart aus
`adventure.json` gesetzt. Ein `!uhr neu "Wachsamkeit des Kettenbunds" 6` würde jetzt eine
**zweite** Uhr gleichen Namens erzeugen.

Prüfen statt anlegen: `!zeit` muss `Tag 1, 21:00 (Abend)` zeigen — steht dort noch
`Tag 1, 08:00 (Morgen)`, wurde das Abenteuer nicht geladen oder die Sitzung stammt aus einer
älteren Datei, dann ist der ganze Zeitdruck des Abends tot. `!uhren` muss die Wachsamkeit des
Kettenbunds und die Verladung zeigen, `!fristen` die Mitternachtssirene mit Restzeit. Die ids
für spätere `!uhr tick <id>` stehen in der Antwort von `!uhren`.

Die Ingame-Uhr läuft ab jetzt **pro Zug** von selbst weiter, plus einen größeren Sprung bei
jedem Ortswechsel. Du musst Zeit nicht mehr schieben, damit die Frist näher rückt.

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
!zeit                     ← Kontrolle: die Uhr läuft pro Zug von selbst
```

**Die Anführungszeichen sind Pflicht.** `!npcmem Bree_Marlok` schlägt fehl — der NSC heißt im
Weltzustand „Bree Marlok" mit Leerzeichen, und nur `!npc add` versteht Unterstriche. Dasselbe
gilt für `!agenda`, `!damage` und `!heal`.

Zeit von Hand zu schieben ist seit D107 nur noch der Notnagel: die Uhr läuft pro Zug und pro
Ortswechsel automatisch, und die Frist wurde beim Start aus dem Abenteuer gesetzt. Wenn ihr im
Zeitplan zurückliegt und das Finale trotzdem sehen wollt, ist `!zeit +1h` weiterhin erlaubt —
es loggt `time advance (manual): …`. Die Fristen-Hälfte von G3 (das Verstreichen) zählt so oder
so, sie hing nie am Marker.

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

---

## 9. Phase-11-Abend — Claude-Backend, isoliert (Ablaufblatt)

> **Kurzfassung zum Danebenlegen am Abend:** [phase-11-abend.md](phase-11-abend.md) — was geprüft
> wird, wie, woran man den Erfolg sieht, mit Protokoll zum Ausfüllen.

**Ein Gate, eine Variable.** Der Abend beantwortet eine Frage: klingt der DM mit Opus so viel
besser, dass sich der Weg lohnt? Alles, was nicht das Modell ist, bleibt gleich oder ist aus.
Die 17 alten Gates sind geparkt und werden an diesem Abend **nicht** geprüft. Grundlage:
[PRD „Live gate"](plans/claude-backend.md), Punkte 0–9; wo PRD und ADR 061 sich widersprechen,
gilt der ADR.

**Der Bot läuft an diesem Abend auf Tobis Rechner**, nicht bei Timo. Mit dem Claude-Backend
benutzt der Bot Tobis Abo-Login, und der darf auf keinem fremden Rechner liegen. Bot A kann
auf demselben Rechner laufen (Loopback wie in §2) oder getrennt bleiben.

Stand vor dem Abend: Code, Doku und Review sind fertig, 1203 Tests grün. Live geprüft ist nur
der Boot-Preflight (Opus und Haiku antworten, ein falscher Modellname fällt auf) und ein kurzer
Haiku-Smoke (Text, Schema-Antwort, Stream mit Verlauf, Schnitt an der Ausgabegrenze). **Opus mit vollem Systemprompt, ein ganzer Zug mit Stimme und alles unter 9.4 sind
live unverifiziert.**

### 9.1 Einmalig vorher

1. Claude Code nativ installieren und einloggen: [SETUP.md B10](../SETUP.md). Prüfen in `cmd`:
   `claude -p "hi"` antwortet, `echo %ANTHROPIC_API_KEY%` gibt den Namen zurück (= nicht gesetzt).
2. Ollama läuft weiter und hat `mistral-nemo` und `bge-m3` (Rückfall und Embeddings).
3. Sandbox der Debug-Kampagne leeren, damit kein alter Stand mitspielt
   ([Runbook „Reset für einen Re-Run"](debug-campaign-runbook.md)): in
   `data/sessions/<channel-id>/` die vier `.debug`-Dateien und `history.*.debug.jsonl` löschen,
   dann `uv run python -m dmbot.rag.ingest_session --wipe-debug <channel-id>`. **Nichts ohne
   `.debug` im Namen anfassen.**
4. Verbrauchsanzeige auf claude.ai öffnen und den Stand notieren (Gate-Punkt 6).

### 9.2 `.env` für den Abend

Nur diese Zeilen weichen vom Normalbetrieb ab. Alles andere bleibt, wie es ist.

```
# das Backend — die eine Variable
DM_LLM_BACKEND=claude
CLAUDE_MODEL_NARRATION=opus
CLAUDE_MODEL_AUX=haiku
CLAUDE_MODEL_FALLBACK=
CLAUDE_NUM_CTX=24576
CLAUDE_CLI_PATH=
CLAUDE_ALLOW_API_KEY=0
DM_LLM_FAILOVER_COOLDOWN_S=600

# Kampagne, Stimme, Logs
DM_ADVENTURE=debug-kampagne
TTS_DEVICE=cuda
DM_LOG_FILE=1

# optionale Schichten AUS
DM_CONSISTENCY_GUARD=0
DM_NPC_MEMORY=0
DM_DEBUG_OVERLAY=0
DM_CLOCKS=0

# Marker-Sonde (Gate-Punkt 7b): ERLEDIGT wird ohne Bestätigungsklick angewendet
DM_FLAG_CONFIRM=0
```

Bewusst auf Default lassen (nicht anfassen): `DM_ROLL_ROUTER=1`, `DM_SCENE_ROUTER=1`,
`DM_FACT_ROUTER=1`, `DM_SCENE_FLAG_GATE=1`, `DM_PLAYER_PANEL=1`, `DM_STREAMING=1`,
`DM_SPEECH_MODE=stream`, `DM_NUM_PREDICT=220`, `DM_AUTORECAP=1`, `DM_SESSION_MEMORY=1`.
Die drei Klassifikatoren müssen an bleiben, sonst lässt sich Gate-Punkt 3 nicht prüfen.

`ANTHROPIC_API_KEY` darf weder in `.env` noch in der Windows-Umgebung stehen.

### 9.3 Die vier Schichten: was sie wirklich abschaltet

Das PRD sagt „Uhren, Agenden, Fäden und Overlay aus, über ihre Schalter oder `!automatik`".
Der Code hat dafür **nicht vier eigene Schalter**; die Uhren haben seit D118 einen
(`DM_CLOCKS`). So sieht es tatsächlich aus (Namen aus `dmbot/config.py` und den Cogs):

| Schicht | `.env`-Schalter | Live-Befehl | Was am Abend zu tun ist |
|---|---|---|---|
| **Uhren** (ADR 047) | `DM_CLOCKS=0` | **keiner nötig** — `!uhr …` und `!uhren` antworten mit „Uhren sind abgeschaltet" | Nichts. Die zwei Uhren der Debug-Kampagne werden gar nicht erst angelegt, im Prompt und im Druck-Panel steht keine Uhr, ein `<<UHR>>` wird aus dem Sprechtext entfernt und ignoriert. Die Bootzeile `⏱ Uhren aus (DM_CLOCKS=0)` bestätigt es. Fristen und Spielzeit laufen weiter. |
| **Agenden** (ADR 049) | **kein eigener** — hängt an `DM_NPC_MEMORY=0` | `!agenda "<NSC>" weg`, Kontrolle mit `!agenden` | Nichts. Die Debug-Kampagne setzt keine NSC-Ziele, und mit `DM_NPC_MEMORY=0` läuft der Extraktor nicht, der Agenda-Schritte schreibt. Am Abend kein `!agenda` benutzen. |
| **Fäden** (ADR 050) | **kein eigener** — hängt an `DM_NPC_MEMORY=0` | `!faden weg <id>`, Kontrolle mit `!fäden` | Nichts, wenn die Sandbox geleert ist (9.1 Punkt 3). Die Extraktion läuft nur im `!wrap` und nur mit NPC-Gedächtnis; mit `DM_NPC_MEMORY=0` entsteht kein neuer Faden. `!fäden` muss nach `!j` leer sein. |
| **Overlay** 🧪 (ADR 052) | `DM_DEBUG_OVERLAY=0` | **keiner** | Nur per `.env`. Die 🧪-Bootzeile und das Panel fehlen dann, das ist an diesem Abend richtig. Die Sandbox (`state.debug.json`) hängt **nicht** am Overlay, sondern an der `testplan.json` neben dem Abenteuer, und bleibt aktiv. |

Dazu die zwei Schichten, die das PRD namentlich nennt und die einen echten Schalter haben:
`DM_CONSISTENCY_GUARD=0` (Konsistenz-Wächter) und `DM_NPC_MEMORY=0` (NPC-Gedächtnis, und damit
auch Agenda-Schritte und Faden-Extraktion). Beide wirken erst nach einem Neustart.

**`!automatik` schaltet keine der vier.** Es kennt genau fünf Namen: `szene`, `flaggen`,
`fakten`, `zeit`, `panel` (Defaults `DM_SCENE_ROUTER`, `DM_SCENE_FLAG_GATE`, `DM_FACT_ROUTER`,
`DM_TURN_TIME_ADVANCE`, `DM_PLAYER_PANEL`). Am Abend bleiben alle fünf **an**. Bares `!automatik`
zeigt den Stand; das ist der Notgriff, falls einer der Klassifikatoren am Tisch stört
(`!automatik fakten aus`).

Nicht abgeschaltet, weil das PRD „alles andere Default" sagt: die Spielzeit pro Zug und die
Frist `mitternachtssirene` aus dem Abenteuer. Verstreicht die Frist, bekommt der DM einen
Regie-Hinweis. Wer das für den Abend nicht will: `!frist weg mitternachtssirene` — dann aber im
Protokoll vermerken.

**Live-Befehle des Abends, getrennt von der `.env`:**

| Wann | Befehl | Wozu |
|---|---|---|
| nach `!j` | `!uhren` | Kontrolle: antwortet „Uhren sind abgeschaltet (`DM_CLOCKS=0`)" |
| nach `!j` | `!fäden` · `!automatik` · `!backend` | Kontrolle: keine Fäden, fünf Schalter an, Primär Claude und nicht degradiert |
| Gate 5 | `!backend claude` | nach dem erzwungenen Failover sofort zurück auf Opus |
| Notfall | `!backend ollama` | den Rest des Abends lokal spielen |
| Notfall | `!backend auto` | wieder dem Failover folgen |

### 9.4 Sollbild beim Start

```
Ollama preflight OK — http://127.0.0.1:11434 reachable, model 'mistral-nemo' available.
Claude preflight OK — narration opus: OK · aux haiku: OK (CLI 2.1.x (Claude Code)).
loaded adventure 'Die Mitternachtsfracht' (6 scenes, 8 NPC statblocks)
rulebook RAG store found — retrieval is on
```

Die 🧪-Zeile fehlt (Overlay aus). Steht statt der zweiten Zeile `Claude preflight FAILED`, wird
nicht gespielt, sondern repariert: die Zeile nennt, welche Stufe fehlschlug und warum
([conventions.md „LLM not answering on the Claude backend?"](conventions.md)). Der Bot würde
trotzdem starten und aus Nemo antworten — das wäre dann aber der falsche Abend.

### 9.5 Gate-Punkte 0–9

Abhaken und die Beweiszeile aus `logs/debug.log` dazulegen. Reihenfolge wie hier; 5 und 7 ändern
die `.env` und brauchen je einen Neustart, deshalb stehen sie hinten.

- [ ] **0 — Aufbau.** `.env` wie 9.2, Sandbox leer, Uhren per `DM_CLOCKS=0` aus (9.3). `!automatik` zeigt fünf
      Schalter an, `!fäden` ist leer, `!backend` nennt Claude als Primär.
- [ ] **1 — Boot.** Beide Preflight-Zeilen wie in 9.4. Während des Spiels `nvidia-smi`: XTTS liegt
      auf der GPU, `ollama ps` zeigt **kein** `mistral-nemo` (nur `bge-m3`).
- [ ] **2 — Fünf Züge.** `!join` → `!start` → fünf gesprochene Spielerzüge. Fünf `[latency]`-Zeilen
      sichern (`first_audio`, `spawn`, `ctx`, `cache`). Daneben die Nemo-Zeilen vom 22.08. legen.
- [ ] **3 — Klassifikatoren auf Haiku.** Ein Würfelknopf vom Router (`🎲 router: <Figur> — '…' → …`),
      ein automatischer Szenenwechsel (`📖 Auto-Szenenwechsel vorgeschlagen → …`), ein harter
      Fakt (`📌 Fakt aufgenommen (…)`).
- [ ] **4 — Recap.** `!wrap` → `📜 **Was bisher geschah:**` auf Deutsch, gespeichert
      (`recap.debug.md` in der Sitzungsmappe).
- [ ] **5 — Failover.** Bot stoppen, `CLAUDE_MODEL_NARRATION=opus-gibts-nicht`, starten: die
      Bootzeile meldet `narration opus-gibts-nicht: FAILED · aux haiku: OK`. Ein Zug → **genau
      eine** ⚠-Zeile im Chat, Nemo antwortet (der erste lokale Zug lädt das Modell, 10–15 s).
      Zweiter Zug: keine zweite ⚠-Zeile. Dann `.env` zurück auf `opus`, Neustart, ein Zug auf Opus.
      *Variante ohne Neustart:* Netz kurz trennen, ein Zug, Netz wieder an, `!backend claude`.
- [ ] **6 — Verbrauch.** Stand der Verbrauchsanzeige auf claude.ai nach dem Abend, Differenz zum
      Wert aus 9.1 notieren. Steht im Log eine `Claude rate limit warning`-Zeile, mit ablegen.
- [ ] **7 — Marker-Sonde für Phase 12.** Je ein paar Züge:
      - **a)** `DM_ROLL_ROUTER=0` (Neustart). Setzt Opus von selbst ein korrektes `<<TEST …>>`, wo
        eine Probe fällig ist? Ja/Nein und den rohen Marker aus der Zeile `🪵 LLM roh` notieren.
      - **b)** `DM_FLAG_CONFIRM=0` ist schon gesetzt. Erledigt die Gruppe sichtbar eine Gelegenheit
        der Szenenkarte: kommt ein korrektes `<<ERLEDIGT id>>` und wird es angewendet? Ja/Nein
        und den rohen Marker notieren (`🪵 LLM roh`, dazu `✅ Erledigt …` oder `🚫 ERLEDIGT … abgelehnt`).
- [ ] **8 — Abschnitt-Zähler.** Anteil der abgeschnittenen Erzählzüge, siehe Messung C. Ist das
      mehr als eine seltene Ausnahme, ist Punkt 7 nicht aussagekräftig — dann stand der Marker
      dort, wo die Grenze schneidet.
- [ ] **9 — Das Urteil des Tisches.** Von jedem Spieler drei Sätze zur Erzählqualität, wörtlich,
      ins Befundprotokoll. **Das ist das eigentliche Gate.**

### 9.6 Drei Messungen

Alle drei lassen sich nach dem Abend aus `logs/debug.log` ziehen. Am Tisch nichts stoppen.

**A — Ein Opus-Zug mit vollem Systemprompt: `spawn` und `first_audio`.**
Quelle ist die `[latency]`-Zeile, die jeder Erzählzug schreibt:

```
[latency] turn=3 stream stt=…ms trigger→llm_done=…ms ctx=…/24576 gen=… spawn=…ms cache=… chars=… first_audio=…ms tts=…ms …
```

`spawn` ist die Zeit vom Aufruf bis zur ersten Nachricht der CLI, `first_audio` die Zeit vom
Auslöser bis zum ersten Ton, `cache` die Prompt-Tokens aus dem Cache. Zwei Zeilen notieren: den
**ersten** Spielerzug nach `!start` (kalter Cache) und einen aus der Mitte (warmer Cache). Der
Systemprompt ist dann echt voll: Persona, Szenenkarte, Weltzustand, Regelwerk-Treffer.
Bisher gemessen ist nur Haiku mit einem Einzeiler (Spawn rund 0,7 s).

```
Select-String -Path logs\debug.log -Pattern '\[latency\]' | Select-Object -First 8
```

**B — Klassifikator-Latenz auf Haiku: Zeit bis zum Würfelknopf.**
Jeder Klassifikator-Aufruf schreibt eine eigene Zeile mit seiner Dauer in Millisekunden und dem
Ergebnis:

```
[classifier] roll 1840ms → Überreden (Herausfordernd)
[classifier] roll 1510ms → no test
[classifier] scene 2100ms → schrein
[classifier] fact 1730ms → none
```

`roll` ist die Zeit bis zum Würfelknopf: vom Start des Routers (die Erzählung ist dann fertig
erzeugt, der DM spricht meist noch) bis zum Urteil. Die Zahl enthält auf Claude den Start der
CLI. `scene` und `fact` laufen nach dem Zug nebeneinander. Steht hinter dem Pfeil `failed`,
`timeout` oder ein anderer Fehlername, ging das Urteil verloren. Drei `roll`-Zeilen mit
Würfelknopf notieren, alle drei Werte, nicht den Mittelwert.

```
Select-String -Path logs\debug.log -Pattern '\[classifier\]'
```

Diese Zahl entscheidet in Phase 12, ob der Router früher im Zug starten muss. Züge nach einem
Failover messen Nemo, nicht Haiku — die Züge aus Gate-Punkt 5 nicht mitzählen.

**C — Anteil ✂ an allen Erzählzügen.**
Jeder Erzählzug schreibt genau eine `[latency]`-Zeile; ein an der Ausgabegrenze abgeschnittener
Zug trägt dort `cut` und zusätzlich die Warnung `✂ Antwort an der Ausgabegrenze abgeschnitten`.

```
$alle = (Select-String -Path logs\debug.log -Pattern '\[latency\]').Count
$cut  = (Select-String -Path logs\debug.log -Pattern '\[latency\].* cut ').Count
"$cut von $alle"
```

Beide Zahlen notieren, nicht nur den Quotienten. Züge, die auf Nemo liefen (nach einem Failover),
tragen nie `cut` — die Züge aus Gate-Punkt 5 deshalb vorher abziehen.

### 9.7 Bekannte Risiken dieses Abends

- **`[latency]` nach einem Failover.** Solange der Rückfall aktiv ist, teilen sich auf dem
  Ollama-Pfad Erzählung und Klassifikatoren wie bisher einen Statistik-Platz. Eine
  `[latency]`-Zeile aus dieser Zeit kann die Zahlen eines Klassifikators zeigen. Auf dem
  Claude-Pfad ist das seit dieser Runde getrennt. Für die Messungen nur Züge auf Opus verwenden.
- **Zwei Prosa-Aufrufe gleichzeitig** (ein Erzählzug und ein Auto-Recap) teilen sich weiterhin
  einen Platz, auf beiden Backends. Selten; betrifft höchstens eine `[latency]`-Zeile.
- **Die CLI läuft nach einem Abbruch bis zu fünf Sekunden nach** (Pause, Sprecher-Etikett,
  Schnitt an der Ausgabegrenze). Der Zug wartet nicht darauf; im Task-Manager können kurz
  mehrere `claude.exe` stehen.
- **Erster Nemo-Zug nach einem Failover ist langsam** (Modell wird geladen). Kein Fehler.
- **`spawn` enthält einen Versionsaufruf.** Das SDK ruft vor jedem Start `claude -v` auf; die
  Zeit steckt in `spawn=`. Nichts ändern, nur beim Lesen der Zahl wissen.
- **Klassifikator-Timeouts dauern auf Claude etwa 5 s länger** als die eingestellten 20 s (das
  SDK wartet beim Abbruch auf das Ende der CLI). Eine Zeile `scene-router: no verdict within
  20s` oder `fact-router: no verdict within …` gehört ins Protokoll.
- **Etikett im gesprochenen Text.** Beginnt eine Antwort hörbar mit „Spielleitung“ oder steht
  „Spieler“ mitten im Satz, hat Opus das Verlaufsformat nachgeahmt und die Etikett-Wächter
  haben es nicht erwischt. Zug und Uhrzeit notieren; das ist ein Befund für Phase 12.
- **Temperatur wirkt nicht.** `DM_INTRO_TEMPERATURE` ist auf Claude ohne Wirkung; im Log steht
  dazu einmal eine Warnung.

### 9.8 Danach

Übergabe wie §6 (`logs/debug.log`, `logs/transcript.log`, `logs/terminal.log`, das rotierte
`history.<stamp>.debug.jsonl`). Dann in der nächsten Sitzung: Befunde in `progress.md` (Phase 11
`VERIFY EVIDENCE`), ADR 061 auf „Accepted" oder mit Begründung zurück, die 17 geparkten Gates
neu sichten, und erst danach das PRD für Phase 12 — die drei Messungen und die Marker-Sonde sind
dessen Eingabe.
