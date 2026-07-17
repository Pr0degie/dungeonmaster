# Live-Run-Skript — EIN Abend schließt die Gates (+ kurze Folge-Session)

Stand: 2026-07-18 (G10 ergänzt nach D102 / ADR 055; davor 2026-07-11, D98 / ADR 051).
**Ersetzt `docs/live-test-checklist.md`** — alle offenen Live-Gates (G1–G10), die
Tuning-Checks und die Sekundär-Prüfungen aus `progress.md` sind hier in EIN geordnetes
Drehbuch gemerged.
Log-Zeilen sind exakt aus dem Code zitiert und damit direkt in `logs/debug.log` greppbar.

> **Wiederverwendbare Alternative:** die Debug-Kampagne „Die Mitternachtsfracht“
> (`DM_ADVENTURE=debug-kampagne`, lokal) triggert alle Gates natürlich im Spiel —
> Drehbuch + Debrief-Greps in [debug-campaign-runbook.md](debug-campaign-runbook.md).
> Dieses Skript bleibt der One-Shot-Plan für den aktuellen Backlog.

**Spielregeln für den Abend:**

- **Nicht live debuggen.** Was nicht klappt: notieren, weiterspielen, Logs sichern,
  hinterher pasten (→ `/playtest-triage`).
- **Eine Variable pro Run** (`docs/lessons/one-variable-per-live-run.md`): der GPU-Offload
  (Workstream A) ist die einzige Konfig-Änderung dieses Runs. Der Modell-A/B-Test
  (Mistral Small etc.) kommt erst NACH der Gate-Session.
- **Gates schließen erst nach dem Spielen:** die Ergebnisse werden in der Session nach dem
  Run in `progress.md` eingetragen (`VERIFY EVIDENCE` Phase 9/10, Last session). Dieses
  Skript wird nur abgehakt.
- Kür-Punkte (⭐) sind optional — zuerst die Pflicht. Ein Gate gilt als geschlossen, wenn
  die Pflicht-Punkte sitzen.

---

## Gate-Register — was dieser Run schließt

Sortiert nach Setup-Kosten (billigste zuerst). „Beweis“ = die Zeile/Anzeige, die hinterher
ins `VERIFY EVIDENCE` wandert.

