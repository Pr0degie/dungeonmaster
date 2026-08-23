# Sprechmodus-Vergleich — 20 Minuten am Tisch, danach steht der Default

Stand: 2026-08-22 (nach dem Debug-Lauf „Die Mitternachtsfracht", Befund A-Block „hackt an den
Nähten" + Plan `docs/plans/coherent-campaign-run.md`, Abschnitt „Speech delivery").

**Warum das hier existiert.** Der aktuelle Default `stream` + `flach` ist eine
**CPU-Entscheidung** aus ADR 033: schneller erster Ton, alle Satzzeichen entfernt, damit XTTS
nicht verhaspelt. Der Lauf vom 22.08. lief aber auf **cuda** — und hat den CPU-Preis trotzdem
bezahlt: hörbare Nähte zwischen den Sätzen und keine Satzendbetonung, auf Hardware, die das
nicht mehr nötig hat. Der Default wird **nicht** blind umgestellt: erst hören, dann setzen.

> **Der Default bleibt bis dahin `stream` + `flach`.** Das ist Absicht, nicht Vergessen.
> Umgestellt wird erst nach diesem Vergleich, mit Ergebnis in einem ADR.

**Spielregeln für den Block** (`docs/lessons/one-variable-per-live-run.md`): der Sprechmodus ist
in diesen 20 Minuten die **einzige** Variable. Nicht gleichzeitig Sprecher, Modell oder
`DM_NUM_PREDICT` anfassen. Nicht mitten in einer Szene — vor dem Spiel oder in einer Pause.

---

## 0. Vorflug (2 Minuten, bevor jemand hört)

| Prüfung | Kommando / Zeile | Erwartet |
|---|---|---|
| Stimme ist die konfigurierte | `logs/debug.log`: `XTTS v2 loaded on … — speaker: …` | der Name aus `TTS_SPEAKER`, **nicht** „Dionisio Schuyler" als Zufallstreffer |
| Sprecher-Konfig ist sauber (Start) | `logs/debug.log`: `XTTS speaker preflight` | `… OK — …`. Steht dort `XTTS speaker preflight FAILED`, erst **die Zeile lesen und `.env` reparieren** — sie nennt den falschen Wert, die gültigen Namen und die Env-Variable |
| Sprecher-Konfig ist sauber (nach dem Modell-Laden) | `logs/debug.log`: `XTTS speaker misconfigured:` | **kommt gar nicht vor**. Diese Zeile prüft gegen die echte Sprecherliste des geladenen Modells und hat das letzte Wort |
| Gerät | `logs/debug.log`: `XTTS v2 loaded on cuda` | `cuda` (auf `cpu` ist dieser Vergleich sinnlos, siehe unten) |
| Aktueller Modus | `!sprechmodus` (ohne Argument) | zeigt Lieferart + Betonung + Puffertiefe |

Seit dem 22.08. ist ein unbekannter Sprecher ein **lauter** Fehler beim Start
(`voice/preflight.py`), kein stiller Rückfall mehr. Genau dieser stille Rückfall hat den ganzen
Abend vom 22.08. in einer zufälligen Stimme sprechen lassen.

---

## 1. Der Vergleich (6 Durchgänge)

Immer **dieselbe Eingabe**, damit die Antworten vergleichbar lang und vergleichbar gebaut sind.
Vorschlag (ein Satz, der garantiert 4–6 Sätze Antwort erzeugt):

> `!dm Beschreib uns die Zoll-Sakristei und was Kaad gerade tut.`

Ablauf pro Durchgang: **erst** den Modus setzen, **dann** die Zeile schicken, zuhören, ankreuzen.

| # | Kommando (Modus setzen) | dann |
|---|---|---|
| 1 | `!sprechmodus stream flach` | `!dm Beschreib uns die Zoll-Sakristei und was Kaad gerade tut.` |
| 2 | `!sprechmodus stream intoniert` | dieselbe `!dm`-Zeile |
| 3 | `!sprechmodus puffer 3 flach` | dieselbe `!dm`-Zeile |
| 4 | `!sprechmodus puffer 3 intoniert` | dieselbe `!dm`-Zeile |
| 5 | `!sprechmodus nahtlos flach` | dieselbe `!dm`-Zeile |
| 6 | `!sprechmodus nahtlos intoniert` | dieselbe `!dm`-Zeile |

**Was der Vergleich nicht kann:** wortgleiche Antworten. Das Modell würfelt jedes Mal neu; nur
die *Eingabe* ist identisch. Beurteilt wird der **Klang**, nicht der Text. Der einzige feste
Anker mit identischem Ablauf ist `!intro test` (immer `nahtlos` + `flach`, ADR 031/033) — und
`!say <Text>` spricht zwar wortgleich, geht aber **am Sprechmodus vorbei** (eigener Pfad), taugt
also nur zum Stimmen-Vergleich, nicht zum Modus-Vergleich.

---

## 2. Worauf man hört

Drei Dinge, in dieser Reihenfolge — es sind genau die drei, die sich zwischen den Modi ändern:

1. **Nähte.** Hört man die Übergänge *zwischen den Sätzen* als Klick, Loch oder Atemabbruch?
   `stream` setzt pro Satz einen eigenen Bridge-Aufruf ab — dort sitzen die Nähte.
   `nahtlos` klebt alles zu einer Spur zusammen, da darf nichts hörbar sein.
   (Nicht mit den XTTS-Chunk-Fugen verwechseln: die Chunk-Grenzen liegen an Satzgrenzen und sind
   in allen Modi gleich — `dmbot/tts/textsplit.py`. Was hier verglichen wird, ist die Lieferart.)
2. **Betonung am Satzende.** Klingt eine Frage wie eine Frage, endet ein Satz oder rutscht er in
   den nächsten? Das ist die `flach`/`intoniert`-Achse. Gegenprobe: verhaspelt sich XTTS bei
   `intoniert` irgendwo („Anfälle bei Satzzeichen", D55)? Ein einziges Verhaspeln in sechs
   Durchgängen ist noch kein Ausschluss — drei sind es.
3. **Wartezeit bis zum ersten Ton.** Ab Absenden der Zeile bis zum ersten hörbaren Wort. Gefühlt
   ankreuzen — die Zahl steht hinterher exakt im Log (Abschnitt 3).

---

## 3. Die Zahl dazu — aus dem Log, nicht aus dem Gefühl

Jeder Zug schreibt eine Zeile, die alles Nötige enthält:

```
[latency] turn=12 stream stt=… trigger→llm_done=…ms gen=… chars=… first_audio=…ms tts=…ms wav=…s bridge_wait=…ms total=…ms
```

- `first_audio=` — **die** Vergleichszahl für „Wartezeit bis zum ersten Ton". Wird in allen drei
  Lieferarten gesetzt.
- `tts=` gegen `wav=` — das Synthesetempo: `wav`-Sekunden geteilt durch `tts`-Sekunden ergibt den
  Echtzeitfaktor.
- Das Wort `stream` hinter `turn=` erscheint nur im Streaming-Pfad — `nahtlos` läuft über den
  Batch-Pfad und hat es nicht. So sieht man im Log, welcher Modus wirklich lief.

Auslesen nach dem Block: `grep "\[latency\]" logs/debug.log | tail -6`

### Erwartungswerte aus dem Lauf vom 22.08. (cuda)

| Größe | Gemessen am 22.08. | Bedeutung für den Vergleich |
|---|---|---|
| XTTS-Synthesetempo (cuda) | **2–3,5× Echtzeit** | die Synthese ist schneller als das Sprechen — das ist der Grund, warum `nahtlos` überhaupt zur Debatte steht |
| `nahtlos`, normaler Zug | **≈ 17 s** bis zum ersten Ton | der Preis für die lückenlose Spur bei einer normalen Antwort |
| `nahtlos`, `!intro` | **≈ 44 s** bis zum ersten Ton | Intro-Länge; als Regelfall am Tisch grenzwertig |
| `stream` | erster Ton nach dem **ersten Satz** | schnellster Einstieg, dafür die Nähte |
| `puffer 3` | erster Ton nach **3 Sätzen** | Kompromiss: kurzer Vorlauf, danach glatter als `stream` |

Weichen die gemessenen `first_audio`-Werte stark davon ab, ist wahrscheinlich nicht der Modus
schuld: `XTTS v2 loaded on cpu` im Log prüfen (auf CPU ist die Synthese langsamer als Echtzeit,
dann sind schneller Start und Lückenlosigkeit gegenseitig ausgeschlossen — ADR 033).

---

## 4. Ankreuzen

Pro Durchgang eine Zeile. „Naht" und „Betonung" mit ✓/✗, Gesamturteil 1 (unbrauchbar) bis
5 (so soll es klingen).

| # | Modus | Naht hörbar? | Betonung am Satzende | Wartezeit gefühlt | `first_audio=` (Log) | Urteil 1–5 |
|---|---|---|---|---|---|---|
| 1 | stream + flach | | | | | |
| 2 | stream + intoniert | | | | | |
| 3 | puffer 3 + flach | | | | | |
| 4 | puffer 3 + intoniert | | | | | |
| 5 | nahtlos + flach | | | | | |
| 6 | nahtlos + intoniert | | | | | |

Zusatzfrage, wenn `nahtlos` gewinnt: ist die Wartezeit **am Tisch** erträglich, wenn vier Leute
sie gleichzeitig aussitzen? Die 17 s fühlen sich beim Testen anders an als im Spiel.

---

## 5. Danach — den Default setzen

1. Gewinner in `.env` eintragen: `DM_SPEECH_MODE=stream|puffer|nahtlos`,
   `DM_SPEECH_PUNCT=flach|intoniert`, bei `puffer` zusätzlich `DM_SPEECH_PREBUFFER=<n>`
   (Standard 3).
2. Auf der zweiten Maschine mit `uv run dm-sync` gegenprüfen, damit der neue Default nicht auf
   einer Box hängen bleibt.
3. Ergebnis als ADR festhalten (ein Satz Begründung + die Tabelle oben) und ADR 033 dort
   verlinken — der dortige Default ist ausdrücklich eine CPU-Entscheidung und wird damit abgelöst.
4. Ist das Ergebnis „kommt drauf an" (z. B. `nahtlos` für `!intro`, `stream` im Gespräch), gehört
   genau das in den ADR — `!sprechmodus` ist zur Laufzeit umschaltbar, ein Split ist zulässig.
