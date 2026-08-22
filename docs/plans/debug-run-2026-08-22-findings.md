# Findings — the debug-campaign run of 2026-08-22

The evidence base under [`coherent-campaign-run.md`](coherent-campaign-run.md). Section A is what
the four players said out loud during the session, quoted with timestamps; section B is what the
log shows without anyone having noticed at the table; section C is Tobi's own summary. The
findings are referenced by id (A1–A15, B1–B18) from the root-cause analysis.

Withdrawn after review: **B14's sibling claim** that the run left no `.debug` session artifacts on
disk — an artefact of where the analysis ran, not of the code. The evening happened on another
machine.

Kept deliberately: the things that worked. The dice chain routed and resolved three tests
correctly, the feedback protection filtered Bot A's voice at layer 1 as designed, and the campaign
content itself is sound. None of the evening's failures were dice or audio-loop failures.

---

Lauf: `DM_ADVENTURE=debug-kampagne` ("Die Mitternachtsfracht", 6 Szenen, 8 NPCs, testplan
aktiv), 4 Spieler (Timo/Sezgin/Vinnie/Pr0degie), mistral-nemo, XTTS, push_to_talk=True.
22 Turns in ~33 Minuten. Start 19:04, Abbruch des Pastes bei 19:37.

## A. Was die Spieler wörtlich kritisiert haben

A1. "Die ersten zwei Paragraphen, diese ganzen Fachbegriffe ... Chinesisch mit mir reden"
    (Timo 19:09) — das Intro ist unverständlich für Spieler ohne 40k-Vorwissen.
    Folge: Pr0degie hält danach 2 Minuten lang selbst einen Lore-Vortrag (19:11:35 + 19:11:52),
    d.h. ein Mensch musste die Aufgabe des DMs übernehmen.
A2. "Das hat schon wieder absolut mit nichts Null zu tun" / "Das ist der gleiche Absatz von
    oben" (Pr0degie + Vinnie 19:13) — turn=2 beschreibt einen generischen Raum
    (Schimmel/Moder/uralte Schriften) statt der Zoll-Sakristei und wiederholt Fridolins
    Flüster-Absatz aus dem Intro fast wörtlich.
A3. "Jetzt labert er schon wieder, das ist ich" (Pr0degie 19:20:51) / "Er redet einfach für
    dich oder was?" (Timo 19:21:29) — der DM spielt die Spielercharaktere: gibt ihnen
    Dialog, Motive und Handlungen in den Mund (Intro, turn=8, turn=12).
