# 10 · Warum so? Die wichtigsten Entscheidungen in Kurzform

Die Kapitel 1 bis 9 beschreiben, *wie* der Bot gebaut ist. Dieses Kapitel sammelt das
*Warum*. Im Repo stehen dafür 67 ADRs unter `docs/decisions/` und 26 Lektionen unter
`docs/lessons/`. Niemand muss die alle lesen. Hier stehen die, ohne die sich der Aufbau nicht
erklären lässt, jeweils als Problem, Entscheidung und Folge.

## Konzept: ADR

Ein **ADR** („Architecture Decision Record“) hält eine Entscheidung fest, bei der es
ernsthafte Alternativen gab und die spätere Arbeit bindet. Der Aufbau ist immer gleich:
Kontext, Entscheidung, Alternativen, Folgen. Ein überholter ADR wird nicht gelöscht, sondern
bekommt den Status „Superseded by ADR NNN“. Nachträge stehen als „Amendment“ mit Datum
darunter.

Der Nutzen: In drei Monaten fragst du dich (oder ein Modell fragt sich), warum etwas so und
nicht anders gebaut ist. Ohne ADR wird die Frage neu diskutiert und oft falsch entschieden,
weil der damalige Grund vergessen ist.

Kleine Entscheidungen stehen als einzelne Zeile in `docs/decision-log.md` (die
`D`-Nummern, die überall im Code in Kommentaren auftauchen, etwa `D152`).

**Wie du einen ADR liest:** zuerst `## Decision`, dann den neuesten Nachtrag. Den Rest nur bei
Bedarf.

## Die Grundpfeiler

Diese fünf erklären den Großteil des Aufbaus.

### ADR 005 · Systemunabhängige Engine

- **Problem:** Der Bot sollte nicht für ein einziges Regelwerk gebaut sein.
- **Entscheidung:** Eine generische Engine im Code, die Mechanik eines Systems als
  Datendatei (Profil).
- **Folge:** `rules/engine.py` kennt kein Imperium Maledictum. Alles Systemspezifische steht
  in `data/systems/`. → Kapitel 4

### ADR 003 · Wann spricht die Spielleitung?

- **Problem:** Mit mehreren Leuten im Sprachkanal weiß ein Bot nicht, ob er angesprochen ist
  oder ob der Tisch untereinander redet.
- **Entscheidung:** Dauernd mitschreiben, aber nur auf Knopfdruck antworten. Der VAD
  schneidet nur Äußerungen, er löst nie einen Zug aus.
- **Folge:** Der Mikro-Knopf als Umschalter, der Puffer im Brain, das „Knopf-Fenster“.
  → Kapitel 2

### ADR 015 · Bogen und Zustand getrennt

- **Problem:** Wo lebt der veränderliche Spielzustand, ohne die von Hand angelegten
  Charakterbögen zu verändern?
- **Entscheidung:** `characters.json` bleibt nur lesbar. Eine eigene `state.json` gehört dem
  Code und wird bei jeder Änderung atomar gespeichert.
- **Folge:** `WorldState` mit seinen prüfenden Methoden, `_persist_and_refresh` an jeder
  Stelle, die etwas ändert. → Kapitel 5

### ADR 014 · Roll-Router

- **Problem:** Erzählmodelle lösen unsichere Aktionen gern selbst auf, statt eine Probe zu
  verlangen. Das lag nicht an der Modellgröße.
- **Entscheidung:** Ein eigener, zustandsloser Aufruf mit JSON-Schema entscheidet über
  Proben.
- **Folge:** Das Muster „Pflichtentscheidung bekommt einen eigenen Klassifizierer“. Es wurde
  später für Szene (ADR 057), Fakten (ADR 058) und Anwesenheit (ADR 062) wiederverwendet.
  → Kapitel 4 und 6

### ADR 061 · Claude hinter einer Naht

- **Problem:** Das lokale Modell erzählte nicht gut genug. Ein Anbieterwechsel sollte den
  Bot nicht umkrempeln und keinen API-Schlüssel brauchen.
