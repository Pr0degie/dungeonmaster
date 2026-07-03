# Live-Test-Checkliste — der eine Run mit den Freunden

Alle offenen **Live-Gates** (Code fertig + Suite grün, aber am Tisch unbestätigt), als
Ablauf für EINE Session in circlejerk sortiert. Stand: 2026-07-03 (nach D91 / ADR 044).
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
   (Phase 9/10), D87/D91-Punkte im Last-session-Block, Tuning-Werte die geblieben sind
   in `.env.example`-Kommentare.
3. Diese Liste ausmisten: Erledigtes raus, Reste bleiben der nächste Run.
