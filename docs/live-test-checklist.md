# Live-Test-Checkliste — der eine Run mit den Freunden

Alle offenen **Live-Gates** (Code fertig + Suite grün, aber am Tisch unbestätigt), als
Ablauf für EINE Session in circlejerk sortiert. Stand: 2026-07-03 (nach D96 / ADR 049).
Hake ab, was klappt; was nicht klappt, **nicht live debuggen** — notieren, Log sichern,
danach pasten (→ `/playtest-triage`).

> Quelle der Wahrheit bleibt `progress.md` (Next concrete step). Diese Datei ist das
> ausformulierte Drehbuch dazu — nach dem Run die Ergebnisse in `progress.md`
> (`VERIFY EVIDENCE` / Last session) zurückschreiben und diese Liste ausmisten.

---

## 0. Vorbereitung (vor dem Abend, 10 min)

- [ ] `git pull` + `uv sync` (auf **beiden** Maschinen, falls Timo mitspielt).
- [ ] `uv run dm-sync` auf beiden Maschinen, Blöcke diffen — Abenteuer-sha, rag.db,
      .env-Keys gleich? (SETUP.md § „Staying in sync"; Tobis .env war zuletzt 38/38 ✅)
- [ ] **Workstream A / GPU-Offload, reine `.env`:** `OLLAMA_HOST` auf die Offload-Box,
      `TTS_DEVICE=cuda`. Dann `nvidia-smi`: kein OOM, XTTS-cuda + Whisper passen auf die
      freie 4070.
- [ ] `DM_LOG_FILE=1` steht (Default) — `logs/debug.log` + `logs/transcript.log` sind
      hinterher das Triage-Material.
- [ ] Kompendium-Spot-Check: `data/adventures/chemical_burn/adventure.json` + `npcs.json` —
      Ton okay, Geheimnisse nur in `secrets_de`.
- [ ] *(Optional für den Gossip-Test, 2 min):* bei 2–3 zusammengehörigen NSCs in
      `npcs.json` ein `"faction": "..."` eintragen (z. B. dieselbe Gang) — ohne Fraktionen
      schläft der Gossip-Teil von Test 7.

## 1. Start & Join

- [ ] **Schneller Start** (ADR 024): Konsole erreicht zügig „logged in"; `!j` zeigt ggf.
      ⏳/⚠-TTS-Hinweis, erster Satz wird trotzdem gesprochen.
- [ ] **Join-Line-up:** Party namentlich (Fridolin / Gellicus / Rektalus — eine
      ⚠-Beispiel-Party-Warnung = falscher Channel, **abbrechen**) +
      `📖 Abenteuer: Chemical Burn — Szene: Der Auftrag`.

## 2. Tempo (Workstream A verifizieren)

- [ ] `[latency]`-Zeile vor/nach dem Offload vergleichen: `first_audio` und `tts` fallen
      deutlich, Sprech-Lücken weg.
- [ ] Wenn's schnell genug ist: `!sprechmodus nahtlos` live gegen `stream`/`puffer` hören
      (A/B aus D68/D69) — Kandidat für den neuen Default. Ergebnis notieren
      (→ ADR-002-Addendum + `architecture.md` §3 nachziehen).

## 3. Intro (D82–D86 / ADR 031+041)

- [ ] `!intro`: **ein** zusammenhängender Monolog — nennt **Ort** (Hive Rokarth / Voll),
      **Auftrag** (Halikarn/Gratis), das **Hergekommensein**, und bindet **jede Figur
      namentlich** mit einem persönlichen Moment ein.
- [ ] Kein Würfel-Aufruf, keine wörtlich vorgelesenen privaten Ziele, kein Meta-Auftakt
      („Als Spielleitung…") und kein `"…"`-Umschlag.
- [ ] Gegen-Check `!start`: bleibt das kurze 2–4-Sätze-Briefing.
- [ ] Tuning-Knöpfe falls nötig: `DM_INTRO_TEMPERATURE` (0.8 = mehr Flair, 0.3 = ruhiger),
      `DM_INTRO_NUM_PREDICT` runter bei Abschweifen.

## 4. Gesprächsqualität (D85 / ADR 042)

- [ ] Ein paar normale Spieler-Turns: **weniger Wiederholung/Generik** als vor der
      repeat_penalty-Runde? Verweist der DM knapp auf Etabliertes, statt es neu
      auszuerzählen (W4-Guard)?
- [ ] Geht der DM auf die Story ein (Plot statt Improvisation — der alte num_ctx-Befund)?
- [ ] Tuning: `DM_REPEAT_PENALTY` (1.0 = aus, höher = strenger — zu hoch franst Deutsch aus).

## 5. Würfel & Kampf (D61-Nachprüfungen)

- [ ] Spieler beschreibt eine riskante Aktion → 🎲-Button erscheint (Roll-Router), Wurf
      wird erzählt — **nie** erfindet das Modell Würfelergebnisse.
- [ ] Würfel-Button erscheint auch, wenn die Sprachausgabe mal hakt.
- [ ] Kampf: Angriff auf registrierten NSC → Auto-Schaden (Waffe + SL − Soak) wird
      angewendet + erzählt; `!damage`/`!heal` als Override.
- [ ] Psyker (Rektalus/Mortn-Äquivalent): Manifest über Schwelle → Perils erupten spürbar
      *häufiger* (Containment würfelt jetzt gegen Disziplin (Psi), D61).
- [ ] Verklebte Marker (`<<ORT1>>` etc.) werden **nicht** vorgelesen.

## 6. Szenen & Scene Cards (ADR 026 + ADR 043 / D87)

- [ ] **Auto-Szenenwechsel:** Gruppe bewegt sich zu einem verbundenen Ort → DM endet mit
      `<<ORT …>>` (**nicht** gesprochen), „Wechseln"-Button erscheint, Klick verschiebt den
      Pointer wie `!ort`. Erfundene/Nicht-Nachbar-ID im `verbunden`-Modus: ignoriert + geloggt.
      Kurz `!ortmodus frei` testen, dann zurück.
- [ ] **(a)** `!ort` zeigt die Element-IDs der Szene (⬜).
- [ ] **(b)** Eine Gelegenheit im Spiel abschließen → `<<ERLEDIGT>>`-Confirm-Button
      erscheint, Antwort enthält kein `<<`; nach „Abhaken" zeigt `!ort` ✅ und die nächste
      Karte „Bereits geschehen:".
- [ ] **(c)** `!erledigt <id>` / `!offen <id>` togglen ohne Button.
- [ ] **(d)** Gated Exit: testweise ein `leads_to` auf `{"ziel": …, "requires": "opp-1"}`
      setzen → Ziel fehlt in „Mögliche nächste Orte", Auto-`<<ORT>>` dorthin wird abgelehnt
      (🚫-Konsole nennt `opp-1`, nichts im Channel); nach `!erledigt opp-1` geht's.
- [ ] **(e)** NSC auf 0 Wunden → Karte rendert `(tot)`, übersteht Neustart.

## 6b. Konsistenz-Wächter (D92 / ADR 045) — **neues Gate**

Setup: der tote NSC aus 6(e) reicht. Der Regenerate-Schutz greift nur im **Batch-Pfad** —
für den Test kurz `!sprechmodus nahtlos` schalten (oder einen Würfel-Folge-Turn nutzen);
im Default-`stream`-Modus loggt der Wächter nur (Trade-off, ADR 045).

- [ ] Gespräch gezielt auf den Toten lenken („frag <Name>, was er gesehen hat") und ein
      paar Turns provozieren: lässt der DM ihn sprechen, feuert in der Konsole
      `[consistency] violated (dead:<Name>) — regenerating once` und die **gelieferte**
      Antwort lässt ihn nicht mehr sprechen (bloße Erwähnung/Leichenfund ist okay).
- [ ] Gegen-Check False Positives: normale Turns über den Toten reden (Erinnerungen,
      „<Name> sagte damals …") → **kein** Regenerate (unnötige `[consistency]`-Zeilen =
      Latenz-Fresser; dann Muster in `dmbot/llm/consistency.py` schärfen oder
      `DM_CONSISTENCY_GUARD=0`).
- [ ] Optional (szenenfremder NSC): einen registrierten NSC einer *anderen* Szene ins
      Gespräch ziehen → gleiche Mechanik (`absent:<Name>`).
- [ ] Im `stream`-Modus einmal die Log-only-Warnzeile sehen:
      `[consistency] streamed answer violates … logged only`.

## 6c. Consequence Clocks (D94 / ADR 047) — **neues Gate**

Setup: nichts nötig — Uhren funktionieren mit und ohne Abenteuer. Confirm-Buttons hängen am
selben `DM_FLAG_CONFIRM`-Knopf wie die Element-Flags (Default: an).

- [ ] `!uhr neu "Arbites-Ermittlung" 6` → Antwort nennt die id (`arbites-ermittlung`),
      das **Panel** erscheint im Textkanal (`⏱ ○○○○○○ …`).
- [ ] Einen Tick provozieren: etwas Lautes/Riskantes tun oder eine Probe verhauen (die Uhr
      steht als `[arbites-ermittlung] … 0/6` im Weltzustand-Prompt) → `⏱ Tick vorgeschlagen`-
      Button erscheint, die gesprochene Antwort enthält **kein** `<<`; nach „Tick" zeigt das
      Panel `◉○○○○○` — **dieselbe Nachricht editiert**, kein neues Panel.
- [ ] Gegen-Check Misfires: tickt der DM in Beiträgen ohne echte Verschärfung (Small Talk)?
      → Persona-Bullet in `prompts/dm_core_de.md` schärfen; Buttons einfach nicht klicken.
- [ ] Clamp: schlägt der DM zweimal dieselbe Uhr in einem Beitrag vor, erscheint nur EIN
      Button (Konsole: `🚫 UHR … abgelehnt`).
- [ ] Voll-Mechanik: per `!uhr tick` auf voll ticken (Panel: `⌛ … — VOLL`) → der **nächste**
      DM-Turn trägt `[Regie] Die Uhr „…“ ist voll …` und erzählt die Konsequenz als Ereignis
      → danach `!uhr weg` (Panel räumt die Uhr ab). Kür: `!uhr zurück` direkt nach einem
      versehentlichen Voll-Tick → die Regie-Zeile erscheint NICHT.
- [ ] Neustart-Check (mit §9 kombinierbar): Uhrenstand übersteht Bot-Neustart (`state.json`).

## 6d. Ingame-Zeit & Fristen (D95 / ADR 048) — **neues Gate**

Setup: nichts nötig — Zeit läuft mit und ohne Abenteuer. Confirm-Buttons hängen am selben
`DM_FLAG_CONFIRM`-Knopf; Szenenwechsel-Kosten via `DM_SCENE_TIME_ADVANCE` (Default 30 min).

- [ ] `!zeit` → `🕐 Tag 1, 08:00 (Morgen)`. `!frist neu "Treffen mit dem Informanten" +2h`
      → Antwort nennt die id, das **Druck-Panel** zeigt 🕐-Zeitzeile + ⏳-Frist mit Restzeit.
- [ ] Tagesphase bespielen: per `!zeit tag` oder `!zeit +14h` in den Abend/die Nacht springen
      → beschreibt der DM die Szene phasengerecht (dunkel, Läden zu, Wirt weg)?
- [ ] `<<ZEIT>>`-Marker provozieren: etwas Zeitiges tun („wir durchsuchen das Archiv gründlich",
      „wir rasten") → `🕐 Zeitfortschritt vorgeschlagen`-Button erscheint, die gesprochene
      Antwort enthält **kein** `<<`; nach Bestätigung zeigen Panel + `!zeit` den neuen Stand.
- [ ] Szenenwechsel (`!ort` oder bestätigter `<<ORT>>`) schiebt +30 min (Panel/`!zeit`).
- [ ] Clamp: schlägt der DM absurde Sprünge vor, wendet der Button max. **+12h** an
      (Konsole: `🕐 ZEIT-Vorschlag … geklemmt`); Duplikate im selben Beitrag → nur EIN Button.
- [ ] Frist-Ablauf: die Frist per `!zeit +3h` verstreichen lassen → der **nächste** DM-Turn
      trägt `[Regie] Die Frist „…“ ist verstrichen …` und erzählt die Konsequenz als Ereignis;
      `!fristen`/Panel zeigen **ABGELAUFEN** (genau EINMAL angemahnt) → danach `!frist weg`.
- [ ] Neustart-Check (mit §9 kombinierbar): Zeitstand + Fristen (inkl. „schon angemahnt")
      überstehen den Bot-Neustart (`state.json`).

## 7. NPC-Gedächtnis (D91 / ADR 044) — **das neue Gate**

- [ ] Einem NSC etwas Markantes erzählen — ideal: ihn **anlügen** (falsche Identität,
      z. B. „Wir sind im Auftrag der Arbites hier").
- [ ] Szene wechseln (`!ort` oder ORT-Button) → Konsole:
      `🧠 NPC-Gedächtnis: N neue Erinnerungen`.
- [ ] `!npcmem <Name>`: Eintrag da? Lüge **mit wörtlichem Zitat**, `believed` noch true,
      Wichtigkeit plausibel (Small Talk ≤ 2, Lüge/Versprechen 5)?
- [ ] **Zurückkommen** und den NSC ansprechen: erinnert sich der DM im Dialog an das
      Gespräch (ohne dass es jemand wiederholt)?
- [ ] **Kür — Lügen-Flip:** die Lüge im Spiel auffliegen lassen → nächster Szenenwechsel →
      `!npcmem` zeigt „LÜGE aufgeflogen" + neuen Wichtigkeit-5-Eintrag, Haltung ist eine
      Stufe Richtung hostile gerückt.
- [ ] **Kür — Gossip** (nur mit `faction` aus Schritt 0): wichtige Info (≥4) bei NSC A
      lassen → Szenenwechsel → `!npcmem <B>` (gleiche Fraktion) zeigt den Eintrag als
      Hörensagen (ohne Zitat, Wichtigkeit −1); gibt der DM es **vage** wieder?
- [ ] Gegen-Check: erfindet der Extraktor Erinnerungen für NSCs, die nichts mitbekommen
      haben? Falls ja/nervig: `prompts/npc_memory_extract_de.md` nachschärfen oder
      `DM_NPC_MEMORY=0`.

## 7b. NPC-Agenden (D96 / ADR 049) — **neues Gate**

- [ ] Einem markanten NSC ein Ziel geben: `!agenda <NSC> "will die Ware aus der Stadt
      schaffen"` → `!agenden` zeigt Ziel (🎯).
- [ ] **Zwei Szenen spielen** (jeder Wechsel triggert die 🧠-Extraktion, die jetzt auch den
      Agenda-Schritt vorschlägt) → `!agenden` zeigt nach jedem Wechsel einen neuen
      offscreen-Schritt mit Ingame-Zeitstempel.
- [ ] **Die Kernfrage:** hat sich seine Lage **glaubwürdig** bewegt? Kleine konkrete
      Schritte (jemanden treffen, etwas verstecken, Wachen anheuern), plausibel zur
      verstrichenen Ingame-Zeit — keine Festungsbauten über Nacht.
- [ ] Zum NSC **zurückkehren**: spielt der DM die veränderte Lage (der Block trägt Ziel +
      Schritte)? Ist er woanders, tauchen **Gerüchte/Spuren** auf (Weltzustand-Zeile)?
- [ ] Gegen-Check: erfindet der Extraktor Schritte für NSCs **ohne** Ziel (Code verwirft
      sie — Konsole `agenda step … without a goal`)? Absurde Sprünge? → Agenda-Regel in
      `prompts/npc_memory_extract_de.md` nachschärfen; `!agenda <NSC> weg` oder
      `DM_NPC_MEMORY=0` schaltet ab.

## 8. Regelfragen / RAG (Phase-10-Gate, Hälfte 1)

- [ ] Regelfrage per Stimme („Was passiert bei einem kritischen Erfolg?") → Antwort aus dem
      Buch (in `debug.log` erscheint eine `📚 Regelwerk:`-Zeile), kein Bauchgefühl.
- [ ] Conditions: „Was bewirkt Blutend/Betäubt?" → korrekte deutsche Antwort.
- [ ] Inquisitions-Frage (z. B. Ordos/Radical Methods) trifft player_guide/gm_guide.
- [ ] Spoiler-Disziplin: eine „wer steckt dahinter?"-Frage in Teil 1 bleibt unbeantwortet.

## 9. Memory & Neustart (Phase-9-Gate)

- [ ] Mitten in der Session: HP-Stand notieren → Bot **komplett neu starten** → `!j` →
      HP/Zustände stimmen noch, `scene_id` steht wo sie stand, Szenen-Flags (✅) und
      `!npcmem`-Einträge sind noch da.
- [ ] Recap erscheint beim nächsten `!join` im Prompt (DM knüpft an, statt neu zu starten).
- [ ] `!wrap up` am Ende: Recap wird erzeugt + gespeichert (und triggert nebenbei die
      NPC-Gedächtnis-Extraktion der letzten Szene — Konsole zeigt die 🧠-Zeile).

## 10. Nebenbei / wenn Zeit ist

- [ ] `!lore tts`-Reader: Block-Text + ⏭/🔊/⏹; bei Doppel-Audio in `debug.log` prüfen:
      eine `🔊 TTS … speaking` + ein `/speak` pro Block ⇒ das Doppeln liegt an Bot A.
- [ ] Shutdown: zweimal Strg+C → „Voice-Channel verlassen"-Stufe dauert ≤ ~2 s (D67).

## Nach dem Run

1. `logs/transcript.log` + `logs/debug.log` sichern und pasten → `/playtest-triage`.
2. Ergebnisse in `progress.md` zurückschreiben: erfüllte Gates in `VERIFY EVIDENCE`
   (Phase 9/10), D87/D91/D92-Punkte im Last-session-Block, Tuning-Werte die geblieben sind
   in `.env.example`-Kommentare.
3. Diese Liste ausmisten: Erledigtes raus, Reste bleiben der nächste Run.