- **Entscheidung:** Ein `ClaudeClient` hinter demselben Protokoll, umhüllt von einem
  `FailoverClient`. Die Modellstufe wählt der Client an der Form des Aufrufs.
- **Folge:** Oberhalb der Naht hat sich nichts geändert. Dieser ADR hat viele Nachträge, weil
  sich das SDK anders verhielt als geplant. → Kapitel 8

## Nach Themen

### Hören und Sprechen

| ADR | Problem | Entscheidung |
|---|---|---|
| 006 | Empfangenes Audio war nach der Transportentschlüsselung immer noch verschlüsselt | DAVE selbst entschlüsseln, Opus selbst dekodieren |
| 007 | Äußerungen sauber schneiden, ohne PyTorch | silero-vad über onnxruntime, Resampling mit soxr |
| 010 | Die zwei Bots sollen auch auf zwei Rechnern laufen können | Bridge schickt wahlweise Pfad oder Bytes |
| 011 | Die Spielleitung reagierte bei vier Sprechern rund anderthalb Minuten zu spät | Whisper auf die GPU; Push-to-talk als Weiche: alles mitschreiben, nur das Knopf-Fenster weiterleiten |
| 017 | Lange Wartezeit bis zum ersten Ton | Antwort streamen und satzweise sprechen |
| 033 | Lücken zwischen Sätzen, Brabbeln an Satzzeichen | Sprechmodi `stream`, `puffer`, `nahtlos`; `flach` oder `intoniert` |
| 067 | Zwei kurz hintereinander ausgelöste Züge erzählten durcheinander | Eine Erzählung zur Zeit generieren, Antworten in Reihenfolge und ganz sprechen |

### Schutz vor Modellfehlern

| ADR | Problem | Entscheidung |
|---|---|---|
| 016 | Das Modell spricht für die Spieler weiter und redet zu lang | Sprecher-Labels als Stopp-Sequenzen und als Schnittfilter; harte Längenbegrenzung |
| 018 | Nach einem Wurf wiederholt das Modell die Spielerzeile oder sich selbst | Echo-Schutz: einmal neu versuchen, sonst den Zug unterdrücken |
| 045 | Tote oder abwesende NSCs sprechen | Regelbasierte Prüfung gegen den Weltzustand, einmal neu generieren |
| 060 | Der Tisch hörte Dinge, die keine Erzählung sind: Entschuldigungen im Assistenten-Ton, vorgelesene Regieanweisungen | Feste Textfilter im Code statt Hoffnung auf die Persona |

### Abenteuer und Welt

| ADR | Problem | Entscheidung |
|---|---|---|
| 019 | Ähnlichkeitssuche weiß nicht, wo die Gruppe steht, und verrät späte Kapitel | Dreistufig: Zusammenfassung immer, eine Szenenkarte per Zeiger, Vektorsuche nur fürs Regelwerk |
| 043 | Die Spielleitung fragt mehrfach nach Erledigtem | Szenenkarten mit Zustand: Elemente abhaken, gesperrte Ausgänge |
| 047 | Der Welt fehlt sichtbarer Druck | Konsequenz-Uhren, vom Code geführt |
| 048 | Zeit als Freitext lässt sich nicht berechnen | Spielzeit als eine Zahl, Fristen als Vergleich |
| 057 | Der Szenenwechsel hing an einem Marker am Antwortende, der oft abgeschnitten wurde | Klassifizierer plus Flag-Zwang; sofort wechseln, eine Minute rücknehmbar; Ablehnungen laut |
| 058 | Zusagen und Übergaben verdunsten im gekürzten Verlauf | Fakten-Klassifizierer schreibt sie als harte Fakten |
| 062 | Improvisierte NSCs fehlen im Zustand und in der Zielauswahl | Anwesenheits-Klassifizierer |

### Gedächtnis

