# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## State header

_The only mandatory session-start read from this file (CLAUDE.md ritual). Everything below
is on-demand._

- **Phase:** 9 (Memory) + 10 (Adventure/RAG) code-complete, live gates pending; Phasen 0–8
  live-validated. Phase 10b (profile bootstrap) deliberately deferred until play runs smoothly.
- **Project priority:** the ONE tuning + scene-cards live run — script in
  [docs/live-test-checklist.md](docs/live-test-checklist.md), plan under `## Next concrete step`.
- **Newest round:** D98 → ADR 051 (marker pipeline consolidated onto the declarative
  `MarkerSpec` registry, 2026-07-04) — suite 689 green, `dm-eval` exit 0, no new live gate.
  2026-07-11: doc-diet round (this State header; Current focus → 2 blocks; decision-log rows
  slimmed, detail preserved in the ADRs).
- **Next concrete step:** Lessons memory bootstrap round (`docs/lessons/`) — workflow
  migration round 3/5.
- **Open live gates (8, all stacked into the one live run):** NPC memory (D91), consistency
  guard (D92), clocks (D94), in-game time/deadlines (D95), NPC agendas (D96), Chekhov threads
  (D97 — needs a 2nd session) + Phase 9 (HP survives restart, recap) and Phase 10 half 1
  (rule question from RAG). Over the WIP limit → next feature round that would open a new
  gate must wait for the live run; doc/tooling rounds are exempt.