| # | Gate | Setup | Drehbuch | Beweis (Kurzform) |
|---|---|---|---|---|
| G1 | **Phase 10 Hälfte 1 — Regelfrage aus RAG** | keins (1 Frage) | Akt 2 | `📚 rulebook:'…' (d=0.xx)` in debug.log + korrekte Antwort |
| G2 | **Consequence Clocks** (D94 / ADR 047) | keins (Commands) | Akt 2 + 7 | Panel `⏱ ◉○…` edit-in-place; `⏱ Tick vorgeschlagen: … (0/6)` |
| G3 | **Ingame-Zeit & Fristen** (D95 / ADR 048) | keins (Commands) | Akt 2 + 7 | `🕐 Zeitfortschritt vorgeschlagen: +N min`; `⏳ Frist '…' … verstrichen …` |
| G4 | **Stateful Scene Cards** (D87 / ADR 043) | 1 `leads_to`-Edit (Pre-Flight #6) | Akt 6 | `✅ Erledigt vorgeschlagen: …`; `🚫 Ausgang '…' → '…' verriegelt — Bedingung '…' nicht erledigt` |
| G5 | **NPC-Gedächtnis** (D91 / ADR 044) | 1 Lüge im Spiel | Akt 4 + 6b | `🧠 NPC-Gedächtnis: N neue Erinnerungen (Szene '…')`; `!npcmem` |
| G6 | **Konsistenz-Wächter** (D92 / ADR 045) | toter NSC (fällt in Akt 5 ab) | Akt 8 | `[consistency] violated (dead:…) — regenerating once` |
| G7 | **NPC-Agenden** (D96 / ADR 049) | 1 Ziel + zwei Szenenwechsel | Akt 2 + 9 | `NPC-memory: '…' Agenda-Schritt: …`; `!agenden` mit Ingame-Zeitstempel |
| G8 | **Phase 9 — HP übersteht Neustart + Recap** | 1 Neustart | Akt 10 + 11 → S2 | `loaded world state from …`; `📜 Was bisher geschah` beim nächsten `!j` |
| G9 | **Chekhov-Fäden** (D97 / ADR 050) — **braucht ZWEI Sessions** | keins | Akt 4 + 11 (Saat) → **Session 2** (Ernte) | `🧵 Chekhov-Liste: N neue Fäden, M aufgelöst`; Callback in S2 |
| G10 | **Kampagnen-Gedächtnis** (D102 / ADR 054+055) — **reitet auf der G9-Zweitsession** | keins (`DM_SESSION_MEMORY` an = Default) | `!leave` S1 → **Session 2**: eine Erinnerungs-Frage in natürlicher Sprache + eine mit Eigennamen aus S1 (mitten im Satz) | `🗂 session memory: ingested history.<stamp>.jsonl (N chunks)` beim `!leave`; `🗂 session memory: catch-up — N rotated journal(s) pending` beim `!j` von S2; pro Treffer `🗂 Szene '…'/<stamp> (FTS)` bzw. `(d=0.xx)` + Block `## Früher in der Kampagne` |

**Strukturell zweigeteilt sind nur G9 und G10 — beide auf derselben Zweitsession:** Session 1
sät (Detail beiläufig fallen lassen + `!wrap`-Extraktion; ihr `!leave` ist zugleich der
G10-Ingest), Session 2 erntet (spielt der DM es zurück? ⭐ Auflösung — und beantwortet die
G10-Erinnerungs-Sonden aus dem Session-Store). G8s Recap-Hälfte wird in Session 1 nach dem
`!wrap` per Neustart vorgeprüft und am echten Anfang von Session 2 bestätigt. Alles andere
schließt an EINEM Abend. G10-Nebeneffekt fürs Protokoll: das `SESSION_MAX_DISTANCE`-Livetuning
(ADR 054) bekommt hier seine ersten echten Messwerte.

**Ruht (bewusst nicht in diesem Run):** der Augmetik-Live-Check (D52) — die aktuelle
Party (Fridolin/Gellicus/Rektalus) hat keinen Implantat-Charakter; wieder aufnehmen, wenn
einer dazukommt. Der Profil-Bootstrap (Phase 10b) bleibt zurückgestellt, bis das Spielen
rund läuft.

---

## Pre-Flight (vor dem Abend, ~15 min)

1. **Sync (beide Maschinen, falls Timo mitspielt):** `git pull` + `uv sync`, dann
   `uv run dm-sync` und die `[sync]`-Blöcke diffen (SETUP.md § „Staying in sync“).
   Soll-Bild (Tobis Maschine, 2026-07-11):
   - `repo … (clean)` — gleicher Commit auf beiden Maschinen
   - `adventure chemical_burn/adventure.json sha=5858acc … (15 scenes)` und
     `npcs.json sha=c2fd772 … (24 npcs)` *(shas ändern sich durch Pre-Flight #5/#6 —
     dann zählt: auf beiden Maschinen gleich)*
   - `rag.db 14.9 MB model=bge-m3 dim=1024` + gleiche Chunk-Zahlen
     (`ingest: … unbekannt` ist okay — ältere DB; die Chunk-Zahlen sind der Check)
   - `.env 42/42 keys … (0 fehlen, 0 überzählig)` — Tobis `.env` am 2026-07-11 um die 4
     Gate-Kill-Switches ergänzt (`DM_CONSISTENCY_GUARD`, `DM_NPC_MEMORY`,
     `DM_NPC_MEMORY_TOP_K`, `DM_SCENE_TIME_ADVANCE`)
   - `seeds tracked seed files unmodified`
2. **Workstream A / GPU-Offload (die EINZIGE Konfig-Variable):** in `.env` `OLLAMA_HOST`
   auf die Offload-Box + `TTS_DEVICE=cuda`. Dann `nvidia-smi`: kein OOM — XTTS-cuda +
   Whisper passen auf die freie 4070.
3. **Logs an:** `DM_LOG_FILE=1` + `DM_TRANSCRIPT_FILE=1` (standen zuletzt) —
   `logs/debug.log` + `logs/transcript.log` sind hinterher das Triage-Material.
4. **Kompendium-Spot-Check:** `data/adventures/chemical_burn/adventure.json` + `npcs.json`
   — Ton okay, Geheimnisse nur in `secrets_de`.
5. **⭐ Gossip-Seed (2 min):** aktuell trägt KEIN NSC eine `faction` — für die Gossip-Kür
   (Akt 6b) bei 2–3 zusammengehörigen NSCs in `npcs.json` z. B. `"faction": "kult"`
   eintragen (Kandidaten: Kultist + Verfluchter Kultist, oder eine Gang um Ganger/Dreg).
   Ohne Seed schläft die Kür.
6. **Gated-Exit-Edit (für G4d, 2 min):** in Szene `auftrag` einen `leads_to`-Eintrag
   (z. B. `"cathedrum"`) ersetzen durch `{"ziel": "cathedrum", "requires": "<opp-id>"}` —
   die opp-id vorher aus der Szenenkarte/`!ort` ablesen. Nach dem Test zurückdrehen oder
   einfach `!erledigt <opp-id>` spielen.
7. **Party-Check:** Channel ist `circlejerk`; `!j` muss **Fridolin Feuchtgebietheld /
   Gellicus Schulz / Rektalus Zerfickus** aufstellen — **Fridolin ist der Psioniker**
   (die alte Checkliste nannte fälschlich Rektalus). Eine ⚠-Beispiel-Party-Warnung =
   falscher Channel → abbrechen.
8. **Handout:** `docs/how-to-play.html` an Timo & Sezgin (spart die Regelerklärung am
   Tisch).

**Kill-Switch-Spickzettel** (`.env`, wirksam nach Neustart):

| Knopf | Default | Schaltet ab / stellt um |
|---|---|---|
| `DM_NPC_MEMORY=0` | 1 | NPC-Gedächtnis + Agenden + Chekhov-Extraktion (EIN Knopf für alle drei) |
| `DM_CONSISTENCY_GUARD=0` | 1 | Konsistenz-Wächter |
| `DM_FLAG_CONFIRM=0` | 1 | Confirm-Buttons für ERLEDIGT/UHR/ZEIT (0 = auto-apply) |
| `DM_SCENE_TIME_ADVANCE=0` | 30 | +Minuten pro Szenenwechsel |
| `DM_ROLL_ROUTER=0` | 1 | Router aus → wieder inline `<<TEST>>` |
| `DM_STREAMING=0` | 1 | Batch-Modus (ein WAV) — für den first_audio-Kontrast |
| `DM_REPEAT_PENALTY` | 1.1 | 1.0 = aus, höher = strenger (zu hoch franst Deutsch aus) |
| `DM_INTRO_TEMPERATURE` | 0.7 | 0.8 = mehr Flair, 0.3 = ruhiger |
| `DM_INTRO_NUM_PREDICT` | 800 | runter bei Abschweifen |

**Command-Spickzettel** (fürs Tischpult):
`!j` / `!leave` · `!intro` / `!start` · `!dm` / `!redo` ·
`!sprechmodus stream|puffer|nahtlos` · `!test <spec>` / `!roll` /
`!npc add <Name> [Wunden] [TB] [Rüstung]` / `!npc list` / `!damage` / `!heal` ·
`!ort [id]` / `!szenen` / `!ortmodus verbunden|frei` / `!erledigt <id>` / `!offen <id>` ·
`!uhr neu|tick|zurück|weg` / `!uhren` · `!zeit [+2h|tag]` / `!frist neu|weg` / `!fristen` ·
`!agenda <NSC> "<Ziel>"|weg` / `!agenden` · `!faden neu|erledigt|weg` / `!fäden` ·
`!npcmem <Name>` · `!rules <frage>` / `!lore [frage|tts]` · `!wrap` ·
Pause = **Esc** im DMbot-Terminal oder der ⏸-Button (es gibt KEIN `!pause`-Command).

---

## Session 1 — das Drehbuch

### Akt 0 — Boot & Join (5 min)

- [ ] Boot-Konsole zeigt: `loaded system profile 'imperium_maledictum' …`,
      `loaded adventure 'chemical_burn' (15 scenes, 24 NPC statblocks)`,
      `rulebook RAG store found — retrieval is on`.
- [ ] **Schneller Start (ADR 024):** „logged in“ kommt zügig, VOR dem TTS-Load; später
      `TTS backend 'xtts' ready in …s.`
- [ ] `!j`: ggf. ⏳/⚠-TTS-Hinweis (okay), erster Satz wird trotzdem gesprochen.
- [ ] **Join-Line-up:** Party namentlich (Fridolin / Gellicus / Rektalus) +
      `📖 Abenteuer: Chemical Burn — Szene: Der Auftrag`.

### Akt 1 — Tempo-Baseline (Workstream A verifizieren)

- [ ] `[latency]`-Zeile pro Turn (`… ctx=… gen=… chars=… first_audio=…ms tts=…
      bridge_wait=… total=…`) vor/nach dem Offload vergleichen: `first_audio` und `tts`
      fallen deutlich, die Sprech-Lücken zwischen Sätzen verschwinden. *(Nach einem
      Stop-Abbruch können `gen=`/`ctx=` stale sein — Anzeige-Eigenheit, kein Bug.)*
- [ ] Wenn schnell genug: `!sprechmodus nahtlos` live gegen `stream`/`puffer` hören —
      Kandidat für den neuen Default. Ergebnis notieren (→ ADR-002-Addendum +
      `architecture.md` §3 nachziehen).
- [ ] `ctx=`-Anteil im Blick behalten; ab ~85 % feuert der Auto-Recap
      (`🧵 Kontext bei X/Y — Auto-Recap: history wird kompaktiert …`) — gewollt, kein Fehler.

### Akt 2 — Sofort-Gates & Saatgut (10 min, vor dem eigentlichen Spiel)

**G1 — Regelfrage aus RAG (Phase-10-Gate Hälfte 1):**
- [ ] Regelfrage per Stimme („Was passiert bei einem kritischen Erfolg?“) → Antwort aus
      dem Buch, kein Bauchgefühl; `debug.log` zeigt `📚 rulebook:'…' (d=0.xx)`.
- [ ] Gegenprobe explizit: `!rules Was bewirkt Blutend?` → Embed **📖 Regelauskunft** mit
      „Quelle (Regeltexte)“-Feld; Log `📖 !rules … → conditions:'…' (d=0.xx)`.
- [ ] Inquisitions-Frage (Ordos/Radical Methods) trifft `player_guide:`/`gm_guide:`.
- [ ] Spoiler-Disziplin: eine „Wer steckt hinter Gratis?“-Frage in Teil 1 bleibt vage.

**Saatgut legen (zahlt auf G2/G3/G7/G9 ein, Ernte später):**
- [ ] `!zeit` → `🕐 Tag 1, 08:00 (Morgen)`.
- [ ] `!uhr neu "Arbites-Ermittlung" 6` → Antwort nennt die id (`arbites-ermittlung`),
      Panel erscheint (`⏱ ○○○○○○ … 0/6`).
- [ ] `!frist neu "Treffen mit dem Informanten" +2h` → Panel zeigt 🕐-Zeitzeile +
      `⏳ … — noch ~2 Std`.
- [ ] `!agenda <markanter NSC> "will die Ware aus der Stadt schaffen"` → `🎯 … verfolgt
      jetzt: …`; `!agenden` zeigt das Ziel. NSC wählen, der im Abenteuer wiederkehrt.
- [ ] G9-Doppelcheck-Saat: `!faden neu "Die Münze aus der Bar" 2` → `🧵 Neuer Faden: …
      (t1, Gewicht 2)`. Das ECHTE Chekhov-Detail kommt beiläufig im Spiel (Akt 4).

### Akt 3 — Intro (D82–D86 / ADR 031+041)

- [ ] `!intro`: **ein** zusammenhängender Monolog — nennt **Ort** (Hive Rokarth / Voll),
      **Auftrag** (Halikarn/Gratis), das **Hergekommensein**, und bindet **jede Figur
      namentlich** mit einem persönlichen Moment ein.
- [ ] Kein Würfel-Aufruf, keine wörtlich vorgelesenen privaten Ziele, kein Meta-Auftakt
      („Als Spielleitung …“), kein `"…"`-Umschlag.
- [ ] Gegen-Check `!start`: bleibt das kurze 2–4-Sätze-Briefing.
- [ ] Tuning falls nötig: `DM_INTRO_TEMPERATURE`, `DM_INTRO_NUM_PREDICT`.

### Akt 4 — Gespräch, die Lüge & das Detail (D85 + Saat für G5/G9)

- [ ] Qualität: **weniger Wiederholung/Generik** (repeat_penalty-Runde); verweist der DM
      knapp auf Etabliertes statt neu auszuerzählen (W4-Guard)? Plot statt Improvisation
      (Halikarns Auftrag)?
- [ ] W4/W5: „Warum sind wir hier?“ **zweimal** fragen → Antwort statt Re-Beschreibung
      (self-repetition WARNING im Log beobachten).
- [ ] **G5-Saat:** einen NSC **anlügen** — markant, mit falscher Identität („Wir sind im
      Auftrag der Arbites hier“).
- [ ] **G9-Saat:** beiläufig ein markantes **Nicht-Quest-Detail** etablieren (erwähntes
      Objekt, Andeutung, offenes Versprechen) — und bewusst liegen lassen.
- [ ] Passiv beobachten: 🎲 erscheint, **während** der DM noch spricht, genau einer pro
      Aktion (D40); keine leeren/Marker-only-Turns, kein Dice-Loop (D42); keine
      `echo guard`-WARNINGs nach Würfen.

### Akt 5 — Würfel & Kampf (D61-Nachprüfungen; produziert den toten NSC für Akt 8)

- [ ] Riskante Aktion per Stimme → 🎲-Button (Log `🎲 router: '…' → <Skill> (…)`), der
      Wurf wird erzählt — **nie** erfindet das Modell Würfelergebnisse.
- [ ] `!npc add Kultist 10 3` → Angriff → auf Erfolg Ziel-Dropdown („Ziel des Treffers
      wählen …“) → `💥 … = N Wunden → Kultist M/10`. Nur bei Nahkampf/Fernkampf + nur bei
      Erfolg. `!damage`/`!heal` als Override (0 → „kampfunfähig“).
- [ ] **Den Kultisten auf 0 Wunden bringen** → Vorrat für Akt 8 (G6); die Szenenkarte
      rendert ihn `(tot)` (G4e, übersteht den Neustart in Akt 10).
- [ ] Psyker: **Fridolin** wirkt eine Kraft per Stimme → `🌀 Manifestation angefordert`-
      Button → `🌀 … Warp X/4`-Zeile, der DM erzählt den Effekt. ⭐ Push über die
      Schwelle → `🜏 Perils of the Warp` feuert, Warp resettet.
- [ ] Verklebte Marker (`<<ORT1>>` etc.) werden **nicht** vorgelesen.

### Akt 6 — Szenen & Scene Cards (G4 + Szenenwechsel #1)

- [ ] **(a)** `!ort` zeigt die Element-IDs der Szene (⬜).
- [ ] **(b)** Eine Gelegenheit im Spiel abschließen → ✅-„Abhaken“-Button erscheint (Log
      `✅ Erledigt vorgeschlagen: …`), die gesprochene Antwort enthält **kein** `<<`; nach
      „Abhaken“ zeigt `!ort` ✅ und der nächste Prompt-Dump „Bereits geschehen:“.
- [ ] **(c)** `!erledigt <id>` / `!offen <id>` togglen ohne Button.
- [ ] **(d)** Gated Exit (Pre-Flight #6): das verriegelte Ziel fehlt in „Mögliche nächste
      Orte“; ein Auto-`<<ORT>>` dorthin → Konsole `🚫 Ausgang 'auftrag' → 'cathedrum'
      verriegelt — Bedingung '<opp-id>' nicht erledigt`, **nichts im Channel**; nach
      `!erledigt <opp-id>` geht der Wechsel.
- [ ] **Auto-Szenenwechsel (ADR 026):** Bewegung zu einem verbundenen Ort → DM endet mit
      `<<ORT …>>` (**nicht** gesprochen) → „Wechseln“-Button (Log `📖 Auto-Szenenwechsel
      vorgeschlagen → …`); erfundene/Nicht-Nachbar-ID → `🚫 Auto-Szenenwechsel '…'
      abgelehnt (Modus 'verbunden', …)`. Kurz `!ortmodus frei` testen, dann zurück.
- [ ] **Der Wechsel selbst ist der Extraktions-Trigger:** Konsole
      `🧠 NPC-Gedächtnis: N neue Erinnerungen (Szene '…')` + Zeit +30 min
      (Panel/`!zeit` — `DM_SCENE_TIME_ADVANCE`).

### Akt 6b — NPC-Gedächtnis ernten (G5)

- [ ] `!npcmem <Name>`: die Lüge steht drin — **mit wörtlichem Zitat**, noch geglaubt
      (kein „LÜGE aufgeflogen“-Tag), Wichtigkeit plausibel (Small Talk ≤ 2,
      Lüge/Versprechen 5)?
- [ ] **Zurückkommen** und den NSC ansprechen: erinnert sich der DM im Dialog, ohne dass
      es jemand wiederholt (der `[NPC-Gedächtnis: …]`-Block reitet im Prompt)?
- [ ] ⭐ **Lügen-Flip:** die Lüge im Spiel auffliegen lassen → nächster Szenenwechsel →
      Log `NPC-memory: '…' — Lüge aufgeflogen (Haltung jetzt …)`; `!npcmem` zeigt „LÜGE
      aufgeflogen“ + neuen Wichtigkeit-5-Eintrag; Haltung eine Stufe Richtung hostile.
- [ ] ⭐ **Gossip** (nur mit `faction`-Seed): wichtige Info (W ≥ 4) bei NSC A lassen →
      Szenenwechsel → Log `NPC-memory: N Gossip-Einträge verteilt`; `!npcmem <B>` (gleiche
      Fraktion) zeigt den Eintrag als Hörensagen (ohne Zitat, Wichtigkeit −1); der DM gibt
      es **vage** wieder.
- [ ] Gegen-Check: erfindet der Extraktor Erinnerungen für NSCs, die nichts mitbekommen
      haben? → `prompts/npc_memory_extract_de.md` nachschärfen oder `DM_NPC_MEMORY=0`.

### Akt 7 — Uhren & Zeit ernten (G2 + G3)

- [ ] **Tick provozieren** (etwas Lautes/Riskantes tun oder eine Probe verhauen — die Uhr
      steht als `[arbites-ermittlung] … 0/6` im Weltzustand) → „Tick“-Button erscheint
      (Log `⏱ Tick vorgeschlagen: … (0/6)`), gesprochene Antwort ohne `<<`; nach „Tick“
      zeigt das Panel `◉○○○○○` — **dieselbe Nachricht editiert**, kein neues Panel (Log
      `⏱ Tick: … → 1/6 [bestätigt]`).
- [ ] Misfire-Gegen-Check: Small-Talk-Beiträge ticken NICHT; schlägt der DM dieselbe Uhr
      zweimal im Beitrag vor → nur EIN Button (Konsole `🚫 UHR '…' abgelehnt
      (unbekannt/voll/Duplikat)`).
- [ ] **`<<ZEIT>>` provozieren** („wir durchsuchen das Archiv gründlich“, „wir rasten“) →
      „Zeit vergeht“-Button (Log `🕐 Zeitfortschritt vorgeschlagen: +N min`); nach
      Bestätigung zeigen Panel + `!zeit` den neuen Stand (Log `… [bestätigt]`).
- [ ] ⭐ Clamp: absurder Sprung → `🕐 ZEIT-Vorschlag N min auf 720 min geklemmt (max 12h
      pro Turn)`; Duplikat im Beitrag → `🚫 ZEIT '…' abgelehnt (unlesbar/rückwärts/Duplikat)`.
- [ ] **Tagesphase:** per `!zeit +14h` in den Abend/die Nacht springen → beschreibt der DM
      phasengerecht (dunkel, Läden zu, Wirt weg)?
- [ ] **Frist-Ablauf:** die Frist per `!zeit +3h` verstreichen lassen → Konsole `⏳ Frist
      '…' (…) verstrichen — Konsequenz-Hinweis für den nächsten Turn eingereiht` → der
      **nächste** DM-Turn erzählt die Konsequenz als Ereignis; `!fristen`/Panel zeigen
      **ABGELAUFEN** (genau EINMAL angemahnt) → danach `!frist weg`.
- [ ] **Uhr voll:** per `!uhr tick` auf voll (`⌛ … — VOLL`) → Konsole `⌛ Uhr '…' (…) ist
      voll — Konsequenz-Hinweis für den nächsten Turn eingereiht` → der nächste Turn
      erzählt die Konsequenz → danach `!uhr weg`. ⭐ `!uhr zurück` direkt nach einem
      versehentlichen Voll-Tick → Log `⏱ Uhr '…': eingereihter Konsequenz-Hinweis
      zurückgezogen` — die Regie-Konsequenz bleibt aus.

### Akt 8 — Konsistenz-Wächter (G6; braucht den toten Kultisten aus Akt 5)

- [ ] `!sprechmodus nahtlos` schalten — nur der **Batch-Pfad** kann regenerieren
      (ADR 045); alternativ einen Würfel-Folge-Turn nutzen.
- [ ] Gespräch gezielt auf den Toten lenken („frag <Name>, was er gesehen hat“): lässt der
      DM ihn sprechen → Konsole `[consistency] violated (dead:<Name>) — regenerating once`
      und die **gelieferte** Antwort lässt ihn nicht mehr sprechen (bloße Erwähnung /
      Leichenfund ist okay).
- [ ] Gegen-Check False Positives: normal ÜBER den Toten reden (Erinnerungen, „<Name>
      sagte damals …“) → **keine** `[consistency]`-Zeilen (unnötige Regenerationen =
      Latenz-Fresser) — sonst Muster in `dmbot/llm/consistency.py` schärfen oder
      `DM_CONSISTENCY_GUARD=0`.
- [ ] ⭐ Szenenfremder NSC: einen registrierten NSC einer *anderen* Szene ins Gespräch
      ziehen → gleiche Mechanik (`absent:<Name>`).
- [ ] Zurück zu `!sprechmodus stream`; dort einmal die Log-only-Zeile sehen:
      `[consistency] streamed answer violates (…) — audio already played, logged only
      (ADR 045)`.

### Akt 9 — Agenden ernten (G7; nach inzwischen ZWEI Szenenwechseln)

- [ ] `!agenden` nach jedem Wechsel: ein neuer offscreen-Schritt **mit
      Ingame-Zeitstempel** (Log `NPC-memory: '…' Agenda-Schritt: …`).
- [ ] **Die Kernfrage:** hat sich seine Lage **glaubwürdig** bewegt? Kleine konkrete
      Schritte (jemanden treffen, etwas verstecken, Wachen anheuern), plausibel zur
      verstrichenen Ingame-Zeit — keine Festungsbauten über Nacht.
- [ ] Zum NSC **zurückkehren**: spielt der DM die veränderte Lage (der Block trägt Ziel +
      Schritte)? Ist er woanders, tauchen **Gerüchte/Spuren** auf (die Agenden-Zeile im
      Weltzustand weist den DM genau dazu an)?
- [ ] Gegen-Check: Schritte für NSCs **ohne** Ziel verwirft der Code (Log `NPC-memory:
      agenda step for '…' without a goal — discarded`); absurde Sprünge → Agenda-Regel in
      `prompts/npc_memory_extract_de.md` nachschärfen; `!agenda <NSC> weg`.

### Akt 10 — Neustart-Gate (G8 Hälfte 1 + Crash-Recovery D41)

- [ ] Stand notieren: HP (`data/sessions/<id>/state.json` zeigt die reduzierten Wunden),
      `scene_id`, ✅-Flags, Uhrenstand, `!zeit` + Frist-Status, `!npcmem`, `!fäden`.
- [ ] Bot **hart killen** (Prozess beenden, nicht `!leave`) → Neustart → Konsole
      `loaded world state from …` + `restored N conversation turns from the autosave
      (!redo unavailable for the last)` (D41).
- [ ] `!j` → alles unverändert: Wunden, Szene, Flags (✅ und `(tot)`), Uhren-Panel-Stand,
      Zeit + Frist (inkl. „schon angemahnt“ — keine zweite Anmahnung), `!npcmem`-Einträge,
      Fäden.

### Akt 11 — Wrap & Abschied (G9-Saat Hälfte 1 + G8-Recap + Shutdown D47/D67)

- [ ] `!wrap` → `📜 Ich fasse die Sitzung zusammen …` → Konsole: die 🧠-Zeile (letzte
      Szene) **und** `🧵 Chekhov-Liste: N neue Fäden, M aufgelöst` → danach
      `📜 Was bisher geschah:` gepostet + `recap.md` geschrieben.
- [ ] `!fäden`: ist das in Akt 4 fallengelassene Detail dabei (1 Satz, plausibles
      Gewicht)? Der Hand-Seed `t1` auch noch?
- [ ] **Fenster-Check:** stammt das Detail aus einer Szene VOR dem letzten Wechsel und
      taucht **trotzdem** auf? (Der Wrap-Call bekommt den früheren Sitzungsverlauf als
      eigenen „nur für Fäden“-Kontextblock — genau das prüft dieser Punkt.)
- [ ] Qualitäts-Gegen-Check: stehen **Quests/Aufträge** oder Banalitäten in der Liste? →
      `prompts/chekhov_extract_de.md` nachschärfen; `!faden weg <id>` räumt auf.
- [ ] ⭐ Recap-Vorprüfung (G8 im Schnelldurchlauf): nach dem Wrap den Bot neu starten →
      `!j` → `📜 Was bisher geschah` erscheint, der DM knüpft an. (Der echte Beweis ist
      der Anfang von Session 2.)
- [ ] Sauberer Shutdown: **zweimal Strg+C** → Exit prompt, Stufen als `[i/n] … ✓`;
      „Voice-Channel verlassen“ in ≤ ~2 s (D67; eine `voice confirm wait
      abandoned`-Warnung ist okay).

### Nebenbei (wenn Luft ist — keine Gates)

- [ ] `!lore` blättert (◀/▶); `!lore wer ist der Imperator?` → Embed **📚 Weltwissen**.
- [ ] Lore-Färbung in den `📚`-Logzeilen: Rokarth-Frage → `setting:`, Chaos-Frage →
      `lore_chaos:`, Astronomican-Frage → `lore_imperium:`.
- [ ] `!lore tts`: Block-Text + ⏭/🔊/⏹; bei Doppel-Audio in `debug.log` prüfen: EINE
      `🔊 TTS … speaking` + EIN `/speak` pro Block ⇒ das Doppeln liegt an Bot A.
- [ ] Ein Turn mit `DM_STREAMING=0` (first_audio-Kontrast, alte Ein-WAV-Zeile); `!redo`;
      Esc/⏸ mitten im Stream.
- [ ] Watch (kein Gate-Blocker): Meta-Ramble („Als Spielleitung …“) zählen — nemos
      Ceiling, bei Häufung melden; liest XTTS echte Interpunktion vor (`. , ! ?` sind
      absichtlich drin)?

---

## Session 2 — kurze Folge-Session (G9 Hälfte 2 + G8-Bestätigung)

Kann eine ganz normale Spielsession sein — die Checks kosten keine zehn Minuten.

- [ ] Boot → `!j` → `📜 Was bisher geschah:` wird gepostet und der DM **knüpft an**,
      statt neu zu starten → **G8 vollständig**.
- [ ] **G9:** der „Lose Fäden“-Block (Top 3, für die Spieler unsichtbar) reitet im
      Weltzustand — spielt der DM das Detail **bei passender Gelegenheit** zurück, als
      Wiedererkennen statt Fremdkörper?
- [ ] Gegen-Check: zwängt er Callbacks in jede Antwort? → Persona-Bullet („nicht
      erzwingen“) in `prompts/dm_core_de.md` nachschärfen.
- [ ] ⭐ **Auflösung:** den Faden im Spiel auflösen (Frage beantwortet, Objekt erklärt) →
      `!wrap` → Konsole `chekhov: Faden [tX] als aufgelöst markiert` (die 🧵-Zeile zählt
      `M ≥ 1 aufgelöst`) → `!fäden` zeigt ihn unter „Aufgelöst“, er verlässt den
      Prompt-Block. Manueller Weg: `!faden erledigt <id>`.

---

## Nach dem Run

1. `logs/transcript.log` + `logs/debug.log` sichern und pasten → `/playtest-triage`.
2. Ergebnisse in `progress.md` zurückschreiben: Phase-9/10-`VERIFY EVIDENCE`, die
   D87/D91–D97-Befunde in den Last-session-Block, gebliebene Tuning-Werte als
   `.env.example`-Kommentare. **G9 bleibt offen bis nach Session 2.**
3. **Frisches Live-Golden ziehen (D93):** das rotierte Journal der Session kopieren → auf
   eine Handvoll Turns kürzen → `uv run dm-eval <datei>` muss sofort Exit 0 sein
   (`tests/golden/README.md`). Chemical-Burn-Referenzen bleiben lokal
   (`data/adventures/` ist git-ignored). Ab dann: `dm-eval` vor jedem Refactor-Merge.
4. Dieses Skript ausmisten: Erledigtes raus, Reste sind der nächste Run.
