# Target vision — what the finished DM should feel like

> Tobi's target picture for the bot, agreed 2026-10-06, plus the review of `main` (01a8d14)
> against it. Kept in German because it describes the table experience, not the code. Every
> later PRD measures itself against this file. Editable source: the "Dungeonmaster – Zielbild"
> doc on claude.ai.

## Ziel & Rolle

Der Bot ist ein deutschsprachiger Game Master für eine Warhammer-40K-Runde mit drei Spielern im
Discord-Voice-Channel. Er soll sich anfühlen wie ein echter GM: Er improvisiert, lenkt durch die
Geschichte, setzt Regeln durch, spricht die NSCs und erklärt das Setting.

- Eine Erzählerstimme für alle Figuren, keine eigene Stimme pro NSC.
- Grundprinzip: Das LLM interpretiert und erzählt, der Code rechnet und verwaltet den Zustand.

## Kampagne & Story

Die Kampagne ist ein grober Leitfaden, kein Skript. Die Gruppe darf jederzeit eigene Wege gehen.

- Pro Szene: Zusammenfassung, NSCs, Orte, Auslöser, mögliche Ausgänge, Status (offen, aktiv,
  erledigt).
- Im Kontext stehen nur die aktive Szene und die nächsten möglichen Beats.
- Nach jeder Runde wird geprüft, ob ein Beat erfüllt ist, und der Status aktualisiert.
- **Die Welt drängt, nicht der Erzähler.** Statt zu erinnern lässt der Bot etwas passieren
  (ein Bote, ein handelnder Gegner, eine ablaufende Frist). Kampagnen-Elemente werden nach
  Abweichungen später wieder eingewoben.

## Regeln & Proben

Regelwerk ist Imperium Maledictum.

