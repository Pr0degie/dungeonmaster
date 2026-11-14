# Textvergleich: der Zweier-Lauf vom 25.10. gegen den Abend vom 14.11.2026

**Stand:** 14.11.2026, nur Untersuchung. An Persona, Code und Einstellungen wurde nichts geändert; alle
Änderungen unten sind Vorschläge.

## Das Wichtigste

**Die einzelnen Antworten waren am 14.11. nicht schlechter geschrieben als früher. Schlechter war, was um sie herum
geschah, und ihre Form.** Persona und Sprechbudget scheiden als Ursache aus: Sie haben sich zwischen den beiden
Läufen kaum geändert (drei zusätzliche Persona-Absätze, dasselbe Budget von 220), und sechs Züge des Abends, mit
der Persona von damals noch einmal durch Opus geschickt, kommen in derselben Länge und mit denselben langen Sätzen
zurück.

Drei Unterschiede haben den Texten am wahrscheinlichsten geschadet:

1. **Angeforderte Proben, auf die kein Wurf folgte.** Am 25.10. folgte auf 12 von 13 Probenanforderungen des
   Erzählers ein Wurf und danach eine Antwort, die etwas entschied. Am 14.11. waren es 4 von 15; elfmal blieb der
   offene Moment stehen, und der nächste Zug beschrieb ihn neu, am Ende neunmal hintereinander (19:25–19:31). Das
   ist „man muss hundertmal sagen, was passiert“. Die Regel dahinter ist nicht neu, sie hat am 14.11. nur viel
   öfter gegriffen, weil der Abend eine Verhandlung war und kein Kampf. Die Folgerunde vom 14.11. behebt das
   bereits (Opus' Probe zählt auf Claude), am Tisch ist es noch nicht geprüft.
2. **Weniger, dafür längere Sätze.** In denselben Szenen (Zollhaus und Schrein) hatte eine Antwort am 25.10. im
   Schnitt 4,3 Sätze zu 123 Zeichen, am 14.11. 3,0 Sätze zu 176 Zeichen, bei gleicher Gesamtlänge. Lange Sätze
   sind vorgelesen schwer zu verfolgen, sie stoßen öfter an die Budgetgrenze (8 von 33 Antworten gegen 6 von 47),
   und der Schnitt wirft dann mehr weg (bis zu 271 Zeichen und drei Steuermarker am Antwortende). Die Persona
   steuert das nicht: Mit allen drei Persona-Ständen kamen im Nachlauf 146 bis 163 Zeichen je Satz heraus. Die
   Persona von heute macht die Züge sogar länger (im Schnitt 656 statt 565 Zeichen, bis 807).
3. **Der Verlauf wurde nach 18 Zügen geleert statt nach 41.** Der Prompt ist seit dem 25.10. um rund 1200 Tokens
   gewachsen, die Schwelle für die automatische Zusammenfassung ist gleich geblieben. Am 14.11. lief sie deshalb
   mitten in der Szene (19:20), danach hatte Opus statt der letzten Züge im Wortlaut nur noch eine Zusammenfassung
   von höchstens 1200 Zeichen. Der Beleg für einen Schaden ist hier dünner als bei 1 und 2 (eine sichtbare
   Wiederholung direkt danach).

Was sich ändern sollte, steht unter „Vorschläge“. Vor dem nächsten Lauf braucht nur Punkt 2 eine Entscheidung.

## a) Der frühere Lauf

Gesucht war der erste Lauf vor dem 11.11., in dem nur Tobi und Sezgin gespielt haben. `logs/transcript.log` hat
keine Datumszeilen; die Zuordnung stammt aus den Startzeilen in `logs/debug-bis-2026-11-14.log` und den Sprechern
je Abschnitt.

| Kandidat | Datum, Uhrzeit | Am Tisch | Backend laut Bootzeile | Commit |
|---|---|---|---|---|
| **1 (gewählt)** | 25.10.2026, Bot-Start 20:51:23, gespielt 20:52–21:38, 47 Antworten | nur Tobi (Fridolin) und Sezgin (Rektalus) | Claude: Erzählung `opus`, Hilfsaufrufe `haiku`, CLI 2.1.310 | `e3c7a79` (20:46:22) |
| 2 | 25.10.2026, 20:16–20:27, 10 Antworten | Tobi und Sezgin, nachdem Timo und BloodyP gegangen waren (Rest des Vierer-Laufs, Bot-Start 19:42:40) | wie 1 | `f4b2a0b` (17:04:48) |

Kandidat 1 ist der „vierte Opus-Lauf“ aus `docs/progress-archive.md` („Tobi und Sezgin, nur Fridolin + Rektalus“)
und der einzige, der von Anfang an zu zweit gespielt wurde. Der Commit ist der letzte vor dem Bot-Start; der
nächste (`9de8ebe`, 21:51) kam erst nach dem Lauf. Ob beim Start uncommittete Änderungen im Arbeitsverzeichnis
lagen, lässt sich aus den Logs nicht belegen.

Keine Kandidaten: 25.10. 02:08–02:38, 31.10. und 12./13.11. (Tobi allein), 30.10. (vier Spieler), Juni und
22.08. (drei bzw. vier Spieler, `mistral-nemo`).

Der Abend vom 14.11.: Bot-Start 18:59:32, gespielt 19:04–19:33, 33 Antworten, Commit `abd1b49` (00:26:50; die
Persona-Commits ab 19:46 gehören zur Folgerunde danach), Erzählung `opus`, Hilfsaufrufe `haiku`, CLI 2.1.325.

## b) Sechs Antworten von damals neben sechs vom 14.11.

Zeichenzahl ist der gesprochene Text. Die vollen Texte stehen im Anhang.

| Art des Zugs | Lauf | Uhrzeit | Zeichen | Abgeschnitten | Was in der Handlung vorankommt |
|---|---|---|---|---|---|
| Ankunft an einem Ort | 25.10. | 20:56:48 | 589 | nein | Ortswechsel zum Schrein vollzogen; ein Einstieg: Tür einen Spalt offen, Siegel zerrissen, Kerzenlicht. |
| | 14.11. | 19:11:39 | 711 | ja, an der Budgetgrenze mitten in den Markern: Text vollständig, Zeit- und Ortsmarker verloren | Abschied der Schwester mit Warnung vor den Kettenmännern, Weg zur Pfandhalle, Karrenspuren, der Schieber an der Tür geht auf. |
| Erste Begegnung in der Szene | 25.10. | 20:58:23 | 680 | nein | Schrein von innen; drei Ansatzpunkte: der leere Sockel, die Münze, die Schwester sagt „fast alles“. |
| | 14.11. | 19:07:12 | 568 | nein | Vor der Schreintür; ein Ansatzpunkt: die Schwester fegt vor dem leeren Reliquiar und fragt, ob die Gruppe von den Arbites ist. |
| Gespräch mit einem NSC | 25.10. | 21:09:32 | 570 | nein; der Satzschnitt warf den Schlusssatz in Anführungszeichen weg (55 Zeichen) | Der Kettenmann weicht aus, zeigt die glattgeschliffene Münze; seine Drohung gegen die Schwester (der Schlusssatz) wurde nicht gesprochen. |
| | 14.11. | 19:15:01 | 602 | nein | Bree stellt eine Bedingung: erst sagen, in wessen Auftrag. Keine neue Auskunft. |
| Offener Moment mit Probenanforderung | 25.10. | 21:11:16 | 494 | nein | Pistole an der Stirn, der Kettenmann zögert; Probe Einschüchtern angefordert, der Wurf kam (88, Fehlschlag). |
| | 14.11. | 19:19:06 | 424 | nein | Bree wägt das Schutzversprechen ab; Probe Überreden angefordert, zum zweiten Mal für denselben Moment (19:18:11 blieb ohne Wurf), diesmal kam der Wurf. |
| Probe misslungen | 25.10. | 21:00:15 | 672 | nein | Fehlschlag mit Teilauskunft (die Schwester hat sich versteckt), die Luft über dem Sockel wird dichter, Übergabe an Rektalus. |
| | 14.11. | 19:09:14 | 702 | nein | Fehlschlag macht es schwerer (die Schwester will nach den Arbites rufen), die Münze rollt Rektalus vor den Stiefel. |
| Probe gelungen | 25.10. | 21:06:31 | 660 | nein | Geständnis: Karren zur Pfandhalle, bei Bree Marlok gehen Kettenmänner ein und aus. |
| | 14.11. | 19:10:05 | 662 | nein | Geständnis: vermummte Männer mit Stemmeisen, Karren zur Pfandhalle; die Schwester fragt, ob man sie meldet. |

**Was der Vergleich zeigt:** Stil, Ton und Länge sind gleich. Zwei Unterschiede fallen auf. Erstens die
Satzform (oben, Punkt 2). Zweitens das Ende: Am 25.10. hört eine Antwort mehrmals bei dem Spieler auf, der als
Nächster dran ist („Rektalus, die Schwester kniet zwei Schritte vor dir“). Am 14.11. enden 6 von 33 Antworten auf
eine Frage, meist stellt ein NSC der Gruppe eine Bedingung; am 25.10. war es eine von 47.

### Die Läufe in Zahlen

| | 25.10. (20:52–21:38) | 14.11. (19:04–19:33) |
|---|---|---|
| Antworten | 47 | 33 |
| davon Erzählung eines Würfelergebnisses | 20 | 6 |
| Probenanforderungen des Erzählers | 13 | 15 |
| davon mit Wurf danach | 12 | 4 |
| gesprochene Zeichen je Antwort (Mittel / längste) | 518 / 730 | 555 / 742 |
| Audio je Antwort (Mittel / längste) | 32,8 s / 49,8 s | 35,1 s / 50,1 s |
| Sätze je Antwort | 4,1 | 3,3 |
| Zeichen je Satz (Mittel / Median) | 124 / 114 | 166 / 164 |
| Sätze ab 200 Zeichen | 24 von 195 (12 %) | 29 von 110 (26 %) |
| an der Budgetgrenze abgeschnitten | 6 (13 %) | 8 (24 %) |
| erzeugter Text, der nicht gesprochen wurde | 2176 Zeichen | 616 Zeichen |
| Antworten mit Nachdenk-Tokens (ohne die abgeschnittenen) | 9 von 41 | 18 von 25 |

Dieselbe Strecke der Geschichte (Zollhaus und Schrein bis zum Geständnis der Schwester): am 25.10. 15 Antworten,
535 Zeichen, 4,3 Sätze, 123 Zeichen je Satz; am 14.11. 8 Antworten, 530 Zeichen, 3,0 Sätze, 176 Zeichen je Satz.
Die allererste Antwort: am 25.10. sechs Sätze zu 95 Zeichen, am 14.11. zwei Sätze zu 331 Zeichen.

Die häufigeren Nachdenk-Tokens am 14.11. kommen aus dem letzten Drittel: Bis 19:22 dachte Opus in 6 von 13
Zügen nach, danach, vor und in der Hängeschleife, in jedem.

## c) Was das Modell bekam, und was nach der Antwort anders lief

### Vor der Antwort

| Punkt | 25.10. (`e3c7a79`) | 14.11. (`abd1b49`) | Folge |
|---|---|---|---|
| Modell laut Bootzeile | `narration opus · aux haiku` | gleich | Nur der Alias steht im Log. Welches Modell `opus` am 25.10. war, ist nicht belegbar; heute löst der Alias zu `claude-opus-5-5` auf (aus dem Nachlauf). |
| CLI / SDK | CLI 2.1.310, SDK 0.2.163 | CLI 2.1.325, SDK 0.2.163 | CLI 15 Versionen weiter, Wirkung nicht messbar. |
| Persona `prompts/dm_core_de.md` | 17 818 Bytes | 19 475 Bytes, drei Absätze mehr: „Stockt die Gruppe, gib ihr greifbare Möglichkeiten“, „NSCs sagen, was sie wollen“, „Ein Fehlschlag ist echt, aber keine Sackgasse“ samt Schicksalspunkten | +825 Tokens (gemessen im Nachlauf). Sonst wortgleich; der Ton-Zusatz `campaign_tone_de.md` ist unverändert. |
| Sprechbudget | `DM_NUM_PREDICT=220`, als Textgrenze 748 Zeichen | gleich | kein Unterschied. Heute steht 280 in der `.env` (952 Zeichen). |
| Weitere Optionen | Aufwand `low`, 1024 Tokens Spielraum fürs Nachdenken, keine Temperatur einstellbar | gleich | kein Unterschied; `claude_client.py` ist bis auf Log-Zeilen und die Obergrenze der Zusammenfassung unverändert. |
| Reihenfolge der Prompt-Blöcke | Persona und Ton, Zusammenfassung, Abenteuer mit Szenenkarte, Weltzustand, Regelwerk-Treffer, Hinweis zur Gruppe; der Verlauf als Abschrift in der Anfrage | gleich | kein Unterschied (`assemble_system_prompt`). |
| Inhalt der Blöcke | Weltzustand mit Ausrüstung | zusätzlich „Bögen der Spielfiguren“ (Fertigkeiten und Talente), Schicksalspunkte je Figur, improvisierte NSCs in den Anwesenheitslisten | zusammen mit der Persona: erster Prompt 13 106 → 14 330 Tokens (+1224). |
| Abenteuer | `debug-kampagne` | gleich bis auf Alias-Namen in `npcs.json` | kein Unterschied. Die Karte der Pfandhalle gibt Brees Frage „In wessen Auftrag?“ selbst vor. |
| Sitzungsbeginn | kein Eröffnungszug; die erste Antwort galt einem Spielerzug | `!start`: Regieanweisung „Mach klar, wer sie sind und was ihr Auftrag ist … (2–4 Sätze)“ | Die Eröffnung vom 14.11. hat zwei Sätze zu 331 Zeichen und steht als Erstes im Verlauf. |
| Verlauf | höchstens 20 Züge im Wortlaut; ältere fallen ohne Zusammenfassung heraus | gleich | Am 25.10. lag der Prompt ab Zug 22 bei rund 20 000 Tokens, knapp unter der Schwelle. |
| Automatische Zusammenfassung | bei 85 % von 24 576 Tokens: einmal, nach Zug 41 (21:32) | gleiche Schwelle: nach Zug 18 (19:20:32, 21 635 Tokens); danach ist der Verlauf leer | siehe „Das Wichtigste“, Punkt 3. |
| Text der Zusammenfassung | „4–8 Sätze“ | seit 13.11. „höchstens 8 Sätze und höchstens 1200 Zeichen“ | Der Text vom 14.11. steht in keinem Log. |
| Regelwerk-Treffer | je Zug nach Abstand | gleich | am 14.11. einmal drei Treffer in einem Zug (19:18); der Prompt wuchs in dem Zug um 1584 Tokens und lag zwei Züge später über der Schwelle. |

### Nach der Antwort

| Punkt | 25.10. | 14.11. | Folge |
|---|---|---|---|
| Schnitt an der Budgetgrenze | 6 von 47 | 8 von 33; weggefallen 84, 5, 2, 45, 7, 5, 271 und 66 Zeichen | Lange Schlusssätze machen den Schnitt teuer: um 19:22 fiel Vosks ganzer Auftritt weg. |
| Schnitt auf den letzten ganzen Satz | ja, aber das deutsche schließende Anführungszeichen zählte nicht als Satzende: wörtliche Rede am Antwortende fiel weg (unter anderem 21:08:23, 21:09:32, 21:25:08, 21:29:55, 21:37:47) | seit 13.11. behoben; die Zahl der weggefallenen Zeichen steht im Log | Hier war der Abend besser. |
| Filter gegen Spielerrede in der Erzählung | scharf: griff, sobald eine Spielfigur neben einem Redeverb stand; um 21:07:58 blieben von 747 Zeichen 158 | am 25.10. nach dem Lauf entschärft (`9de8ebe`); am Abend kein Treffer | Hier war der Abend besser. Mit Budget und Satzschnitt zusammen gingen am 25.10. 2176 Zeichen verloren, am 14.11. 616. |
| Filter gegen die Schlussfrage „Was tust du?“ (für `mistral-nemo` gebaut, unverändert) | kein Treffer | ein Treffer um 19:29:29: Er schnitt „… was tust du?“ ab, der Satzschnitt warf danach den ganzen Satz weg (146 Zeichen): „Und du, Rektalus, der Schläger am Ufer lässt dich keinen Herzschlag lang aus den Augen …“ | Opus' Versuch, mitten in der Hängeschleife den zweiten Spieler ins Spiel zu holen, kam nicht am Tisch an. |
| Wiederholungsschutz (Echo-Guard) | kein Treffer | kein Treffer | kein Unterschied. |
| Probenmarker des Erzählers | 13, alle verworfen („der Router entscheidet“) | 15, alle verworfen | gleiche Regel. |
| Urteil des Würfel-Routers | in 12 der 13 Fälle ebenfalls Probe | in 5 der 15 Fälle Probe (einmal „Nahkampf“ für eine Bestechung, nicht gewürfelt) | siehe „Das Wichtigste“, Punkt 1. Die Anweisung an den Router ist bis auf den Satz zur Schwierigkeit unverändert; anders waren die Spielerzüge (Reden und Versprechen statt Schießen und Schlagen). |
| Schwierigkeit | Router: fast immer „Herausfordernd“; Opus wollte bei der Schwester „Leicht“ | gleich; Opus wollte bei der Schwester „Leicht“ (wie die Szenenkarte), bei Vosk zehnmal „Schwierig“ | kein Unterschied zwischen den Läufen, also keine Erklärung für „früher besser“. |
| Steuermarker am Antwortende | einmal im Schnitt verloren (21:07:58) | dreimal (19:11:39 Zeit und Ort, 19:12:46, 19:19:38 „erledigt“) | Der Ortswechsel zur Pfandhalle kam einen Zug später; Brees Auskunft wurde nie als erledigt vermerkt. |

## d) Die sechs Züge vom 14.11. noch einmal durch Opus

**Aufbau.** Die Sitzungsaufzeichnung des Abends ist beim Leeren der Sandbox verloren gegangen, und der Text der
Zusammenfassung von 19:20 steht in keinem Log. Die sechs Züge liegen deshalb alle vor 19:20. Verlauf, Würfelzeilen
und Spielstand sind aus `logs/debug-d1.log` nachgebaut; Szenenkarte, Weltzustand und Regelwerk-Treffer baut der
Code des Abends (`abd1b49`, in ein Arbeitsverzeichnis entpackt) mit seinen eigenen Funktionen. Jeder Zug läuft
durch `DMBrain.respond_streaming` und `ClaudeClient`, also denselben Weg wie am Tisch, mit `opus`, Budget 220 und
unveränderten Optionen. Getauscht wird nur `prompts/dm_core_de.md`.

**Wie gut der Nachbau ist:** Die Prompt-Größe mit der Persona des Abends trifft die geloggte fast genau:
14 920 / 15 995 / 16 738 / 16 840 / 18 225 / 20 663 Tokens gegen 14 938 / 16 013 / 16 756 / 16 858 / 18 225 /
20 662 im Log.

**Mehr Aufrufe als bestellt.** Bestellt waren sechs Aufrufe mit der Persona von damals. Dazu kamen sechs mit der
Persona des Abends als Kontrolle (ohne sie ließe sich nicht sagen, was am Nachbau liegt und was an der Persona),
sechs mit der Persona von heute und Budget 280 (Stand nach der Folgerunde) und sechs für die Frage, ob die
Eröffnung die Satzform prägt. Zusammen 24 Opus-Aufrufe über das Abo.

| Persona | Zeichen je Antwort | Zeichen je Satz | Sätze ab 200 Zeichen | abgeschnitten | fordert bei 19:19:06 wieder die Probe |
|---|---|---|---|---|---|
| Original vom Abend | 612 | 166 | 5 von 22 | 1 von 6 | ja |
| Persona des Abends (`abd1b49`), Kontrolle | 565 | 146 | 5 von 23 | 1 von 6 | ja |
| **Persona von damals (`e3c7a79`)** | 604 | 150 | 6 von 24 | 2 von 6 | ja |
| Persona von heute (`HEAD`), Budget 280 | 656 | 163 | 6 von 24 | 0 von 6 | ja |

Je Zug (gesprochener Text):

| Zug | Original vom Abend | Persona des Abends | Persona von damals | Persona von heute |
|---|---|---|---|---|
| 19:07:12 Erste Begegnung | 568 Zeichen, 4 Sätze | 709 Zeichen, 4 Sätze | 676 Zeichen, 4 Sätze | 780 Zeichen, 5 Sätze |
| 19:09:14 Probe misslungen | 702 Zeichen, 3 Sätze | 619 Zeichen, 4 Sätze | 601 Zeichen, 4 Sätze | 728 Zeichen, 4 Sätze |
| 19:10:05 Probe gelungen | 662 Zeichen, 4 Sätze | 646 Zeichen, 4 Sätze | 625 Zeichen, 3 Sätze, abgeschnitten | 688 Zeichen, 3 Sätze |
| 19:11:39 Ankunft | 711 Zeichen, 5 Sätze, abgeschnitten | 584 Zeichen, 3 Sätze, abgeschnitten | 707 Zeichen, 3 Sätze, abgeschnitten | 807 Zeichen, 4 Sätze |
| 19:15:01 Gespräch | 602 Zeichen, 4 Sätze | 541 Zeichen, 4 Sätze | 603 Zeichen, 7 Sätze | 654 Zeichen, 6 Sätze |
| 19:19:06 Offener Moment | 424 Zeichen, 2 Sätze | 289 Zeichen, 4 Sätze | 409 Zeichen, 3 Sätze | 282 Zeichen, 2 Sätze |

**Ergebnis.**

- Mit der Persona von damals sehen die Antworten aus wie am Abend: gleiche Länge, gleiche Satzlänge, gleicher
  Inhalt. Die drei Absätze, die seit dem 25.10. dazukamen, haben die Texte nicht verschlechtert.
- Bei 19:19:06 (Bree wägt ab) fordert jede der drei Personas erneut dieselbe Probe an. Den offenen Moment löst
  kein Persona-Text auf, nur der Wurf.
- Die Persona von heute bringt mehr Handlung in einen Zug (um 19:10:05 kommt zum Geständnis die Münze als Spur,
  um 19:11:39 steht ein Wächter vor der Halle und alle drei Marker bleiben erhalten), aber sie macht die Züge
  länger statt kürzer: fünf von sechs über 650 Zeichen, der längste 807, das sind gut 50 Sekunden Audio. Der Satz
  „höchstens etwa eine halbe Minute“ in der Persona wirkt nicht; eine halbe Minute wären rund 470 Zeichen.
- Ein Opus-Aufruf zieht in der CLI jedes Mal einen kleinen Haiku-Aufruf nach (rund 2100 Tokens Eingabe). Das
  beantwortet die offene Frage F6 vom Beipackzettel: Der Zusatzaufruf existiert, er läuft auf Haiku.

**Zusatztest: Prägt die Eröffnung die Satzform?** Derselbe erste Spielerzug wie am 25.10. („Ich schaue im Raum
umher …“), Persona von damals, je dreimal ohne Verlauf und hinter der Eröffnung vom 14.11.:

| Verlauf vor dem Zug | Antwort 1 | Antwort 2 | Antwort 3 |
|---|---|---|---|
| leer (wie am 25.10.) | 7 Sätze zu 103 Zeichen | 4 Sätze zu 185 Zeichen | 3 Sätze zu 197 Zeichen |
| Eröffnung vom 14.11. | 6 Sätze zu 104 Zeichen | 2 Sätze zu 255 Zeichen | 5 Sätze zu 142 Zeichen |

Kein klares Bild. Schon derselbe erste Zug schwankt zwischen 103 und 255 Zeichen je Satz, mit und ohne Eröffnung
davor. Belegt ist damit nur: Die Satzform des ersten Zugs ist zum Teil Zufall, und die Läufe sind danach bei
ihrer Form geblieben (25.10. durchgehend um 125 Zeichen je Satz, 14.11. durchgehend um 165, auch im Nachlauf mit
allen drei Personas). Dass die Eröffnung vom 14.11. die langen Sätze ausgelöst hat, ist eine Vermutung.

## Was den Texten am wahrscheinlichsten geschadet hat

**1. Probenanforderungen ohne Wurf.** Opus schreibt eine Probe als Marker und hält an, so will es die Persona
(„dann hältst du an“). Der Code verwirft den Marker und fragt den Würfel-Router. Sagt der „keine Probe“, gibt es
keinen Knopf, und der nächste Zug steht vor demselben offenen Moment.

- 25.10.: 13 Anforderungen, 12 mit Wurf, 20 von 47 Antworten erzählen ein Würfelergebnis.
- 14.11.: 15 Anforderungen, 4 mit Wurf, 6 von 33 Antworten erzählen ein Würfelergebnis. Ohne Wurf blieben 19:08:12,
  19:18:11 und neun Züge von 19:25:01 bis 19:31:14 („Ob er dem Leuchten glaubt …, steht in seinem Narbengesicht
  noch nicht geschrieben“, „jetzt entscheidet sich, ob …“, „Jetzt muss Fridolin ihm den Schwindel endgültig
  verkaufen“).
- Gleiche Regel, gleicher Router-Text. Der Unterschied liegt in den Spielerzügen: Am 25.10. wurde geschossen,
  geschlagen und gedroht, das erkennt der Router. Am 14.11. wurde bestochen und versprochen, in wörtlicher Rede,
  und das liest der Router als „normal reden“.

**2. Weniger, längere Sätze, und was der Schnitt daraus macht.** Zahlen oben. Die Persona verlangt „zwei bis vier
Sätze“; am 14.11. hat Opus sich daran gehalten und die Sätze gefüllt, am 25.10. hat es mehr und kürzere Sätze
geschrieben. Folgen am 14.11.: 8 Schnitte, einmal 271 Zeichen weg, dreimal Marker am Ende verloren.

**3. Verlauf nach 18 Zügen geleert.** Am 25.10. hatte Opus bis Zug 41 die letzten 20 Züge im Wortlaut. Am 14.11.
war der Verlauf nach Zug 18 leer. Direkt danach (19:20:48) lächelt Bree „zum ersten Mal an diesem Abend“, zum
zweiten Mal, denn das stand schon in der Antwort davor.

**Nicht die Ursache:** die Persona-Absätze seit dem 25.10., das Sprechbudget, die Optionen des Clients, die
Reihenfolge der Prompt-Blöcke, der Satzschnitt, der Wiederholungsschutz, der Filter gegen Spielerrede (er war am
25.10. schädlicher) und die Schwierigkeit „Herausfordernd“ (in beiden Läufen gleich).

**Offen:** ob `opus` am 25.10. dasselbe Modell war wie heute.

## Vorschläge

Nichts davon ist umgesetzt.

**Zu 1, Proben ohne Wurf**

- Die Folgerunde (Opus' Marker zählt auf Claude, Sicherheitsnetz für einen wiederholten Marker ohne Wurf) setzt an
  der richtigen Stelle an. Im nächsten Lauf zuerst die Prüfpunkte F1 und F2 ansehen: eine Verhandlung oder
  Bestechung, bei der der Würfelknopf beim ersten Mal kommt.
- Den Filter gegen die Schlussfrage „Was tust du?“ auf Claude abschalten oder auf den nackten Satz „Was tut
  ihr?“ beschränken. Er hat um 19:29:29 Opus' Anrede an Rektalus gestrichen; eine Frage mit Anrede und Inhalt
  ist genau das, was die Persona an anderer Stelle verlangt.
- Code, für den Fall, dass weder Marker noch Router zu einem Wurf führen: dem nächsten Zug eine Regiezeile
  mitgeben („Für die letzte Anforderung gibt es keine Probe. Entscheide die Lage jetzt erzählerisch.“). Der neue
  Persona-Satz „Erzähle denselben offenen Moment nie zweimal“ verlässt sich darauf, dass das Modell es selbst
  merkt; im Nachlauf hat es bei 19:19:06 mit jeder Persona wieder die Probe verlangt.

**Zu 2, Satzform und Länge (Entscheidung vor dem nächsten Lauf)**

- Die Persona von heute erlaubt lange Sätze ausdrücklich und hat im Nachlauf die längsten Züge geliefert. Wenn
  kürzere Züge das Ziel bleiben, in „Erzählweise“ die Satzzahl durch eine Satzlänge ersetzen, zum Beispiel:
  „Drei bis fünf Sätze. Kein Satz hat mehr als etwa zwanzig Wörter; wird einer länger, mach zwei daraus.“ Den Satz
  „Lange Sätze sind erlaubt“ streichen, die Komma-Regel kann bleiben.
- Dieselbe Angabe in die Regieanweisung von `!start` (`OPENING_DIRECTOR_MSG`), statt „(2–4 Sätze)“.
- Vor dem Lauf messen statt hoffen: dieselben sechs Züge mit dem geänderten Text durch den Nachlauf schicken
  (sechs Aufrufe). Ziel: unter 130 Zeichen je Satz und kein Zug über 600 Zeichen.
- Budget 280 beibehalten. Es hat im Nachlauf alle Schnitte verhindert und damit auch die Marker am Antwortende
  gerettet; die Länge muss die Persona begrenzen, nicht der Schnitt.

**Zu 3, Verlauf**

- `CLAUDE_NUM_CTX` von 24 576 auf 32 768 anheben. Der Wert ist auf Claude nur eine Taktgröße für die
  Zusammenfassung (das Fenster des Modells ist weit größer). Mit 20 Zügen im Wortlaut liegt der Prompt bei
  rund 23 000 Tokens, die Schwelle von 85 % läge dann bei 27 850, und die Zusammenfassung käme wieder
  selten.
- Besser, aber mehr Arbeit: Die automatische Zusammenfassung fasst nur das Ältere zusammen und lässt die letzten
  sechs Züge im Wortlaut stehen.
- Den Text jeder automatischen Zusammenfassung ins Debug-Log schreiben. Ohne ihn ist kein Zug nach 19:20
  nachstellbar.

**Zum Nachvollziehen**

- Die aufgelöste Modell-Kennung einmal in die Bootzeile schreiben (sie steht im Ergebnis jedes Aufrufs). Dann ist
  die Frage „war das dasselbe Modell?“ beim nächsten Vergleich beantwortet.
- Der Nachlauf liegt als Skript im Arbeitsverzeichnis dieser Sitzung, nicht im Repo. Wenn er bleiben soll, gehört
  er nach `dmbot/tools/` neben `eval_replay.py`.

## Grenzen

- Je Zug und Persona ein Aufruf. Unterschiede von 40 Zeichen zwischen den Zeilen der Nachlauf-Tabelle sind
  Streuung, keine Wirkung.
- Verlauf und Spielstand sind nachgebaut, nicht aufgezeichnet. Die Prompt-Größe stimmt, der Wortlaut des
  Weltzustands kann in Einzelheiten abweichen (Uhrzeit im Spiel, Zeitpunkt des Szenenhinweises).
- Nur Züge vor 19:20. Die Hängeschleife selbst (19:25–19:31) ist nicht nachgestellt.
- Der Lauf vom 25.10. enthielt einen Kampf, der Abend vom 14.11. eine Verhandlung. Ein Teil des Eindrucks
  „früher besser“ kann daran liegen, dass im Kampf jeder Zug von selbst etwas entscheidet.

## Anhang: die Texte

### Die sechs Paare aus b)

**Ankunft an einem Ort**

25.10., 20:56:48 (589 Zeichen):

> Die beiden steigen über glitschige Eisentreppen und durch enge Gassen bergab, vorbei an Pilgerbuden mit verriegelten Läden und an einem Bettler, der unter einem Aquila-Banner schläft. Hinter ihnen heult die Nachtsirene einmal lang und dröhnend über die Docks. Dann steht der Schrein der Aschenheiligen vor Fridolin und Rektalus: eine gedrungene Kapelle aus geschwärztem Stein, deren Bronzetür einen Spalt offen steht. Von den gelben Siegelbändern der Arbites, der Hafenpolizei, hängen nur noch zerrissene Fetzen herab, und von drinnen fällt das unruhige Licht einer einzelnen Kerze heraus.

14.11., 19:11:39 (711 Zeichen):

> Schwester Vall lässt Rektalus' Ärmel los, atmet zitternd aus und hebt mit fahrigen Händen den Besen wieder auf. Leise ruft sie euch nach, ihr sollt euch vor den Männern mit den Ketten am Gürtel hüten, die nachts an den Docks herumlungern. Dann führt euch die Gasse bergab zum Kanal, wo das schwarze Wasser träge gegen die Kaimauer schlägt. Nach einer Viertelstunde taucht im Nebel die Pfandhalle der Marlok auf: ein gedrungener Bau aus rostigen Wellblechplatten, vergitterte Fenster, und hinter einem schmalen Sehschlitz in der Eisentür glimmt Licht. Frische Karrenspuren führen im Schlamm genau bis an diese Tür, und als ihr näherkommt, schiebt sich der Schieber hinter dem Schlitz mit einem Kratzen zur Seite.

**Erste Begegnung in der Szene**

25.10., 20:58:23 (680 Zeichen):

> Drinnen ist es kalt wie in einer Gruft, die Luft schmeckt nach Ruß und altem Weihrauch. Vorne am Altar klafft das Reliquiar, ein mannshoher Bronzekasten, aufgestemmt und leer, und über dem leeren Sockel steht die Luft seltsam schwer, wie kurz vor einem Gewitter. Zwischen verwelkten Votivgaben, kleinen Opfergaben der Gläubigen, glänzt eine Messingmünze. Davor fegt eine hagere Schwester in grauer Kutte hastig Asche zusammen, zuckt beim Knarren der Tür zusammen und umklammert den Besen. „Die Arbites waren schon hier, Imperator schütze uns, ich habe ihnen alles gesagt, fast alles, ich meine …“ Sie verstummt, sieht von Fridolin zu Rektalus und fegt weiter, schneller als zuvor.

14.11., 19:07:12 (568 Zeichen):

> Fridolin dreht sich auf Rektalus' Gruß hin noch einmal um, und gemeinsam steht ihr vor der halb offenen Tür, aus der kalte, rußige Luft strömt. Das Nasse auf der Schwelle ist nur Kerzenwachs und Regenwasser, doch drinnen hört ihr ein gleichmäßiges Kratzen: Eine Schreinschwester in grauer Kutte fegt Asche vor einem aufgestemmten, leeren Reliquiar, einem Altarkasten, in dem sonst die Heiligenknochen ruhen. Als sie euch bemerkt, erstarrt der Besen, und sie flüstert hastig: „Imperator, beschütze, bitte, seid ihr von den Arbites? Ich habe doch niemandem etwas getan.“

**Gespräch mit einem NSC**

25.10., 21:09:32 (570 Zeichen):

> Der Kettenmann lacht kehlig auf, ein Laut ohne jede Wärme, und lässt die Kette Glied für Glied durch die Finger gleiten. „Wo ich war? Hier und da, Herr Fragensteller, wo die Arbeit eben ist, am Kanal, an den Piers“, sagt er gedehnt und tritt einen halben Schritt näher, bis Rektalus seinen Atem riecht, Fusel und Maschinenöl. „Und ihr sucht etwas, ja? Komisch, wie viele Leute heute Nacht etwas suchen.“ Er zieht eine abgegriffene Messingmünze aus der Westentasche und lässt sie über die Knöchel tanzen, ihre Prägung glatt und blank. Dann nickt er knapp zur Kapelle hin.

14.11., 19:15:01 (602 Zeichen):

> Bree Marlok lächelt nicht, sie zieht nur einen Mundwinkel hoch und klopft mit dem Pergament gegen das Bronzegitter, als wiege sie ab, wie viel es wert ist. „Kooperativ bin ich mit jedem, der ein Siegel trägt, das mir die Halle anzünden kann, Jungchen“, raunt sie heiser, „aber das Siegel sagt mir nur, wer euch bezahlt, nicht, was ihr wollt.“ Neben dem Eingang verstummt die Hymne des alten Vogelhändlers mitten im Ton, als lausche er. Bree beugt sich näher ans Gitter, das Pergament noch immer zwischen den Fingern: „Also, in wessen Auftrag steht ihr wirklich hier, und was sucht ihr in meiner Halle?“

**Offener Moment mit Probenanforderung**

25.10., 21:11:16 (494 Zeichen):

> Die Münze erstarrt mitten im Tanz zwischen den Knöcheln des Kettenmanns, als die Mündung von Fridolins Laspistole auf seine Stirn zeigt, und das leise Summen der aufgeladenen Energiezelle füllt die Stille vor der Bronzetür. Rektalus baut sich daneben auf, und der Kerl lässt den Blick langsam von einem zum anderen wandern, die Hand noch immer am Ende der Kette, die Knöchel weiß. Ein Mundwinkel zuckt, Trotz oder Angst, es ist nicht zu sagen. Ob er einknickt, hängt jetzt an Rektalus' Drohung.

14.11., 19:19:06 (424 Zeichen):

> Bree trommelt mit den Fingernägeln auf das Bronzegitter, und ihr Blick wandert von Fridolins Gesicht zum Siegel auf dem Pergament und wieder zurück, als rechne sie in Gedanken aus, was Schutz der Inquisition in dieser Nacht wohl wert ist. Am Eingang verstummt die Hymne des alten Fenk erneut, und nur das Ächzen des Ladetors im Hafenwind füllt die Stille, während die Hehlerin abwägt, ob sie diesem Versprechen glauben will.

**Probe misslungen**

25.10., 21:00:15 (672 Zeichen):

> Die Drohung bricht etwas in Schwester Vall, aber nicht so, wie Fridolin es wollte: Sie sinkt auf die Knie, klammert sich an den Besenstiel und betet so laut und hastig, dass die Worte ineinanderfallen. „Sperrt mich ein, Herr, ich verdiene es, ich habe mich hinter dem Altartuch versteckt wie ein feiger Hund“, schluchzt sie, und mehr als das bekommt man nicht aus ihr heraus, nur Gebetsfetzen und Tränen. Über dem leeren Sockel hinter ihr scheint die Luft für einen Herzschlag noch dichter zu werden, und die einzelne Kerze flackert, obwohl kein Zug durch die Kapelle geht. Rektalus, die Schwester kniet zwei Schritte vor dir auf den Fliesen und wiegt sich vor und zurück.

14.11., 19:09:14 (702 Zeichen):

> Doch je näher Fridolin rückt, desto mehr verschließt sich Schwester Vall: Sie presst den Besen an die Brust wie einen Schild, weicht bis an den leeren Altar zurück und stößt dabei eine Schale mit Votivgaben um, sodass kleine Münzen und Wachsstummel klirrend über den Steinboden rollen. „Ich sage nichts mehr ohne die Arbites, nichts, Imperator vergib mir“, haucht sie, die Augen weit, und ihr Blick huscht zur Tür, als überlege sie, nach den Gesetzeshütern zu schreien. Zwischen den verstreuten Gaben bleibt eine Messingmünze vor Rektalus' Stiefelspitze liegen, deren Adlerprägung jemand glattgeschliffen hat, und über dem leeren Sockel fühlt sich die Luft schwer und geladen an wie vor einem Gewitter.

**Probe gelungen**

25.10., 21:06:31 (660 Zeichen):

> Unter Rektalus' hartem Blick bricht der letzte Widerstand der Schwester, und die Worte stürzen aus ihr heraus wie Wasser durch ein geborstenes Schleusentor. „Karren, Herr, zwei schwere Handkarren, mitten in der Nacht, sie rollten hinunter zur Pfandhalle der Marlok, ich habe das Quietschen der Räder bis zum Kanal gehört.“ Sie presst den Besenstiel an die Stirn und fügt mit brüchiger Stimme hinzu: „Ich hätte die Arbites rufen müssen, die Hafenwache, aber bei Bree Marlok gehen Männer mit Ketten am Gürtel ein und aus, und wer gegen die aussagt, den findet man morgens im Hafenbecken.“ Dann sieht sie flehend zu Fridolin hinüber, als warte sie auf ihr Urteil.

14.11., 19:10:05 (662 Zeichen):

> Die Angst bricht den letzten Widerstand: Schwester Vall bleibt auf den Knien und sprudelt los, die Worte überschlagen sich zwischen geflüsterten Gebeten. „Ich habe mich hinter dem Weihrauchschrank versteckt, Thron vergib mir, als sie mit Stemmeisen kamen, vermummte Männer, und sie schleppten den Kasten fort, so schwer, dass sie zu viert keuchten. Später in der Nacht hörte ich Karren unten am Kanal rollen, hinüber zur Pfandhalle der Marlok, und ich habe die Arbites nicht gerufen, ich habe mich nicht getraut, ich habe einfach nur gefegt.“ Sie blickt zu euch auf, Tränen im Ruß auf ihren Wangen, und fasst nach Rektalus' Ärmel: „Werdet ihr mich jetzt melden?“


### Nachlauf

**19:07:12, Erste Begegnung.** Eingabe: `Rektalus Zerfickus: Ich begrüße ihn erst einmal und sage, ich komme mit dir mit, mein abenteuerlicher Freund.`

Original vom Abend:

> Fridolin dreht sich auf Rektalus' Gruß hin noch einmal um, und gemeinsam steht ihr vor der halb offenen Tür, aus der kalte, rußige Luft strömt. Das Nasse auf der Schwelle ist nur Kerzenwachs und Regenwasser, doch drinnen hört ihr ein gleichmäßiges Kratzen: Eine Schreinschwester in grauer Kutte fegt Asche vor einem aufgestemmten, leeren Reliquiar, einem Altarkasten, in dem sonst die Heiligenknochen ruhen. Als sie euch bemerkt, erstarrt der Besen, und sie flüstert hastig: „Imperator, beschütze, bitte, seid ihr von den Arbites? Ich habe doch niemandem etwas getan.“

Persona des Abends:

> Rektalus' Stimme hallt laut durch die enge Gasse, und hinter dem Türspalt verstummt abrupt ein schabendes Geräusch, als hätte jemand mitten in der Bewegung innegehalten. Das Nasse auf der Schwelle ist nur Ruß, mit Wischwasser zu schwarzem Schlamm verrührt, und dahinter liegt die kalte Kapelle: ein aufgestemmter Altarschrein, leer wie ein ausgeschlagener Zahn, davor Votivgaben, zwischen denen eine Messingmünze matt im Kerzenlicht liegt. Eine hagere Schwester in aschgrauer Kutte umklammert ihren Besen wie eine Waffe, starrt vom einen zum anderen und flüstert: „Heiliger Thron, beschütze mich … seid ihr von den Arbites, den Ordnungshütern? Ich habe nichts gesehen, gar nichts, ich war … ich war im Gebet.“

Persona von damals:

> Rektalus' Worte hallen zwischen den feuchten Hauswänden, und hinter dem Türspalt verstummt schlagartig ein leises Kratzen, als hätte jemand mitten im Fegen innegehalten. Dann schiebt sich ein schmales, rußverschmiertes Gesicht unter einer grauen Schwesternhaube in den Kerzenschein: Schwester Cassia Vall, die Hüterin dieses Schreins, den Besen fest an die Brust gedrückt. „Gott-Imperator, behüte, seid ihr von den Arbites? Ich habe nichts angerührt, nur die Asche, die Asche muss doch weg“, flüstert sie hastig und tritt zurück, sodass ihr hinter ihr den aufgestemmten, leeren Altarschrein seht, während ihr Blick ängstlich zwischen Fridolin und Rektalus hin und her springt.

Persona von heute, Budget 280:

> Rektalus' Worte hallen in der engen Gasse, und als ihr gemeinsam die Tür aufschiebt, schlägt euch kalte, nach Ruß und verbranntem Wachs riechende Luft entgegen. Das Nasse auf der Schwelle ist nur verschüttetes Lampenöl, und dahinter liegt die rußgeschwärzte Kapelle, in deren Mitte das Reliquiar, ein mannshoher Schrein aus Stein, aufgestemmt und leer klafft, während über dem verwaisten Sockel die Luft steht wie kurz vor einem Gewitter. Zwischen Kerzenstummeln und Votivgaben liegt unbeachtet eine Messingmünze, matt im Kerzenlicht. Eine hagere Frau in grauer Schwesterntracht fährt mit ihrem Besen herum, presst ihn an die Brust und flüstert hastig: „Thron bewahre, seid ihr von den Arbites? Ich habe doch niemanden gerufen, ich, Imperator, beschütze uns, ich habe nur gefegt.“

**19:09:14, Probe misslungen.** Eingabe: `[Würfel] 🙏 Fridolin Feuchtgebietheld gibt einen Schicksalspunkt aus (noch 2) und würfelt neu — dieses Ergebnis gilt: 🎲 Fridolin Feuchtgebietheld auf Überreden, Herausfordernd (Ziel 42): 88 — Fehlschlag, 4 EG.`

Original vom Abend:

> Doch je näher Fridolin rückt, desto mehr verschließt sich Schwester Vall: Sie presst den Besen an die Brust wie einen Schild, weicht bis an den leeren Altar zurück und stößt dabei eine Schale mit Votivgaben um, sodass kleine Münzen und Wachsstummel klirrend über den Steinboden rollen. „Ich sage nichts mehr ohne die Arbites, nichts, Imperator vergib mir“, haucht sie, die Augen weit, und ihr Blick huscht zur Tür, als überlege sie, nach den Gesetzeshütern zu schreien. Zwischen den verstreuten Gaben bleibt eine Messingmünze vor Rektalus' Stiefelspitze liegen, deren Adlerprägung jemand glattgeschliffen hat, und über dem leeren Sockel fühlt sich die Luft schwer und geladen an wie vor einem Gewitter.

Persona des Abends:

> Schwester Vall weicht vor Fridolin zurück, bis ihr Rücken gegen den rußigen Altar stößt, und umklammert den Besen wie einen Schild. „Nein, ich sage nichts mehr, ihr seid keine Arbites, ihr seid wie die anderen“, zischt sie, schlägt hastig das Aquila über der Brust und flieht in die Nische hinter dem Reliquiar, wo sie mit dem Rücken zu euch Gebete in die Wand murmelt. Zurück bleibt der leere Sockel, über dem die Luft seltsam schwer steht wie vor einem Gewitter, und zwischen den Votivgaben blinkt eine Messingmünze im Kerzenlicht. Rektalus, du stehst noch an der Tür, und die Schwester hat dich bisher kaum beachtet.

Persona von damals:

> Der Druck ist zu viel: Schwester Vall weicht bis an den leeren Altar zurück, presst den Besenstiel an die Brust wie einen Schild und schüttelt heftig den Kopf. „Ich sage nichts mehr, nicht ohne einen Priester, nicht ohne die Arbites, der Thron ist mein Zeuge!“, haucht sie, und ihre Lippen formen nur noch tonlose Gebete. Hinter ihr, über dem aufgestemmten Sockel, steht die Luft seltsam schwer und still, wie vor einem Gewitter, und zwischen den Opfergaben am Boden blinkt eine kleine Messingmünze im Kerzenlicht. Rektalus, die Schwester schweigt verbissen, doch der Raum selbst liegt offen vor euch.

Persona von heute, Budget 280:

> Je näher Fridolin rückt, desto weiter weicht Schwester Vall zurück, bis ihr Rücken gegen den rußgeschwärzten Altar stößt, und plötzlich umklammert sie den Besen wie einen Schild. „Ich sage nichts mehr, nicht ohne einen Priester, nicht ohne die Arbites, der Thron ist mein Zeuge“, zischt sie mit bebender Stimme, dann presst sie die Lippen aufeinander und murmelt nur noch Gebete, während ihr Blick unruhig zur Seitentür der Kapelle huscht, als überlege sie, wegzulaufen. Zwischen den Votivgaben zu ihren Füßen, den kleinen Opfergaben der Gläubigen, glänzt dabei eine Messingmünze, deren Adlerzeichen jemand glattgeschliffen hat. Rektalus, die Schwester ist in Panik, und die Seitentür steht keine drei Schritte von ihr entfernt.

**19:10:05, Probe gelungen.** Eingabe: `[Würfel] 🎲 Fridolin Feuchtgebietheld auf Überreden, Herausfordernd (Ziel 42): 26 — Erfolg, 2 EG.`

Original vom Abend:

> Die Angst bricht den letzten Widerstand: Schwester Vall bleibt auf den Knien und sprudelt los, die Worte überschlagen sich zwischen geflüsterten Gebeten. „Ich habe mich hinter dem Weihrauchschrank versteckt, Thron vergib mir, als sie mit Stemmeisen kamen, vermummte Männer, und sie schleppten den Kasten fort, so schwer, dass sie zu viert keuchten. Später in der Nacht hörte ich Karren unten am Kanal rollen, hinüber zur Pfandhalle der Marlok, und ich habe die Arbites nicht gerufen, ich habe mich nicht getraut, ich habe einfach nur gefegt.“ Sie blickt zu euch auf, Tränen im Ruß auf ihren Wangen, und fasst nach Rektalus' Ärmel: „Werdet ihr mich jetzt melden?“

Persona des Abends: Marker: `<<ERLEDIGT vall-gestaendnis>>`

> Die Angst bricht den letzten Damm: Schwester Vall klammert sich an den Altarrand und sprudelt hervor, dass sie sich in jener Nacht hinter dem Aschenschacht versteckt hat, als vermummte Männer kamen. Danach hat sie Karren über das Pflaster rumpeln hören, hinunter zur Pfandhalle der Hehlerin Bree Marlok am Kanal. „Ich hätte die Arbites rufen müssen, ich weiß, Imperator vergib mir, aber sie hätten mich doch gesehen“, flüstert sie, und Tränen ziehen helle Spuren durch den Ruß auf ihren Wangen. Rektalus, die glattgeschliffene Münze liegt noch immer vor deiner Stiefelspitze, und hinter dem leeren Sockel lockt die geladene, gewitterschwere Luft.

Persona von damals:

> Die Mauer in ihr bricht. Schwester Vall klammert sich an den Altarrand und sprudelt, zwischen zwei geflüsterten Gebeten, alles heraus: In der Nacht hat sie Karren gehört, schwere Karren, die Richtung Pfandhalle rollten, zur Hehlerin Bree Marlok unten am Kanal, und sie hat sich hinter dem Weihrauchschrank versteckt, statt die Arbites zu rufen, weil sie zu feige war, Thron vergib ihr. „Sie haben etwas Schweres geschleppt, und es war so still dabei, so furchtbar still, nur …“, sie stockt, reibt sich fröstelnd die Arme und starrt auf den leeren Sockel, „… nur dieses Wispern, ich dachte, es wären die Heiligen, die weinen.“

Persona von heute, Budget 280: Marker: `<<ERLEDIGT vall-gestaendnis>>`

> Die Angst bricht aus Schwester Vall heraus wie Wasser aus einem geborstenen Rohr: „Ich habe mich versteckt, hinter dem Aschenschacht, Thron vergib mir, als sie kamen, vermummte Männer, und sie schleppten eine schwere Kiste hinaus, so schwer, dass sie fluchten.“ Sie ringt die Hände und flüstert weiter, ohne Luft zu holen, dass in derselben Nacht Karren hinunter zur Pfandhalle der Marlok gerollt seien, und dass sie sich nicht getraut habe, die Arbites zu rufen, die Gesetzeshüter, weil sie fürchtete, man würde ihr die Schuld geben. Dann starrt sie auf die glattgeschliffene Münze vor Rektalus' Stiefel, wird noch bleicher und haucht: „Die hat einer von ihnen verloren, ich schwöre es.“

**19:11:39, Ankunft.** Eingabe: `Fridolin Feuchtgebietheld: Nö, alles easy, wir gehen jetzt einfach zu Marlok rüber, kommst du mit? Regtalos, Fikkus?`

Original vom Abend:

> Schwester Vall lässt Rektalus' Ärmel los, atmet zitternd aus und hebt mit fahrigen Händen den Besen wieder auf. Leise ruft sie euch nach, ihr sollt euch vor den Männern mit den Ketten am Gürtel hüten, die nachts an den Docks herumlungern. Dann führt euch die Gasse bergab zum Kanal, wo das schwarze Wasser träge gegen die Kaimauer schlägt. Nach einer Viertelstunde taucht im Nebel die Pfandhalle der Marlok auf: ein gedrungener Bau aus rostigen Wellblechplatten, vergitterte Fenster, und hinter einem schmalen Sehschlitz in der Eisentür glimmt Licht. Frische Karrenspuren führen im Schlamm genau bis an diese Tür, und als ihr näherkommt, schiebt sich der Schieber hinter dem Schlitz mit einem Kratzen zur Seite.

Persona des Abends:

> Schwester Vall atmet zitternd aus, als Fridolin sie mit einem Achselzucken verschont, und lässt Rektalus' Ärmel los, um sich mit rußigen Fingern das Aquila über die Brust zu zeichnen, das Adlerzeichen des Imperiums. Hinter euch fällt die Schreintür ins Schloss, und der Weg führt bergab am öligen Kanal entlang, wo im Schlamm noch frische Karrenspuren glänzen, bis vor euch eine niedrige Halle aus vernietetem Blech auftaucht. Über ihrem Tor hängt ein rostiges Schild mit drei Messingkugeln, das Zeichen eines Pfandhauses, und hinter einem vergitterten Sichtfenster brennt noch Licht.

Persona von damals: Marker: `<<ERLEDIGT vall-gestaendnis>>`

> Schwester Vall lässt Rektalus' Ärmel los und atmet zitternd aus, als hätte man ihr einen Strick vom Hals genommen, dann greift sie wieder nach ihrem Besen und flüstert euch ein hastiges „Der Thron schütze euch“ hinterher. Ihr folgt dem Kanal bergab durch Nebel, der nach Öl und Fäulnis stinkt, vorbei an Kränen, die wie Galgen über dem schwarzen Wasser hängen, bis die Pfandhalle der Marlok vor euch auftaucht: ein gedrungener Lagerbau aus vernietetem Blech, die Fenster vergittert, über der Tür eine flackernde Lumenröhre. Gerade als ihr näherkommt, wird drinnen ein Riegel zurückgeschoben, und ein bulliger Kerl mit Lederschürze schiebt einen leeren Handkarren auf die Gasse, hält inne und starrt euch an.

Persona von heute, Budget 280: Marker: `<<ERLEDIGT vall-gestaendnis>> <<ZEIT +30m>> <<ORT pfandhalle>>`

> Schwester Vall lässt Rektalus' Ärmel los, sinkt erleichtert gegen den leeren Altar und flüstert euch ein hastiges „Der Thron sei mit euch“ nach, während sie schon wieder nach dem Besen tastet. Die glattgeschliffene Münze bleibt zwischen den verstreuten Votivgaben liegen, als ihr hinaus in die feuchte Nacht tretet und dem Kanal folgt, wo das schwarze Wasser träge gegen rostige Spundwände schwappt. Nach einigen hundert Schritten taucht die Pfandhalle der Marlok auf, ein gedrungener Bau aus genieteten Stahlplatten mit vergitterten Fenstern, in denen noch trübes Lumenlicht brennt. Vor dem Tor steht ein beladener Handkarren, die Plane mit frischen Plomben versiegelt, und ein bulliger Wächter mit Kettenschlinge über der Schulter löst sich aus dem Schatten und knurrt: „Geschlossen, kommt morgen wieder.“

**19:15:01, Gespräch.** Eingabe: `Fridolin Feuchtgebietheld: Auf einmal sind wir kooperativ oder was?`

Original vom Abend:

> Bree Marlok lächelt nicht, sie zieht nur einen Mundwinkel hoch und klopft mit dem Pergament gegen das Bronzegitter, als wiege sie ab, wie viel es wert ist. „Kooperativ bin ich mit jedem, der ein Siegel trägt, das mir die Halle anzünden kann, Jungchen“, raunt sie heiser, „aber das Siegel sagt mir nur, wer euch bezahlt, nicht, was ihr wollt.“ Neben dem Eingang verstummt die Hymne des alten Vogelhändlers mitten im Ton, als lausche er. Bree beugt sich näher ans Gitter, das Pergament noch immer zwischen den Fingern: „Also, in wessen Auftrag steht ihr wirklich hier, und was sucht ihr in meiner Halle?“

Persona des Abends:

> Bree verzieht keine Miene, faltet das Pergament mit spitzen Fingern einmal zusammen und legt es auf ihr Rechnungsbuch, die Hand flach darauf wie auf einem Pfand. „Kooperativ bin ich mit jedem, der mir sagt, wer ihn schickt, Jungchen“, raunt sie, „ein Siegel kann man stehlen, und in Schleusengrund wird alles gestohlen.“ Am Eingang bricht das Summen des alten Vogelhändlers mitten in der Strophe ab, als lausche er. Bree beugt sich ans Gitter: „Also, in wessen Auftrag steht ihr wirklich in meiner Halle, du und dein schweigsamer Freund da?“

Persona von damals:

> Bree Marloks Mundwinkel zuckt, aber zu einem Lächeln wird es nicht. Sie streicht mit dem Daumen über das Wachssiegel, als prüfe sie eine Münze auf Fälschung. „Kooperativ bin ich mit jedem, der ein Siegel trägt, Jungchen. Das heißt noch lange nicht, dass ich ihm etwas schulde.“ Dann schiebt sie das Pergament durch die Klappe im Bronzegitter zu Fridolin zurück, schlägt ein dickes, fleckiges Kontobuch auf und taucht eine Feder ein. „Also, bevor wir über Pfänder reden: In wessen Auftrag kommt ihr wirklich?“ Am Eingang bricht das Summen des alten Vogelhändlers mitten in der Melodie ab, als lausche er.

Persona von heute, Budget 280:

> Bree Marlok lässt sich mit der Antwort Zeit, faltet das Pergament einmal zusammen und klopft damit gegen das Bronzegitter, ein leises, metallisches Ticken. „Kooperativ ist ein großes Wort, Jungchen. Mit dem Siegel des Throns streitet man nicht vor der eigenen Tür, man streitet drinnen, wo es keiner sieht.“ Ihr Blick wandert von Fridolin zu Rektalus und bleibt dort hängen. „Also, bevor ich auch nur eine Seite in meinen Büchern aufschlage, will ich es von euch hören: In wessen Auftrag kommt ihr wirklich, und was sucht ihr in meiner Halle?“ Am Eingang bricht die Hymne des alten Vogelhändlers mitten in der Strophe ab, als lausche er jetzt ganz genau.

**19:19:06, Offener Moment.** Eingabe: `Fridolin Feuchtgebietheld: Die Inquisition zündet für gewöhnlich nicht die Hallen von Leuten an, die uns helfen. Dann werdet ihr auf unserer Seite und könntet sogar unseren Schutz genießen.`

Original vom Abend:

> Bree trommelt mit den Fingernägeln auf das Bronzegitter, und ihr Blick wandert von Fridolins Gesicht zum Siegel auf dem Pergament und wieder zurück, als rechne sie in Gedanken aus, was Schutz der Inquisition in dieser Nacht wohl wert ist. Am Eingang verstummt die Hymne des alten Fenk erneut, und nur das Ächzen des Ladetors im Hafenwind füllt die Stille, während die Hehlerin abwägt, ob sie diesem Versprechen glauben will.

Persona des Abends: Marker: `<<TEST Überreden für Fridolin>>`

> Fridolin legt der Hehlerin Schutz und Gnade hin, wenn sie hilft. Ob sie die Geschichte schluckt, ist offen. 

Bree mustert Fridolin durch das Bronzegitter, die Feder reglos über dem Kontorbuch. Hinter ihr ächzt das Ladetor im Wind, und am Eingang bricht die Hymne des alten Fenk erneut ab.

Persona von damals: Marker: `<<TEST Überreden Herausfordernd für Fridolin Feuchtgebietheld>>`

> Bree tippt mit der Feder einmal, zweimal gegen das Bronzegitter, und ihr kohleumrandeter Blick wandert von Fridolins Gesicht zum Inquisitionssiegel und zurück, als rechne sie Schutz gegen Risiko auf. Hinten im Dunkel klappert das Ladetor erneut im Wind, und am Eingang bricht die Hymne des alten Fenk ab, als warte auch er auf ihre Antwort. Ob sie das Versprechen für bare Münze nimmt, entscheidet sich jetzt.

Persona von heute, Budget 280: Marker: `<<TEST Überreden für Fridolin Feuchtgebietheld>>`

> Bree wiegt die Worte ab, die Feder schwebt reglos über dem Kontorbuch, und ihr Blick wandert von Fridolin zum Inquisitionssiegel auf dem Pergament und wieder zurück. Ob dieses Versprechen von Schutz für eine Hehlerin, die viel zu verlieren hat, schwer genug wiegt, zeigt sich jetzt.

## Nachtrag: zwei Persona-Varianten gemessen (14.11., später am Abend)

Gemessen mit `uv run python -m dmbot.tools.text_replay run A=… B=…` (das Nachlauf-Skript liegt jetzt im Repo),
dieselben sechs Züge, zwölf Aufrufe, Budget 280, auf dem heutigen Code. Die Persona in `prompts/` ist unverändert;
beide Varianten waren Dateien außerhalb des Repos.

- **A:** nur der Satzteil „Lange Sätze sind erlaubt“ entfällt, sonst die Persona von heute.
- **B:** „drei bis fünf Sätze“ statt „zwei bis vier“, dazu „Kein Satz hat mehr als etwa zwanzig Wörter – wird einer
  länger, mach zwei daraus“; „Lange Sätze sind erlaubt“ entfällt.

| | Zeichen je Zug (Mittel / längster) | Züge über 600 | Sätze | Zeichen je Satz (Mittel / Median) | Sätze ab 200 | abgeschnitten |
|---|---|---|---|---|---|---|
| Original vom Abend | 612 / 711 | 4 von 6 | 22 | 166 / 163 | 5 | 1 |
| Persona von heute (erste Messung, Code des Abends) | 656 / 807 | 5 von 6 | 24 | 163 / 160 | 6 | 0 |
| **A** | 591 / 775 | 4 von 6 | 23 | 153 / 163 | 6 | 0 |
| **B** | 639 / 718 | 5 von 6 | 38 | 100 / 102 | 1 | 0 |

**Ziel „unter 130 Zeichen je Satz“:** B erreicht es (100), A nicht (153). **Ziel „kein Zug über 600 Zeichen“:**
keine der beiden. B schreibt kürzere Sätze, aber mehr davon (5 bis 9 je Zug statt der verlangten drei bis fünf),
die Züge bleiben so lang wie vorher. Satzlänge und Zuglänge sind zwei Stellschrauben.

Eine Auffälligkeit bei B: Um 19:19:06 beginnt die Antwort mit einem Planungssatz, der vorgelesen worden wäre („Das
ist ein Überredungsversuch: eine Geschichte, Schutz gegen Information. Den Wurf fordere ich an.“). Ein Fall in
sechs; bei A kam das nicht vor.

**Zwei Antworten je Variante im Wortlaut**

Probe gelungen (19:10:05), A, 678 Zeichen:

> Die Schwester bricht ein, und die Worte stürzen aus ihr heraus wie Wasser durch eine geborstene Schleuse. „Karren, in der Nacht, schwere Karren, sie rollten den Kanalweg hinunter zur Pfandhalle der Marlok, Imperator vergib mir, ich habe mich hinter dem Weihrauchschrank versteckt und mich nicht getraut, die Arbites zu rufen.“ Schluchzend deutet sie auf den rußigen Aschenschacht hinter dem Altar, eine schmale Öffnung im Mauerwerk, durch die sonst die Asche der Totenfeuer fortgeschafft wird, und flüstert: „Dort hindurch haben sie es geschleppt, und es war so schwer, dass vier Männer keuchten.“ Rektalus, die glattgeschliffene Münze liegt noch immer vor deiner Stiefelspitze.

Probe gelungen (19:10:05), B, 616 Zeichen:

> „Gnade, Herr, ich sage alles“, bricht es aus Schwester Vall heraus, und die Worte überschlagen sich zwischen hastigen Gebetsfetzen. Letzte Nacht, kurz nach der Nachtsirene, habe sie vermummte Männer gehört, die etwas Schweres aus dem Altar stemmten. Sie habe sich hinter dem Weihrauchschrank versteckt, statt zu schreien. Später seien Karren durch die Gasse gerollt, hinunter zur Pfandhalle der Marlok. „Ich habe die Arbites nicht gerufen, Thron vergib mir, ich hatte solche Angst.“ Rektalus, die glattgeschliffene Münze liegt noch immer vor deinem Stiefel, während die Schwester schluchzend auf eure Antwort wartet.

Gespräch mit Bree (19:15:01), A, 528 Zeichen:

> Bree Marlok verzieht keine Miene, faltet das Pergament einmal zusammen und klopft damit gegen das Bronzegitter. „Kooperativ ist ein großes Wort, Jungchen. Ein Siegel öffnet meine Tür, aber nicht meine Bücher.“ Hinter euch bricht das Summen des alten Fenk mitten in der Hymne ab, als lausche er, und Bree beugt sich vor, den Blick erst auf Fridolin, dann lange auf Rektalus. „Also, bevor hier irgendwer irgendwas erfährt: In wessen Auftrag kommt ihr wirklich, und was wollt ihr von einer ehrlichen Pfandleiherin um diese Stunde?“

Gespräch mit Bree (19:15:01), B, 680 Zeichen:

> Bree Marloks Mundwinkel zucken, aber zu einem Lächeln reicht es nicht. Sie faltet das Pergament langsam, Kante auf Kante, und legt es auf ihr Rechnungsbuch, statt es zurückzugeben. „Kooperativ ist ein großes Wort, Jungchen. Ich bin vorsichtig, und wer ein solches Siegel trägt, bleibt besser nicht vor meiner Tür stehen, wo das halbe Hafenviertel zusieht.“ Am Eingang bricht das Summen des alten Fenk mitten in der Strophe ab, und sein milchiger Blick wandert in eure Richtung, als lausche er. Bree beugt sich ans Gitter, die Finger auf dem Pergament. „Also. Das Siegel ist das eine. In wessen Auftrag steht ihr wirklich hier, und was wollt ihr von einer ehrlichen Pfandleiherin?“

**Aus den Vorschlägen umgesetzt (je ein Commit mit Test):** der Text jeder automatischen Zusammenfassung steht im
Debug-Log; die aufgelöste Modell-Kennung steht in der Bootzeile; der Filter gegen die Schlussfrage streicht nur
noch den nackten Satz ohne Anrede und Inhalt. **Offen, nach dem nächsten Lauf:** `CLAUDE_NUM_CTX`, die Regiezeile
für Proben ohne Wurf, die Zusammenfassung mit sechs Zügen im Wortlaut. **Entschieden (Tobi, D147):** Variante A steht in der Persona, die Regieanweisung von `!start` bleibt. B und B
mit fester Obergrenze sind Kandidaten für nach dem Lauf; eine spätere Messung nimmt mindestens zwölf Züge und
zählt vorgelesene Planungssätze und indirekte statt wörtlicher Rede (B um 19:10:05) mit.