| ADR | Problem | Entscheidung |
|---|---|---|
| 027 | Der wachsende Prompt schnitt bei Nemo die Persona ab | Kontextbudget überwachen, Auto-Recap nach dem Zug |
| 044 | NSCs vergessen, was mit ihnen besprochen wurde | Erinnerungen pro NSC, am Szenenende extrahiert; Haltung vom Code begrenzt |
| 049 | Die Welt steht still, wenn die Spieler nicht hinsehen | Agenden: wenige NSCs verfolgen ein Ziel abseits der Gruppe |
| 050 | Lose Enden gehen verloren | Tschechow-Liste, vom Code verwaltet |
| 054 | Was vor Wochen wörtlich gesagt wurde, ist weg | Gespielte Sitzungen szenenweise ins RAG, hybride Suche |
| 055 | Testläufe verschmutzen das Kampagnengedächtnis | Abgetrennter Bereich für Debug-Läufe, erkannt am Dateinamen |

### Struktur des Codes

| ADR | Problem | Entscheidung |
|---|---|---|
| 029 | Ein einziger Riesen-Cog | `SessionRuntime` als gemeinsamer Zustand, mehrere Cogs, Hooks statt Cog-Suche |
| 034 | `orchestrator.py` war zu groß und mischte reine Textlogik mit Zustand | Reine Helfer in eigene Module (`sanitize`, `stream_assembler`, …) |
| 035 | Batch- und Streaming-Auslieferung waren doppelt geschrieben | Eine `DeliveryPipeline` |
| 038 | Die Prompt-Reihenfolge stand an mehreren Stellen | Ein Besitzer: `assemble_system_prompt` |
| 046 | Umbauten ließen sich nur am Spieltisch prüfen | Journal als Replay-Aufzeichnung, `dm-eval` als Pflicht-Tor |
| 051 | Jeder neue Marker brauchte Änderungen an vielen Stellen | Marker-Register `MARKER_SPECS` |
| 065 | `runtime.py`, `orchestrator.py` und `dicecog.py` waren zu groß | Methodengruppen in Mixins, Byte für Byte verschoben |

### Ein ADR, der eine Idee wieder verwarf

**ADR 066** ist lehrreich, weil er ein Nein dokumentiert. Die drei Klassifizierer an der
Zuggrenze kosten drei Aufrufe. Naheliegend wäre, sie zu einem zusammenzulegen. Das wurde
gebaut, gemessen und wieder entfernt: Die einzigen Fehler des kombinierten Aufrufs waren
Zeitüberschreitungen, und eine Zeitüberschreitung verlor dann alle drei Urteile des Zugs auf
einmal. Drei getrennte Aufrufe verlieren im schlimmsten Fall eines. Ohne den ADR würde die
Idee alle paar Monate neu aufkommen.

## Die Lektionen, die sich durchziehen

`docs/lessons/` hält fest, was beim Bauen schiefging und was daraus folgt. Diese acht
erklären die meisten Eigenheiten im Code:

| Lektion | Kurz | Wo du sie siehst |
|---|---|---|
| `llm-requests-code-validates` | Das Modell bittet, der Code prüft und schreibt | alle Marker, alle Klassifizierer |
| `mandatory-decisions-need-a-separate-classifier` | Eine Entscheidung, die fallen *muss*, gehört nicht ans Ende eines Erzähltexts | Roll-Router, Szenen-Klassifizierer |
| `optional-layers-fail-open-core-fails-loud` | Zusatzschichten fallen leise aus, der Kern laut | die vielen `try/except` mit „never breaks a turn“ |
| `spoken-audio-cannot-be-retracted` | Gesprochenes lässt sich nicht zurückholen | Zurückhalte-Regeln, Echo-Schutz nur vor dem ersten Ton, Streaming-Regel im Failover |
| `snapshot-state-at-event-time` | Zustand zum Zeitpunkt des Ereignisses festhalten | `for_dm` an der Äußerung, `classified_from` in `close_turn` |
| `parity-by-construction` | Zwei Wege zum selben Ergebnis teilen sich eine Funktion | `finalize_answer` für Batch und Stream, `_build_request` |
| `unwired-knobs-and-silent-fallbacks` | Stille Rückfallebenen verstecken Fehler | laute Failover-Meldungen, Warnung bei fehlender `characters.json` |
| `incidents-become-preflights` | Jeder Vorfall am Tisch wird zu einer Prüfung beim Start | `check_ollama`, `check_claude`, `voice/preflight.py` |