## Current focus
**Cleanup-Runde: Marker-Pipeline konsolidiert + Doku-Sweep (2026-07-04, D98 → ADR 051). Suite 689 grün (+6 Registry-Tests, 0 Änderungen an bestehenden Tests), ruff-F sauber, `dm-eval` Exit 0 gegen die unveränderten Goldens — nach jedem Migrationsschritt. Verhaltensneutral, KEIN neues Live-Gate.** Das selbst notierte D94-Debt ist eingelöst, **bevor** ein sechster Marker kommt: die fünfmal handkopierte Marker-Naht (TEST/MANIFEST/ORT/ERLEDIGT/UHR/ZEIT — je eigene Regex+Dataclass+`_pending_*`-Dict, `finalize_answer` als 7-Tupel) läuft jetzt über eine **deklarative `MarkerSpec`-Registry** (`dmbot/rules/marker.py`; Tabellen-Reihenfolge = Extraktions- UND Journal-Key-Reihenfolge) + EINE generische Naht: `extract_all` (kettet die bestehenden Extraktoren byte-identisch), `finalize_answer_markers → (answer, {kind: requests})` (das 7-Tupel bleibt als test-gepinnte View), keyed Pending-Store im Brain (Queue/Redo/Reset/Consistency-Snapshot als Loops, Suppression aus `spec.suppressible`; `take_pending_<kind>`-Wrapper + Alias-Attribute halten die öffentliche Surface), labelled Task-Liste statt zwei kopierter Dispatch-Blöcke in der Delivery, dm-eval liest Keys+Drain aus der Registry. Die per-Marker-**Eigenheiten sind unangetastet** (ZEIT first-valid+12h-Clamp, UHR +1/Uhr/Turn, UHR/ZEIT suppressions-exempt, Confirm-Views unter `DM_FLAG_CONFIRM`, verklebte Marker strippen weiter); Handler-Bodies + pure Verdicts bewusst NICHT generalisiert (ADR 051 #5 — das ist das Feature, nicht die Naht). Migration marker-weise (ORT zuletzt), Journal byte-kompatibel. **Teil B:** README auf den echten Stand (Memory/RAG gelandet + Session-Tools-Liste), progress-Rotation (D75–D81-Focus-Blöcke + D60–D63-Next-step-Verlauf ins Archiv), `logsetup`-Docstring-Kosmetik, Open-questions ausgeräumt. Ein sechster Marker kostet jetzt: Dataclass + Extraktor + eine Registry-Zeile + sein eigentliches Feature. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Chekhov-Liste gebaut (2026-07-04, D97 → ADR 050). Suite 683 grün (+24), ruff-F sauber, `dm-eval` Exit 0 gegen die alten Goldens, live-unverified.** Menschliche GMs merken sich lose Fäden und spielen sie später zurück („die Münze aus Session 1? *Die* Münze.") — der Bot hat dafür jetzt eine **code-verwaltete Chekhov-Liste**: `data/sessions/<id>/chekhov.json` (atomar wie `state.json`; neues pures `dmbot/memory/chekhov.py`) mit `Thread{id (t1, t2 …), detail, origin_scene, created_session, status open|resolved, weight 1–3}`, Cap **20 offene** (Überlauf: der älteste mit dem niedrigsten vorhandenen Gewicht fliegt), Aufgelöste bleiben als Historie (gedeckelt 20). **Extraktion nur beim Wrap-up** (Fäden sind Session-Granularität, keine Szenen-Extraktion): der EINE ADR-044-Extraktor-Call bekommt bei `!wrap` eine `chekhov`-Sektion (Schema-Variante + `prompts/chekhov_extract_de.md` als System-Zusatz) — max. **5 neue** unaufgelöste Details pro Session (erwähnte Objekte, Andeutungen, offene Versprechen, unbeantwortete Fragen; KEINE aktiven Quests) + IDs in dieser Session **aufgelöster** Fäden. Code klemmt alles: Dedupe per normalisiertem Substring-/Wortmengen-Vergleich gegen ALLE Fäden (ein aufgelöster kommt nicht wieder), Auflösung wird **erkannt, nicht erzwungen** (LLM nennt IDs, Code flippt den Status; unbekannte IDs verworfen + Log). **Fenster-Problem gelöst:** der Wrap-up-Call sieht nur die letzte Szene (das Extraktions-Fenster) — der Chekhov-Input trägt deshalb zusätzlich den früheren Sitzungsverlauf als klar markierten „nur für Fäden"-Kontextblock + die offenen Fäden nummeriert; das NSC-Gedächtnis bleibt per Prompt-Anweisung aufs Szenen-Fenster gebunden (Überreichweite fangen Gist-Dedupe/±1-Clamp — Trade-off im ADR). **Injektion bewusst klein:** die Top 3 offenen (Gewicht, dann **älter zuerst** — alte Fäden sind die besten Callbacks) als „Lose Fäden (… nicht erzwingen)"-Block am Weltzustand + Persona-Absatz (einen aufgreifen, wenn er sich natürlich fügt; Liste nie wörtlich erwähnen). Commands im neuen dünnen **ChekhovCog** (TimeCog-Muster): `!fäden`, `!faden neu "<Detail>" [1-3]` (Mensch-Autorität + macht das Live-Gate ohne Voll-Extraktion testbar), `!faden erledigt <id>`, `!faden weg <id>`. Kill-Switch geerbt (`DM_NPC_MEMORY=0` schaltet die Extraktion ab; kein neuer Env-Knopf). **Live-Gate offen** (s. Next step, braucht ZWEI Sessions): in Session 1 ein Detail fallen lassen → `!wrap` → spielt Session 2 es zurück? Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

## Last session
**Doc-Diet-Runde: State header + progress.md-Diät (2026-07-11, Workflow-Migration Runde 2/5). Doc-only, Suite 689 grün als Tripwire, KEIN neues Live-Gate.**
Für den Spieltisch ändert sich nichts — die Runde macht den Session-Start billiger: `progress.md` trägt jetzt einen **`## State header`** (≤ 25 Zeilen, die einzige Pflicht-Lektüre aus dieser Datei laut CLAUDE.md-Ritual).
- **Rotation:** `## Current focus` auf die 2 neuesten Blöcke (D98/D97) gekürzt; die Blöcke D82–D96 und D74-und-älter (bis Phase 9) verbatim per Slice-Skript ins Archiv (`## Current focus (Verlauf)`, chronologisch einsortiert).
- **Decision-Log-Diät:** alle 55 langen Zeilen mit `→ ADR`-Link auf „was + Ein-Satz-Warum + → ADR NNN" gekürzt; Zeilen-Detail, das der ADR nicht schon hielt, vorher als append-only **„Addendum — detail preserved from decision log D#"**-Sektionen in 27 ADRs gerettet (~30 Addenda). Zeilen ohne ADR-Link (26 Stück) bewusst unangetastet (exempt — ihre Rationale hat kein anderes Zuhause).
- **Verifiziert (moved ≠ deleted):** 3 read-only-Audit-Pässe — Rotation byte-identisch (Archiv nur Einfügungen), Detail-Erhalt aller 55 Zeilen (ein Fund: `skill_value`-Mechanik von D61 #9 → in ADR 030 nachgetragen), Struktur-Sweep (ADR-Diffs append-only, exempt-Zeilen byte-identisch, D-Nummern-Menge unverändert). Suite 689 grün.
- **Stand:** progress.md 854 → 579 Zeilen (~52k → ~30k Tokens); über dem 400-Zeilen-Ziel bleiben das lebende Live-Run-Drehbuch in `## Next concrete step` + die exempt No-ADR-Zeilen (laut Regel akzeptiert — Token-Bulk war der Hebel). Alte Open Question „Aufräum-Pass progress.md" (D82–84) damit ✅ (Volltext im Archiv).

**Cleanup-Runde: Marker-Pipeline auf die `MarkerSpec`-Registry konsolidiert + Doku-Sweep (2026-07-04, D98 → ADR 051). Suite 689 grün (+6 neue Registry-Tests, 0 Änderungen an bestehenden Tests), ruff-F sauber, `uv run dm-eval` Exit 0 gegen die unveränderten Goldens — nach JEDEM Migrationsschritt. Verhaltensneutral, KEIN neues Live-Gate.**
- **Teil A — die Registry (`dmbot/rules/marker.py`):** `MarkerSpec{kind, keyword, extract (normalisierte Signatur), needs_profile, suppressible}` × 6 in `MARKER_SPECS`; Tabellen-Reihenfolge ist load-bearing (= Extraktions- UND `markers.*`-Journal-Key-Reihenfolge, per Test gepinnt). `extract_all(text, profile)` kettet die **bestehenden** Extraktoren in exakt der historischen Reihenfolge (byte-identisch per Konstruktion, Paritätstest gegen die handgeschriebene Kette; ohne Profil bleiben TEST/MANIFEST im Text — das alte Guard-Verhalten). `empty_markers()` = das `{kind: []}`-Skelett.
- **Teil A — die Nähte:** `finalize_answer_markers → (answer, {kind: requests})` ist die kanonische Post-Processing-Naht (Batch + `StreamAssembler.finish` — ADR-017-Parität by construction); `finalize_answer` bleibt als 7-Tupel-View (test-gepinnt, ~10 Testdateien unangefasst). `StreamResult{remaining, answer, markers}` mit `__getattr__`-Back-Compat (`res.uhr` etc. lesen `markers[kind]`); `_body` strippt über `extract_all`. Brain: **ein** keyed Store `_pending[kind]` (die Alt-Attribute `_pending_<kind>` sind lebende Aliase der inneren Dicts — `test_clocks` pokt `_pending_uhr` direkt), `_queue_markers` (geteilt von Batch+Stream; Suppression liest `spec.suppressible` — UHR/ZEIT exempt wie gehabt), `_drop_pending` (redo/redo_streaming/reset), Consistency-Snapshot/-Restore als Dict-Loops, generisches `take_pending(kind)` + die sechs Wrapper als öffentliche Surface (dicecog, die test-gepinnten getattr-Guards der Delivery-Handler, dm-eval). Delivery: beide Pfade spawnen die vier Proposal-Handler über EIN labelled `_marker_proposal_tasks` (+ `_await_turn_tasks` statt der 5-Parameter-Signatur); `eval_replay` leitet `_MARKER_KEYS` + den Replay-Drain aus der Registry ab.
- **Bewusst NICHT generalisiert (ADR 051 #5):** die Handler-Bodies (ORT first-request-only + `resolve_move`, ERLEDIGTs load-bearing Guard-Reihenfolge, UHRs Race-Recheck + Panel-Update, ZEITs first-valid + async Apply), die puren Verdicts (bleiben in `delivery.py` — die EINE Quelle für Handler + dm-eval; `rules/` darf nicht `voice/` importieren) und das profilgetriebene TEST/MANIFEST-Parsing. Ein sechster Marker kostet jetzt: Dataclass + Extraktor + eine Registry-Zeile + sein eigentliches Feature (Handler/View/Verdict/Persona) — Tupel, StreamResult, Pending-Store, die vier Lifecycle-Nähte, Journal-Dict und dm-eval-Keys ändern sich nicht mehr.
- **Vorgehen + Gates:** Registry + `extract_all` NEBEN dem Bestand (Commit), dann die Finalize/Stream-Naht in einem Schritt (dichte Marker-Unit-Tests + dm-eval `answer`/`marker` decken sie), dann die Pending-Nähte **einzeln** ZEIT→UHR→ERLEDIGT→MANIFEST→TEST→**ORT zuletzt** — Suite + `ruff --select F` + `uv run dm-eval` grün nach jedem Schritt (der Filter „kind im Store?" verschwand mit dem letzten Umzug von selbst). Journal-Kontrakt unangetastet: `markers.*`, `*_verdicts`, `lines`/`results`/`notes` byte-kompatibel, alte Goldens replayen ohne Anpassung.
- **Teil B — Doku-Sweep:** README-Intro auf den echten Stand („Persistent memory … are next" ersatzlos; neue „What the DM keeps track of"-Liste: NPC-Gedächtnis, Agenden, Konsistenz-Wächter, Uhren, Ingame-Zeit/Fristen, Chekhov, dm-eval — je ein Satz); progress-Rotation per Slice-Skript (Current-focus-Blöcke D75–D81 + die ERLEDIGT-Next-step-Blöcke des D60–D63-Verlaufs verbatim ins Archiv, neue „(Verlauf)"-Sektionen, die drei „gehört ins Archiv"-Hinweise raus); `logsetup._short_name`-Docstring nennt jetzt `voice.delivery` (D60-Kosmetik erledigt); Open questions: D94-Marker-Debt als eingelöst markiert (Volltexte im Archiv); `rules-subsystem`-Skill um den `MARKER_SPECS`-Zeilen-Schritt ergänzt.


_Ältere `## Last session`-Einträge (D97 Chekhov-Liste [Fäden-Schema + Wrap-up-Extraktion + Top-3-Injektion + ChekhovCog → ADR 050], D96 NPC-Agenden [`goal` + `agenda_log` + Extraktor-Erweiterung → ADR 049], D95 Ingame-Zeit [Minuten-Zähler + `<<ZEIT>>`-Marker + Fristen + Druck-Panel → ADR 048], D94 Consequence Clocks [`<<UHR id>>`-Marker + ClockCog + Druck-Panel + Voll-Uhr-`[Regie]`-Note → ADR 047], D93 Replay-Eval-Harness [Replay-Journal + `uv run dm-eval`, 6 Diff-Kategorien, synthetische Goldens → ADR 046], D92 Konsistenz-Wächter [deterministischer Pre-Delivery-Check, Regenerate-once, fail-open → ADR 045], D91 NPC-Gedächtnis [NpcMemory-Schema + Extraktor + Lügen-Flip/Gossip + Prompt-Block → ADR 044], D90 `dm-sync`-Entry-Point [Package-Move + hatchling, byte-identischer `[sync]`-Block], D89 Sync-Check-Fingerprint-Tool [`[sync]`-Block, Ingest-Stempel, SETUP.md-Sync-Sektion], D88 `/author-adventure`-Authoring-Skill [5-Pass-Workflow + `validate.py`, Dry-Run-Abnahme gegen Chemical Burn], D87 Stateful Scene Cards [`<<ERLEDIGT>>`-Flags, tote NSCs, gated Exits → ADR 043], D85+D86 Spielbarkeits-Tuning [repeat_penalty + Roll-Router-Carve-out, `intro_guard`-Retry], D84 `!intro`-Meta-Auftakt-Strip + Temp 0.7, D83 `!intro`-Temperatur + Direktive, D82 Default-Party-Fix, D81 Scene-/Lore-Sub-Cogs, D80 Deepening #4–#6 [prompt_assembly/seed_session/clear_panel], D79 Deepening #1+#2 [`combat.py`-Auslagerung + `segments.py`-Verdrahtung], D78 Skill-Tooling-Runde [4 Claude-Code-Skills: /tdd, /grill-me, /improve-architecture, /to-prd], D77 Dev-Gates [Lint-Stop-Hook + blockierender git-pre-commit + Review/Simplify-Checkliste], D76 `disconnect_voice`-Kontrakt + neuer Delivery-Test, D75 One-Shot-Setup, D74
Delivery-Pipeline-Auslagerung, D73 `_TurnTiming`-Auslagerung, D70–D72 `orchestrator`-E1–E4-Verschlankung, D69 `puffer`-Modus,
D68 globaler Sprech-Modus, D67 Shutdown-Leave-Limit u. a.): siehe **[docs/progress-archive.md](docs/progress-archive.md)**._

## Next concrete step

**Lessons memory bootstrap round (docs/lessons/)** (Workflow-Migration Runde 3/5; der Live-Run-Fahrplan unten bleibt die Projekt-Prio).

> **Drehbuch für den Live-Run:** alle offenen Gates unten sind als abhakbare Checkliste in
> **[docs/live-test-checklist.md](docs/live-test-checklist.md)** ausformuliert (Session-Reihenfolge:
> Vorbereitung → Tempo → Intro → Gespräch → Würfel → Scene Cards → Konsistenz-Wächter →
> **Uhren** → **Zeit & Fristen** → NPC-Gedächtnis → **NPC-Agenden** → **Lose Fäden (Hälfte 1, §7c)** → RAG → Neustart-Gate → Nachbereitung; Chekhov-Hälfte 2 = Folge-Session). Nach dem Run:
> Ergebnisse hierher zurückschreiben, Liste ausmisten.

**0. Vorab (D89 ✅ / D90):** Die 20 fehlenden `.env`-Keys sind nachgezogen (`dm-sync` meldet 38/38, 2026-07-02). Vor dem nächsten Timo-Sync auf beiden Maschinen `uv run dm-sync` (Timo vorher einmal `git pull` + `uv sync`), Blöcke diffen (SETUP.md §„Staying in sync").

**1. Der EINE Live-Run der Spielbarkeits-Tuning-Runde (Top-Prio, Tobi nächste Session — pullt `f44cba8` + Neustart).** Zwei Teile in einem Run:
- **Workstream A (Tempo/GPU-Offload) zuerst, reine `.env`:** `OLLAMA_HOST` auf die Offload-Box + `TTS_DEVICE=cuda` setzen → `nvidia-smi` (kein OOM, XTTS-cuda + Whisper passen auf die freie 4070) → `[latency]`-Zeile vorher/nachher (`first_audio`/`tts` fallen klar, Sprech-Lücken weg). Wenn schnell genug: Default-Lieferart Richtung `nahtlos` live abwägen; dann **ADR-002-Addendum + `architecture.md` §3** nachziehen.
- **Dann `!intro test` + ein paar Spieler-Turns + eine Regelfrage:** Intro zuverlässig **ein** Monolog mit **jeder Figur** (C1-Retry greift bei zu kurz/Figur fehlt, D86), **weniger Wiederholung/Generik** (B1 repeat_penalty, D85). Tuning live: `DM_REPEAT_PENALTY` (1.0 = aus, höher = strenger), `DM_INTRO_TEMPERATURE` (0.8 mehr Flair / 0.3 ruhiger). Schließt nebenbei **Phase-10-Gate-Hälfte 1** (Regelfrage aus RAG) + die offenen D82–D84-Intro-Punkte ab.
- **Neu dazu (D91, im selben Run abprüfbar) — das NPC-Gedächtnis-Gate:** eine Szene spielen und einem NSC etwas Markantes erzählen (ideal: ihn **anlügen**, z. B. eine falsche Identität behaupten) → Szene wechseln (`!ort` oder bestätigter `<<ORT>>`-Button; Konsole zeigt `🧠 NPC-Gedächtnis: N neue Erinnerungen`) → `!npcmem <Name>` zeigt den Eintrag (Lüge mit Zitat, `believed` noch true) → **zurückkommen** und prüfen, ob der DM sich im Dialog erinnert (der `[NPC-Gedächtnis: …]`-Block reitet im Prompt). Kür: die Lüge im Spiel auffliegen lassen → nächster Szenenwechsel → `!npcmem` zeigt „LÜGE aufgeflogen" + Wichtigkeit-5-Eintrag, Haltung eine Stufe Richtung hostile. Feature ist **live-unverified** bis dahin; Fehlverhalten (Small Talk als Wichtigkeit 5, erfundene Erinnerungen) → `prompts/npc_memory_extract_de.md` nachschärfen oder `DM_NPC_MEMORY=0`.
- **Neu dazu (D92, im selben Run abprüfbar) — das Konsistenz-Wächter-Gate (Checkliste §6b):** einen NSC auf 0 Wunden bringen (oder das tote-NSC-Setup aus dem D87-Skript nutzen), dann das Gespräch gezielt auf ihn lenken („frag Grendel, was er gesehen hat") → im Batch-Pfad (`!sprechmodus nahtlos` oder ein Würfel-Folge-Turn) sollte bei einem Verstoß die `[consistency] violated … regenerating once`-Zeile feuern und die gelieferte Antwort den Toten **nicht** sprechen lassen; im Default-`stream`-Modus stattdessen die Log-only-Warnzeile beobachten (Trade-off, ADR 045). Fehlverhalten (False Positives → unnötige Regenerationen) → Verbliste/Muster in `dmbot/llm/consistency.py` schärfen oder `DM_CONSISTENCY_GUARD=0`.
- **Neu dazu (D87, im selben Run abprüfbar):** Stateful-Scene-Cards-Live-Skript — (a) `!ort` zeigt die Element-IDs (⬜); (b) eine Gelegenheit im Spiel abschließen → `<<ERLEDIGT>>`-Button erscheint, Antwort enthält kein `<<`, nach „Abhaken" zeigt `!ort` ✅ und der nächste Prompt-Dump „Bereits geschehen:"; (c) `!offen`/`!erledigt` togglen ohne Button; (d) einen `leads_to`-Eintrag testweise auf `{"ziel": …, "requires": "opp-1"}` setzen → Ziel fehlt in „Mögliche nächste Orte", Auto-`<<ORT>>` dorthin wird abgelehnt (🚫-Konsolen-Zeile nennt `opp-1`, nichts im Channel), nach `!erledigt opp-1` geht's; (e) NSC auf 0 Wunden → Karte rendert `(tot)`, übersteht Neustart. (Stand ist committet + gepusht — nur pullen + Neustart.)
- **Neu dazu (D94, im selben Run abprüfbar) — das Consequence-Clocks-Gate:** vor oder während der Session eine Uhr anlegen (`!uhr neu "Arbites-Ermittlung" 6` — Panel erscheint mit ◉/○-Segmenten), dann den DM einen Tick provozieren (etwas Lautes/Riskantes tun oder eine Probe verhauen — die Uhr steht als `[arbites-ermittlung] … 0/6` im Weltzustand-Prompt) → ein `⏱ Tick vorgeschlagen`-Button erscheint (Antwort enthält kein `<<`), nach Bestätigung zeigt das **Panel** den neuen Stand (edit-in-place, keine neue Nachricht). Kür: per `!uhr tick` bis auf voll ticken → nächster DM-Turn trägt die `[Regie] Die Uhr „…“ ist voll`-Zeile und der DM erzählt die Konsequenz; danach `!uhr weg`. Fehlverhalten (Marker feuert nie / bei jedem Beitrag) → Persona-Bullet in `prompts/dm_core_de.md` nachschärfen; Misfires bleiben dank Confirm-Button folgenlos.
- **Neu dazu (D95, im selben Run abprüfbar) — das Ingame-Zeit-Gate:** `!zeit` zeigt „Tag 1, 08:00 (Morgen)"; eine kurze Frist setzen (`!frist neu "Treffen mit dem Informanten" +2h` — Druck-Panel zeigt 🕐-Zeit + ⏳-Frist), dann spielen: (a) der DM webt die **Tagesphase** in Beschreibungen ein (abends/nachts andere Stadt); (b) bei spürbar vergehender Zeit (Durchsuchung, Fußmarsch, Rast) erscheint ein `🕐 Zeitfortschritt vorgeschlagen`-Button (Antwort enthält kein `<<`), nach Bestätigung zeigen Panel + `!zeit` den neuen Stand; (c) ein Szenenwechsel schiebt +30 min (Konsole/Panel); (d) die Frist per `!zeit +3h` **verstreichen lassen** → nächster DM-Turn trägt `[Regie] Die Frist „…“ ist verstrichen` und der DM spielt die Konsequenz ein; `!fristen` zeigt ABGELAUFEN bis `!frist weg`. Fehlverhalten (Marker feuert nie / ständig / absurde Sprünge) → Persona-Absatz nachschärfen; Misfires bleiben dank Confirm-Button + 12h-Clamp folgenlos.
- **Neu dazu (D96, im selben Run abprüfbar) — das NPC-Agenden-Gate:** einem markanten NSC ein Ziel geben (`!agenda <NSC> "will die Ware aus der Stadt schaffen"` — `!agenden` zeigt es), dann **zwei Szenen spielen** (jeder Szenenwechsel triggert die 🧠-Extraktion, die jetzt auch den Agenda-Schritt vorschlägt) → `!agenden` zeigt nach jedem Wechsel den neuen offscreen-Schritt (mit Ingame-Zeitstempel) und die Frage ist: **hat sich seine Lage glaubwürdig bewegt** (kleine konkrete Schritte, plausibel zur verstrichenen Zeit — keine Festungsbauten über Nacht)? Dann zurück zum NSC: der DM spielt die veränderte Lage (Block trägt Ziel + Schritte); während er woanders ist, sollten Gerüchte/Spuren auftauchen (Weltzustand-Zeile). Fehlverhalten (absurde Sprünge, Schritte für ziellose NSCs im Text, tote Planer) → `prompts/npc_memory_extract_de.md`-Agenda-Regel nachschärfen; `!agenda <NSC> weg` oder `DM_NPC_MEMORY=0` schaltet ab.
- **Neu dazu (D97, braucht ZWEI Sessions) — das Chekhov-Gate:** in Session 1 beiläufig ein markantes Detail etablieren (oder direkt seeden: `!faden neu "Die Münze aus der Bar" 2`), am Ende `!wrap` — Konsole zeigt `🧵 Chekhov-Liste: N neue Fäden, M aufgelöst`, `!fäden` zeigt die Liste. In Session 2 prüfen: spielt der DM das Detail bei passender Gelegenheit zurück (der Top-3-Block „Lose Fäden" reitet im Weltzustand) — und zwängt er es NICHT in jede Antwort? Kür: den Faden im Spiel auflösen → das nächste `!wrap` markiert ihn `resolved` (`!fäden`). Fehlverhalten (Quest-Duplikate, Banalitäten als Faden, Dauer-Callbacks) → `prompts/chekhov_extract_de.md` bzw. den Persona-Bullet nachschärfen; `!faden weg <id>` räumt auf.
- **Neu dazu (D93, Nachbereitung des Runs):** aus dem rotierten Journal der Session ein **frisches Live-Golden** ziehen (`tests/golden/README.md`: kopieren → auf eine Handvoll Turns kürzen → `uv run dm-eval <datei>` muss sofort Exit 0 sein). Referenziert es Chemical Burn, bleibt es lokal (data/adventures/ ist git-ignored) — trotzdem wertvoll als Regressions-Gate auf Tobis Maschine. Ab dann: `uv run dm-eval` vor jedem Refactor-Merge (conventions.md §Testing).
- Danach: Log pasten → Playtest-Triage-Iteration. **Bootstrap bleibt zurückgestellt**, bis das Spielen rund läuft.
- **Parat, wenn Abenteuer #2 dran ist (D88):** `/author-adventure <md> <id>` — erst „The Blazing Seraph" per `/rag-ingest`-Konverter nach `data/pdfs/md/`, dann der Skill (stoppt zur Szenenschnitt-Freigabe). Drafts landen im untracked `data/adventures/<id>/` — Buch-Derivate bleiben lokal, nur der Skill ist committet.

**2. Die offenen Phase-9/10-Live-Gates abhaken (Code ist da, nur Live-Abnahme fehlt):**
- **Phase 9:** eine HP-Änderung übersteht einen echten Neustart + der Recap erscheint beim nächsten `!join` (in-prompt).
- **Phase 10:** eine konkrete **Regelfrage** wird korrekt aus dem Regelbuch-RAG beantwortet. Danach das **einzige noch zu bauende** Feature: **Profil-Bootstrap (§9)** — der DM schlägt aus dem Regelbuch ein System-Profil vor → Tobi bestätigt → speichern.

**Zusätzlich diese Session live zu verifizieren** (alle code-complete, unverifiziert) — fällt im
selben circlejerk-Run mit ab:
- **Schneller Start** (ADR 024): Konsole erreicht zügig „logged in"; `!join` zeigt ggf. ⏳/⚠-TTS-Hinweis; erster Satz wird gesprochen.
- **`!lore tts`**-Reader: Block-Text im Chat + ⏭/🔊/⏹; **Doppel-Beleg** in `debug.log` (eine `🔊 TTS … speaking` + ein `/speak` pro Block ⇒ Doppeln liegt an **Bot A**).
- **Conditions/`!rules`**: „Was bewirkt Blutend/Betäubt?" → korrekte deutsche Antwort (neue `conditions`-Quelle); Inquisitions-Fragen treffen player_guide/gm_guide.
- **Wiederholung**: verweist der DM auf Etabliertes knapp, statt es neu auszuerzählen?
- **Auto-Szenenwechsel** (ADR 026): die Gruppe betritt einen verbundenen Ort → DM beendet den Zug mit `<<ORT …>>` (**nicht** gesprochen), ein **„Wechseln"-Knopf** erscheint, Klick verschiebt den Pointer wie `!ort`; eine erfundene/Nicht-Nachbar-ID im `verbunden`-Modus wird ignoriert+geloggt. `!ortmodus frei` testen, dann zurück. `scene_id` überlebt Neustart.

**ONE live session in circlejerk covers everything (Tobi).** Before it: **review the compendium**
(`data/adventures/chemical_burn/adventure.json` + `npcs.json` — spot-check scene cards for tone
and the never-say secrets). Then `!j` **in circlejerk** and check in this order:
1. **Join line-up:** party named (**die drei neuen Charaktere** — a ⚠ warning = wrong channel,
   stop) + `📖 Abenteuer: Chemical Burn — Szene: Der Auftrag`.
2. **Phase 10 gate half 1:** ask a rule question by voice („Was passiert bei einem kritischen
   Erfolg?") → answer grounded in the book (a `📚 Regelwerk:` line appears in `debug.log`).
3. **Plot coherence (D44):** the DM opens with Halikarns Auftrag, not improv; `!ort mud_gate` →
   the narration moves to the harbour; a part-1 „wer steckt dahinter?" stays unspoiled.
4. **D43 checks:** post-roll turn narrates the consequence (no parroted player line — watch for
   `echo guard` WARNINGs); attack → **combat-skill** button (router decides); `history.jsonl`
   pairs correct when 🎲 is clicked mid-speech.
5. **Phase 9 gate:** `!npc add Kultist` (statblock auto-fills now) → attack → `💥 …` → **restart**
   → `!j` → wounds unchanged; recap flow as before.
6. **W4/W5:** ask „Warum sind wir hier?" twice — expect an answer, not a re-description (watch
   for the self-repetition WARNING). Then fill the Phase-9 + Phase-10(half) VERIFY EVIDENCE.
7. **Lore (D46):** eine Rokarth-Frage („Wem gehört diese Stadt eigentlich?") → Antwort mit
   Setting-Färbung (`📚`-Logzeile zeigt `setting:`); „wer steckt hinter Gratis?" bleibt vage.
8. **Lore (D48/ADR 021):** eine Chaos-Frage („Was weiß man über die Chaosgötter?") → grimdark
   Antwort mit Kompendiums-Färbung (`📚`-Logzeile zeigt `lore_chaos:`); eine Imperiums-Frage
   („Was ist das Astronomican?") zeigt `lore_imperium:`.
9. **`!lore` (D49):** `!lore` blättert (◀/▶), `!lore wer ist der Imperator?` antwortet als
   Embed (Retrieval offline schon verifiziert — hier nur checken, dass Embed + Buttons im
   echten Discord rendern).
10. **Psyker (D51/ADR 022):** with a psyker in the party (the example **Mortn**, or a new build
    with a `psyker: true` + `known_powers` + a `Psi-Meisterschaft` skill), have them wield a power
    by voice → a `🌀 Manifestation angefordert` button appears; click it → a `🌀 … Warp X/4` line,
    and the DM narrates the effect. Push a power a few times to drive Warp Charge over the threshold
    → a `🜏 Perils of the Warp` line fires and Warp resets; the value survives a restart. First do
    the **Player's Guide RAG ingest** (command in Current focus) so a psyker rule question
    („Was sind Perils of the Warp?") retrieves the book.
11. **Augmetik + Erstellung (D52/ADR 023):** ein Charakter mit Implantat (Beispiel: Vask
    „Augmetischer Arm", Mortn „Augur-Array"). Greif Vask an → Soak +1 (1 Wunde weniger); ein
    Wahrnehmungs-Wurf für Mortn liegt +5 höher. Im Weltzustand erscheint der
    `## Augmetik/Implantate`-Block. Erstellung: `docs/how-to-create-a-character.html` öffnen →
    Implantate/Psioniker wählen → JSON enthält `augmetics`/`known_powers`;
    `tools/fill_character_sheet.py` → Psi-Tabelle, Warp-Schwelle und Augmetik-Spalte sind im PDF gefüllt.
Watch `ctx=` in the `[latency]` lines — the adventure block adds ~1k tokens; the D36 warning
fires above 85% of 8192. Dial: **Opus 4.8 / xhigh** (roadmap recommends opusplan/high for
Phase 10 planning; the building is done — the run is verification).

**✅ Prerequisite resolved (2026-06-10) — party registered + session reset.** The
`circlejerk` channel (`1343673766487654464`) now has a hand-authored
`data/sessions/<id>/characters.json` with three deliberately-different IM builds (so rolls aren't
raw any more): **Garran Vex** (Pr0degie/Tobi — Nahkampf bruiser, Kettenschwert 1d10+5, Tgh 52),
**Eli Castor** (Timo — Fernkampf, Lasgewehr 1d10+4), **Magos Yann** (Sezgin/SezBoss69 — tech/skill,
„Schockstab" not in the weapons table → tests the `default_damage` 1d10 fallback, starting condition
„Benommen"), with aliases mapping each Discord name → character. The old `state.json` + `history.jsonl`
+ `recap.md` (seeded from the example party, test-run garbage, bar recap) were **deleted**, so the
next `!join` re-seeds the world state fresh from the new sheet. (Channel files are git-ignored —
session-local.)

**Secondary live checks (same session, when convenient — older landed-but-unproven work):**
- **D42 re-confirm:** no empty/marker-only turn read aloud (no 15-s lone quote), **no dice loop**.
- **Crash recovery (D41):** kill the bot hard (not `!leave`) → `!j` → `restored N conversation
  turns`; a clean `!leave` → next `!j` is fresh.
- **Router timing (D40):** the 🎲 appears **while the DM still speaks**; exactly one per action.
- **first_audio contrast** + `!redo` + pause/Esc mid-stream: one turn with `DM_STREAMING=0`.
- **Shutdown (D47 + D67):** Ctrl+C twice during a streamed turn → exit is prompt (no multi-second hang)
  and prints `[i/n] … ✓` per stage + a summary that names the dropped synth. **D67:** the
  „Voice-Channel verlassen" stage now finishes in ≤ ~2 s (no more up-to-30 s confirmation hang); a
  `voice confirm wait abandoned` warning is fine (the channel is already left).
- **Vor der Session:** `docs/how-to-play.html` an Timo & Sezgin verteilen (deutsches
  Regel-Primer, 2026-06-12 erstellt) — spart die Regelerklärung am Tisch.

**Watch (persona/adherence, not gate blockers):** the **meta-ramble** („Als Spielleitung beschreibe
ich nicht direkt die Szene…") — nemo's ceiling, report if frequent; and whether XTTS still reads any
*real* punctuation aloud (the lone-quote bug is fixed; `. , ! ?` are kept on purpose for intonation).

**Exact test sequence (durable copy of the chat checklist — `DM_LOG_FILE=1` + `DM_TRANSCRIPT_FILE=1`
are already on in `.env`):**
1. _Auto-combat:_ `!j` → `!npc add Kultist 10 3` (10 Wunden, ToughnessBonus 3; optional armour as a
   4th arg) → `!test Nahkampf für Timo` (or a voice "ich greife den Kultisten an" → router posts the
   button) → click 🎲 → on success, pick **Kultist** in the target dropdown → expect a `💥 … = N Wunden
   → Kultist M/10` line. Confirm it fires **only** on Nahkampf/Fernkampf + only on success.
2. _Gate 1 (HP survives restart):_ check `data/sessions/<id>/state.json` shows the reduced wounds;
   `!npc list`; try `!damage Kultist 5` / `!heal Kultist 3` (0 → "kampfunfähig"). **Restart the bot** →
   `!j` → wounds still reduced.
3. _Gate 2 (recap):_ play a few turns → `!wrap up` (or `!wrapup`) → German "Was bisher geschah" posted +
   stored (`state.json` recap + `data/sessions/<id>/recap.md`). **Restart** → `!j` → "📜 Was bisher
   geschah" shown and the DM continues from it.
4. _Watch & report (paste `debug.log` + `transcript.log`):_ damage numbers sane? target dropdown listing
   fellow PCs annoying or fine? does the DM honour the injected world-state HP without inventing values?
   recap quality (German, factual, length)? any `ERROR` lines?
5. _Latency / streaming (D35 + ADR 017):_ every DM turn logs `[latency] turn=… [stream] stt=…
   trigger→llm_done=… ctx=…/8192 gen=… chars=… first_audio=…ms tts=… bridge_wait=… total=…`. Paste a
   few — the **before/after** is `first_audio` (streamed) vs `trigger→llm_done + tts` (the old
   pre-audio gap). Toggle `DM_STREAMING=0` for one turn to see the old single-WAV line for contrast.
6. _Crash recovery (D41):_ play a few turns → **kill the bot** (not `!leave`) → `!j` → expect
   `restored N conversation turns`. Then a clean `!leave` → next `!j` is fresh and the old log is at
   `data/sessions/<id>/history.<ts>.jsonl`.
- Run the unit suite with **`uv run --with pytest python -m pytest -q`** (pytest isn't in the default
  venv — see [[run-tests-command]] memory). Currently **177/177** green.

_Resolved this session (no longer open):_ the **gemma3 vs nemo** taste test (gemma3 didn't fix the
marker problem; nemo kept for tone — the fix was the **roll-detection router**, ADR 014); **two-stage
Ctrl+C** shutdown (done); the **auto-test** (router, live-validated).

_Carry-overs & future directions (Stand 2026-06-12 abends):_
1. **Modell-Test (Timo):** Mistral Small (o.ä.) auf Timos Box / der 5080 via Tailscale —
   unabhängig vom Story-Code, Umschalten = `OLLAMA_HOST`-Einzeiler (D6/ADR 002). A/B gegen nemo
   mit identischer Story fahren, erst NACH der Gate-Session (sonst zwei Variablen gleichzeitig).
2. **Director→Narrator-Experiment (Timos Architektur-Idee, Diskussion 2026-06-12):** ein
   constrained-JSON-Call entscheidet pro Turn strukturiert *was passiert* (Szenenziel,
   NSC-Aktionen, State-Änderungen), nemo macht nur Prosa. **Bewusst aufgeschoben** — der
   Szenen-Tracker (ADR 019) ist die deterministische Vorstufe; erst bauen, wenn Live-Spiel
   zeigt, dass `!ort`-Handarbeit nervt oder die Szenen-Kohärenz trotz Karten kippt.
   Kosten wären ~+1–3 s pro Turn (Single-GPU).
3. **„The Blazing Seraph"** (Starter-Set-Abenteuer, 49 S., eigenes Bestiarium) → zweites
   Szenen-Kompendium, NACH dem Chemical-Burn-Live-Test (Feedback einarbeiten). Danach:
   `DM_ADVENTURE` umschalten genügt.
4. **„Villains on Voll" (Setting Guide S. 58–67) nachingestieren**, sobald die
   Chemical-Burn-Kampagne durch ist (`pdf_to_md --pages 58-68` → `ingest --source setting`).
5. **RAG-Schwelle tunen:** `MAX_DISTANCE` 0.45 ist auf wenigen Fragen kalibriert; deutsche
   Zustandsnamen („Blutend") liegen knapp drüber. Gegen Live-`📚`-Logzeilen nachjustieren.
6. **Repo-Sichtbarkeit (Tobi-Entscheidung):** Repo ist PUBLIC → `data/adventures/` bleibt
   untracked (Ableitung gekaufter Bücher). Auf privat stellen + whitelisten, wenn das
   Kompendium versioniert/auf die 5080-Box synchronisiert werden soll.
7. **Remote/Tailscale bridge (ADR 010)** — implemented, **never live-tested**; two-machine check
   per README "Split hosting" when wanted.
8. **Roll-router live feel** — router-wins ist seit D43 die einzige Quelle; spurious/odd buttons →
   classifier prompt (`dmbot/llm/roll_router.py`) tunen. Inline `<<TEST>>` nur noch bei
   `DM_ROLL_ROUTER=0`.
9. Older: STT confidence filter on noisy speech; toggleable edit/review window (Part 2; pause
   control D27/ADR 013 is its groundwork); **input bleed** (stream audio into mics — wake-word
   concern, not a bug); benign `voice_recv` `voice_member_disconnect` traceback (alpha lib — watch).
10. **Player-wish status (ADR 016 W-Liste):** **W1** (puppeting) Code-Backstops seit ADR 016,
    **W2** (Latenz) ✅ Streaming ADR 017, **W3** (Stop-Button) ✅ Tobi, **W4** (Wiederholung)
    Code-Guard seit D45 (live-unverified), **W5** (exakte Frage) adressiert über
    Roll-Direktive + Szenenkarten + W4-Nudge (live-unverified), **W6** (TTS-Interpunktion) ✅,
    **W7** = Phase-9-Gate (pending), **W8** (derbe Inhalte engagen) **offen** — nemos Ceiling,
    beim Modell-Test (Punkt 1) mitbewerten.

---

## Decision log

**This log is the index to the ADRs.** Each row with a real trade-off links its decision to
a full ADR under `docs/decisions/` (the `→ ADR NNN` at the end of the rationale). The
session-start read covers only the *newest* ADR for recency; the **older ADRs are read on
demand** — when you start a phase or touch a subsystem, follow the `→ ADR` links of the
decisions that govern it (see the phase → ADR map below). A new non-trivial decision →
create the next-numbered ADR.

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Ruleset approach | **System-agnostic** — generic engine + per-system profile; **Imperium Maledictum is the first** profile (1d100 roll-under, SL) | Reusable DM, not a 40k one-off; IM only the first loaded system → ADR 005 |
| D2 | Mechanic depth v1 | Voice narration **+ dice & turn buttons** in the text channel | Playable without the bot having to manage all the rules |
| D3 | Memory | **JSON world state + session recaps** | JSON = hard facts, recap = narrative thread; together coherent without context overflow |
| D4 | Knowledge source | **RAG over rulebook & story PDFs** (NOT character sheets) | Rule knowledge ingestible; reduces rule hallucination. Sheets → JSON (D12) |
| D5 | Bot language | **Python (discord.py)** for both bots | Music bot is discord.py; the voice-recv ecosystem is Python |
| D6 | LLM host | **Dev: everything local on Tobi's 4070** (Nemo 12B); later optionally only Ollama on the 5080 via Tailscale | Develop/debug locally; separate networks are a non-issue for the MVP; upgrade = one `OLLAMA_HOST` switch → ADR 002 |
| D7 | Language/tone | **German play language**; generic GM persona + **per-campaign tone overlay** (first: Eisenhorn / Dan Abnett grimdark) | Tone is campaign-specific, not the DM's fixed identity → ADR 005 |
| D8 | Player count | 2–5, semi-turn-based | — |
| D9 | Output bot | **Reuse the music bot** + `/speak` bridge | Already in the voice channel, can play audio |
| D10 | Conversational control | **Transcribe continuously + buffer, DM turn triggered by button**; VAD only for segmentation. Wake word is a later goal | DM doesn't talk over anyone, no table talk in the game, semi-turn-based → ADR 003 |
| D11 | Dice test trigger | **LLM emits a test marker** (`<<TEST …>>`), code rolls; manual button fallback | Loop mostly automatic but robust against parse errors → ADR 004 |
| D12 | Character data | **Lean structured JSON**; the stat/skill/resource shape follows the **active system profile**; sheets transferred once, NOT RAG | Enables stat-aware rolls + resource tracking per system; Phases 8/9 one piece → ADR 004 + 005 |
| D13 | Registration | **Guided & sequential** — bot asks character by character, a click maps user-ID → character | Bot must know who plays whom (addressing + rolls) → ADR 003 |
| D14 | Recap trigger | **`wrap up` command** ends the session & generates the recap; rolling mid-summary later | Clear trigger; 128k context has headroom |
| D15 | Bot A signal | **`/speak` blocks until playback ends** | Return moment = resume signal; no status/shared state needed. _Confirmed in implementation (commit `249cc38`); a redundant callback was removed._ |
| D16 | Runtime environment | **Windows** (both bots + pipeline) | No `/tmp` (OS temp dir); Opus DLL for voice; cuDNN/cuBLAS DLLs on `PATH` for faster-whisper. _WSL considered but rejected — keeps both bots co-located so the file-path bridge works without path translation. Co-location is no longer mandatory: the bridge now also runs split across machines via bytes-over-Tailscale (D23 / ADR 010)._ |
| D17 | Doc language | **Dev docs in English** (game content stays German) | Token efficiency on docs read every session; matches the schema precedent |
| D18 | System-agnostic engine | **Generic dice/resolution engine + per-system profile**; DM **proposes the profile from the PDF**, user confirms (MVP). Persona = generic GM + per-campaign tone overlay | Reusable across rulesets; "paste PDFs → DM knows what's played"; dice still code → ADR 005 |
| D19 | DAVE/E2EE on voice receive | **Decrypt the DAVE layer via discord.py's `dave_session`** (keep E2EE; sink takes `wants_opus=True`, decrypts each frame before Opus-decode) | Discord calls are end-to-end encrypted; voice-recv only undoes transport → garbage. Declining DAVE is rejected (voice close 4017) → ADR 006 |
| D20 | VAD segmentation stack | **silero-vad via `onnxruntime`** (no torch) + **`soxr`** streaming resampler; model vendored in-repo | Robust neural VAD without torch's ~GB weight; webrtcvad too noise-prone; soxr is the smallest correct resampler → ADR 007 |
| D21 | TTS engine | **XTTS v2 (`coqui-tts`) default + Piper fallback**, selectable via `TTS_ENGINE`; XTTS speaker Dionisio Schuyler | Piper's German voices were rejected; XTTS gives 58 voices + cloning, local → **ADR 008 + 009** |
| D22 | GPU XTTS / portability | **CUDA torch from the `cu130` index**, device env-driven (`TTS_DEVICE`/`WHISPER_DEVICE`), same Windows-only lock for both boxes, XTTS auto-degrades to CPU | One repo runs 4070 dev + 5080 full-GPU → **ADR 009** |
| D23 | Bridge transport | **Hybrid `/speak`**: loopback → WAV path (unchanged); remote → WAV bytes + shared secret over Tailscale; Bot A plays its own copy | Lets DMbot + Bot A run on different machines without breaking the proven localhost path; partially relaxes D16/ADR 002 co-location for the bridge → ADR 010 |
| D24 | STT latency | **GPU whisper (`WHISPER_DEVICE=cuda`) + push-to-talk DM-routing gate** (whole table still transcribed + logged; the button gates what reaches the DM) | CPU whisper fell ~1.5 min behind; gating cuts DM noise, keeps the full record → **ADR 011** |
| D25 | Feedback layer 2 | **Pausing the VAD while Bot A speaks is now opt-in, off by default** (`DM_PAUSE_VAD_WHILE_SPEAKING=0`). Layer 1 (Bot-A user-ID filter) stays mandatory | Layer 1 already stops self-transcription and the push-to-talk routing gate keeps narration table talk out of the DM, so layer 2 was redundant and blocked transcription during the DM's narration — players wanted the table kept in the record. golden rule #4 (layer 1) unchanged; updates `architecture.md` §5 |
| D26 | Phase-8 dice flow | **Difficulty is a ladder *word* resolved to a number in code**; minimal character JSON + alias map pulled into Phase 8; turn order seeded from the voice channel | Honours "dice = code" (open items K + F); the number lives in profile/character data, not the LLM → **ADR 012** |
| D27 | Pause control | **One shared `_paused` freeze**, driven by the terminal Esc key AND a Discord ⏸ button; pause mutes the VAD/STT pipeline + blocks all DM turns | Tobi wanted both controls, a visible state and a real freeze → **ADR 013** |
| D28 | Lore representation (Phase 10) | **RAG, not fine-tuning, for facts.** 40k lore from **both** wiki sources (Fandom official XML dump + Lexicanum via MediaWiki API / archive.org), **text only**, chunked + `nomic-embed-text` → **`sqlite-vec`** with rulebook vs lore as separate `source`s. Fine-tuning only later as a **tone-LoRA** (style, not facts) | Fine-tuning hallucinates facts, can't cite, needs retraining to update + a wiki doesn't fit in 12B weights/context; RAG is grounded/citeable/updatable (golden rule #7). Both wikis ≈ 0.8–1.3 GB (images excluded). Plan saved; → a new ADR when Phase 10 starts |
| D29 | Auto-test trigger | **Roll-detection router** — a stateless constrained-JSON classifier picks the test after narration; inline `<<TEST>>` kept as fallback; **ON by default** (`DM_ROLL_ROUTER`) | The inline marker failed live — a documented, model-size-independent LLM-GM failure → **ADR 014** |
| D30 | Ollama readiness | **`start_dmbot.bat` warms a *local* Ollama before launch** (boots the daemon + loads the model; skipped for a remote `OLLAMA_HOST`) + a **boot preflight** (`llm/preflight.py`) pings the host / checks the model is pulled | A not-running Ollama failed turns mid-game with a cryptic `ConnectError`; warm-up + a clear boot message turn that into a startup-time signal. Ops polish, no ADR |
| D31 | Shutdown UX | **Two-stage Ctrl+C** — first press prints "Quit?" and keeps running, the second an animated "Shutting down …" then tears down cleanly | Avoids killing a live session on a single fat-fingered Ctrl+C; discord.py 2.7.1 installs no SIGINT handler so ours stays in effect. Ops polish, no ADR |
| D32 | Memory state file | **Split** — `characters.json` stays the read-only sheet; a code-owned `data/sessions/<id>/state.json` holds the mutable layer, seeded once from the sheet, saved atomically on every change | Keeps the hand-authored sheet pristine and gives a clean reset + restart gate; rejected one code-rewritten blob → **ADR 015** |
| D33 | Combat damage | **Auto-applied on a hit** — a successful attack rolls weapon damage and applies **weapon + SL − soak** to a target, driven by the profile's `combat` block | Realises the dice engine's damage in play and stays system-agnostic via profile data → **ADR 015** |
| D34 | Log verbosity | **Trim the logger name** — drop it entirely on INFO console/mirror lines, strip the `dmbot.` prefix on WARNING/ERROR + in `debug.log`; third-party names kept | Tobi pastes logs for the playtest-tuning loop; the repeated `dmbot.voice.commands` prefix wasted tokens while the message (often emoji-prefixed) already carries the context. Levels/colour/tracebacks unchanged. Ops polish, no ADR |
| D35 | Latency instrumentation | **One `[latency]` log line per DM turn** — a `_TurnTiming` record (monotonic) threaded through the existing turn flow: stt (reused `transcribe_ms`) · trigger→llm_done (+ broken-out autosend `wait=`) · tts · bridge_wait · total, plus `chars`/`wav` and Ollama `ctx=<prompt>/<num_ctx> gen=<eval>`. Emitted once in `_deliver_answer` (all four triggers; not `!say`). `OllamaClient.last_stats` keeps the previously-discarded token counts without changing `chat()`'s return type | Need a baseline of where a turn's seconds go *before* the streaming optimisation; reuses existing measurements + surfaces for free whether the growing prompt is nearing `num_ctx`. Logging only, zero behaviour change, no trade-off → no ADR |
| D36 | Context-budget warning | **WARNING when a narration prompt exceeds ~85% of `num_ctx`** (`[ctx] prompt N/8192 …`), beside the per-turn `ctx=` display; pure `_TurnTiming.ctx_over_budget()` predicate, narration turns only (router/recap exempt) | The persona leads the system prompt, so Ollama truncates **it** first when prompt+history overflow — a silent quality cliff. 85% gives a turn or two to trim history/recap/state before the cap (raising `num_ctx` costs KV-cache VRAM we don't have on the 4070). Logging only, no trade-off → no ADR |
| D37 | Anti-puppeting + length | **Deterministic speaker-label backstop** — every known character/player name becomes a `_cut_at_labels` cut-point + Ollama stop sequence, plus persona rescoping and `num_predict` 220→160 | Persona-only rules failed three live sessions and the puppet scripts were the latency; a guard the model can't ignore → **ADR 016** |
| D38 | TTS speech-only normalization | **`normalize_for_tts()`** on the synth path only (never the Discord post) — drops quotes/symbols, maps ellipsis/dashes to a pause, keeps `. , ! ? ; :` | XTTS verbalised raw punctuation; keep the prosody-bearing marks, strip only what it reads aloud → **ADR 016** |
| D39 | Streaming pipeline | **Stream the DM turn** — `chat_stream()` deltas → pure `StreamAssembler` sentence cuts → per-sentence synth + playback over the blocking `/speak`; `DM_STREAMING=1` default, `0` = byte-identical batch path | Shrinks time-to-first-audio to one sentence; history parity via the shared `finalize_answer()` → **ADR 017** |
| D40 | Roll-router timing | **Fire the ADR-014 classifier at generation-end and post the 🎲 button concurrently with playback** (`_handle_dice` runs as a task beside `_speak`/the streaming playback), so the button appears while the DM still speaks. Inline `<<TEST>>` still wins the dedupe (`should_post_router`) | The button used to appear only after generation **and** playback. Input (action + skills) is known earlier, but single-GPU Ollama serialises — firing at turn-start would just queue the classifier behind the narration (or delay it), so gen-end is the earliest point that overlaps playback without delaying narration. Supersedes ADR 014's *timing* only, not its design → D-entry, no new ADR |
| D41 | History autosave | **Third session artifact** `data/sessions/<id>/history.jsonl` (`dmbot/memory/history.py`) — append-only, one line per turn (`{ts, user_msg, answer, redo}`), appended off-loop after each turn, restored into an empty `DMBrain` history on `!join`, rotated to `history.<ts>.jsonl` on `!leave`. `DM_AUTOSAVE=1` | World state already persists (ADR 015); a crash still lost the conversational thread. Code-owned like `state.json` (the read-only `characters.json` split is unchanged). Append-only (no atomic dance; torn tail tolerated); a `redo` record replaces the prior turn. `_last_turn` not restored → `!redo` unavailable for the restored last turn (documented). Extends ADR 015's artifact set → D-entry, no new ADR |
| D42 | Streaming content tuning (first live run) | **(a)** skip TTS+post of a **content-less** answer (`has_speakable_content`: no letter/digit) — a marker-only / code-fenced turn no longer makes XTTS read a lone quote for ~15 s; the dice button still posts. **(b)** `_sanitize` strips **code-fence backticks** (`` ` ``) like markdown `*`. **(c)** suppress inline `<<TEST>>` markers on **results-only turns** (`_last_action is None`) so a post-roll consequence narration can't request a new roll | First live streaming run: the model emitted marker-only turns (15 s of lone-quote audio each) and a `<<TEST>>` on every turn incl. consequence narrations → an endless attack→roll→narrate+marker→roll **dice loop**. (a)/(b) are output cleanup (ADR 016 family); (c) is the real flow decision — a consequence narration legitimately *never* needs a fresh roll; the router handles real player-action rolls on the next turn. Builds on ADR 014/D40 + ADR 016/017 → D-entry, no new ADR |
| D43 | Post-roll robustness (echo collapse, 2026-06-12) | **Echo guard (retry once, then suppress) + roll-feedback directive + router wins the dedupe + autosave race fix + ADR 016 partial rollback (`num_predict` back to 220)** | The 2026-06-12 session collapsed into a self-reinforcing echo loop; deterministic guards over persona hopes → **ADR 018** |
| D44 | Adventure into the DM (Phase 10a) | 3-stage hybrid instead of pure vector RAG: always-in-prompt adventure summary, deterministic scene tracker (`WorldState.scene_id`, human-moved), rulebook-only RAG (sqlite-vec) | Similarity can't answer plot position and leaks spoilers; plot state belongs in code → **ADR 019** |
| D45 | Embedder + W4 guard | RAG embedder switched to multilingual `bge-m3` (store meta pins model+dim); echo guard extended by fuzzy `is_self_repetition` (retry once, then suppress) | nomic barely matched German queries against the English rulebook; live W4 repetitions dodged substring checks → **ADR 019** |
| D46 | Starter Set as lore + patron source | **(a)** The Starter Set's **Setting Guide → `source=setting`** in the existing RAG store (pages 1–57 only — the „Villains on Voll" chapter with the Mireclaw reveal stays out until the campaign finale); retrieval searches rulebook+setting and groups hits as `## Regelwerk` / `## Weltwissen (… nur als Färbung nutzen)`, TOP_K=3 total. **(b)** The **Aegidius-Halikarn patron sheet** folded into the chemical_burn compendium (Motivation Information, Auftreten undurchschaubar, Boons incl. Sanctum-Obscurus-Ausstattung in der Thaler-Szene). „The Blazing Seraph" (SS adventure book) wird erst NACH dem Chemical-Burn-Live-Test zum zweiten Kompendium | The Setting Guide is a better first lore source than D28's wiki plan: campaign-specific (Chemical Burn plays in Rokarth), curated, already owned — wikis stay the later broad-lore step. Spoiler discipline (ADR 019) applies to lore too: similarity must not surface the villain chapter on „wer steckt dahinter?" (verified: the question returns nothing). Applies ADR 019, no new trade-off → D-entry, no new ADR |
| D47 | Visible, fast shutdown | **TTS synth on abandonable daemon threads (`shutdown.py::to_daemon_thread`) + a thread-safe `[i/n]` teardown step display in `DMBot.close()`** | Non-daemon executor threads join-blocked exit on an in-flight XTTS synth; daemon-abandon is the only lever for uncancelable synth → **ADR 020** |
| D48 | Curated German lore compendium | **Hand-authored `data/lore/imperium.md` + `chaos.md` (committed) → two new RAG sources `lore_imperium`/`lore_chaos`** | Chaos cosmology isn't in the IM books and German-vs-English inflates distances; authored German lore wins TOP_K while rules keep hitting the rulebook → **ADR 021** |
| D50 | `!rules <frage>` command | **Two modes** — `!rules` (alias `!regeln`) still pages the system's short rules (◀/▶); **`!rules <frage>`** retrieves the matching rulebook chunks (`RulebookRetriever.lookup(sources=("rulebook",), k=3, max_distance=0.55)`) and the new **`DMBrain.answer_rules`** has the LLM synthesise a short German answer grounded **only** in those excerpts (golden rule #7: no invented rules; "Regelbuch hergibt nichts" when uncovered). No hits → honest "nichts im Regelbuch". Read-only embed, never spoken; +3 unit tests | Counterpart to D49's `!lore <frage>`, but the rulebook is **English layout-soup**, so raw chunk display (the `!lore` model) is unreadable — a rule question needs an LLM translate/condense step, unlike curated German lore. Grounding it in retrieved chunks (not the model's gut) is golden rule #7 applied, not a new trade-off → D-entry, no ADR. Verified end-to-end against the live store (Ausweichen, kritischer Treffer → correct) |
| D53 | TTS-Normalisierung gehärtet (Whitelist + Pro-Chunk-Guard) | **`normalize_for_tts` von Blocklist auf Whitelist** + Pro-Chunk-Sprechbarkeits-Guard (nicht-sprechbare Chunks → kurze Stille statt Synthese) | XTTS vokalisierte durchgerutschte Unicode-Symbole, die Blocklist fing sie nicht; Whitelist ist zukunftssicher → **ADR 016** (Nachtrag) |
| D52 | Augmetik/Implantate + Psyker-Erstellungs-Backfill | Profilgetriebener, passiver `augmetics`-Block; Engine wendet Rüstungs-/Merkmals-Boni deterministisch an, der Rest bleibt narrativ; Creator-HTML + Sheet-Filler für Augmetik und Psyker nachgezogen | Würfelrelevante Effekte gehören in Code, Katalog ist Profildaten → **ADR 023** |
| D51 | Psyker / Warp subsystem | Profile-driven, fully rules-faithful: `psyker` profile block + pure engine resolvers (`resolve_manifest`/`resolve_perils`/`resolve_phenomena`) and a `<<MANIFEST>>` marker→button flow; Warp Charge code-owned | Tobi chose full fidelity; engine stays system-agnostic, per-power prose via RAG → **ADR 022** |
| D49 | `!lore` command | **Weltwissen, two modes** — `!lore [topic]` (alias `!hintergrund`) pages `data/lore/<topic>.md` (no arg → `imperium`, `!lore chaos` → Chaos) through the existing `RulesView` (◀/▶); **`!lore <frage>`** (same-day extension, Tobi) looks the question up in the vector store and posts the best-matching compendium sections as an embed — new `RulebookRetriever.lookup()` (caller-picked sources = `lore_imperium`/`lore_chaos`/`setting` only, k=2, **own ceiling 0.52**), deterministic chunk display, no LLM. New pure `dmbot/rag/lore.py` (`lore_pages`: heading = page, H1 + `>`-source-note skipped, >4000-char guard; `available_topics`). Read-only — no TTS, no DM turn. Plus `tools/lore_to_html.py` → `docs/lore.html` (grimdark standalone, review/handout view, re-run after lore edits) | Tobi wants players to read an ausführlicher human-lore rundown (reviewed via HTML first) AND ask direct lore questions; the readable file covers the rundown case. Single source of truth: command, RAG Weltwissen and handout all read the same committed files. Lookup ceiling tuned on live probes: looser than the 0.45 prompt gate (narrative phrasings ~0.48 deserve an answer on an explicit ask) but under 0.54 where the off-corpus Tyranid question grabbed the nearest wrong chunk — "steht nichts im Weltwissen" beats a misleading hit. Rulebook excluded (English layout soup; rule questions → `!rules`/DM turn). Applies existing patterns → D-entry, no ADR |
| D54 | Anti-repetition persona rule | **Prompt-side W4 fix** — persona rule „established facts are already known, describe only what's new" + sharpened recap label in `_build_request`; no code guard | The DM re-explained settled context every turn; prompt-only, D45's fuzzy guard stays the fallback → **ADR 016** (Nachtrag) |
| D55 | XTTS-Babble bei Satzzeichen | **Zwei XTTS-Sampling-Hebel** — `split_sentences=False` (kein pysbd-Re-Split unserer Chunks) + `repetition_penalty=10.0` (via `XTTS_REPETITION_PENALTY`) | Der Live-Test brauchte die von D53 zurückgestellten Hebel gegen Decoder-Loops an Satzzeichen; live-unverifiziert → **ADR 016** (Nachtrag) |
| D56 | Auto scene transitions | Third LLM marker `<<ORT <scene-id>>>`: code validates the requested move (default mode `verbunden` = `leads_to` neighbours only), a human confirms via button, then the deterministic `!ort` move runs | `!ort` mid-scene was live friction; the LLM requests the pointer move, never writes it → **ADR 026** |
| D57 | Context budget (1st live round) | `OLLAMA_NUM_CTX` env (default 24576) replaces the hardcoded 8192, plus a rolling auto-recap (`DM_AUTORECAP`) compacting history off the hot path when `prompt_eval` crosses 0.85·num_ctx | the 1st live round's failures traced to silent prompt-head truncation → **ADR 027** |
| D58 | `!start` briefing + persona steer | **(a) `!start`** (aliases `!briefing`/`!auftrag`): a dedicated opening turn — the DM narrates the `auftrag` briefing (Halikarn message, mission, leads as atmosphere) via the existing stream/speak path; a thin `respond_opening*` path leaves `_last_action` None so dice routing is suppressed; sets `scene_id` to the start scene if unset. **(b) Persona** (`prompts/dm_core_de.md`): keep the current scene's goal in view + steer gently toward open leads (not a list, not railroad); every turn ends with the **world in motion** (an NSC acts/speaks or a concrete hook), never a flat description that stops; **spotlight** — bring other named/silent characters in by name | 1st-round complaints: "am Anfang nicht gesagt, was abgeht" (`!join` only printed status), the DM stopped on static descriptions with passive NPCs, and one player sat idle all session. Prompt/feature tuning in ADR 016's persona-discipline domain (like D54) — effective only because D57 stops the persona being truncated → D-entry, no new ADR. Live-unverified |
| D59 | RAG junk-shape filter | Distance-independent `_is_junk_hit` in `fetch_block` drops OCR/statblock/picture-text shapes (103/2482 chunks); `MAX_DISTANCE` stays 0.45, recall@1/@3 unchanged | tightening the threshold costs real recall, a shape filter is surgical → **ADR 028** |
| D60 | Voice cog split → SessionRuntime | **Pure structural refactor: the 2300-line `VoiceReceiveCog` split into a shared `SessionRuntime` (`dmbot/runtime.py`) + three thin cogs (VoiceCog/DiceCog/DMCog), cross-cog calls via five runtime hooks; suite 263 green** | god-cog with a 26-kwarg ctor; moved-not-rewritten, zero behaviour change → **ADR 029** |
| D61 | Code-review correctness round (post-cog-split) | **9 verified defects fixed in the day's feature work (Warp containment skill, lost dice button, recap race, glued markers, mute depth counter, …) + cleanup; suite 293 green** | multi-agent review over `5d672b6~1..HEAD`; system-agnostic altitude findings deferred to Phase 10b → **ADR 030** |
| D62 | `!intro` opening monologue | **New `!intro`: one long opening monologue that involves every PC (`intro_roster_de()` + `[Regie]` director msg, `num_predict` override `DM_INTRO_NUM_PREDICT`=800); `!start` stays the short briefing; 300 green** | monologue over multi-beat; roster rides in the director message so per-turn prompts stay untouched → **ADR 031** |
| D90 | `dm-sync` entry point for the sync check (dev-tooling) | **The D89 tool moved from `tools/sync_check.py` to `dmbot/tools/sync_check.py` (new subpackage) and runs as `uv run dm-sync` via `[project.scripts]`.** As a package module the `sys.path.insert` hack is gone (`REPO_ROOT` = `parents[2]`); `main() -> int` + `__main__` guard unchanged. To make the script entry exist, `[tool.uv] package = false` was replaced by a **hatchling build backend** (`packages = ["dmbot"]`) — `uv sync` now installs `cogitator` editable, solely for the entry point (still an application, not a published library). All references repointed (SETUP.md, conventions.md, ingest.py docstring, `tests/test_sync_check.py` import — assertions unchanged); **no shim at the old path** (a silently-drifting stale copy is worse than a hard break). `[sync]` block verified byte-identical pre/post move (only the repo line's clean→dirty = the change itself). Suite **459 green**, no new ruff findings | The long `uv run python tools/sync_check.py` should be one short command on both machines — the fingerprint format is now a mini-contract Timo may diff against, so zero output change was the constraint. Packaging the project is the one real cost, accepted as the only way `[project.scripts]` materializes under uv. Timo needs one `git pull` + `uv sync` before `dm-sync` exists on his machine. Pure ergonomics → D-entry, no ADR |
| D91 | NPC memory: how do NPCs remember conversations without violating golden rule #3? | LLM-extracted per-NPC memories as a narrative layer in `state.json`; every hard effect (attitude drift, lie flips, faction gossip) is code-clamped | Same request/validate/apply pattern as dice — LLM requests, code decides → **ADR 044** |
| D92 | Consistency guard: how to stop a dead/absent NPC "speaking" without an LLM judge? | Deterministic pre-delivery check (`dmbot/llm/consistency.py`), regenerate once with a KORREKTUR nudge, strictly fail-open | Conservative heuristics because a false positive costs a full regeneration → **ADR 045** |
| D93 | Replay-eval harness: how to prove a refactor didn't change pipeline behaviour? | Golden transcripts + playback replay (`uv run dm-eval`): `history.jsonl` doubles as a replay journal, diffed per turn in six categories — a merge gate for refactor rounds | Recorded-live expectations pin what the table actually saw; regression, not quality → **ADR 046** |
| D94 | Consequence clocks: how does the world get visible pressure without the LLM owning state? | Code-owned Blades-style progress clocks; the LLM proposes ticks via `<<UHR id>>`, code clamps +1 per clock per turn; humans create clocks; a full clock injects a one-shot `[Regie]` note | The exact ADR-043 request/validate/apply pattern (golden rule #3) → **ADR 047** |
| D95 | In-game time: how does time become a tool without the LLM owning the clock? | One code-owned minutes counter + derived rendering (`gametime.py`); LLM proposes advances via `<<ZEIT>>`, code clamps (first marker only, max +12h); human-only deadlines fire one-shot `[Regie]` notes | The clocks pattern applied to time — code owns the counter → **ADR 048** |
| D96 | NPC agendas: how does the world move offscreen without a world simulator or a second LLM call? | Only human-marked agenda NPCs (`goal` on the `Combatant`); the ADR-044 extractor call gains one code-clamped narrative `agenda_step` per NPC per scene change, injected as goals/rumours | Rides the existing extraction call — no new latency, no LLM-owned state → **ADR 049** |
| D97 | Chekhov list: how do loose ends survive a session and come back as callbacks? | Code-managed thread list (`chekhov.json`, cap 20 open), extracted at wrap-up by the same ADR-044 call with a pre-window history block; top 3 open threads offered to the DM, never forced | Session granularity + one call keeps the extraction budget intact → **ADR 050** |
| D98 | Marker-pipeline consolidation: how does a sixth marker stop costing six hand-copied seams? (the D61/D94 altitude debt) | Declarative `MarkerSpec` registry in `rules/marker.py` + one generic seam for extraction, pending store, lifecycle drops and journal; handlers/verdicts stay concrete | Behaviour-neutral (goldens replay green, no new live gate) → **ADR 051** |
| D89 | Sync fingerprint tool for the untracked must-haves (dev-tooling) | **New standalone `tools/sync_check.py` (`uv run python tools/sync_check.py`): one compact `[sync]` block — repo commit (clean/dirty), per adventure JSON a short sha256 + mtime + scene/NPC count via the real `Adventure.load` (a broken compendium prints a loud LADEFEHLER line instead of crashing), `rag.db` size + meta (model/dim) + chunk count PER SOURCE + per-source ingest date, `.env` KEY coverage vs `.env.example` (missing/extra names only — never values), and `git status --porcelain` over the tracked data seeds.** Offline (no bot/Ollama), degrade-don't-die per line (missing artifact → FEHLT line), repo-anchored paths (runs from any cwd). Companion: `dmbot/rag/ingest.py` now stamps `ingested:<source>` (`YYYY-MM-DD HH:MM`) into the existing key/value meta table per ingest and clears stale stamps on the model/dim rebuild-drop; pre-stamp DBs read tolerantly as „unbekannt". SETUP.md gained „Staying in sync (second machine)". +15 tests (`tests/test_sync_check.py`); suite **459 green** | The untracked must-haves (adventure cards, rag.db, .env keys) drift silently between Tobi's and Timo's machines — „hast du die aktuelle?" was answered by guessing; now both run the tool and diff the blocks. Short sha256 over mtime as truth (copying changes mtimes — mtime stays as a human-readable hint); rag.db compared by meta + per-source counts, deliberately NO whole-DB hash (vacuum/row order makes identical content binary-unequal). Ingest stamp as meta ROWS (key per source), not a chunks column — the meta table is already key/value, so old DBs need zero migration. Output = file names + counts only: no book content, no `.env` values (pinned by test). First real run surfaced drift immediately: Tobi's local `.env` is 20 keys behind the template. No ADR: no design trade-off worth a record |
| D88 | `/author-adventure` authoring skill (adventure-md → compendium draft, dev-tooling) | **New Claude-Code skill `.claude/skills/author-adventure/` (SKILL.md + `validate.py`): 5-pass offline workflow — structure pass with a HARD STOP for scene-cut approval, card/NPC/summary passes in profile-aligned German (difficulties verbatim from `difficulty_ladder`, skills = party sheets ∪ profile; mismatches go on the checklist, never invented), spoiler self-check, loader validation via the real `Adventure.load` (id collisions, dangling `leads_to`, gate integrity, statblock coverage), and a review checklist of the draft's own weak spots.** Hard rules: `git check-ignore` guard before writing (bought-book derivatives never in tracked paths), zero book content in the skill file, never commit. Acceptance test: blind dry-run against the Chemical-Burn md → 14-scene draft, loader-valid incl. ADR-043 gates; diff vs the 15-scene hand-built compendium found 4 convention gaps, folded back into the skill (dedicated opening scene as `start_scene`; sparse forward-dramaturgical `leads_to` — `verbunden` treats it as the legal-move list; summary carries the WAHRHEIT with an explicit secrecy frame; a statblock for EVERY `npcs_here` name). Throwaway deleted; no bot code touched | Adventure #2 („The Blazing Seraph", 49 pp.) and later books should cost an afternoon of *redigieren*, not days of authoring — the human stays Kurator (draft + checklist, never a silently-finished compendium). Validation imports the existing loader instead of duplicating schema knowledge; the diff-vs-hand-built comparison is the honest acceptance test (draft written before looking at the hand-built cut). No ADR: precedent-following conventions, no new schema/design trade-off |
| D87 | Stateful scene cards (element flags, dead NPCs, gated exits) | Code-owned `WorldState.scene_flags` + fourth marker `<<ERLEDIGT id>>` (confirm button, `DM_FLAG_CONFIRM`); stateful render (resolved/revealed/`(tot)`), hidden gated exits | The card must reflect world state without the LLM ever writing it (golden rule #3); live-unverified → **ADR 043** |
| D86 | Deterministic `!intro` weakness check + one-shot retry | Pure `dmbot/llm/intro_guard.py::is_weak_intro` (too short or a roster figure unnamed); `respond_opening` regenerates once with `INTRO_RETRY_NUDGE`, batch path only | Don't trust the prompt — a deterministic backstop against thin openings → **ADR 041** (Addendum 2) |
| D85 | Anti-repetition sampling (`repeat_penalty`) + deterministic roll-router carve-out | `DM_REPEAT_PENALTY` (1.1) / `DM_REPEAT_LAST_N` (256) as OllamaClient instance defaults via shared `_merged_options()`; the roll router pins `repeat_penalty=1.0` | Attacks looping at the cause, before the echo guard; the deterministic verdict must stay penalty-free → **ADR 042** |
| D84 | Strip the `!intro` meta-open deterministically + raise intro temperature to 0.7 (ADR 041 addendum) | `sanitize.py`: `_META_PREAMBLE` gains opener verbs + new `_unwrap_enclosing_quotes`; default `DM_INTRO_TEMPERATURE` 0.5 → 0.7 | A prompt instruction can't suppress the tic on a 12B model — the deterministic strip owns removal → **ADR 041** (Addendum) |
| D83 | Make `!intro` reliable (fixed low temperature + hardened director brief) | New `DM_INTRO_TEMPERATURE` (default 0.5) threaded through the opening path only, plus a hardened director brief forbidding meta-narration and the curt close | Root cause was sampling variance at nemo's ~0.8 default; scoped to the opener, live-unverified → **ADR 041** |
| D82 | Default party so the real party isn't bound to one voice-channel id | Committed `data/sessions/_default/characters.json` (env `DM_DEFAULT_PARTY`); resolution: channel sheet → default party → `_example`, D43 warning only for `_example` | A committed file travels via git to any clone and channel, unlike an env var → **ADR 040** |
| D81 | Split scenes + lore out of DMCog into thin sub-cogs (`/improve-architecture`, deferred ADR-035 follow-up) | Sub-cogs, not a mixin: `scenecog.py` (`!ort`/`!szenen`/`!ortmodus`) + `lorecog.py` (`!lore`), bodies byte-identical; lore speaks via new `runtime.speak` hook | Sidesteps the `CogMeta` mixin risk; two narrow files for context-leanness → **ADR 039** |
| D80 | Deepen prompt assembly + session seed + panel helper (`/improve-architecture` #4/#5/#6) | Pure, order-explicit `assemble_system_prompt` in new `dmbot/llm/prompt_assembly.py` (join-only); plus `runtime.seed_session` + `runtime.clear_panel` | Join-only keeps the deliberate cache-vs-pull timing; #4/#6 detail in the addendum → **ADR 038** |
| D79 | Deepen STT filter + combat resolution (`/improve-architecture` #1+#2) | Pure `dmbot/rules/combat.py` (attack soak + Warp→Perils, RNG injected); cog keeps the state mutations. #1: pure `confident_text` wired into the transcriber | Fixed-seed tests for the deterministic core; the seam stops before the WorldState mutation → **ADR 037** (addendum has the #1 detail) |
| D78 | Curated agent-skill set (Pocock-derived) | **Added 4 Claude Code skills under `.claude/skills/` — own `/tdd` + 3 adapted from `mattpocock/skills`: `/grill-me`, `/improve-architecture`, `/to-prd`.** `/grill-me`+`/to-prd` are a designed pair (grill builds the context, to-prd writes the PRD to `docs/plans/<slug>.md` — no issue tracker, unlike the original). `/improve-architecture` = whole-codebase deepening review (deletion test), repo-adapted (architecture.md/docs/decisions, golden rules), Markdown not HTML, grilling conditional not forced. `/tdd` = red-green-refactor on the deterministic core. README index kept in sync; commits abb49c8/0f371be/1cd671c/0924001/76c0b1a on main; no bot code, suite untouched (324) | Tobi asked for a "tdd skill" (none existed) → researched + built, then surveyed external skill repos. **Adopted** Pocock's workflow skills, each adapted to this repo's invariants (issue-tracker→`docs/plans`, CONTEXT.md→`architecture.md`, forced-grill→conditional). **Rejected** the `rohitg00/awesome-claude-code-toolkit` aggregator wholesale (generic stack tutorials, cloud-API-oriented or overlapping `/code-review`·`/simplify`) — keep the skill set lean (golden rule #9). Tooling/process → D-entry, no ADR |
| D77 | Auto gates: ruff in the hooks + review/simplify trigger checklist | **Cheap zero-token checks run automatically; the expensive LLM reviews stay on judgement.** (1) The Claude Stop hook (`tools/hooks/test-on-change.sh`) now runs **`ruff --select F`** (pyflakes: unused imports/names) before pytest — same philosophy (only on dmbot/tests/data-systems changes, silent on green, non-blocking); F-only on purpose (line-length/style E* off — long doc lines are deliberate, re-export shims carry `# noqa: F401`). It immediately caught + removed 2 dead imports (`re`, `difflib.SequenceMatcher` in `orchestrator.py`, D70 extraction leftovers). (2) New **blocking git pre-commit hook** (`tools/hooks/pre-commit`, activated via `git config core.hooksPath tools/hooks`) runs the same ruff-F + suite on the *user's own* commits, aborting on red (bypass `git commit --no-verify`), scope-guarded to staged dmbot/tests/data-systems. (3) New `docs/conventions.md` section "Code-Review-, Simplify- & Lint-Gates": when `/code-review` (read-only) is worth pulling vs. the day-end fan-out, and `/simplify` (write-pass → never automatic; hand-simplify race-sensitive code per D72). Suite 324 green throughout | Tobi asked whether to auto-run `/code-review` (and later `/simplify`) before every commit. Decided **no**: those are billed LLM passes (the D76 fan-out ≈ 983k tokens) and `/simplify` *mutates* code — auto-running it contradicts the project's hand-control discipline (D72). Right split: **cheap + deterministic = automatic (0 tokens), expensive LLM review = on judgement**, the judgement encoded as a checklist that survives context-clears. Other skills (verify/run, security-review) judged not worth a standing reminder. Tooling/process → D-entry, no ADR |
| D76 | Review-round fixes: `disconnect_voice` contract + delivery test-gap | **Fan-out `/code-review`-style pass over the day's commits `7b5af54..HEAD` (21 agents, every finding adversarially verified): 14 findings → 3 confirmed, 11 dismissed; no D70–D75 refactor regression survived, golden-rules sweep clean.** Fixed in 2 pushed commits. **(1) `dmbot/shutdown.py::disconnect_voice`** keyed its True/False on `asyncio.wait_for` raising `TimeoutError`, but against the real discord.py + Py 3.12 that branch is dead — the post-leave confirmation wait **swallows** the bounding cancel and returns normally, so `wait_for` returns and the function always returned `True` (the caller's "abandoned at shutdown" warning never fired); the slow-confirmation test masked it with a bare-`sleep` mock that lets the cancel propagate (a green `False` production never yields). Rewrote to decide via `asyncio.wait` (finished-in-window → confirmed, else cancel the lingering wait + report abandoned) — deterministic, no elapsed-time boundary flake; the test now models the real swallow-and-cleanup contract + a second propagating-cancel test (`2b608e7`). **(2) New `tests/test_delivery.py`** pins the previously-untested `puffer` head-start state machine in `_deliver_streaming`: prebuffer fill before the first play, plain-stream instant start, transform-to-empty skip, and **mid-stream-failure temp-WAV cleanup (no leak)** (`5499066`). Suite **324 green** (319 → +4 delivery, +2 shutdown −1 replaced) | The day's big refactors (D70–D75) were claimed behaviour-preserving; a thorough fan-out review confirmed that (adversarial verify killed every refactor-regression finding, golden-rules sweep clean) and surfaced one real low-impact bug + the largest coverage gap (`delivery.py`, the biggest extraction, had zero tests). The 11 dismissed = nits / intentional (ADR-033 `flach` default) / unreachable (`num_predict=0`, empty `content`) / born-that-way. Bugfixes, not trade-offs → D-entry, no ADR |
| D75 | One-shot setup: install + persistent PATH + robust Ollama/exec-policy | **`setup.ps1` installs everything end-to-end, idempotently, on the persistent user PATH; Ollama winget→installer fallback, `bge-m3` embedder fix, prefetch default-on, one-click `setup.bat`; 319 green** | colleague's fresh-machine snags (winget, ExecutionPolicy) + the stale embedder → **ADR 036** |
| D74 | Extract the delivery pipeline → `dmbot/voice/delivery.py` (composition) | **12 delivery methods moved byte-identically into a new `DeliveryPipeline`; the recap tail stays on DMCog behind one `post_deliver` callback; `dmcog.py` 1188→662; 319 green, 0 test edits** | composition over mixin (CogMeta question); scene/lore splits stay deferred → **ADR 035** |
| D73 | Extract `_TurnTiming` → `dmbot/turn_timing.py` (ADR 034 continuation) | **The per-turn latency record + `_CTX_WARN_FRACTION` moved out of `runtime.py` (610→516) with re-import shims; byte-exact, 0 test edits, 319 green** | next queued context-lean candidate, same mechanics as D70/D71 → **ADR 034** (Addendum) |
| D72 | Unify the twin delivery tail (`_post_deliver`) | **Extract the byte-identical end-of-turn tail shared by `_deliver_answer` (batch) and `_deliver_streaming` into one `_post_deliver` helper** (autosave → mic re-anchor → off-hot-path rolling auto-recap, D56). Both paths call it after their own `timing.end`/`log_line()`/`_await_dice_scene` step. Behaviour- and speed-identical (same calls/order/args; runs after `/speak`, off the hot path). The deliberately per-path bit is **not** merged: batch awaits dice/scene in a `finally` (button still posts if speak raised), streaming after the pipeline cleanup — that D40/D43 placement stays. Suite **319 green** | The two paths duplicated the tail (spotted in the `/simplify`-scope discussion). Did the extraction **by hand** (3 lines) rather than letting `/simplify` auto-edit the D40/D43-race-sensitive delivery code, per the agreed plan: only the twin paths, no functional/speed regression. Maintainability only — not a size win (the file stays large; that needs the deferred cog split) → D-entry, no ADR |
| D71 | Extract stream-assembler + finalize_answer (ADR 034 E4) | **`StreamAssembler` + the shared `finalize_answer` post-processing seam moved to `dmbot/llm/stream_assembler.py` (re-export shims); 933→783 lines, byte-exact, 0 test edits, 319 green** | last self-contained state-free block in `orchestrator`; same shim approach as D70 → **ADR 034** (E4) |
| D70 | Extract orchestrator pure helpers → `dmbot/llm/*` | **Pure top-band of `orchestrator.py` moved into `llm/sanitize.py` / `echo_guard.py` / `director_msgs.py` with re-export shims; 1175→933 lines, byte-exact, 0 test edits, 319 green** | context-leanness: the most-edited pure band extracts cheaply; `DMBrain` body stays → **ADR 034** |
| D69 | `puffer` head-start delivery mode | **Third delivery value between `stream` and `nahtlos`: prebuffer `DM_SPEECH_PREBUFFER` (default 3) WAVs before the first playback, then keep synthesising in parallel; depth live-settable via `!sprechmodus puffer N`; 319 green** | cushions CPU synth < realtime so gaps appear later; tunable middle point → **ADR 033** (Addendum) |
| D68 | Global spoken-delivery mode (delivery × intonation) | **Two orthogonal, runtime-switchable axes on EVERY DM turn: `DM_SPEECH_MODE` = stream \| nahtlos, `DM_SPEECH_PUNCT` = flach \| intoniert; live toggle `!sprechmodus`; default stream+flach; 316 green** | one style for all output, A/B both axes live; GPU offload is the real nahtlos enabler → **ADR 033** |
| D67 | Shutdown voice-leave hang | **Bound discord.py's post-leave confirmation wait at exit** — `shutdown.py::disconnect_voice` wraps `vc.disconnect(force=True)` in a 2 s `asyncio.wait_for` | discord.py awaits a gateway confirmation up to 30 s that rarely arrives at exit and only guards a moot race → **ADR 020 Addendum** |
| D66 | `!intro` fast streamed mode + CPU root-cause | **Plain `!intro` = streamed + punctuation-free (new optional `speech_transform`), `!intro test` stays the gapless one-track; root cause of the slow start: XTTS deliberately on CPU; 309 green** | Tobi chose fast start with minor gaps; GPU offload (ADR 002) is the structural fix → **ADR 031** (Addendum) |
| D65 | `!intro test` seamless chunked playback | **Per-sentence synth WAVs joined into ONE continuous track (`wavio.concat_wavs`, 0.2 s in-track pauses), played in one muted bridge call; 309 green** | gapless chosen over instant start — CPU synth < realtime makes both impossible at once → **ADR 031** (Addendum) |
| D64 | `!intro` Discord 2000-char crash | **Split long message `content` at the single send choke point.** `SessionRuntime._send_with_retry` now splits `content` > 2000 chars into several messages (any `view`/`embed` on the last) instead of one `channel.send`; the 5xx retry moved into a `_send_once` helper. New pure `split_for_discord` in `dmbot/tts/textsplit.py` — **verbatim** (drops nothing, unlike the TTS `chunk_text`), breaking at the latest paragraph/line/sentence/word boundary ≥ half-limit, hard-cutting only an unbroken over-limit run. Covers all three delivery paths (batch/streaming/`!intro test`). +4 tests (**306 green**) | Colleague's live run: `!intro test` raised `HTTPException 400 / 50035 ("Must be 2000 or fewer in length")` — the `!intro` monologue runs on a large length budget (`DM_INTRO_NUM_PREDICT` 800) and exceeds Discord's content cap. Pure correctness fix at the one send path every delivery route already shares; no trade-off → D-entry, no new ADR |
| D63 | Lean live docs vs. on-demand archive | **Split progress.md history + CLAUDE.md per-module detail into on-demand `docs/progress-archive.md` + `docs/conventions.md`; rotation rule keeps live files lean (1637→678 / 226→153 lines, nothing deleted)** | always-loaded docs had outgrown the context budget → **ADR 032** |

### Phase → ADR map (read these when you enter the phase)

| Phase | ADRs to read first |
|---|---|
| 0 — Foundation & setup | ADR 002 (topology, `OLLAMA_HOST`, localhost bridge) |
| 1 — Bridge (done) | ADR 002 + `architecture.md` §3 (bridge contract) |
| 2–4 — Voice / VAD / STT | **ADR 006** (DAVE/E2EE decrypt on receive) + **ADR 007** (VAD stack, Phase 3) + `architecture.md` §4–§5 (feedback protection) |
| 5 — LLM wiring + persona | ADR 002 + ADR 005 (persona = generic core + campaign overlay) + **ADR 016** (anti-puppeting backstop, length cap, output cleanup) + **ADR 038** (single owner for the system-prompt assembly order) + **ADR 031** (`!intro` opening monologue) + **ADR 041** (`!intro` reliability: fixed low temperature + hardened director brief; add. 2 = deterministic weak-intro retry) + **ADR 042** (anti-repetition sampling `repeat_penalty`, with a deterministic carve-out for the roll router) + **ADR 045** (deterministic consistency guard: dead/absent NPC speech → regenerate once, fail-open; streaming logs only) |
| 6 — TTS + full loop | **ADR 008** (TTS engine: Piper + XTTS) + ADR 002 (bridge, VRAM, GPU offload) + `architecture.md` §3 (bridge contract) + **ADR 016** (TTS speech-only normalization) + **ADR 017** (streaming pipeline: sentence-chunked TTS, hold-back rules, history parity) + **ADR 033** (global spoken-delivery mode: stream vs nahtlos × flach vs intoniert, `!sprechmodus`) |
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) + **ADR 011** (STT latency: push-to-talk gate) + **ADR 013** (pause control) |
| 8 — Dice engine, IM profile, marker flow | ADR 005 (engine + profile) + ADR 004 (test marker, character data) + ADR 001 (IM specifics) + **ADR 012** (difficulty ladder, character store, marker grammar) + **ADR 014** (roll-detection router; timing now D40 — fires concurrent with playback) + **ADR 018** (router wins the dedupe; echo guard + roll-feedback directive on post-roll turns) + **ADR 040** (committed default party — party loading no longer bound to one voice-channel id) |
| 9 — Memory (JSON + recaps) | ADR 004 (character/state JSON) + **ADR 015** (sheet/state split, auto-combat damage) + **ADR 027** (rolling auto-recap / context handoff — recap is no longer wrap-up-only) + **ADR 037** (attack/Warp resolution → pure `rules/combat.py`) + **ADR 044** (NPC memory: per-NPC Erinnerungen, clamped attitude drift, faction gossip) + **ADR 049** (NPC agendas: human-set goals, one clamped offscreen step per scene change riding the ADR-044 extractor) + **ADR 050** (Chekhov list: wrap-up-only thread extraction riding the ADR-044 call, code-owned cap/dedupe/status, top-3 callback offer) |
| 10 — RAG + profile bootstrap | ADR 005 (profile bootstrap) + **ADR 019** (3-stage hybrid: scene tracker + rulebook-only RAG, bge-m3, W4 guard) + **ADR 021** (curated German lore compendium: `lore_imperium`/`lore_chaos` sources) + **ADR 025** (German rules glossary + 0.45 calibration) + **ADR 028** (RAG junk-shape filter) + **ADR 027** (configurable `num_ctx`, context-budget compaction) + **ADR 026** (auto scene transitions, `<<ORT>>`) + **ADR 043** (stateful scene cards: `<<ERLEDIGT>>` element flags, gated exits, dead-NPC render) + **ADR 047** (consequence clocks: `<<UHR>>` ticks, +1/turn clamp, full-clock `[Regie]` injection, clock panel) + **ADR 048** (in-game time: minutes counter, `<<ZEIT>>` advance clamped to first-marker/+12h, deadlines with one-shot expiry `[Regie]`, day phases, shared pressure panel) |

---

## Phase status (Part 1 — MVP)

Legend: ⬜ open · 🔄 in progress · ✅ done (with proof)

> Abgeschlossene Phasen 0–8 (volle Checklisten + `VERIFY EVIDENCE`): **[docs/progress-archive.md](docs/progress-archive.md)**.

### ✅ Phase 0 — Foundation & setup — Gate met 2026-06-04
### ✅ Phase 1 — Bridge: Bot A `/speak` — Gate met 2026-06-04
### ✅ Phase 2 — DMbot scaffold: voice receive — Gate met 2026-06-04 (ADR 006)
### ✅ Phase 3 — VAD segmentation — Gate met 2026-06-04 (ADR 007)
### ✅ Phase 4 — STT (faster-whisper) — Gate met 2026-06-04
### ✅ Phase 5 — LLM wiring + DM persona — Gate met 2026-06-04 (ADR 002/005)
### ✅ Phase 6 — TTS + first full loop ⭐ (PLAYABLE) — Gate met 2026-06-04 (ADR 002)
### ✅ Phase 7 — Turn-taking & feedback protection layer 2 — Gate met 2026-06-05/06 (live, ADR 011)
### ✅ Phase 8 — Dice engine, system profile & turn-order buttons — Gate met 2026-06-07 (live, ADR 014/004/012)

### 🔄 Phase 9 — Memory (JSON + recaps)  (code-complete; live gate pending)
- [x] **`dmbot/memory/state.py`** — `WorldState` (+ `Combatant`/`Quest`): per-channel mutable state in
      `data/sessions/<id>/state.json` (wounds/conditions/inventory, NPCs, quests, location, time, recap).
      **Split** from the read-only `characters.json` (ADR 015): seeded once from the sheet, code-owned,
      **atomic** save (temp + `os.replace`) on every change. Pure deterministic advancement
      (`apply_damage` clamps at 0 + sets `kampfunfähig`; `heal` clamps at max + clears it; NPCs/quests/
      location) + `world_state_summary_de` (compact structured prompt block).
- [x] **Auto-combat damage** — engine `resolve_damage` (weapon + SL − soak, ≥0) + `describe_damage_de`;
      profile `combat` block (attack_skills, weapons table, default_damage, soak source) + accessors. On
      a successful Nahkampf/Fernkampf test the cog rolls the weapon's damage, computes soak (TB = tens of
      Tgh + armour), applies it to a target (auto if one candidate, else `discord_ui/target.py` dropdown),
      persists, and feeds it back so the DM narrates. `!npc add` registers enemies; `!damage`/`!heal` GM
      overrides. IM weapon values are approximate Core-Rulebook figures (tune live).
- [x] **Recap** — `dmbot/memory/recap.py` (German summariser prompt + history renderer) +
      `DMBrain.summarize`; `!wrap`/`!wrapup` generates → stores in `state.json` (+ `recap.md`) → `!join`
      re-injects it. `DMBrain.set_context` injects recap + state block into the system prompt (CLAUDE.md
      order: persona → recap → state → who-plays-whom → history); `reset` clears it.
- [x] **Unit tests** — `tests/test_memory_state.py` + `test_memory_recap.py` (seed, clamp/down/heal,
      save→load round-trip = the gate's code half, summary, engine damage math, profile accessors, recap
      + prompt injection). **Suite 102/102 green.** All changed modules import clean.
- **Gate:** HP change survives a restart; next session starts with a correct recap.
- **VERIFY EVIDENCE:** _Code + unit level (2026-06-09):_ persistence is unit-proven —
  `test_save_load_round_trip_survives` writes a damaged party (Seskin 11→6, an NPC, location, a quest, a
  recap), reloads, and asserts the reduced wounds + recap + quest survive; damage math
  (`weapon + SL − soak`, clamp ≥0) and the profile `combat` accessors are seeded-tested. _Live Discord
  gate (HP survives a real restart; recap shown + in-prompt on the next `!join`): **pending Tobi.**_

### 🔄 Phase 10 — adventure + rulebook into the DM + system-profile bootstrap
- [x] **10a (ADR 019, code-complete 2026-06-12, live-unverified):** adventure as 3-stage hybrid —
  summary + deterministic scene tracker (`data/adventures/chemical_burn/`, `!ort`/`!szenen`,
  `WorldState.scene_id`, `!npc add` statblocks) instead of vector RAG; **rulebook** ingestion
  (`dmbot/rag/ingest.py` → `sqlite-vec`, bge-m3, 1505 chunks) + threshold-gated retrieval into
  the prompt. The adventure is deliberately NOT in the vector store (spoilers).
- [x] **Lore source 1 (D46, 2026-06-12):** Starter-Set Setting Guide (ohne Villains-Kapitel) als
  `source=setting`, gruppiert als `## Weltwissen`; Patron-Sheet ins Kompendium. Wiki-Korpus
  (D28: Fandom + Lexicanum) bleibt der spätere Breiten-Ausbau.
- [x] **Lore source 2 (D48, 2026-06-13 → ADR 021):** kuratiertes deutsches Lore-Kompendium
  `data/lore/imperium.md` + `chaos.md` (grimdark, **committed** — eigene Formulierung freien
  40k-Wissens, keine Buch-Ableitung) als `source=lore_imperium`/
  `lore_chaos` → `## Weltwissen`. Schließt die Tobi-Anforderung „Menschen- + Chaos-Lore";
  Chaos-Kosmologie steht in keinem IM-Buch (verifiziert: „vier Chaosgötter" d=0.53 miss → jetzt
  d=0.43 hit). 24-Fragen-Offline-Probe grün; Tyraniden/Necrons/T'au bewusst draußen. Spieler-
  Zugang: **`!lore [topic]`** (D49, paged Embed) + `docs/lore.html` (Handout/Review).
- [ ] **Gate half 1 (live):** a concrete rule question answered correctly from the PDF
- [ ] Profile bootstrap: DM proposes a draft system profile from the rulebook → user confirms → saved
- VERIFY EVIDENCE: _(pending the circlejerk run)_
- **Decided approach (D28, 2026-06-08 — lore + RAG; full plan in this session's plan file):**
  - **→ superseded on the embedder:** D28 planned `nomic-embed-text`; Phase 10a (ADR 019) switched to
    **`bge-m3`** because nomic barely aligns German queries with the English rulebook (DE-query↔EN-text).
    The `nomic` mentions below record the original plan.
  - **Lore = RAG, never fact-fine-tuning** (golden rule #7). Fine-tuning only later as a **tone-LoRA**
    (style, on `logs/transcript.log`), Part-2 backlog — facts always stay in RAG.
  - **Both wiki sources** into one **`sqlite-vec`** DB, **text only (no images)**: **Fandom** (official
    XML dump, ~7.3k articles) + **Lexicanum** (MediaWiki API, throttled + cached, or an archive.org/
    WikiTeam dump, ~48.6k). Rulebook vs lore kept as separate `source`s so a rule question pulls the
    rulebook, a lore question the wiki. ≈ 0.8–1.3 GB total, ~40–100 min one-time embedding on the 4070.
  - **Pipeline mirrors `tools/pdf_to_md.py`:** new offline `tools/wiki_to_md.py` (`mwparserfromhell`,
    `mwclient`) → shared `dmbot/rag/{ingest,embed,store,retrieve}.py` (`nomic-embed-text` via Ollama
    `/api/embed`) → `!lore <frage>` (`discord_ui/lore.py`), then fold lore into DM turns behind
    `DM_RAG_LORE`; rule-retrieval into DM turns from the start.
  - **New deps to declare (§3, rule #9):** `sqlite-vec` (runtime), `mwparserfromhell` + `mwclient` (offline CLI).
- **Gate:** a concrete rule question answered correctly from the PDF; a fresh ruleset yields a working profile.
- **VERIFY EVIDENCE:** _(empty)_
- _Groundwork done:_ `tools/pdf_to_md.py` (`pymupdf4llm`) converts a rulebook PDF → Markdown
  (`data/pdfs/md/`, gitignored) as the ingestion front-end. The bought IM Core Rulebook is already
  converted. **Tool decision (Tobi 2026-06-07):** stay with `pymupdf4llm` until Phase 10 *or* until it
  causes problems; only then benchmark vs **Marker / Docling / MinerU** (ML+OCR, GPU — better on
  image/table-heavy pages) and, if switching, add a `--backend` flag rather than a second script. Note:
  IM tables can be **embedded images** (the Difficulty Table was) — `pymupdf4llm` does no real OCR, so
  table extraction is the thing to spot-check when building ingestion.

---

## Part 2 — Beyond the MVP (backlog)
- [ ] **XTTS as its own process/service** — XTTS v2 (`coqui-tts`) is wired in-process as an
      alternative TTS (`TTS_ENGINE=xtts`, picked speaker **Dionisio Schuyler**), but it drags the
      torch/torchaudio/torchcodec stack into the bot venv and is slow on CPU (~1.5× realtime).
      Move it behind a small local service (own venv, GPU once VRAM is freed) to keep DMbot lean
      and get near-realtime synthesis. Until then it runs on CPU. _Tobi chose Dionisio 2026-06-04
      after auditioning all 58 built-in speakers (samples in `voices/samples/`, pitch-ranked)._
- [ ] **Edit/review window before the DM speaks** — a toggleable human-in-the-loop step that
      briefly intercepts the DM response (and optionally the transcript) so a player can read /
      correct it before TTS. Off once trusted, so play flows. _Requested live by Pr0degie + Timo,
      2026-06-04; fits Phase 7 (turn-taking) — keep it switchable, not a permanent gate._
      _Groundwork done (2026-06-08, D27/ADR 013):_ the **pause control** (Esc + Discord ⏸ button →
      one `_paused` freeze) is the same human-in-the-loop gate; a review step can hook the same flag.
- [x] **Pause control (Esc + Discord ⏸ button)** — done 2026-06-08 (D27/ADR 013). Esc in the DMbot
      terminal *and* a Discord button flip one shared freeze (mute VAD/STT + block DM turns);
      animated `rich` box in the terminal, status embed in Discord. _Live test pending Tobi._
- [ ] GUI for the bot (session/turn/dice/sheets)
- [ ] LLM finetuning (LoRA on session logs)
- [ ] Streaming TTS (latency)
- [ ] Wake word / push-to-talk
- [ ] Per-NPC voices
- [ ] Automatic character progression
- [ ] Long-term vector memory

---

## Open questions / to clarify

**Von der Replay-Eval-Runde (2026-07-03, D93 / ADR 046):**
- **Live-Modellvergleich (Nemo vs. Mistral Small auf Timos Box)** — die explizite Folge-Runde,
  setzt genau dieses Harness voraus (echte LLM-Calls + Qualitäts-Report statt Playback). Nicht
  starten, bevor der Tuning-Live-Run durch ist (sonst vergleicht man ein untuned Setup).
- **Würfel-RNG-Replay aufgeschoben** — gewürfelte Rohwerte aufzeichnen und durch die Engine
  re-runnen (voller State-Snapshot-Diff statt Verdikte) lohnt erst, wenn ein Refactor den
  Roll→Damage-Pfad anfasst; die Fixed-Seed-Engine-Tests decken ihn heute dicht ab (ADR 046).
- **Erstes Live-Golden fehlt noch** — die eingecheckten Goldens sind synthetisch; das erste
  echte kommt aus dem rotierten Journal des nächsten Live-Runs (Schritt in „Next concrete step").

**Vom Playtest-Fix-Runde (2026-06-16, D82–D84) — live-unverified:**
- **Klingt `!intro` jetzt zuverlässig wie der 14.06.-Lauf?** Party lädt channel-unabhängig (D82), die drei
  Chat-Tics (Meta-Auftakt, `"…"`-Umschlag, „Was tut ihr?"-Abwürgen) werden deterministisch gestrippt (D84),
  Temp auf 0.7 (D84). Ob die **Prosa-Reichheit** (atmosphärisch vs. formelhaft) jetzt passt, ist Modell-Sache —
  am Tisch prüfen; Stellschraube `DM_INTRO_TEMPERATURE` (0.3–0.8) bzw. Director-Brief-Wortlaut.
- ✅ **Aufräum-Pass `progress.md` — erledigt (2026-07-04 D98 Teil B + 2026-07-11 Doc-Diet-Runde):**
  Current-focus-Blöcke rotiert (2 live), Decision-Log-Zeilen mit ADR gekürzt (Detail in die ADRs
  gerettet), State header eingeführt. Volltext im Archiv.

**From the skill-tooling round (2026-06-15, D78):**
- **Golden-Rules-Konformitäts-Check noch offen** — die brauchbare Idee aus Pococks `review`-Skill (Standards-Achse als
  paralleler Sub-Agent) auf euren Fall gemünzt: ein kleiner Skill, der einen Diff gegen die Golden Rules + `docs/conventions.md`
  prüft (dice=code / Memory-Split / Feedback-Schutz / Two-Bot-Isolation). Heute prüft das nichts (`/code-review` sucht Bugs,
  nicht Regelbruch). Bewusst auf „später" geschoben.

**Cross-repo (Bot A):**
- **`!lore tts` reads each block twice** — verified NOT in DMbot (lore_pages/loop/synth/concat all
  1×, no custom `on_message`). If the live `debug.log` shows **one** `🔊 TTS … speaking` + **one**
  `/speak` per block, the doubling is **Bot A's playback** (separate `Pr0degie/musicbot` repo) → fix
  there (two-bot isolation). A Bot-A `/stop` would also enable true mid-block skip in the lore reader.
- **Weapon / stat-block tables don't retrieve** (calibration finding, ADR 025) — table-row chunking;
  a German weapon glossary under `data/rules_de/` (same pattern as `conditions.md`) is the likely fix.

**From the cog-split refactor (2026-06-13, D60 / ADR 029):**
- ✅ **Kosmetik geputzt (2026-07-04, D98):** das `_short_name`-Docstring-Beispiel in
  `dmbot/logsetup.py` nennt jetzt ein existierendes Modul (`voice.delivery`); Details im Archiv.
- **Smoke-Test offen:** der Schnitt ist test-grün (263), aber live nur per Smoke-Test abzunehmen
  (`!join`→sprechen→`!dm`→Würfel→`!leave`) — siehe „Next concrete step".

**Deferred altitude debt from the code-review round (2026-06-13, D61 / ADR 030):**
These are the review's *altitude* findings — real, but the **system-agnostic generalisation** they
ask for is postponed to the **second-profile / Phase-10b** point (ADR 005's profile bootstrap). There
is no second system yet to generalise against, the changes are large + behaviour-risky, and the
project's stance (D1) is "IM is the first profile; generalise when the second arrives". Revisit each
when a second system is actually loaded:
- **Engine hardcodes IM arithmetic.** `engine.warp_charge_gain` (Success=Warp-Rating, Critical−WB,
  Fumble×2, Push+1d10) and `reverse_d100` + the `advantage` digit-reversal bake IM's p.163/p.189 rules
  into the generic engine. Move the charge-gain + advantage model into the profile alongside the
  resolution/degrees rules that are already data.
- ✅ **Per-marker pipeline grows linearly — EINGELÖST (2026-07-04, D98 → ADR 051):** deklarative
  `MarkerSpec`-Registry + eine generische Strip/Queue/Pending-Naht (keyed Store, `take_pending(kind)`),
  verhaltensneutral, marker-weise migriert mit dm-eval als Gate. Voller Alt-Text im Archiv.
- **RAG corpus catalog is IM-/OCR-specific in code.** `retrieve._SOURCES` (source names + German
  group labels) and `_is_junk_hit` (IM-PDF OCR-noise regexes) live in the retriever. A second ruleset
  needs them in data/profile + ingest-time denoise, not hardcoded.

**From the lore work (2026-06-13):**
- **`!lore`-Antworten zu Rokarth sind englisch** — die `setting`-Quelle ist der englische
  Setting-Guide-Text; eine Rokarth-Frage liefert also rohe englische Chunks ins Spieler-Embed
  (Imperium/Chaos kommen deutsch aus dem Kompendium). Kosmetik; Optionen wären eine deutsche
  Rokarth-Sektion im Kompendium oder `setting` aus den `!lore`-Quellen nehmen. Erst mal
  beobachten, ob es die Runde stört.

**From the Phase-7 playtests (2026-06-06) — carry into Phase 8 / quality work:**
- **Latency grows with context** as history accumulates; the 20-turn cap helps but recaps (Phase 9)
  are the real fix. **Now observable (D35/D36):** the per-turn `[latency]` line shows
  `ctx=<prompt>/8192 gen=<eval>`, and a WARNING fires once the prompt passes ~85% of `num_ctx` — so
  the cap-creep is no longer silent. Capture the live baseline before the streaming work; don't raise
  `num_ctx` (KV-cache VRAM) — trim history/recap/state if the warning shows.

**Loose ends / housekeeping (from the Phase 3 session):**
- **Intermittent voice-connect `TimeoutError` on `!join`** (seen once, ~18:45): the discord.py
  voice handshake occasionally times out; the command errored but a retry joined fine. Benign
  so far — watch it; if it recurs, look at the connect timeout / a clean error message in
  `voice/commands.py` rather than the raw traceback.
- Logging now also writes `logs/dmbot.log` (UTF-8, gitignored) — handy for inspecting a run
  after the window closes.
- Continuous silence injection runs silero on every silent user ~50×/s (cheap, ~1–2 %/core
  each); fine for a small table, revisit only if many idle users ever cost CPU.

**From the streaming/robustness session (2026-06-10) — open, carry forward:**
- **Pending live validation (Tobi tests 2026-06-11).** What's already confirmed live: streaming
  (`first_audio≈3.2s`) + the Phase-9 recap. Still open: HP-survives-restart (+ auto-combat),
  re-confirm the D42 tuning (no empty read-aloud, no dice loop), crash-restore (D41), router timing
  (D40), first_audio before/after. The prioritised checklist + exact sequence live in **`## Next
  concrete step`**.
- **Open persona/adherence — meta-ramble (nemo's ceiling).** On one live turn the model broke the
  fiction mid-narration („Nein, tut mir leid, ich habe mich versprochen. Als Spielleitung beschreibe
  ich nicht direkt die Szene. Ich reagiere lediglich auf das, was die Spielenden tun…") and it got
  spoken. Not the leading-preamble shape `_strip_meta_preamble` catches, and a generic mid-text
  meta-stripper risks false positives. Left as a persona/tone-LoRA item; watch frequency.
- **Caveat — `[latency] gen=` can be stale on a *client-side* stop-label abort (streaming).** When a
  mid-text speaker label trips `StreamAssembler.stopped` and the brain aborts the httpx stream, the
  Ollama `done` object (which carries `eval_count`) never arrives, so `last_stats` — hence the
  `[latency]` line's `gen=`/`ctx=` — holds the **previous** turn's numbers. In practice Ollama's
  server-side `options.stop` (the `\n<label>:` sequences) usually stops generation first **with** a
  `done` object, so this rarely shows; the client-side cut is only the safety net. Not worth fixing
  now — but if a `gen=` ever looks implausibly carried-over after a truncated turn, this is why.
  (Stored history is unaffected — `finalize_answer` recomputes from the accumulated raw either way.)
- **first_audio reliability depends on XTTS-on-GPU latency per sentence.** Streaming spreads synthesis
  over sentences, so per-sentence synth must keep up with playback or gaps appear between sentences.
  Watch the live `tts=` (now summed) vs `wav=`; if synth lags, the `wav_q` (maxsize=1) backpressure
  just means the table hears a short gap — acceptable, but a signal that XTTS is the next bottleneck
  (→ Part-2 streaming-TTS, the deeper W2 latency lever).

---

## Notes
- Order deliberately risk-minimal: bridge first (curl-testable, no risk to the music bot),
  then DMbot layer by layer.
- **Principle:** dice/success = code, narration = LLM. Do not mix.
- Verify each phase in isolation before the next begins.