1. Das LLM interpretiert die Aktion („Klettern → Probe auf Beweglichkeit, erschwert wegen
   nasser Wand").
2. Der Code würfelt, vergleicht mit dem Charakterbogen, berechnet die Erfolgsgrade.
3. Das LLM erzählt das Ergebnis.

Das LLM würfelt und rechnet nie selbst. Erst Fertigkeitsproben, dann Kampf.

## Spielablauf

Zwei Modi; den Wechsel entscheidet der Bot („Würfelt Initiative"), die Gruppe kann überstimmen.

| Modus | Wann | Wer ist dran |
| --- | --- | --- |
| Frei | Gespräche, Erkunden, Verhandeln | Wer den Knopf beendet; danach reagiert der Bot |
| Runden | Kampf, Gefahr | Spieler 1 → Bot → Spieler 2 → Bot → Spieler 3 → Bot → Bot spinnt weiter |

- **In-Game-Knopf** (Chat-Button, Umschalter): erstes Drücken = ab jetzt in-game, zweites
  Drücken = fertig, Bot ist dran. Alles außerhalb ignoriert der Bot. Keine Pausenerkennung.
- **Unterbrechbarkeit:** Drückt jemand den Knopf, während der Bot spricht, verstummt er.

Ein Zug: Knopf an → Spieler spricht → Knopf aus → LLM deutet die Aktion und wählt die Probe →
Code würfelt und rechnet → LLM erzählt das Ergebnis → Zustand und Gedächtnis werden
aktualisiert → nächster Spieler.

## Gedächtnis

Der Bot merkt sich über Sessions hinweg auch Kleinkram („Timo hat dem Händler gedroht, der ist
jetzt sauer").

- Ein Eintrag pro NSC, Ort und Fraktion: Haltung zur Gruppe, was passiert ist, was die Figur
  weiß.
- Nach jeder Runde werden Änderungen eingetragen.
- Nur die Einträge der gerade beteiligten NSCs und Orte kommen in den Kontext.
- NSCs reagieren von sich aus auf Vergangenes.

## Charaktere

Die Bögen existieren und werden importiert; keine Charaktererschaffung im Bot.

- Strukturierte Daten, nur der Code ändert sie.
- Das LLM fordert Änderungen an (z. B. `schaden(Timo, 4)`), der Code prüft.
- Im Kontext nur eine Kurzfassung pro Charakter; volle Werte bei Bedarf.
- `/bogen` zeigt den aktuellen Stand, ein Korrektur-Befehl behebt Fehler.

## Kampf

Version 1: Zonen-Kampf (nah/mittel/fern oder benannte Bereiche), Proben, Schaden und Wunden voll
nach Regeln. Langfristig volle Regeln.

- Das Datenmodell kennt Positionen und Reichweiten von Anfang an.
- Gegnerwerte aus der Kampagne; der Code würfelt für Gegner, das LLM wählt ihre Taktik.

## Session-Ablauf

- **Start:** automatisch Intro (neue Kampagne) oder Recap „Was bisher geschah".
- **Laufend:** Zustand nach jeder Runde gespeichert; nach einem Absturz geht es dort weiter.
- **Ende:** ein Befehl schreibt die Session-Zusammenfassung.

---

## Review von `main` (01a8d14, 2026-10-04) gegen dieses Zielbild

Die Architektur deckt sich fast vollständig mit dem Zielbild. Was nicht funktioniert, hat drei
Ursachen:

1. **Das Modell.** Mistral Nemo 12B ist die Wurzel der meisten Fehler; mindestens neun der 60
   ADRs sind Schutzschichten gegen sein Verhalten. Die Persona umfasst rund 17.000 Zeichen.
2. **Das Abhaken ist tot.** `<<ERLEDIGT id>>` ist ein Inline-Marker am Antwortende (dort, wo
   `DM_NUM_PREDICT` kappt) und braucht per Default einen Bestätigungsklick
   (`DM_FLAG_CONFIRM=1`). Kein Klassifikator prüft Möglichkeiten. Erledigtes bleibt unter
   „Möglichkeiten hier", die Persona lässt das Modell darauf hinarbeiten — es erinnert weiter.
   Das Flag-Gate aus ADR 057 hängt an denselben Flags; `chemical_burn` hat keine
   Möglichkeits-IDs. Dazu vier Drängel-Quellen: Persona „treibe sanft darauf zu", Persona
   „erinnere an Fristen", Kaads Spielweise „spricht in Fristen", die Frist jede Runde im
   Weltzustand.
3. **Nichts ist am Tisch bestätigt.** 1090 Tests grün, 17 Live-Gates offen und per WIP-Override
   auf einen Abend gestapelt.

| Bereich | Stand im Code | Bewertung |
| --- | --- | --- |
| Knopf | `MicToggleView`: erstes Tippen hört zu, zweites löst den DM-Zug aus | passt |
| Proben | Roll-Router, Würfelknopf je Figur, Engine rechnet Erfolgsgrade | passt |
| Story | Szenenkarten, Uhren, Fristen, Agenden vorhanden; Abhaken defekt | Lücke |
| Gedächtnis | NSC-Gedächtnis, lose Fäden; Extraktion erst bei Szenenwechsel oder `!wrap` | passt, hängt am Szenenwechsel |
| Charaktere | `characters.json` + `state.json`, `!damage`/`!heal`; keine Bogen-Anzeige | fast |
| Modi | nur freier Modus; Reihenfolge ist eine manuelle ◀ ▶-Anzeige | fehlt |
| Kampf | Spielerangriffe mit Schaden; Gegner würfeln nie, Schaden an Spielern nur per `!damage`; keine Initiative, keine Zonen | fehlt größtenteils |
| Session | `!intro`, Recap beim Join als Chat-Text, `!wrap`, laufendes Speichern | passt |
| Bedienung | rund 45 Chat-Befehle | zu viel für den Tisch |

## Reihenfolge

Eine Variable pro Abend.

1. **Feature-Stopp**, bis der Kernablauf an einem Abend funktioniert hat.
2. **Phase 11 — Claude-Backend** (`docs/plans/claude-backend.md`, ADR 061). Nur das Modell
   tauschen; die 17 alten Gates sind geparkt, die optionalen Schichten am Abend aus.
3. **Claude-Abend** mit den Gate-Punkten des PRD, inklusive Marker-Probe für `<<TEST>>` und
   `<<ERLEDIGT>>` und Zählung abgeschnittener Antworten.
4. **Phase 12 — Story-Fortschritt und Tools:** Abhaken als Tool, Drängel-Anweisungen raus,
   alle übrigen Marker als Tools, Schaden an jeder Figur.
5. **Phase 13 — blockierender Tool-Zug** (wenn die Latenz es zulässt).
6. **Phase 14 — Rundenmodus, Gegnerzüge, Zonen-Kampf.**
