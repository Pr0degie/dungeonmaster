# Charakter-Erstellungs-Prompt (zum Selbermachen)

Ein eigenständiger Prompt für **neue Mitspieler**: Der Spieler kopiert den Block unten in
Claude (oder ein anderes LLM), beantwortet ein paar Fragen in eigenen Worten, und bekommt am
Ende **einen kompletten, regelkonformen Charakter als JSON** zurück — Werte, optional Psioniker,
und Hintergrund. Dieses JSON schickt er an den Spielleiter; der legt es nach `data/party/`,
lässt es validieren (Budget/Wunden/Kräfte), generiert den Bogen (`tools/fill_character_sheet.py`)
und führt es später in die Session-`characters.json` zusammen.

Die Regeln im Prompt spiegeln `docs/how-to-create-a-character.html` (90-Punkte-Kauf, Herkunft
+5/+5, 6 Skill-Steigerungen à +5 / max 2 je Skill, Wunden = StrB + 2×TghB + WilB) und das
Psioniker-Subsystem (ADR 022; `known_powers` = Schlüssel aus dem Profil-Katalog in
`data/systems/imperium_maledictum.json`, damit der `<<MANIFEST>>`-Würfel-Flow greift).

> Für reine **Backstory-Nachträge** (Charakter hat schon Werte, nur Erzähl-Felder fehlen) genügt
> eine gekürzte Variante — frag den SL, der baut sie aus diesem Prompt ab.

---

## Der Prompt (alles ab hier kopieren)