A4. "Der Bot denkt immer noch, dass wir alle Fridolinfeuchtgebietheld sind" (Timo 19:31:23)
    — keine Sprecher-Zuordnung; auf Nachfrage entschuldigt sich der DM meta ("Ich werde in
    Zukunft darauf achten") statt zu spielen.
A5. "Du sollst mal ein bisschen chillen mit diesem ganzen Zeitdruck" (Pr0degie 19:29:57) —
    Kaad sagt in 8 von 10 Antworten irgendeine Variante von "Die Zeit läuft uns davon" +
    "schaut demonstrativ auf seine Uhr".
A6. "Ist nicht schon vorhin eine Vollmacht gegeben?" (Pr0degie 19:31:18) — die in turn=7
    ausgehändigte Zollvollmacht existiert in turn=16 nicht mehr; Kaad verweigert sie erneut.
A7. "Du bist doch nicht am Marktplatz, du bist am Hafen" (Timo 19:33:56) — Spieler-Aktion
    erfindet Orte, der DM widerspricht nicht.
A8. "Aber ich dachte, Kaad ist ganz woanders" / "Der hat uns doch eigentlich alleine
    gelassen" (Timo + Vinnie 19:35:43) — Kaad ist in turn=4 gegangen, in turn=8/9 sind die
    Spieler am Hafen, und in turn=21 führt Kaad sie wieder durch die Zoll-Sakristei.
A9. "Was ist eigentlich unsere Mission?" (Vinnie 19:19:11), "Wissen wir überhaupt schon, was
    das Osarium ist?" (Sezgin 19:28:53) — nach 25 Minuten weiß niemand am Tisch, was das
    Zielobjekt ist. Auf direkte Nachfrage: "Das Ossarium ist ein heiliger Schrein" — eine
    Tautologie ohne Bild.
A10. "Der kann nicht mehrere Charaktere, mehrere Anweisungen, die miteinander reden,
    verarbeiten" (Timo 19:34:27) — mehrere gepufferte Spieleräußerungen pro Turn werden zu
    einer einzigen Antwort verschmolzen, meist nur die letzte beantwortet.
A11. "Wenigstens was, wo wir alle einen Plan von haben und nicht fucking Warhammer 40k, wo
    keiner einen Plan hat außer Tobi" (Timo 19:23:44) — Setting-Barriere; "dann verstehen
    wir doch gar nicht mal, ob der überhaupt Scheiße labert oder nicht" = die Debug-Kampagne
    kann ihren Zweck (Fehler erkennbar machen) für die Mitspieler nicht erfüllen.
A12. "Lasst halt so ein bisschen die Storyline folgen" (Sezgin 19:37:26) — die Gruppe
    bemerkt selbst, dass die Kiste (der einzige Hinweis) sofort wieder fallengelassen wird.
A13. "Das war's für heute, tschüss" (Whisper-Halluzination) wird als Spieleräußerung
    transkribiert; Timo verlangt, dass die Zwei-Satz-Kombination geblockt wird — die
    Einzelsätze stehen offenbar auf der Blockliste, die Kombination nicht.
A14. "Muss man auswählen oder erkennt der automatisch, wer dran ist?" (Timo 19:09:30) und
    "Irgendjemand muss auf diesen grünen Button drücken" (19:21:58) — Bedienmodell
    (push-to-talk, Würfelknopf) ist am Tisch nicht selbsterklärend; Timo drückt erst nach
    Aufforderung, Sezgin findet den Bot-Commands-Channel nicht.
A15. "Ich muss die Probe würfeln, deswegen" (19:18:01), "Du hast einen Erfolg, aber auch
    nicht" (19:18:13) — Würfelergebnis (16, Erfolg, 4 EG) und die erzählte Konsequenz
    stehen nicht erkennbar in Beziehung; 4 EG lesen sich wie 1 EG.

## B. Was im Log sichtbar ist, ohne dass es jemand ausgesprochen hat

B1. **Keine einzige Szene gewechselt.** 6 Szenen geladen, `start_scene`=zollhaus. Im ganzen
    Paste kein Szenenwechsel-Log, kein 🧪-Overlay-Eintrag nach dem Boot. Die Kampagne ist
    nie über Szene 1 hinausgekommen — obwohl die Spieler zweimal explizit den Raum verlassen
    haben (turn=4 "Wir gehen aus dem Raum raus", turn=8 "Ich verlasse den Raum in Richtung
    Hafen"). Der DM erzählt den Hafen, aber der State bleibt im Zollhaus. Daher A8.
2 Ebenen prallen aufeinander: Erzähl-Ort (Hafen) vs. State-Ort (zollhaus) — die Szenenkarte
    im Prompt bleibt die Sakristei, deshalb springt der DM immer wieder dorthin zurück.
B2. **Von 8 NPC-Statblocks spricht genau einer.** Kaad in 14 von 16 narrativen Antworten.
    Der einzige andere ist ein namenloser "Laufbursche von Kaad". Bree Marlok wird in turn=4
    genannt und nie wieder erwähnt — auch nicht, als die Gruppe nach einem Ansprechpartner
    sucht.
B3. **Turn 14 fehlt in der Latenz-Zählung** (11,12,13,15,...) — ein Turn ohne
    `[latency]`-Zeile. Ursache unklar, potenziell ein verworfener/abgebrochener Turn.
B4. **Meta-Bruch dreimal:** turn=3 "Es tut mir leid, aber ich kann Ihre Frage nicht
    verstehen" (ChatGPT-Stimme, Siezen!), turn=4 "In diesem Fall würde ich als Spielleitung
    antworten: ..." (Regieanweisung wird laut vorgelesen), turn=18 "Ich entschuldige mich für
    das Missverständnis." Dazu turn=19: "Sezgin, ich kann leider nicht offen nach dem
    Osarium fragen" — der DM redet als Mitspieler in der Ich-Form, mit Discord-Namen statt
    Charakternamen.
B5. **Perspektivwechsel mitten im Absatz:** turn=12 lässt den Spieler ("Du drehst dich zu ihm
    um und musterst ihn eingehend ... sagst du kühl") komplette Dialoge sprechen und hängt
    dann wortwörtlich die Szenenkarten-Zusammenfassung als Erzähltext an ("Die Gruppe steht
    in der Zoll-Sakristei, vollgestellt mit versiegelter Konterbande; es riecht nach
    Kerzenrauch und Bilgenwasser ..." = 1:1 der Kartentext). Der Prompt-Block leakt in die
    gesprochene Antwort.
B6. **Antwort-Schablone identisch in fast jedem Turn:** [NSC sieht dich an] + [runzelt die
    Stirn / nickt ernst] + [Zitat] + [schaut auf die Uhr] + [Zeitdruck-Satz] + ["Damit
    übergibt er wieder die Verantwortung an die Gruppe"]. Der Abbinder-Satz ist reine
    Regie-Prosa und wird vorgelesen.
B7. **Der Würfel-Nachtrag ignoriert das Ergebnis-Vorzeichen teilweise.** turn=17: Fehlschlag
    → Kaad verweigert "die Vollmacht", die er in turn=7 bereits gegeben hat (A6). turn=22
    Erfolg (1 EG) → "Ich bin beeindruckt. Ihr wisst also von den Kettenbündlern" — ein
    Wissensstand, den niemand geäußert hatte. Der Würfel-Turn erzeugt Fakten aus dem Nichts.
B8. **Alle Proben laufen auf Gellicus Schulz**, egal wer gesprochen hat (Timo → Gellicus,
    dreimal). Der Roll-Router wählt offenbar nicht nach Sprecher.
B9. **Latenz ist der eigentliche Abend-Killer.** turn=1: gen=628 Tokens, chars=2397,
    wav=156s, bridge_wait=158s, total=167s — knapp 3 Minuten Monolog am Stück, in denen
    niemand eingreifen kann. Über den ganzen Lauf: 22 Turns, davon 9 mit wav > 35s. Die
    Spieler reden während des Vorlesens weiter, Whisper transkribiert das mit, es entstehen
    Halluzinationen. Kurze Antworten (turn=3: 9s, turn=18: 8s) sind genau die, die inhaltlich
    Meta-Bruch sind — d.h. lang = schlecht, kurz = kaputt.
B10. **`gen` schwankt um Faktor 20** (27 bis 628 Tokens) ohne erkennbare Steuerung. Es gibt
    kein Längenbudget pro Antworttyp.
B11. **RAG feuert, aber liefert Müll für die Situation:** 'inFraCtioniSt BeneFitS',
    '— Talin Stride, Manufactorum Worker', '— Interrogator Arnaut Cisneros', 'ten QueStionS'
    — Chunk-Titel aus dem englischen Regelbuch mit kaputter Groß-/Kleinschreibung, retrieved
    bei d≈0.42-0.45, also knapp unter Schwelle. Diese Chunks helfen bei keiner der Fragen und
    verbrauchen Kontext.
B12. **Default-Party geladen**: "no channel sheet — loaded default party from
    data/sessions/_default/characters.json", dann 13 Sekunden später "loaded characters from
    data/sessions/1343673766487654464/characters.json". Zwei Ladewege, und der Lauf zeigt
    noch "Vinzentius Kabelbrand" (vor der D106-Umbenennung).
B13. **XTTS-Speaker-Warnung**: "XTTS speaker 'cuda' unknown — using Dionisio Schuyler" —
    eine Konfigurationsvariable ist an der falschen Stelle gelandet; die DM-Stimme ist eine
    zufällige Default-Stimme.
B14. **Der Testplan war unsichtbar.** Das 🧪-Overlay ist beim Boot aktiv gemeldet, aber im
    ganzen Abend taucht kein Overlay-Text auf und kein Spieler erwähnt, im Chat gelesen zu
    haben, was gerade getestet werden soll. Tobis eigentlicher Wunsch ("im chat steht was
    alles getestet werden soll") ist nie eingetreten — weil das Overlay an der Szene hängt
    und kein Szenenwechsel stattfand (siehe B1).
B15. **stream_assembler-Warnung** (19:17:11): "spoken text diverged from the finalized
    answer — speaking the canonical remainder; 5 sentences already spoken" — die Spieler
    haben in diesem Turn also teils doppelten/inkonsistenten Text gehört.
B16. **Kein Zeit-/Uhren-Marker im ganzen Log.** Trotz harter Frist (Mitternachtssirene) und
    implementierter Uhren (ADR 047) + Ingame-Zeit (ADR 048) feuert kein `<<UHR>>`/`<<ZEIT>>`.
    Der Zeitdruck existiert nur als Kaads Floskel — die Mechanik dahinter läuft nicht.
B17. **Ein Inline-Marker wurde verworfen** (19:25:41, D43) — der Router entschied dagegen.
    Einziger Marker-Event des Abends.
B18. **Die Spieler wurden nie um etwas gebeten, das kein Gespräch mit Kaad ist.** Keine
    Wahrnehmungs-, Technologie- oder Heimlichkeitsprobe, obwohl vier Charaktere mit
    unterschiedlichen Profilen am Tisch sitzen. Rene Redo/Vinzentius (Enginseer) hat
    keinerlei charakterspezifischen Anknüpfungspunkt bekommen.

## C. Tobis eigener Wunsch, wörtlich
- "ich wollte, dass die Debug-Kampagne einen mit einer Story durch das Spiel führt"
- "und im Chat steht, was alles getestet werden soll"
- "und wir dann dadurch den Dungeonmaster testen"
- "aktuell hat nix Kohärenz, die ganze Zeit Lokationswechsel, der Typ der die ganze Zeit
  das Gleiche labert"
