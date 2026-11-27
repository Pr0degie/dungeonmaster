# Den Bot verstehen

Eine Lern-Doku für dieses Repo. Sie ist kein Nachschlagewerk (das sind `architecture.md` und die
ADRs), sondern zum Durchlesen von vorne nach hinten gedacht: Nach jedem Kapitel solltest du den
beschriebenen Teil jemandem ohne Blick in den Code erklären können.

Stand: Commit `89d347a` (27.11.2026, nach der Aufteilung von `SessionRuntime`, `DMBrain` und
`DiceCog` in Mixins), dazu die Änderung D157 am RAG-Nachschlag (Kapitel 2, 3, 5 und 9).

## Reihenfolge

| Nr. | Kapitel | Worum es geht |
|---|---|---|
| 1 | [Überblick](01-ueberblick.md) | Die Bausteine, wer mit wem redet, die drei Grundideen |
| 2 | [Ein Spielzug von A bis Z](02-ein-spielzug.md) | Ein gesprochener Satz durch das ganze Programm |
| 3 | [Der Prompt](03-der-prompt.md) | Was Claude pro Zug zu sehen bekommt, Cache, Auto-Recap |
| 4 | [Würfel und Regeln](04-wuerfel-und-regeln.md) | Router, Marker, Engine, Profil, Kampf |
| 5 | [Gedächtnis](05-gedaechtnis.md) | State, Journal, Recap, NSC-Gedächtnis, lose Fäden, Sitzungs-RAG |
| 6 | [Abenteuer und Szenen](06-abenteuer-und-szenen.md) | Szenenkarten, der Zeiger, die Zuggrenze |
| 7 | [Audio](07-audio.md) | Empfang, VAD, Whisper, XTTS, Bridge |
| 8 | [Das LLM-Backend](08-llm-backend.md) | `LLMClient`, Claude über das Abo, Failover und Pause |
| 9 | [Testen](09-testen.md) | Fakes, Golden Transcripts, `dm-eval`, `dm-check` |
| 10 | [Warum so?](10-warum-so.md) | Die wichtigsten ADRs und Lektionen in Kurzform |

Kapitel 1 und 2 sind die Grundlage. Die Kapitel 3 bis 9 kannst du danach in beliebiger
Reihenfolge lesen. Kapitel 10 ist die Zusammenfassung und hat einen Selbsttest über alles.

## Aufbau der Kapitel

Jedes Kapitel hat dieselben drei Teile:

1. **Das Konzept allgemein.** Was ist das überhaupt (ein Event-Loop, ein VAD, ein Mixin), ohne
   Bezug auf dieses Repo.
2. **So ist es hier gebaut.** Mit Datei und Funktion, damit du die Stelle im Code öffnen und
   mitlesen kannst. Zeilennummern stehen bewusst nicht drin, die veralten beim nächsten Commit.
3. **Selbsttest.** Ein paar Fragen. Wenn du sie ohne Nachschauen beantworten kannst, sitzt das
   Kapitel. Die Antworten stehen eingeklappt darunter.

## Hinweise

- Die Diagramme sind Mermaid. GitHub rendert sie direkt, in VS Code braucht es die Erweiterung
  „Markdown Preview Mermaid Support“.
- Diese Doku ist auf Deutsch, obwohl `CLAUDE.md` für Docs Englisch vorgibt. Der Grund für die
  Regel ist Token-Sparsamkeit, wenn Claude Code die Docs liest. Dieser Ordner ist für dich zum
  Lernen, Claude Code muss ihn nicht lesen.
- Die Doku beschreibt den Stand des Commits oben. Wer hier beschriebene Symbole umbenennt oder
  verschiebt, sollte nach der Regel „Docs follow code in the same commit“ auch hier nachziehen.