```
Du baust mit mir Schritt für Schritt einen kompletten Charakter für das Rollenspiel
Warhammer 40.000 / Imperium Maledictum (deutsche Spielsprache, düsterer „grimdark"-Ton).
Ich beantworte deine Fragen in ein paar Sätzen — DU übernimmst die ganze Regel-Mathematik und
gibst mir am Ende EIN fertiges JSON, das ich weiterschicke. Frag mich erst aus (gern in kleinen
Häppchen), rechne dann, und prüfe dich selbst, bevor du das JSON ausgibst.

────────────────────────────────────────
TEIL 1 — DEINE FRAGEN AN MICH
────────────────────────────────────────
1. Discord-Name + Charaktername (oder sag „mach einen Vorschlag").
2. Konzept in einem Satz: Was ist das für ein Typ?
3. Worin soll er GUT sein? Wähle/priorisiere aus: Nahkampf, Fernkampf, Schleichen/Stealth,
   Reden & Überzeugen, Einschüchtern, Wahrnehmung/Verborgenes-aufspüren, Technik, Wissen,
   Heilen/Medizin, Athletik/Körperkraft. Und was ist ihm egal?
4. Soll er ein PSIONIKER (Psi-Kräfte) sein? Falls ja: eher Richtung Verhör/Verbergen,
   Aufspüren, oder Kampf? (Ich wähle dir passende Kräfte aus.)
5. Herkunftswelt-Gefühl: bodenständig-agrarisch / adelig-feudal / wild & rau / techy-Schmiedewelt /
   Großstadt-Moloch (Hive) / fromm-religiös / militärisch gedrillt / im-Raum-zwischen-Sternen-geboren?
6. Lieblingswaffe? (Nahkampf oder Fernwaffe — beschreib sie, ich nehme die passende aus der Liste.)
   Hast du kybernetische Implantate (Augmetik)? Falls ja, welche?
7. Aussehen: Alter, Haare, Augen, Größe, Statur, ein auffälliges Merkmal.
8. Hintergrund: Woher kommt er, warum zieht er los, was will er kurzfristig und im großen Ganzen?
9. Verbindungen: Wen kennt/vertraut/misstraut er? (Mitspieler, an die du anknüpfen kannst:
   Fridolin — düsterer Inquisitions-Ermittler & Psioniker; Gellicus — notorischer Schwerenöter;
   Rektalus — reicher Schönling und Nahkämpfer.)
10. Ein persönlicher Leitspruch/Schwur in einem Satz.

────────────────────────────────────────
TEIL 2 — REGELN, NACH DENEN DU BAUST (nicht abweichen!)
────────────────────────────────────────
9 EIGENSCHAFTEN (Kürzel): WS=Nahkampf, BS=Fernkampf, Str=Stärke, Tgh=Zähigkeit, Ag=Agilität,
Int=Intelligenz, Per=Wahrnehmung, Wil=Willenskraft, Fel=Charisma.
• Jede startet bei 20. Verteile GENAU 90 zusätzliche Punkte. Jede Eigenschaft bekommt mind. +4
  und höchstens +18 (Werte also 24–38, VOR der Herkunft). Setz die Schwerpunkte nach meinen Wünschen:
  Nahkampf→WS, Fernkampf→BS, Stealth/flink→Ag, Reden/Einschüchtern→Fel, Aufspüren→Per,
  Technik/Wissen/Medizin→Int, Athletik/Schaden→Str, einstecken→Tgh, willensstark/Psioniker→Wil.
• Bonus einer Eigenschaft = Zehnerstelle (38→3, 41→4).

HERKUNFT (gibt +5 auf eine FESTE + +5 auf eine WÄHLBARE Eigenschaft) — wähle passend zum Konzept:
  Agrarwelt: +5 Str | Wahl: Tgh/Ag/Wil          Makropolwelt(Hive): +5 Ag | Wahl: BS/Per/Fel
  Feudalwelt: +5 WS | Wahl: Str/Wil/Fel          Schreinwelt(fromm): +5 Wil | Wahl: Int/Per/Fel
  Wildwelt: +5 Tgh | Wahl: WS/Str/Per            Schola Progenium(militär): +5 Fel | Wahl: WS/BS/Tgh
  Schmiedewelt: +5 Int | Wahl: BS/Tgh/Ag         Leerengeboren(Raum): +5 Per | Wahl: Ag/Int/Wil

WUNDEN = StrB + 2×TghB + WilB. Setze wounds = max_wounds = dieser Wert.

FERTIGKEITEN: Du hast 6 Steigerungen à +5, MAX 2 pro Fertigkeit. Endwert = regierende Eigenschaft
+ (Steigerungen × 5). Liste ALLE 10 Kernfertigkeiten mit Endwert (untrainierte = Eigenschaftswert):
  Nahkampf(WS), Fernkampf(BS), Athletik(Str), Heimlichkeit(Ag), Wahrnehmung(Per),
  Technologie(Int), Wissen(Int), Medizin(Int), Überreden(Fel), Einschüchtern(Fel).

WAFFEN (Schaden, Notation „1W10+X"): Kettenschwert 1W10+5 · Schwert 1W10+4 · Kettenmesser 1W10+3 ·
Kampfmesser 1W10+1 · Lasgewehr 1W10+4 · Stubber 1W10+4 · Laspistole 1W10+3 · Autopistole 1W10+3 ·
(sonstiges/improvisiert 1W10). Waffen-Testwert = Nahkampf (Nahkampfwaffe) bzw. Fernkampf (Fernwaffe).

PSIONIKER (nur falls gewählt):
• Setze "psyker": true. Gib zusätzlich zwei Fertigkeiten an: "Psi-Meisterschaft" = Wil + 10 und
  "Disziplin (Psi)" = Wil + 5 (das Psioniker-Paket, SEPARAT von den 6 Steigerungen).
• "disciplines": 1–2 Flavor-Namen (z.B. "Telepathie","Biomantie","Divination").
• "known_powers": GENAU 5 Kräfte, NUR aus dieser Liste, Namen EXAKT (englisch). Smite ist Pflicht.
  MINOR: Smite(Pflicht) · Psychic Static(unbemerkt/„unsichtbar") · Psychic Scrutiny(Ziel auslesen) ·
  Preternatural Senses(Nacht-/Wärmesicht) · Soulsight(Wesen aufspüren) · Dread Presence(Furcht) ·
  Luck(Probe mit Vorteil) · Jinx(Probe sabotieren) · Lull(bewusstlos) · Nova(Flächenschaden) ·
  Ignite(Handflamme) · Combustion(entzünden) · Sear(glühend heiß) · Dull Pain(Schmerz weg,+Rüstung) ·
  Float(schweben) · Seal Wounds(heilen) · Spasm(Gliedkontrolle weg) · Spectral Hands(Telekinese) ·
  Scalding Glance(Flüssigkeit kochen) · Call Vermin(Ungeziefer) · Ill Omen(Warp-Phänomen) ·
  Auditory Manipulation(Geräusche vorgaukeln) · Cipher Seed(geheime Botschaft) · Force Bolt(Geschoss) ·
  Immolation Directive(Objekt zu Asche) · Mark(arkanes Zeichen).
  BIOMANTIE: Iron Limb(Nahkampf-Boost) · Haemorrhage(ausbluten) · Affliction(Zustand aufzwingen) ·
  Ferrocrete Flesh(Haut härten) · Bio-Lightning(Elektroschaden) · Life Leech(Leben entziehen) ·
  Induce Panic · Ossify(verknöchern) · Stimulating Jolt(auf den Beinen halten).
• Füge ein Talent {"name":"Psioniker","effect":"Kann psychische Kräfte manifestieren; Manifest über
  Psi-Meisterschaft, Warp-Schwelle = WillkürB."} hinzu.

AUGMETIK (optional, für alle): kybernetische Implantate (z.B. Augmetischer Arm, Augur-Array,
Mechadendrit, Bionisches Auge). Dauerhaft, kein Wurf. Faustregel-Grenze: höchstens so viele wie der
ZähigkeitsBonus (Zehnerstelle von Tgh). Rüstungs-/Merkmalsboni rechnet das Spiel ein, situative
Effekte (Auspex, Mechadendriten …) spielt der Spielleiter aus. Als Liste ins Feld "augmetics" —
leer lassen, wenn keine.

────────────────────────────────────────
TEIL 3 — SELBST-CHECK, DANN AUSGABE
────────────────────────────────────────
Prüfe VOR der Ausgabe und fasse das Ergebnis im "_note" zusammen:
✓ Summe aller Verteilungspunkte = genau 90, jede Eigenschaft +4…+18 (vor Herkunft)
✓ Herkunfts-Boni korrekt addiert    ✓ 6 Steigerungen, keine Fertigkeit über +2
✓ Wunden = StrB + 2×TghB + WilB     ✓ (falls Psioniker) 5 gültige known_powers
✓ Augmetik (falls vorhanden) ≤ ZähigkeitsBonus

Gib dann GENAU EINEN JSON-Block aus (deutsche Texte, grimdark-Ton, Psioniker-Felder nur wenn Psioniker):
{
  "_note": "<dein kurzer Selbst-Check, z.B. Summe 90 ✓, Wunden 12 ✓, 6 Steigerungen ✓>",
  "name": "", "player": "", "system": "imperium_maledictum",
  "origin": "", "faction": "", "concept": "",
  "characteristics": { "WS":0,"BS":0,"Str":0,"Tgh":0,"Ag":0,"Int":0,"Per":0,"Wil":0,"Fel":0 },
  "skills": { "Nahkampf":0,"Fernkampf":0,"Athletik":0,"Heimlichkeit":0,"Wahrnehmung":0,
              "Technologie":0,"Wissen":0,"Medizin":0,"Überreden":0,"Einschüchtern":0 },
  "wounds": 0, "max_wounds": 0, "conditions": [],
  "inventory": [],
  "weapons": [ { "name":"","test":"","damage":"","range":"","mag":"","enc":"","traits":"" } ],
  "augmetics": [],
  "psyker": false, "disciplines": [], "known_powers": [],
  "age":"","eyes":"","hair":"","height":"","weight":"","handedness":"",
  "distinguishing":"",
  "talents": [ { "name":"","effect":"" } ],
  "goals":"","connections":"","notes":"","combat_notes":"","divination":""
}
```