## Wie es weitergeht

Wenn du im Code auf etwas stößt, das dir seltsam vorkommt, gibt es fast immer eine Spur:

1. Steht im Kommentar eine Nummer (`ADR 057`, `D152`)? Dann in `docs/decisions/` oder
   `docs/decision-log.md` nachschlagen.
2. Verweist der Kommentar auf eine Lektion (`docs/lessons/…`)? Die Dateien sind kurz.
3. Sonst: `git log -S "<Symbolname>"` zeigt, mit welchem Commit es kam, und die
   Commit-Nachricht nennt meist den Grund.

Und `progress.md` (Abschnitt „State header“) sagt, woran zuletzt gearbeitet wurde und was als
Nächstes ansteht.

## Selbsttest

Diese Fragen gehen über das ganze Dokument. Wenn du sie beantworten kannst, verstehst du den
Bot.

1. Nenne drei Stellen, an denen das Modell etwas vorschlägt und der Code entscheidet.
2. Warum gibt es vier getrennte Klassifizierer und nicht einen großen Aufruf nach jedem Zug?
3. Ein Spieler sagt etwas, und sechs Sekunden später hört er die Antwort. Welche Stufen
   liegen dazwischen, und welche laufen in eigenen Threads?
4. Welche drei Dateien pro Kanal brauchst du, um eine Kampagne auf einen anderen Rechner
   umzuziehen, und was steckt in jeder?
5. Du willst einen neuen Marker `<<GELD +50>>` einführen, mit dem das Modell eine Belohnung
   vorschlagen kann. Welche Teile musst du anfassen?
6. Warum war die Mixin-Aufteilung ein Umbau mit geringem Risiko?

<details>
<summary>Antworten</summary>

1. Zum Beispiel: Proben (`<<TEST>>` oder Router, die Engine würfelt), Szenenwechsel
   (Klassifizierer oder `<<ORT>>`, `resolve_exit` prüft), NSC-Haltung (Extraktor schlägt vor,
   `step_attitude` begrenzt). Auch: Zeit, Uhren, Flags, Fakten, Anwesenheit.
2. Jeder beantwortet eine eng gefasste Frage zuverlässig, läuft auf dem günstigen Modell und
   fällt einzeln aus, ohne die anderen mitzureißen. Der Versuch, drei davon zusammenzulegen,
   wurde gemessen und verworfen (ADR 066).
3. VAD wartet auf Stille, Whisper transkribiert, der Zug wird vorbereitet, RAG sucht, das
   Modell erzeugt den ersten Satz, XTTS synthetisiert ihn, Bot A spielt ihn. Eigene Threads:
   Audioempfang mit VAD (Reader-Thread), Whisper (STT-Thread), XTTS (TTS-Thread). Der Rest
   läuft im Event-Loop.
4. `characters.json` (die Bögen), `state.json` (Weltzustand samt Recap und NSC-Gedächtnis),
   `chekhov.json` (lose Fäden). Dazu die rotierten `history.*.jsonl`, wenn das
   Sitzungs-Gedächtnis mit umziehen soll, oder gleich `data/vectordb/rag.db`.
5. Einen Eintrag in `MARKER_SPECS` mit Erkennungsfunktion (`rules/marker.py`), eine prüfende
   Methode am `WorldState`, eine Verdikt-Funktion und einen Handler in der DeliveryPipeline
   (nach dem Vorbild von `_handle_zeit`), die Erklärung in der Persona, Tests und ein Golden.
   Das Brain selbst nicht: Die Marker-Warteschlangen laufen über das Register.
6. Die Methodenkörper wurden unverändert verschoben, alle teilen weiter dasselbe `self`, und
   Tests wie `dm-eval` waren nach jedem Schritt grün, ohne dass ein Test angepasst werden
   musste.

</details>

Zurück zum [Inhaltsverzeichnis](README.md).
