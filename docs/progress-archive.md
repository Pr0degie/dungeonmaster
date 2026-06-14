# progress-archive — historische Session-Logs, abgeschlossene Phasen, gelöste Open Questions

Hier liegt nur **Historie**. Der Live-Status (current focus, next step, offene Phasen,
Decision-Log, offene Fragen) steht in [`../progress.md`](../progress.md). Dieses Archiv wird
**on demand** gelesen, nicht jede Session. Nichts wird gelöscht — Inhalte werden aus
`progress.md` hierher rotiert, sobald sie nicht mehr aktuell sind.

---

## Last session (Verlauf)

**Ursache von „lädt ewigkeiten" gefunden + `!intro` als Schnellstart-Variante (2026-06-14, D66 → ADR 031 Addendum).
Suite 309 grün.** Tobi: `!intro test` klingt „mega geil", aber lädt ewig. Live-Log entlarvte die Ursache —
`XTTS v2 loaded on cpu` + `first_audio=378s` / `tts=314775ms` / `wav=224.2s` (32 Sätze, 3,7 min Audio):
- **XTTS läuft auf CPU** (`.env TTS_DEVICE=cpu`) — **bewusst**, nicht kaputt: die 4070 hält schon nemo + Whisper;
  XTTS auf cuda kippt das VRAM → CUDA-Device-Assert, vergiftet den Prozess, **STT stirbt mit** (live 2026-06-13,
  dokumentiert in `.env` + ADR 002). torch *kann* CUDA (`cu130`, GPU da) — reines VRAM-Koexistenz-Problem.
- **CPU-Synthese < Echtzeit** → lückenlos (`!intro test`) wartet auf die volle Synthese (Minuten). Auf Rückfrage
  wählte Tobi **Schnellstart mit Mini-Lücken**.
- **Umgesetzt:** optionaler `speech_transform` durch `_deliver_streaming`/`_deliver_answer`/`_speak` (nur auf den
  **gesprochenen** Text, Chat-Text unangetastet, D38). Plain **`!intro`** streamt jetzt punktfrei → spricht nach dem
  1. Satz los; **`!intro test`** bleibt die lückenlose Eine-Spur-Variante. Default-Pfad aller anderen Turns
  byte-identisch (Transform nur wenn gesetzt). Suite **309 grün**, `dmcog`-Import im venv geprüft.
- _Live offen: `!intro` (schnell, kleine Lücken) vs `!intro test` (lückenlos, langsamer Start) vergleichen.
  Größerer Hebel: LLM auf 5080 auslagern (`OLLAMA_HOST`/Tailscale → `TTS_DEVICE=cuda`, ADR 002) ODER Monolog kürzen._

**`!intro test`: gechunkte Synthese, aber Wiedergabe als EINE durchgehende Spur (2026-06-14, D65 → ADR 031 Addendum).
Suite 309 grün.** Kollegen-Feedback nach dem 2000-Zeichen-Fix: Aussprache korrekt/ohne Anfälle, aber zäh — Tobi
benannte den Flaschenhals: die **Synthese jedes Satzes** ist die Totstille zwischen den Chunks. Ziel (geklärt per
Rückfrage): nur Chunks vorlesen (kein Gibberish an Satzzeichen), aber es soll wie **ein voller zusammenhängender
Text** klingen. Harte Randbedingung: XTTS langsamer als Echtzeit → sofortiger Start UND lückenlos geht nicht gleichzeitig;
„klingt wie voller Text" ⇒ Lückenlosigkeit gewählt, Vorsynthese-Wartezeit bewusst in Kauf genommen.
- **`_deliver_intro_chunked` umgebaut** (`dmbot/voice/dmcog.py`): statt seriellem `_speak` pro Satz wird jeder Satz
  einzeln punktfrei synthetisiert (neuer Helfer `_intro_speak_seamless`), die WAVs via `concat_wavs` mit
  `_INTRO_SENTENCE_PAUSE_S` (0,2s) zu **einer** Spur gefügt und in **einem** Bridge-Call gespielt → durchgehend,
  natürlich getaktet, kein Gibberish. try/finally räumt alle Temp-WAVs auf; Pause während Synthese bricht sauber ab.
- **`wavio.concat_wavs`** neu (torch-frei aus `xtts._concat_wavs` herausgezogen, das jetzt dorthin delegiert) — so kann
  die Cog die Join-Logik nutzen, ohne die schwere XTTS-Lib zu laden.
- **+3 Tests** (`tests/test_silent_wav.py`): Reihenfolge+Gap, Null-Gap = reine Konkatenation, Einzelteil ohne
  Trailing-Gap. Suite **309 grün**. _(D66 zeigte dann: der lange Start lag v. a. an XTTS-auf-CPU; plain `!intro` wurde
  zur Schnellstart-Variante, `!intro test` blieb die lückenlose.)_

**`!intro`-Crash beim Kollegen gefixt: Discord-2000-Zeichen-Limit (2026-06-14, D64). Suite 306 grün, committet +
gepusht (`1d48b18`).** Live-Befund aus Kollegen-Run: `!intro test` warf `HTTPException: 400 … 50035: Must be 2000
or fewer in length`. Ursache: die volle Antwort wurde in **einem** `channel.send` gepostet, aber der `!intro`-
Monolog läuft auf großem Längen-Budget (`DM_INTRO_NUM_PREDICT` 800) und sprengt Discords 2000-Zeichen-`content`-Cap.
- **Fix am einzigen Sende-Choke-Point** `SessionRuntime._send_with_retry` (`dmbot/runtime.py`): langer `content` wird
  in ≤2000-Zeichen-Nachrichten zerlegt; `view`/`embed` reiten auf der **letzten** (Würfel-Button/Turn-Order bleibt
  unter dem vollen Text). Der 5xx-Retry ist in einen `_send_once`-Helfer gewandert. Deckt **alle drei** Lieferpfade
  (Batch/Streaming/`!intro test`) auf einmal ab.
- **Neuer reiner Splitter** `split_for_discord` in `dmbot/tts/textsplit.py`: **verbatim** (verwirft nichts, anders als
  der TTS-`chunk_text`), bricht am spätesten Absatz-/Zeilen-/Satz-/Wortrand ≥ halbem Limit, Hard-Cut nur bei einem
  ungebrochenen Über-Limit-Lauf.
- **+4 Tests** (`tests/test_tts_chunk.py`): kurz=1 Stück, langer Monolog splittet verbatim unter Limit, Satzgrenze
  bevorzugt, ununterbrochener Lauf wird hart geschnitten. Suite **306 grün**.

**Kontext-Kosten-Refactor: `progress.md`/`CLAUDE.md` in schlanke Live-Dateien + on-demand `docs/` aufgeteilt
(2026-06-14, D63 → ADR 032). Suite 302 grün, committet + gepusht (`fa6c96d`).** Tobi (Plan-Modus): „der kontext ist
mittlerweile sehr groß und kleinste sachen fressen viele tokens — kann man sachen aus der claude.md auslagern …
und sowas auch mit der progress.md machen?". Geklärt + umgesetzt:
- **`progress.md` 1637→678:** `## Last session`-Historie (D32–D61), Done-Phasen 0–8 (volle Checklisten +
  `VERIFY EVIDENCE`) und ✅-erledigte/abgeschlossene Open Questions **verbatim** nach **`docs/progress-archive.md`**.
  Live bleibt: Current focus, Next step, **kompletter Decision-Log + Phase→ADR-Map**, offene Phasen 9/10 (voll),
  und **alle tatsächlich offenen Fragen** (Tobis Vorgabe). Done-Phasen als Einzeiler + Archiv-Pointer.
- **`CLAUDE.md` 226→153:** per-Modul-Konventionen (DMbot/Rules/Memory/RAG), Testing, Runtime, Troubleshooting,
  Style → **`docs/conventions.md`** (on-demand, in die „read on demand"-Tabelle + README verdrahtet). Inline bleibt:
  Session-Ritual, Golden Rules, Repo-Layout, schlanke Bot-A-Kurzfassung, neuer **Key gotchas**-Block.
- **Rotations-Regel** (CLAUDE.md `## Session ritual` + session-ritual-Skill): beim Eintragen eines neuen
  `## Last session`-Eintrags wandert der vorherige ins Archiv → die Live-Dateien bleiben dauerhaft schlank.
  _Dieser Wrap-up übt sie aus: der D62-`!intro`-Eintrag ist nach `docs/progress-archive.md` rotiert._
- **Konsistenz:** 9 Code-Kommentar-Zeiger (`preflight`/`__main__`/`vad`/`state`/`persona`/`orchestrator`/`resample`)
  von `CLAUDE.md` auf `docs/conventions.md` umgebogen, da ihre zitierten Anker dorthin umgezogen sind.
- **Verifiziert:** 3 parallele read-only Audits (Inhalts-Konservierung verbatim / Querverweise / Live-Korrektheit) →
  alle PASS; Suite **302 grün** (reine Doku-/Kommentar-Änderung). Effekt: ~17K Tokens/Session + ~1.5K/Turn.

**`!intro` — Eröffnungs-Monolog für Chemical Burn, der die Charaktere einbezieht (2026-06-14, D62 → ADR 031).
Suite 300 grün, live-unverified.** Tobi (Plan-Modus): „für chemical burn braucht es eine intro sequenz, in der
der bot erklärt was abgeht, wo man sich befindet, wie man hergekommen ist — und er soll die charaktere mit
einbeziehen." Geklärt: **ein langer Monolog** (kein Skript), als **neuer `!intro`-Befehl** (das kurze `!start`
bleibt), mit **voller Figuren-Tiefe**. Umgesetzt durch **Wiederverwenden + Parametrisieren** des bestehenden
`!start`-Eröffnungspfads (nicht duplizieren, ADR-030-Disziplin), Code-Files per Fan-out über parallele Agenten
auf disjunkten Dateien:
- **`CharacterStore.intro_roster_de()`** (`characters.py`): kompaktes deutsches Party-Roster aus `Character.raw`
  (concept/origin/faction/distinguishing/goals/connections/arc, tolerant gegenüber schlanken `_example`-Sheets,
  Mehrzeiler-Felder auf eine Zeile kollabiert, `""` bei leerem Store).
- **`build_intro_director_msg(roster)`** (`orchestrator.py`): `[Regie]`-Instruktion für **einen** zusammenhängenden
  Monolog (Ort → Ankunft → Auftrag aus Szenenkarte/Summary, dann pro genannter Figur ein persönlicher Moment —
  einweben, geheime/private Ziele nur andeuten, keine Probe). Das Roster reitet in der **Director-(User-)Message**
  mit → ADR-019-Prompt-Reihenfolge unangetastet. Bei leerem Roster degradiert die Instruktion sauber.
- **`num_predict`-Override** durch `_build_request`/`_chat_once`/`_generate`/`_stream_and_store`/`respond_opening`/
  `respond_opening_streaming` durchgereicht (Default `None` → bisheriges Verhalten; alle Altaufrufer unberührt).
  `!intro` läuft auf `DM_INTRO_NUM_PREDICT` (Default **800**; `config.py` + `runtime._intro_num_predict`).
- **`!intro`-Command** (`dmcog.py`, Aliase `einleitung`/`eroeffnung`), modelliert auf `start`: Pause-/Session-Guard,
  Szenen-Pointer deterministisch auf `start_scene` **nur falls ungesetzt** (golden rule #3, kein Reset laufenden
  Fortschritts), Würfel unterdrückt (`_last_action` bleibt None), Stream- **und** Batch-Pfad mit Längen-Override
  (`_deliver_streaming(opening=…, opening_num_predict=…)` bzw. `respond_opening(…, num_predict=…)`). `!start` exakt
  unverändert.
- **Tests:** neues `tests/test_intro.py` (+7): Roster (Volltiefe, lean-Sheet-Toleranz, leerer Store), Director-Shape
  (mit/ohne Roster), `num_predict`-Override greift / Default bleibt 220. Volle Suite **300 grün** (293 → 300).
  Cog importiert sauber, `DMCog.intro` vorhanden. _Offen: Live-Gate (s. Next concrete step)._
- **Nachrunde, testweise Delivery-B-Variante (Tobi): `!intro test`.** Gleicher generierter Monolog, aber andere
  **Sprachausgabe**: erst komplett im Batch erzeugen, dann **satzweise** vorlesen — jeder Satz **ohne jegliche
  Satzzeichen** (`strip_speech_punctuation` = Whitelist, nur Buchstaben/Ziffern/Leerzeichen, inkl. Wort-Bindestrich
  raus — Tobi „alle satzzeichen raus"; XTTS verhaspelt sich an Satzzeichen, D55) über ein eigenes blockierendes
  `_speak`, mit **0,2 s Pause** zwischen den Sätzen (`_deliver_intro_chunked` + `_INTRO_SENTENCE_PAUSE_S=0.2`),
  statt des nahtlosen Streamings — zum Vergleich des Feels. Der gepostete Chat-Text behält die Satzzeichen
  (lesbar, D38). **Nicht** die verworfene Multi-Beat-Sequenz (weiter eine Generierung). Hinter dem `test`-Arg,
  Default-`!intro` unverändert; +2 Unit-Tests für `strip_speech_punctuation` (Delivery-Pfad selbst nicht
  unit-testbar — Live-Vergleich). Wenn es sich nicht bewährt: `test`-Arg + Helfer wieder raus.

**Doku: drei Setup-Dokumente in eine Root-`SETUP.md` zusammengeführt (2026-06-14). Kein Bot-/Phasen-Change,
Suite unverändert 293 grün.** Tobi fragte, ob die SETUP.md noch passt und alles aus der Checkliste drin ist.
Befund: dem B9-Rebuild-Block in `docs/SETUP.md` fehlte die `conditions`-RAG-Quelle, die `docs/CHECKLIST.md`
*und* `retrieve.py` (`_SOURCES`) führen — ein Rebuild strikt nach SETUP.md hätte eine `rag.db` ohne die
deutschen Zustands-Spielwerte gebaut. Tobi wollte alles in **einer** Root-Datei. `docs/SETUP.md` (externe
Prereqs) + `docs/CHECKLIST.md` (Fremd-Maschine) → **Root-`SETUP.md`** gemerged, durchgehend Englisch; die
B1–B9-Labels behalten, damit „SETUP.md B5"-Verweise weiter stimmen. `conditions`-Quelle nachgetragen (alle 7
`_SOURCES` jetzt abgedeckt), B8 auf „Live-Party liegt im Repo" aktualisiert, Tests-Befehl auf
`uv run --with pytest python -m pytest` korrigiert. Alle Live-Verweise (README / architecture / roadmap /
progress / CLAUDE.md / session-ritual-Skill + `vad.py`/`piper.py`-Fehlerstrings) auf die Root-Datei gezogen;
die zwei `docs/`-Dateien gelöscht; historische Erwähnungen (progress-Log, ADR 012) bewusst stehen gelassen.
Commit `a6a011c`. _Kein D-Eintrag/ADR — Doku-Housekeeping, kein Bot-Design._

**Dev-Tooling: projekt-eigene Claude-Code-Skills + Test-Hook (2026-06-14). Kein Bot-/Phasen-Change, Suite
unverändert 293 grün.** Tobi fragte nach Skills für den schnelleren Ausbau. Angelegt unter `.claude/skills/`
(committed via `.gitignore`-Allowlist; `settings.local.json` bleibt lokal): **playtest-triage** (Live-Log →
diagnostizieren → deterministisch fixen → Suite → committen), **rules-subsystem** (neues Profil-Subsystem im
Psyker/Augmetik-Muster), **rag-ingest** (PDF → ingest → kalibrieren → verifizieren), **character-build**
(IM-Charakter validieren+einbauen, Session-Merge erst nach Bestätigung), **session-ritual** (Handshake +
Wrap-up + nächste ADR). Plus ein `Stop`-Hook (`tools/hooks/test-on-change.sh` + committed
`.claude/settings.json`): Suite nur bei Änderungen unter `dmbot/`/`tests/`/`data/systems`, **still bei Grün**
(Output nur bei Rot); `.gitattributes` pinnt `*.sh` auf LF. Index aller Skills in `.claude/skills/README.md`.
_Kein D-Eintrag/ADR — Dev-Workflow-Infra, kein Bot-Design; Rationale im Skills-README._

**Code-Review-Korrektheitsrunde (2026-06-13, D61 → ADR 030). Suite 293 grün, live-unverified.**
Tobi: `/code-review` über die Tagescommits, „Funktionalität soll bleiben", danach „fix alles fan out".
Review als Multi-Agent-Fan-out (9 Finder-Winkel über `5d672b6~1..HEAD` + Pro-Fund-Verifizierer); Fixes
über 7 Agenten auf disjunkten Dateien, zentral mit der vollen Suite verifiziert.
- **9 Korrektheits-Fixes (alle verifiziert, funktionserhaltend):** (1) Warp-Containment → `Disziplin
  (Psi)` via neuem `ResolvedManifest.contain_base` (`characters.py` + `dicecog.py`); (2) Party-Psyker
  nicht in WorldState → einmalige DE-Warnung statt stillem Warp-Charge-Verlust (`dicecog.py`); (3)
  `_deliver_answer` awaitet Dice/Scene-Tasks im `finally` (`dmcog.py`); (4) Auto-Recap `clear_history`
  löscht nur den `summarize`-konsumierten Präfix via `_compact_consumed` (`orchestrator.py`); (5)
  Marker-Regex `\b`→`[\s:]*`, verklebte Marker greifen (`marker.py`); (6) `resolve_test`
  Signatur-Dispatch statt `except TypeError`-Retry (`engine.py`); (7) Streaming cancelt verwaiste
  Tasks + drained WAVs (`dmcog.py`); (8) VadSink-Mute = Tiefenzähler (`recv.py`); (9) Soak via
  `skill_value` strip+CI (`dicecog.py` + `characters.py`).
- **Cleanup/Efficiency:** geteilter `SystemProfile._catalog_lookup` (`profile.py`); geteilter
  `dmbot/tts/wavio.write_silent_wav`; toter `reduce_warp_charge` entfernt (`state.py`); no-op `[:80]`
  auf Konstanten weg (`scene.py`); thread-lokale gecachte sqlite-Connection + Tuple-Rebuilds weg
  (`retrieve.py`); `<<`-freier Fast-Path im `StreamAssembler` (`orchestrator.py`).
- **Bewusst NICHT gemacht:** die Altitude-Punkte (system-agnostische Generalisierung von
  `warp_charge_gain`/`reverse_d100`, der per-Marker-Pipeline, `_SOURCES`/`_is_junk_hit`) — aufgeschoben
  auf den Zweitsystem-/Phase-10b-Punkt (ADR 005); kein zweites System zum Generalisieren da, groß +
  verhaltensriskant. Ebenfalls nicht angefasst: Layer-2-Mute bleibt default-off (D25), XTTS-Sampling
  (D55), Persona-Text; der `marker.py`-`profile`-Param blieb (ein Test außerhalb des Filesets ruft ihn).
- **Verifikation:** volle Suite **293 grün** (+~30 fixed-seed/Unit-Tests in den gefixten Bereichen,
  ein RAG-Fixture-mkdir-Fix). Zwei versehentliche Agenten-Artefakte (`C:…*.diff`) entfernt.

**Cog-Split-Refactor (2026-06-13, D60 → ADR 029). Code-complete, Suite 263 grün, live-unverified
(Smoke-Test reicht).** Reiner Struktur-Refactor (nach Tobis Cog-Split-Spec), Plan-
Modus zuerst, Umsetzung über parallele Agenten auf disjunkten Dateien.
- **Schnitt:** `dmbot/runtime.py` `SessionRuntime` hält allen geteilten State (Brain+OllamaClient,
  STT/TTS, Bridge, Profil+Characters, RAG, Adventure, per-Channel-WorldState, Pause/PTT/Mute-Flags)
  + die State-Helfer (`_persist_and_refresh`/`_set_scene`/`_load_*`/`_send_with_retry`) + die STT/VAD-
  Callbacks (der Transcriber wird hier mit `_on_transcript` gebaut). In `__main__.setup_hook` einmal
  aus `Config` gebaut, in jede Cog injiziert — die 26 Konstruktor-kwargs sind weg.
- **3 Cogs (Tobi-Entscheid statt 4):** VoiceCog (join/leave/vstatus/mic/pause, VAD-Sink),
  DiceCog (roll/test/turn/rules/npc/damage/heal, Würfel+Manifest-Buttons, Auto-Kampf, Turn-Order),
  DMCog (Delivery batch+streaming, `_speak`, Auto-Recap, !dm/!redo/!start/!wrap/!say/!voice + Szenen
  !ort/!szenen/!ortmodus + `<<ORT>>`-Marker + !lore). **Kein `bot.get_cog`:** 5 Runtime-Hooks
  (`run_and_deliver`/`auto_dm_turn`/`handle_dice`/`reanchor_mic`/`post_turn_order`), je von der
  besitzenden Cog im `__init__` registriert.
- **Verschoben statt umgeschrieben:** Methoden-Bodies byte-identisch, nur `self._X → self._rt._X` +
  Hook-Calls; Agenten belegten das per AST/Reverse-Rename-Diff, plus mein Spot-Check der untesteten
  Streaming-Pipeline (`_deliver_streaming`). Boot-Pfad unverändert (Preflights einmal, gleiche
  Reihenfolge); `TEARDOWN_STEPS`-Summe bleibt 4 → Shutdown-Anzeige byte-identisch.
- **Zeilenbilanz:** `commands.py` 2300 (1 Klasse) → runtime 565 / voicecog 412 / dicecog 568 /
  dmcog 838 = 2383 über 4 Module (Mehr = 4× Header/Imports/`__init__`-Gerüst; kein Code verloren).
- **Tests:** 263 grün. Nur Import-Pfade angepasst (`test_context_budget`, `test_autorecap`) + **eine**
  Fixture-Verdrahtung (`test_autorecap` baut die Bare-Cog jetzt mit einer Stub-Runtime statt flacher
  Attribute) — Assertions unverändert; gemeldet, da über reine Imports hinaus (Spec-Smell-Check).
- **Funktional gegengeprüft (ohne Discord):** der `!rules`/`!lore`-Pfad — den die Cogs jetzt über
  `self._rt._retriever` / `self._rt._brain` aufrufen — live gegen `rag.db` + Ollama getestet: 4 Fragen
  (kritischer Erfolg, Zustand Blutend, Gott-Imperator, vier Chaosgötter) treffen die richtigen Quellen
  (d=0.29–0.40) und liefern korrekte, gegroundete Antworten. Offen bleibt nur der **Voice-Smoke-Test**
  (`!join`→sprechen→`!dm`→Würfel→`!leave`), der die zwei Bots im Channel braucht.
- _Kosmetisch (kein Verhaltens-/String-Change): verschobene Log-Calls tragen ihren neuen Modulnamen
  in der opt-in `debug.log`-`%(name)s`-Spalte + in WARNING-Konsolenzeilen (`runtime`/`voice.dmcog`
  statt `voice.commands`); die Log-Messages + Green-Chat/Transcript-Formatierung sind unverändert
  (Filter keyen auf Message-Inhalt + `dmbot`-Präfix, verifiziert)._

**Erste Live-Runde → Playtest-Fix-Runde (2026-06-13, D57–D59, ADR 027/028). Code-complete,
live-unverified.** Die erste echte Runde (Channel circlejerk, Party Gellicus/Fridolin/Rektalus)
lief „teils besser als davor", aber die Hauptklage war: **der Bot geht null auf die Story ein,
sagt am Anfang nicht, was abgeht, und führt nicht durch die Geschichte.** 13 Kritikpunkte aus dem
annotierten Log gezogen; Wurzel-Diagnose + Fixes über parallele Agents (Tobis Vorgabe). Suite
**246 → 262** grün.
- **Smoking Gun (D57 → ADR 027):** `num_ctx` lief real auf **8192** (hartkodiert in `client.py`;
  die 24000, die Tobi zu setzen glaubte, wurden nirgends gelesen). Ab ~Turn 16 lag der Prompt
  >85% → Ollama trunkiert den **Kopf zuerst: Persona + Abenteuer-Zusammenfassung**. Das erzeugte
  gleichzeitig Story-ignoriert, zu lange Antworten, Puppeting, Vorweg-Auflösung. Fix: `num_ctx` per
  `OLLAMA_NUM_CTX` konfigurierbar (Default **24576**, läuft jetzt auf einer 4080) **+** rollierender
  **Auto-Recap** (`DM_AUTORECAP`, default an): bei Budget-Überschreitung nach dem Zug kumulativ
  zusammenfassen (`summarize(..., prior_recap=…)`), wie `!wrap up` persistieren und die
  In-Memory-History leeren → Kopf wird nie mehr trunkiert (der von Pr0degie gewünschte „Handoff").
  _Abweichung von der `prompt-6`-Spec: compact-and-clear am echten Budget-Signal statt
  fold-before-trim — Naht „kein Verbatim-Verlauf direkt nach Kompaktion" als Verfeinerung notiert._
- **Eröffnung + Persona (D58):** neuer **`!start`** (Aliase `!briefing`/`!auftrag`) erzählt das
  `auftrag`-Briefing (Halikarn, Mission, Spuren als Atmosphäre) über die bestehende Stream-/Speak-
  Pipeline; eigener `respond_opening*`-Pfad unterdrückt Würfel-Routing. Persona (`dm_core_de.md`):
  Szenenziel im Blick + sanft auf offene Spuren lenken, **jeder Zug endet mit Welt in Bewegung**
  (NSC handelt/spricht, nie flache Beschreibung die stoppt), **Spotlight** auf andere/stille
  Figuren namentlich.
- **RAG entrauscht (D59 → ADR 028):** `_is_junk_hit` filtert OCR/Statblock-Müll (Dash-Runs,
  `(eLite)`-Tags, Picture-Text) aus dem Pro-Turn-Block; `MAX_DISTANCE` bleibt 0.45, recall@1/@3
  unverändert. Offen: `WARRIOR`-Epigraph-Zeilen brauchen Re-Chunking beim Ingest.
- _Offen / Modell-Ceiling: generische Wurf-Ergebnistexte, NSC-Name/Genus-Halluzinationen, Reste
  von Wiederholung/Vorweg-Auflösung (nemo-12B-Grenze); die Marker-vs-Router-Spannung (#6,
  Inline-`<<TEST>>` verworfen, Router feuert nach der fertigen Erzählung) als spätere Designfrage.
  Live-Gate nächste Runde: `!start` spricht das Briefing, kein `[ctx] … truncating`-Warning mehr
  (bzw. Auto-Recap greift sichtbar), DM nennt Spuren/Szenenziel, kein 📚-Garbage bei reinem RP._

**Auto scene transitions — `<<ORT …>>` marker + confirm button (2026-06-13, ADR 026).** `!ort <id>`
was a manual, human-only pointer move (ADR 020). Now the DM-LLM can *request* a move in-band, code
validates + a human confirms — mirroring the dice/`<<TEST>>` pattern (golden rule #2), so golden
rule #3 still holds (the model never *writes* `scene_id`, only requests).
- **Marker:** third extractor `extract_scenes` in `dmbot/rules/marker.py` (profile-free — scenes
  belong to the *adventure*, not the rules profile) + `SceneRequest`. Reuses the `<<…>>` delimiter so
  the existing strip/withhold TTS guards apply for free.
- **Orchestrator:** `finalize_answer` 3→4-tuple (+`scenes`), `StreamResult.scenes`, `_pending_scenes`
  queue drained via `take_pending_scenes` — queued **only under the `_last_action` post-roll guard**
  (a results-only consequence turn must not move the pointer; same guard tests/manifests use).
- **Move + validation:** `ort()` core refactored into shared `_set_scene(state, id)`; new pure
  `Adventure.resolve_move(current, target, mode)` (unit-tested, no Discord) — `verbunden` (default)
  accepts only the current scene's `leads_to` neighbours, `frei` any known scene; illegal/unknown/
  no-op → None.
- **UI/flow:** `dmbot/discord_ui/scene.py` `SceneChangeView` (Wechseln/Abbrechen, modelled on
  `DiceTestView`); cog `_handle_scene` posts the confirm button from both delivery paths (batch +
  streaming), the move happens on click. Mode is a cog setting: `DM_SCENE_MODE` default + runtime
  `!ortmodus [verbunden|frei]`. Manual `!ort` stays as override.
- Persona bullet in `prompts/dm_core_de.md` ("nur wenn die Gruppe ihn wirklich betritt"). ADR 026.
  Suite **246** (was 234; +12 scene-marker tests). **Live-unverified** — needs a session to confirm
  the marker fires, isn't spoken, and the button moves the pointer.

**Interactive `!lore tts` reader + anti-repetition persona rule (2026-06-13).** Three asks (eval'd
in plan mode against efficiency/speed/correctness):
- **`!lore tts` is now a manual block-by-block reader** (`dmbot/discord_ui/lore_read.py` →
  `LoreReadView`, modelled on `RulesView`): each lore block's **text is shown in chat** and read
  aloud; **⏭ Weiter** advances to + reads the next block (a fast click-through coalesces to the
  latest shown block — Bot A's `/speak` blocks per WAV with no stop, so a running block can't be
  cut mid-playback, one speak task in flight), **🔊 Nochmal**, **⏹ Stopp**. `_lore_speak` rewritten
  to build/post the view; dispatch unchanged.
- **Repetition** (DM re-explained established facts in full): persona rule in `prompts/dm_core_de.md`
  — what's in "Was bisher geschah", the world state and the ongoing scene is **already known to the
  players**; reference it briefly, describe only **new** things + consequences — and the recap label
  in `_build_request` sharpened to "(den Spielenden bereits bekannt — nicht erneut ausführlich
  erzählen)". Prompt-only; live-observe nemo's adherence (a code guard is the fallback, not built).
- **"Reads each block twice":** verified **NOT in DMbot** (lore_pages 17 clean pages, loop/synth/
  concat all 1×, no custom `on_message`) → it's **Bot A's playback** (separate musicbot repo). Beleg
  beim Test: one `🔊 TTS … speaking` + one `/speak` per block in `debug.log`. Suite **234**.

**RAG calibration + a German conditions glossary source (2026-06-13).** Reviewed the open task
prompts 2/5/6 against the goal (efficiency/speed/correctness): did **prompt 5** (RAG calibration —
highest value/risk ratio), deferred 6 (gated on the unmet Phase-9 live gate), skipped 2 (pure
maintainability, zero bot benefit). Built a golden set (`tools/rag_golden_set.json`, 21 positives /
10 negatives, committed — own questions + expected source/heading, no rulebook passages) and
`tools/rag_calibrate.py` (imports the real `retrieve.py` path; per-query hits, recall@1/@3, a
0.35–0.60 threshold sweep per context; report → gitignored `tools/rag_calibrate_report.md`).
- **Finding:** positives (rule questions) and negatives (narration) overlap badly in the embedding
  space — no threshold separates cleanly, so `MAX_DISTANCE` **stays 0.45** (the data didn't support
  a confident change). The real gaps were **content/chunking**, not the threshold: German condition
  names ("Blutend") missed the English condition chunks, and weapon-stat **tables** don't retrieve.
- **Fix (correctness):** a hand-authored German **conditions glossary** — `data/rules_de/conditions.md`
  (12 Zustände, own words grounded in the rulebook), new RAG source **`conditions`** (13 chunks →
  `## Regelwerk`), wired into `_SOURCES` and the `!rules` search. Each section leads with its German
  name **in the body** (the ingest embeds the body, not the heading), which pulled the specific chunk
  to the top (Blutend 0.40→**0.29**). Live: `!rules` now answers Blutend/Betäubt/Vergiftet/Brennend
  **exactly right** (before: Blutend hallucinated). recall@1 38%→**52%**, recall@3 67%→**81%**, narration
  hits 13→**15/21**, **zero** new negative leaks. Store **2482 chunks**, suite **230**. New committed
  source category `data/rules_de/` (`.gitignore` allowlist; pattern of ADR 021). _Open: weapon/stat
  tables still don't retrieve (table-row chunking) — a separate ingestion session._

**Faster startup — background TTS load + parallel Ollama warm-up (2026-06-13 → ADR 024).** Tobi
liked the fast shutdown (ADR 020) and asked for a faster start, then "robust und zuverlässig".
Two synchronous boot costs blocked "bot ready": the XTTS/Coqui load (torch + GPU, several seconds)
in the cog `__init__`, and `start_dmbot.bat`'s `ollama run` warm-up (~15 s cold) *before* launch.
- **TTS now loads on a daemon thread** → `on_ready` fires immediately. A `_tts_enabled` flag drives
  the is-speech-on checks (replacing `self._tts is not None`), and `_synthesize()` waits on a
  `_tts_ready` event **inside the worker thread** (never the loop), so the first spoken line waits
  for the model only if still loading (virtually always warm by first `!join`+speech).
- **`start_dmbot.bat`** backgrounds the model warm-up (`start /b`) so it overlaps boot; the
  boot-time `check_ollama` preflight (reachability + model pulled) is unchanged — only residency is
  deferred. Single-GPU Ollama queues the first turn behind the warm-up; 300 s read timeout covers it.
- **Robustness hardening** (restores ADR 020-era fail-fast without re-blocking boot): bounded wait
  (`_TTS_LOAD_TIMEOUT_S` 90 s → a hung load degrades to text-only, not a frozen synth); loud boot
  logging (`loading … / ready in N s / FAILED`); a `!join` guard that announces ⚠ no-speech / ⏳
  still-loading. Suite **230**. _Live-verify: console reaches "logged in as" fast; `!join` shows the
  notice when relevant; first DM sentence is spoken._

**New player party assembled + deployed, Inquisition guides into the RAG (2026-06-13).** A
player-prep + content session, no core-pipeline change.
- **New party (replaces Garran/Eli/Yann):** built **Fridolin Feuchtgebietheld** (Schreinwelt
  Inquisition interrogator + stealth psyker) via the §how-to rules + ADR 022 (all `known_powers`
  hit the catalog); **Gellicus Schulz** (Timo) + **Rektalus Zerfickus** (Sezgin) came from a parallel
  session, validated (budget 90 / wounds / weapons) and given full backstory. All three live under a
  **committed `data/party/`** (one JSON per player; `.gitignore` allowlist) with filled PDF sheets
  (sheets stay local — bought-sheet derivatives).
- **Deployed to circlejerk:** merged the three into `data/sessions/1343673766487654464/characters.json`
  (+ aliases) and **committed it** (allowlisted) so the bot loads the party on a teammate's clone; the
  old party's sheets archived to `…/archive/2026-06-13_alte_party/`. No `state.json` → first `!join`
  seeds fresh. _Caveat: a different Discord channel needs the file copied into its own `<id>/` folder._
- **Self-service character creation:** `docs/character-creation-prompt.md` — a standalone prompt that
  interviews a new player and emits a budget-correct character JSON (stats + optional psyker + augmetics).
- **Inquisition guides into the RAG** (see Current focus): Player's Guide whole (`player_guide`, 502)
  + GM-Guide spoiler-trimmed (`gm_guide`, 226); `!rules <frage>` now also searches both. Store 2469
  chunks, suite **230**. Docs synced (bge-m3 everywhere, CHECKLIST/SETUP rebuild lists, augmetics).

**Player-prep tooling + `!rules <frage>` (2026-06-13, D50).** A session of player-facing prep and one
new command, no core-pipeline change.
- **`!rules <frage>` answers a rule question from the book (D50).** `!rules` with no arg still pages
  the system's short rules; with a question it retrieves the matching rulebook chunks
  (`source=rulebook`, `lookup(..., max_distance=0.55)`) and the new `DMBrain.answer_rules` has the
  LLM synthesise a **short German answer grounded only in those excerpts** (golden rule #7 — say so
  when the book doesn't cover it; never invent rules). Unlike `!lore <frage>` (raw curated German
  chunks), the rulebook is English layout-soup → an LLM translate/condense step is needed. No hits →
  honest "nichts im Regelbuch". Reading material, never spoken. Verified end-to-end against the live
  store (Ausweichen, kritischer Treffer → correct grounded answers); +3 unit tests. **Suite 191.**
- **Character-creation guide made self-explanatory** (`docs/how-to-create-a-character.html`): a new
  un-numbered **glossary** ("Begriffe") explaining dice notation (1W10+5), bonus = tens digit, how a
  d100 roll-under Probe + difficulty ladder + EG work, and — the main stumbling block — wounds/soak/
  kampfunfähig (`Waffe + EG − Soak`, 0 = down), plus origin and inventory explainers; all grounded in
  the profile + `engine.resolve_damage`. Compact at-a-glance **homeworld** and **weapon** tables added
  at the form's dropdowns so you don't click through.
- **Character-sheet filler reworked to editable PDFs** (`tools/fill_character_sheet.py`): the bought
  sheet is a graphical raster, so every value is now a real **AcroForm text field** (transparent fill)
  pre-filled with the computed value — editable in any reader. **Every** fillable area is a field now
  (all skill rows, weapon/armour/hit-location tables, talents, influence, psychic powers, equipment,
  multi-line goals/connections/notes/combat-notes), with grid/multiline helpers; positions read off
  the raster by pixel analysis (fixed weapon-row drift, the page-1 skill/spec 20-px cumulative drift,
  distinguishing/XP, encumbrance, Body hit-location). New `tools/example_garran_vex.json` (own grimdark
  flavour, committed) drives a fully filled Garran Vex example → `data/pdfs/Garran_Vex.pdf` (git-ignored
  derivative). Back-compat: the mechanical party file still renders. Note: the three Initiative
  Melee/Ranged/Reflexes boxes are a quick-reference (not a required derived stat, IM p.88).

**Lore-Korpus: kuratiertes deutsches Imperium+Chaos-Kompendium (2026-06-13, D48 → ADR 021).**
Tobi fragte „ist die Lore drin?" → Live-Probe gegen `rag.db`: Menschen-Lore trifft aus dem
englischen Rulebook (Imperium d=0.27, Inquisition d=0.34), aber **Chaos-Kosmologie existiert in
den IM-Büchern nicht** („vier Chaosgötter" d=0.53 miss — by design, Chaos als verborgener
Horror); Tyraniden/Necrons/T'au ebenfalls leer (Tobi: bewusst ok). Beschlossen + gebaut:
- **`data/lore/imperium.md` (18 Chunks) + `chaos.md` (17 Chunks)** — handgeschriebene deutsche
  Lore, grimdark in-world (Tobis Wahl: zwei Dateien, beide ausführlich, grimdark). Imperium:
  Imperator/Thron/Astronomican/Custodes/Ekklesiarchie, High Lords/Zehnt, Astartes, Militarum,
  Flotte, Mechanicus, Inquisition+Ordos, Astropathen, Navigatoren, Psioniker, Macharian-Kontext.
  Chaos: Warp/Gellerfeld, die vier Götter (je eigene Sektion), Großes Spiel, Dämonen-Taxonomie,
  Korruption/Kulte, Horus-Häresie + Horus, Chaos Space Marines, Antwort des Imperiums.
  **Committed** (Tobi, Nachrunde gleicher Tag): anders als das Abenteuer-Kompendium keine
  Buch-Ableitung, sondern eigene Formulierung frei zugänglichen 40k-Allgemeinwissens —
  `.gitignore`-Allowlist um `data/lore/*.md` erweitert.
- **`retrieve.py`:** `_SOURCES` + `lore_imperium`/`lore_chaos` (→ `## Weltwissen`), Reihenfolge
  Regeln → breite Lore → lokales Rokarth; `setting`-Label um „lokaler Hintergrund" geschärft.
  Selbstverdrahtend, sonst kein Code-Change. Schwelle bleibt 0.45 global.
- **Probe-getunt:** Entitäts-Sektionen brauchen den definitorischen Satz oben („Wer ist Horus?"
  0.51→0.43 nach eigener `### Horus`-Sektion; „Chaos Space Marines" 0.46→0.36). 24-Fragen-
  Finalprobe: alle Ziel-Fragen treffen die richtige Quelle <0.45; Regressionen sauber (Regelfrage
  → rulebook, Rokarth → setting, Table-Talk + Voll-Spoilerfrage stumm). Tests +2 (Weltwissen-
  Block + Block-Reihenfolge), Suite **183/183**. _Live-Gate offen: `📚 lore_…`-Logzeile in einer
  echten Session._
- **Nachrunde (Doku für den Kollegen):** **`docs/CHECKLIST.md`** (von Tobi aus HANDOVER.md
  umbenannt) — was eine fremde Maschine privat von Tobi braucht (PDFs+md, Abenteuer-Kompendium,
  `rag.db` oder die Rebuild-Befehle) vs. was der Clone mitbringt; **SETUP.md**: B2 stale
  `nomic-embed-text` → `bge-m3` korrigiert + neue **B9-Sektion** (RAG-Store kopieren/neu bauen,
  `DM_ADVENTURE`, `📚`-Sanity-Check) + TL;DR-Schritt 8; README-Transfer-Sektion gefixt
  (bge-m3, CHECKLIST-Link).
- **Nachrunde 2 — `!lore`-Command (D49):** `!lore [topic]`/`!hintergrund` blättert
  `data/lore/<topic>.md` (ohne Arg → imperium, `!lore chaos` → Chaos) über die bestehende
  `RulesView`; neuer pure Parser `dmbot/rag/lore.py` (`lore_pages`: Heading = Seite, H1 +
  Quellen-Blockquote geskippt, 4000-Zeichen-Guard) + `tools/lore_to_html.py` → `docs/lore.html`
  (grimdark Standalone — Tobis Review-Ansicht + Spieler-Handout; nach Lore-Edits neu
  generieren). Kein TTS, kein DM-Turn. Tests +4, Suite **187/187**. Review erledigt: Tobi las
  `docs/lore.html`, ein Begriff-Fix (Gottkaiser → Gott-Imperator, in die md gesynct +
  re-ingestet) → committed.
- **Nachrunde 3 — `!lore <frage>` (D49-Erweiterung, Tobi):** der Command kann jetzt Fragen
  gegen die DB beantworten — `RulebookRetriever.lookup()` (nur Weltwissen-Quellen, k=2,
  eigene Schranke **0.52**: locker genug für erzählerische Formulierungen ~0.48, eng genug
  dass die Off-Korpus-Tyraniden-Frage ehrlich „steht nichts im Weltwissen" bekommt statt des
  nächstbesten falschen Chunks bei 0.54), deterministische Chunk-Anzeige als Embed, kein LLM.
  Topic-Blättern bleibt (`!lore` / `!lore chaos`). Live gegen die DB verifiziert (7 Fragen:
  Gott-Imperator/Dunkle Götter/Navigator/Rokarth treffen; Tyraniden + Regelfrage korrekt
  stumm mit Hinweis). Plus „Dunkle Götter"-Synonym in chaos.md (war knapp drüber). Tests +2,
  Suite **189/189**. Polish nach Tobis erstem Blick: der Frage-Footer im Antwort-Embed flog
  raus (die Frage steht direkt darüber in der Command-Nachricht).

**(Davor) Charaktererstellung (2026-06-12, Runde 2 der Spieler-Doku).** Die Runde will neue
Charaktere (ersetzen Garran/Eli/Yann; Chemical Burn startet dann frisch). Gebaut:
- **`docs/how-to-create-a-character.html`** — deutsche Anleitung (IM-treuer geführter Build:
  Punkte-Kauf 20+90 oder 2W10+20; echte Origin-Tabelle +5/+5; 6 Skill-Steigerungen à +5, max 2
  je Skill; Wunden = StrB+2×TghB+WilB, Buch-verifiziert) **plus interaktives Formular**
  (Vanilla-JS: Live-Punktezähler, Origin-Boni automatisch, Wunden-Autoberechnung,
  Budget-Validierung sperrt den Copy-Button, Live-JSON). JSON-Shape = Character-Schema +
  `player`-Feld (→ Alias; landet harmlos in `raw`, gegen `Character.from_dict` verifiziert).
- **`tools/fill_character_sheet.py`** — füllt den offiziellen IM-Bogen
  (`data/pdfs/…Character sheet.pdf`, KEINE Formularfelder/Text → Koordinaten-Overlay, an
  100-dpi-Renderings kalibriert): Name/Origin/Konzept/Patron, 9 Eigenschaften, Skill-Adv+Totals
  (Adv rekonstruiert aus Wert−Eigenschaft), Initiative, Wunden, Waffenzeile (Testwert + Schaden
  ausm Profil), Inventar ins Equipment-Grid. Sichtgeprüft an der aktuellen Party (3 PDFs nach
  `data/sessions/<id>/sheets/` — git-ignoriert, Ableitung des gekauften Bogens).
- **Einspeise-Prozess (wenn die JSONs kommen):** Spieler → Tobi → Claude validiert (Budgets,
  Formeln, Waffen) → baut `characters.json` + Aliases → löscht circlejerk-State/History/Recap →
  Bögen füllen + verschicken → **how-to-play-Charakterkarten + Checklisten-Namen
  aktualisieren** (Gates sind charakterunabhängig). Suite unverändert 177/177.

**(Same day, earlier) Spieler-Doku (Abschluss):** `docs/how-to-play.html` — deutsches Regel-Primer
(~10 min Lesezeit, gestyltes Standalone-HTML, grimdark): d100-Kernschleife, Schwierigkeitsleiter,
EG, Crits, Kampf mit Schadensformel, Fortgeschrittenes (Vorteil, Zustände, Überlegenheit,
Einfluss/Patron, Korruption) — Beispiele mit den echten Party-Werten durchgerechnet (gegen das
Sheet verifiziert), spoilerfrei, ohne Bot-Bedienung (bewusst, Tobis Wahl). Vor der nächsten
Session an Timo & Sezgin verteilen. Eigene Formulierung → committed trotz public repo.

**Starter Set in den DM (D46, gleicher Tag, direkt nach 10a).** Tobi legte das gekaufte IM
Starter Set nach `data/pdfs/Starter Set/`. Entschieden + gebaut:
- **Setting Guide (68 S.) → Lore-RAG:** `pdf_to_md --pages 1-57` (das „Villains on
  Voll"-Kapitel mit der Mireclaw-Auflösung bleibt bis zum Kampagnenfinale draußen — dieselbe
  Spoiler-Disziplin wie beim Abenteuer) → `ingest --source setting` (201 Chunks). Retrieval
  sucht jetzt rulebook+setting und gruppiert als `## Regelwerk` / `## Weltwissen` (TOP_K=3).
  Sanity verifiziert: „Welche Adelshäuser herrschen in Rokarth?" → NOBLE HOUSES ✓; „Wer steckt
  hinter Gratis?" → **kein Treffer** ✓ (die Spoiler-Frage bleibt stumm).
- **Patron-Sheet Aegidius Halikarn** ins chemical_burn-Kompendium: Motivation Information,
  Auftreten undurchschaubar, 100 Solars/Tag, Boons (Grenzenlose Autorität, Furchteinflößender
  Ruf) + die Sanctum-Obscurus-Ausstattung in der Thaler-Szene.
- **Aufgeschoben:** „The Blazing Seraph" (SS-Adventure-Book, 49 S., eigenes Bestiarium) wird
  erst nach dem Chemical-Burn-Live-Test zum zweiten Szenen-Kompendium; Handouts/Tokens/
  Sektorkarte = Tischmaterial (Backlog-Idee: `!ort` postet Handout-Bilder). Suite **176→177**.

**(Same day, earlier) Phase 10a built — the 3-stage hybrid (same day as D43, after the "perfect gamemaster"
discussion).** Tobi bought *Chemical Burn* (53 pp.), put it in `data/pdfs/`, and asked for a deep
joint planning round ("stell mir sehr viele fragen"). Decisions (via discussion): 3-stage hybrid
over pure RAG, story as guardrail (not railroad), priorities = plot coherence + W5 question
precision, German scene prep, auto-extracted NPC statblocks, story pipeline before Timo's
Tailscale model test (which runs independently via `OLLAMA_HOST`). Built end to end:
- **Compendium:** `tools/pdf_to_md.py` on the story PDF → I read all 53 pages and authored
  `data/adventures/chemical_burn/adventure.json` (15 German scene cards: description, NPCs,
  opportunities with profile-aligned skills/difficulties, secrets flagged "NIE aussprechen",
  leads_to, off-script guidance) + `npcs.json` (24 statblocks from the Core-Rulebook bestiary +
  adventure mods; wounds/TB/armour engine-ready). **Local-only** (public repo — derivative of a
  bought book, like the PDFs). _Tobi: review the cards for tone/quality._
- **Loader + wiring:** `dmbot/rag/adventure.py` (pure, tested); `WorldState.scene_id` (persists
  like HP); prompt order extended (recap → **adventure** → state → **Regelwerk** → hint);
  `DM_ADVENTURE` env; `!join` announces adventure + scene; `!ort <id>`/`!szenen`; `!npc add`
  resolves compendium statblocks (explicit numbers override).
- **Rulebook RAG:** `dmbot/rag/ingest.py` (heading-aware ~400-tok chunks, long pdf_to_md
  paragraph lines split at sentence ends; meta table pins embedder+dim) + `retrieve.py`
  (threshold 0.45 cosine, k=2, source=rulebook only, degrades silently). **Embedder switched
  nomic→bge-m3 after a failed sanity check** (German questions vs English text — exactly the
  CLAUDE.md "inspect a real chunk" reality check). Store: 1505 chunks. Verified: crit/difficulty
  questions hit CRITICAL HIT / DIFFICULTY; "ich gehe zur Tür" stays silent.
- **W4 guard:** `is_self_repetition` (SequenceMatcher ≥0.75, normalized, <60 chars exempt) joins
  the D43 echo guard — catches the live "Warum sind wir hier?" pronoun-swap re-description;
  retry with own nudge, then suppress; streamed-too-late repetitions logged loudly.
- **Tests 157→176** (+`test_adventure.py`, `test_rag.py`; compendium test skips on fresh clones).
  New dep `sqlite-vec` (§3 justified); `bge-m3` pulled. → **ADR 019**, D44/D45.

**(Same day, earlier) The 2026-06-12 echo collapse → diagnosis + the D43/ADR-018 robustness round.** Tobi reported the
bot "fühlt sich nicht mehr wie ein Gamemaster an" with a live log. Diagnosis from `debug.log` +
`data/sessions/1355307134559981709/history.jsonl`:
- **Wrong channel:** the session ran in `1355307134559981709`, not circlejerk (`1343673766487654464`)
  where the party is registered → `_load_characters` silently fell back to the **example party**
  (Pr0degie→Mortn aliases, wrong sheet values). Tobi confirmed circlejerk is the play channel.
- **Echo degeneration:** on the post-roll turn the model answered `Pr0degie: Ich greife den
  Kultisten an.` (predicting the next player line, not narrating); `_strip_leading_label` left a
  clean-looking echo that was spoken + stored → self-reinforced: **three turns in a row the DM
  answered every input — including an elaborate sword attack — with the same parroted sentence.**
- **Trigger:** the model's inline marker requested `<<TEST Heimlichkeit für Pr0degie>>` for an
  *attack* and won the D40 dedupe over the validated router; the bare `[Würfel] …` line carried no
  instruction what to do with it.
- **Race:** a dice click during playback overwrote `_last_turn` before the running turn's autosave
  read it → wrong `(user_msg, answer)` pairs in `history.jsonl` (seen in line 3).
- **Cold start:** the greeting turn hit `httpx.ReadTimeout` after 222 s gen (model load + GPU
  contention) and XTTS ran at RTF 34–45 until warm.

Fixes (all landed, suite **142→157**, live-unverified): echo guard (`is_echo` + retry-with-nudge +
suppress + history-poison protection incl. `restore_history` skipping empty answers), roll-feedback
directive on results-only turns, router-wins dedupe (`roll_button_source`), autosave `user_msg`
snapshot at generation end, `!join` party announcement + ⚠ example-fallback warning, `chat_stream`
read timeout 300 s, `DM_NUM_PREDICT` 160→220 + persona "zwei bis vier Sätze" (ADR 016 partial
rollback — streaming removed the brevity justification). Poisoned session dir
`data/sessions/1355307134559981709/` deleted; circlejerk untouched. **→ ADR 018.**

**(Prior) First live streaming run + tuning (2026-06-10, after the commit).** Tobi ran the streaming
pipeline live and pasted the log. **What worked:** streaming itself (`first_audio=3234ms` on the
narration turn — the old path would've been silent for `gen 6.5s + full synth`), and the **Phase-9
recap came automatically on `!join` and the `!wrap up` of the prior session was very good** (the
memory narrative-thread half is effectively live-confirmed). **Three content bugs fixed (D42 +
cleanup):** (1) the model streamed a **marker-only** answer (`` `<<TEST…>>` ``, code-fenced) → after
stripping it left a lone quote/backtick that XTTS **read aloud for ~15 s** (`total=15719ms` for
nothing) → `has_speakable_content()` now skips synth/post of a content-less answer (the dice button
still posts); (2) `_sanitize` now strips **code-fence backticks** like markdown `*`; (3) the model
appended a `<<TEST>>` on **every** turn incl. the post-roll consequence narration → a **dice loop**
(attack→roll→narrate+marker→roll→…) → inline markers are now **suppressed on results-only turns**
(`_last_action is None`), so a consequence narration can't request a new roll (**D42**). _Still open
(persona/adherence, nemo's ceiling):_ on one turn the model spoke a **meta-ramble** („Nein, tut mir
leid, ich habe mich versprochen. Als Spielleitung beschreibe ich nicht direkt die Szene…") — hard to
catch generically, watch it. Also: characters weren't registered (`für Mortn` → raw d100, „kein
hinterlegter Wert"). Suite **136→142** green (+6).

**Latency & crash-resilience — streaming pipeline + concurrent roll-router + history autosave
(2026-06-10).** Cross-cutting work between Phase 9 and 10, three flag-gated features, suite
**113→136** green (+23 tests). Nothing live-tested at commit time (the run above is the first proof).
- **Streaming pipeline (D39 → ADR 017, `DM_STREAMING=1`).** The DM turn now streams: `OllamaClient.chat_stream()`
  yields deltas; a pure `StreamAssembler` cuts complete sentences under three hold-back rules
  (first-chunk hold for the leading meta-preamble; hold back the latest sentence for the trailing
  strips; withhold from an unmatched `<<` / a mid-text speaker label); the cog synthesises + plays
  each sentence via a producer→synth→play pipeline (synth N+1 while N plays) over the blocking
  `/speak`. **History parity is by construction:** the batch chain is factored into one
  `finalize_answer(raw, labels, profile)` that both paths call, and `StreamAssembler.finish()`
  recomputes it on the accumulated raw — stored == spoken == the non-streaming result. `_sanitize`
  split into `_sanitize_leading` (incremental) + `_sanitize_trailing` (held tail). Layer-2 mute spans
  the whole answer; pause/Esc stops cleanly without replay; a mid-stream httpx error keeps what was
  spoken + notes history `… [Antwort unterbrochen]`. `[latency]` gained `first_audio=…ms` + a `stream`
  marker (tts/wav/bridge summed). `!redo` has its own streaming path. `DM_STREAMING=0` = byte-identical
  old single-WAV path; streaming only engages with a TTS backend.
- **Roll-router concurrent with playback (D40, no ADR — supersedes ADR 014's *timing* only).** The
  ADR-014 classifier now fires at **generation-end** and posts the 🎲 button **concurrently with
  playback** (`_deliver_answer` / `_deliver_streaming` run `_speak`/playback and `_handle_dice` as
  parallel tasks), so the button appears while the DM still speaks instead of after the whole turn.
  Single-GPU Ollama serialises, so firing at turn-start would just queue the classifier behind the
  narration — gen-end is the earliest point that doesn't delay it. Inline `<<TEST>>` marker still wins
  the dedupe (new pure `should_post_router(router_on, marker_posted)`).
- **Per-turn history autosave (D41, no ADR — extends ADR 015's artifact set, `DM_AUTOSAVE=1`).** New
  `dmbot/memory/history.py`: `append_turn`/`load_recent`/`rotate` over append-only
  `data/sessions/<id>/history.jsonl` (`{ts, user_msg, answer, redo}`; a `redo` record replaces the
  prior turn; corrupt tail tolerated). The cog appends after every turn (`asyncio.to_thread`, never
  blocks the loop), restores the last `max_history_turns` into an **empty** `DMBrain` history on
  `!join` (`restore_history`; `_last_turn` not restored → `!redo` unavailable for the restored last
  turn, documented), and rotates to `history.<timestamp>.jsonl` on `!leave`. Code-owned like
  `state.json`; the read-only `characters.json` split (ADR 015) is unchanged.
- **Tests (+23):** `tests/test_streaming.py` (assembler hold-back rules: meta-preamble in chunk 1,
  trailing "Was tut ihr?" split across deltas, `<<TEST` split across a boundary, stop-label mid-stream,
  num_predict mid-sentence cut, history parity vs the batch chain; `_parse_stream_line`;
  `respond_streaming`/`redo_streaming` history + spoken-equals-stored + mid-stream-error degrade),
  `tests/test_history_autosave.py` (append→load round-trip, redo-replaces, cap, corrupt line, rotate,
  restore-into-empty/noop-when-nonempty), `tests/test_roll_router.py` (+`should_post_router` dedupe).
  Flags documented in `.env.example`; architecture.md §4/§6/§7/§9 updated.

**Playtest-tuning round — stop the DM puppeting the party + cut runaway length + TTS punctuation
(2026-06-10).** Tobi pasted three live logs (one 06-09 box, two from one continued 06-10 session —
**all pre-change**). The dominant, repeatedly-voiced failure: the DM **spoke and acted for the
player characters** — scripting `Pr0degie: …` / `Seskin: …` / `Als Spielleitung beschreibe ich: …`
for the whole party (players: *"hat noch nicht gerafft, dass es mehrere Spieler gibt"*; one dictated
a corrected persona aloud). The `[latency]` lines (D35) showed **this puppeting IS the latency**:
scripted turns hit 700+ chars → `wav=55–80 s`, `total` up to **183 s** (each spoken char ≈ 0.1 s of
XTTS audio Bot A's blocking `/speak` waits through); clean short turns ran ~15 s. Fixes (→ **ADR
016**; commits `17adcfe` / `dc33d64` / `f36b5de` / `4564ecb`):
- **Persona + alias hint reframed** — positive top-of-file scoping (only NSCs/enemies/environment,
  never speak/think/act for the PCs, *multiple* players); the alias hint turned from a neutral cast
  list into a hard "these figures belong to the players" boundary placed **last** (recency).
- **Deterministic speaker-label backstop (the real fix; the persona alone never held nemo across 3
  sessions):** `CharacterStore.speaker_labels()` → `DMBrain.set_known_speakers` (wired on join) →
  every character + player name joins the turn's speakers as `_cut_at_labels` cut-points + Ollama
  stop sequences, so an appended `Seskin:`/`Pr0degie:` script is truncated **even when those names
  didn't speak this turn**. Kills the puppet display **and** the runaway length together.
- **Length cap:** `num_predict` 220→160 + persona "zwei bis drei kurze Sätze, die Gruppe wartet".
- **W6 TTS normalization:** `normalize_for_tts()` (XTTS + Piper synth, **not** the Discord post)
  drops quotes/brackets/symbols, maps ellipsis + em/en dashes to a pause, keeps `. , ! ? ; :` +
  word hyphens; also fixed XTTS's single-chunk branch synthesising the **raw** text.
- **`!npc add`** tolerant parsing (the `armour` `BadArgument` that blocked the gate) + a `_sanitize`
  strip for a "…als Sprachmodell … Hier ist die korrekte Antwort:" self-correction frame.
- **Wishlist compiled (W1–W9, now-vs-later):** W1 (puppeting) + **W3 (stop button — Tobi built it
  himself)** + W6 done (W1/W6 unverified live); W7 = the Phase-9 gate; deep latency **W2 = Part-2
  streaming TTS** (roadmap); W4 (within-session repetition) / W5 (answer the exact question asked) /
  W8 (engage provocative content) = persona/adherence, re-assess after the live check. **Suite
  113/113.** _All four commits are **live-unverified** — every log was pre-change; the next run is
  the proof._

**Per-turn latency instrumentation — logging only, baseline groundwork (2026-06-10).** Before any
streaming/latency work touches the pipeline, threaded a per-turn timing record (`_TurnTiming`,
`voice/commands.py`) through the DM turn flow and emit **one `[latency]` INFO line per turn** (console
+ `debug.log`), e.g.
`[latency] turn=42 auto stt=480ms wait=900ms trigger→llm_done=6200ms ctx=3100/8192 gen=180 chars=412 tts=3100ms wav=8.2s bridge_wait=4900ms total=14700ms`.
- **Stages** (all `time.monotonic`, carried in the existing flow — no new threads/globals): **stt**
  (reuses the Transcriber's `transcribe_ms` of the last DM-routed utterance — not re-measured),
  **trigger→llm_done** (turn start → Ollama returned, with the autosend `wait_idle` portion broken
  out as `wait=`), **tts** (synth → WAV), **bridge_wait** (`/speak` POST → return), **total**
  (trigger → `/speak` returned), plus the answer's `chars=` and the WAV's `wav=…s`.
- **Ollama token counts** (`prompt_eval_count`/`eval_count`, previously discarded) are now kept on
  `OllamaClient.last_stats` (the chat return type is **unchanged** for existing callers) → surfaced
  as `ctx=<prompt>/<num_ctx> gen=<eval>`, which shows for free whether the growing system prompt
  (persona + recap + state block + 20-turn history) is nearing the `num_ctx: 8192` cap. The brain
  copies them to `DMBrain.last_llm_stats` only on the **narration** call, so the roll-router /
  summarize calls can't clobber the turn's numbers.
- **Once per turn:** the line is emitted in `_deliver_answer`, the shared funnel for all four
  triggers (`!dm`, `!redo`, autosend, dice-result feedback); `!say` (TTS smoke test) deliberately
  produces none. Speech-less turns (typed `!dm`, redo, dice-feedback) log `stt=—`; text-only turns
  (TTS off) log `tts=—`/`bridge_wait=—`. The existing `⏱ LLM` line is unchanged (its value now
  derived from the record). **Zero behavior change, no new deps; suite 102/102 green** (D35, no ADR).
- **Context-budget warning + a test (same day, D36).** Building on those token counts: the per-turn
  record now also emits a **WARNING** — `[ctx] prompt N/8192 tokens (>85% of num_ctx) …` — when a
  narration prompt fills >85% of `num_ctx`, the early smoke signal *before* Ollama truncates the
  prompt **head** (the persona leads the system prompt — the worst part to silently lose). Narration
  turns only (only those build a `_TurnTiming`; the roll-router / recap calls are exempt), via a pure
  `_TurnTiming.ctx_over_budget()` predicate beside the `ctx=` display. New `tests/test_context_budget.py`
  fakes the `/api/chat` response and asserts the client's meta extraction (counts + default/overridden
  `num_ctx`, `chat()` return type unchanged) and the 85% boundary. **Suite now 107/107 green.**
- _Tobi: run one live session and paste a few `[latency]` lines → that's the baseline before the
  streaming work starts. A `[ctx] … >85%` WARNING in the same paste means the prompt is near the cap
  (trim history/recap/state)._

**Phase 9 built — memory: world state, deterministic advancement, recaps, auto-combat damage (2026-06-09).**
Read ADR 004 + the §7 schema + the wiring points first, then asked Tobi the two shaping decisions →
**split** state-file model + **auto-combat-damage** now (→ **ADR 015**). Built end to end:
- **`dmbot/memory/state.py`** — `WorldState` (+ `Combatant`/`Quest`), pure deterministic advancement
  (`apply_damage` clamps at 0 + sets `kampfunfähig`; `heal` clamps at max + clears it; NPCs, quests,
  location), **atomic** save/load (temp + `os.replace`), `seed_from_store` (once-only sheet → state),
  and `world_state_summary_de` (compact structured prompt block).
- **Engine combat math** — `resolve_damage` (weapon + SL − soak, never < 0) + `describe_damage_de`;
  **profile `combat` block** (attack_skills, weapons table, default_damage, soak source) + accessors,
  so it's system-agnostic. IM profile gained the block (weapon damage = approximate Core-Rulebook).
- **Recap** — `dmbot/memory/recap.py` (German summariser prompt + history renderer) + `DMBrain.summarize`;
  `DMBrain.set_context` injects recap + state into the system prompt in the CLAUDE.md order; `reset` clears it.
- **Cog wiring** — `!join` loads/seeds state + injects recap (and shows "📜 Was bisher geschah"); the
  dice-roll callback runs the **auto-combat** flow on an attack hit (weapon pick → target dropdown
  `discord_ui/target.py` → soak → apply → persist → narrate); new commands `!damage`/`!heal`/`!npc`/
  `!wrap`(`wrapup`); `!leave` persists the final state. State saved on every change.
- **Tests** — `tests/test_memory_state.py` + `test_memory_recap.py` (seed, clamp/down/heal, save→load
  round-trip = the gate's code half, summary, engine damage math, profile accessors, recap + injection).
  **Suite 102/102 green.** All changed modules import clean. _Live gate (HP survives restart; recap on
  next session) pending Tobi._
- **Logging trimmed for token-light pastes (D34, same day).** Dropped the redundant logger name on
  INFO console/mirror lines (the curated console only shows `dmbot.*` anyway), and stripped the common
  `dmbot.` prefix on WARNING/ERROR + in `debug.log` (`dmbot.voice.commands` → `voice.commands`) via a
  `_short_name` helper + a new `_DebugFormatter`; third-party names (httpx, faster_whisper, discord.*)
  kept intact. `ERROR`/`WARNING` levels + colour + tracebacks unchanged — only the noise around them
  shrank. _Tobi sets `DM_LOG_FILE=1` + `DM_TRANSCRIPT_FILE=1` (both already on in `.env`) before the
  live test, then pastes `debug.log` / `transcript.log` for the playtest-tuning round._

**Ops/UX polish during the Phase-8 live test (2026-06-08).** Tobi started the Phase-8 gate; the dice
math verified perfectly live (5 rolls, targets/SL/auto-bands/doubles-crit all correct against the
example party), but every post-roll narration failed with `httpx.ConnectError` — **Ollama simply
wasn't running** (not a bug; an external process). Built around that + two requested features:
- **Ollama can't silently be down anymore.** `start_dmbot.bat` now warms a **local** Ollama before
  launch (`ollama list` boots the daemon, `ollama run <model>` loads it — skipped for a remote
  `OLLAMA_HOST`), and a new boot **preflight** (`dmbot/llm/preflight.py`, wired in `__main__`) pings
  the host + checks the model is pulled, logging a clear error instead of a mid-game traceback.
- **Two-stage Ctrl+C** (`__main__._install_sigint_guard`): first press prints `Quit?` and keeps
  running, second prints `Shutting down …` and raises `KeyboardInterrupt` so discord.py's `run()`
  tears down cleanly (verified discord.py 2.7.1 installs no SIGINT handler of its own).
- **Pause control (D27 / ADR 013):** one shared `_paused` freeze, driven by **Esc in the terminal**
  (Variante A, animated `rich` box) **and** a **Discord ⏸ button** (Variante C, status embed). Pause
  mutes the VAD/STT pipeline + blocks all DM turns; resume reverses both. New dep `rich`. New
  `discord_ui/pause.py`, `!pausebutton`, `paused=` in `!vstatus`.
- **`!rules` / `!regeln`:** paged (◀/▶) Discord embed of the **active system's essentials**, derived
  from the profile (`rules/summary.py` + `discord_ui/rules.py`) so it stays system-agnostic — how a
  test works, the difficulty ladder, SL/auto-bands/crit, damage. Localised the IM profile's `damage`
  field to German (free-text, display-only).
- **Cosmetic:** dropped the double `🎲 🎲` in the dice log line (`commands.py`).
- **Suite 74/74** (new: `test_llm_preflight`, `test_shutdown`, `test_pause`, `test_rules_summary`).

**Then — Phase-8 live test → the marker problem → the roll-detection router (2026-06-08, same day).**
The live run worked for dice (`!test`), turn order and the voice loop, but the LLM **wasn't emitting
the `<<TEST>>` marker** — it self-resolved actions in prose. Diagnosed from `debug.log` (added a raw-LLM
`🪵` line, debug-only). First sharpened the persona (don't self-resolve, emit the marker + example),
stripped the repetitive trailing "Was tut ihr?" closer, and fixed a stray "So:" preamble leftover.
Then a **gemma3:12b vs nemo** taste test: gemma3 narrates cleaner (no meta-ramble/English-leak/tic) but
its markers were **no** better (still self-resolves), and nemo's tone is preferred → **kept nemo**.
**Researched it** (Tobi pushed back on "model-limited"): it's a *documented, model-size-independent*
LLM-GM failure; the fix is a separate roll step, not a bigger model — and an **experiment confirmed it**
(nemo 8/8 as a separate constrained-JSON classifier). Built the **roll-detection router** (D29 / ADR
014): after narration, a stateless constrained-JSON call classifies the action → posts the dice button;
inline marker kept as fallback; **now the default**. Tobi live-confirmed: "funktioniert jetzt besser" →
**Phase 8 flipped to ✅**. Also: split file logging into `terminal.log` (console mirror) + `debug.log`
(heartbeat-collapsed, pasteable). Research written up in `docs/research-notes.md`. **Suite 81/81.**

**Phase 8 built — dice engine, IM profile, marker flow, turn-order buttons (2026-06-07).** The whole
deterministic core, decoupled from the LLM (golden rule #2). New `dmbot/rules/`: `profile.py` (load +
validate `data/systems/<system>.json`, difficulty-ladder lookup), `engine.py` (seeded-RNG dice parser
+ `resolve_test` via a resolver registry — IM `roll_under` first; SL = tens-difference, crit/fumble on
doubles, 01–05 / 96–00 auto-bands; `describe_result_de`), `characters.py` (lean character JSON store +
alias map + pure `resolve_target`: skill value + difficulty → target, all in code), `marker.py`
(tolerant `<<TEST …>>` parser, strips markers, fallback to a manual button). First profile
`data/systems/imperium_maledictum.json` (1d100 roll-under, ladder, auto-bands) + an example party
`data/sessions/_example/characters.json`. **The IM numbers were then verified against the bought Core
Rulebook** (converted via the new `tools/pdf_to_md.py`): the Difficulty Table (Very Easy +60 … Very
Hard −30), SL = tens-difference, 01–05/96–00 auto-bands as Marginal (engine now sets SL 0 + no
crit/fumble on an auto result), crit/fumble-on-doubles is IM's combat rule, damage = weapon + SL (the
inherited d10/d5 guess was wrong — corrected). Two new
Discord views (`discord_ui/dice.py` + `turnorder.py`) on the `mic.py` View→cog pattern, new commands
`!roll`/`!test`/`!turn`, `DM_SYSTEM` env. Orchestrator extended: it extracts markers (before the
sentence-trim, which would otherwise eat a trailing marker), surfaces pending tests, feeds rolled
results back into the next turn, and appends a who-plays-whom alias hint to the prompt (fixes F). The
players' contract (K) is realised: the GM rolls **for** the player and the difficulty number comes from
the profile, never the LLM. **Decisions D26 → ADR 012.** **Suite 63/63 green** (34 new tests). _Live
Discord gate (dice button, turn rotation) pending Tobi._

**(Earlier) Phase 7 (feedback layer 2) implemented + a music-bot bridge race fixed (2026-06-05, later).**
- **Bridge race (music-bot repo, own commit `82393da`).** A `!dm` turn ran fully (STT→LLM→TTS) but
  Bot A returned `HTTP 500 'playback failed'` (`ClientException: Already playing audio.`). Root
  cause: the music cog's `after_playing` auto-advances the queue on **any** track end — including
  the bridge's own `vc.stop()` — so two `play()` owners fought over the voice client. Fix: a shared
  `bot.dm_speaking` flag — `dm_bridge._play_file` sets it (finally-cleared) around playback, and
  `music.play_next` bails while it's set (at the top + again right before `vc.play()`, re-queuing the
  popped track). Diagnosis came straight from `logs/dmbot.log` (now opt-in `DM_LOG_FILE=1`) + the
  music bot's `bot.log`. _Tobi must restart the music bot to load it._
- **Phase 7 — turn-taking & feedback protection layer 2 (this repo).** `VadSink.mute()/unmute()`
  pause the whole segmentation pipeline while Bot A speaks; `voice/commands._speak` mutes around the
  blocking `/speak` and unmutes in `finally`. `mute()` flushes open utterances so pre-DM speech is
  buffered, not glued across the gap. `!leave` now resets per-channel session state
  (`DMBrain.reset` + sink/counters). New `tests/test_feedback_layer2.py`. _(No new ADR — this
  implements ADR 003's existing layer-2 mandate, no fresh trade-off.)_ **Live-tested by Tobi: layer 2
  works (no feedback).**
- **Playability tuning — players' input now drives the narration more (Phase-5 open tuning).** Live
  play showed nemo drifting: it set atmosphere and continued its own thread instead of resolving the
  stated action, and opened every turn with a "Als Spielleitung beschreibe ich:" preamble. Two
  levers (Tobi picked both): (1) **persona sharpened** — new top section "Worauf du reagierst"
  makes resolving the latest action the primary directive + forbids the preamble; (2) **buffer
  noise cut** — `DMBrain` now forwards only the most recent `DM_MAX_LINES` (default 8) so table
  talk between !dm presses doesn't drown the action. Plus `_sanitize` strips the preamble as a net.
  _Still open: the nemo-vs-gemma3:12b taste test._
- **First live session → the criticism-driven fixes (D24/ADR 011).** Read `logs/dmbot.log` of a real
  4-player run. Findings + fixes: **(1) STT ~1.5 min behind** (unbounded queue + CPU whisper + all
  table talk) → **GPU whisper** + **push-to-talk button** so only DM-directed speech is transcribed;
  **(2) the DM answered AS a player** ("SezBoss69: …") → `_strip_leading_label` (the `\n<label>:` stop
  misses a leading label; `_cut_at_labels` skips position 0); **(3) preamble** → sanitized.
- **Second live session → playability polish (the players' requests).** Push-to-talk + GPU whisper
  confirmed working live (`→DM` markers, ~100–1000 ms transcribe). Five fixes from their feedback:
  **(1)** persona forbids the read-aloud meta-disclaimer + `_sanitize` strips a trailing meta
  parenthetical ("(Bitte beachte…)"); **(2)** new persona section: NPCs in **third person**, no
  "Tech-Priester:" script, never address a player AS the NPC; **(3)** vary the closing hook (not
  always "Was tut ihr?"); **(4)** the mic button is **re-posted to the bottom** after each DM turn
  (`_post_mic_button`, delete+resend) so it stops scrolling away; **(5)** a clean **session
  transcript** `logs/transcript.log` (`DM_TRANSCRIPT_FILE=1`) — just the conversation (player lines
  incl. table talk + DM answers) with timestamps, separate from the debug log. Suite **22/22**.
  _Live-tested: layer 2 + push-to-talk + GPU whisper work; the persona/UI polish is NOT yet live-tested._
- **Feedback layer 2 → opt-in, off by default (D25).** Tobi wanted the table to keep being
  transcribed *while the DM speaks* (full record). Layer 1 (Bot-A user-ID filter) already blocks
  self-transcription and the routing gate keeps narration table talk out of the DM, so the VAD pause
  was redundant. Now `DM_PAUSE_VAD_WHILE_SPEAKING=0` by default; mechanism kept for mic-bleed cases.
  `architecture.md` §5 updated; golden rule #4 (layer 1) unchanged.
- **Third live session → more persona/quality fixes.** From the transcript: **(A)** the
  "Als Spielleitung beschreibe ich …" preamble was *still* there — my `_META_PREAMBLE` only matched
  the colon form; rewrote it to strip the colon-less shapes too ("… beschreibe ich die Szene, wie …",
  "… eine dunkle Gasse …") and re-capitalise. **(B)** persona: the DM is **not** in the party — say
  "ihr/euch", never "wir/uns/ich" inside the scene (it kept writing "auf uns zu", "sehen wir").
  **(C)** ask "Was tut ihr?" only when something open is presented, never every turn, never with
  action suggestions. **(D)** no content warnings / lectures / setting commentary (turn 1 produced an
  LGBTQ disclaimer). **(E)** new **`!redo`/`!r`** — re-run the last DM turn with the same input
  (DMBrain.redo, replaces the last history pair) for when the DM misunderstood. Suite **25/25**.
  _Open (F): player→character name mapping_ — the LLM confuses "SezBoss69" vs the character "Seskin"
  and mixes up who did what. Belongs to character registration (D13/ADR 003, Phase 8); a light alias
  map could help sooner.
- **Fourth live session → audio bug + more persona.** **(J)** real bug: XTTS truncates a single
  chunk >253 chars for German (the "bricht mitten im Satz ab" reports) — the wrapper now splits a
  long answer into <240-char chunks (`tts/textsplit.py`, unit-tested) and concatenates the WAVs.
  Persona: **(G)** attribute each action to the *named* player when several acted, not a vague
  "du/dein"; **(H)** don't auto-advance — answer the immediate thing (esp. a perception question),
  NPCs wait until the group reacts; **(I)** engage with *every* player action incl. provocative
  ones, don't dodge/sanitise (model-dependent). Suite **29/29**.
  _Open (K) — Phase-8 dice design input from the players:_ a real GM rolls **for** the player
  ("ich würfle für Tobi auf Spurenlesen, Wert 6, Ziel 12 — nicht geschafft"); skill-check
  **difficulty** must come from the system profile / rulebook, the LLM can't balance it on the fly.
  Confirms "dice = code" (golden rule #2) — fold into ADR 005 / the engine when building Phase 8.
- **Fifth live session → mic-button auto-send (L) + polish.** Persona fixes confirmed working
  (clean answers, no preamble, good POV, NSCs in 3rd person — players: "beste Story die wir je
  hatten"). Built their most-repeated request: **releasing the mic button now auto-runs the DM
  turn** (`DM_BUTTON_AUTOSEND=1`) — no separate `!dm` — and it **waits for the just-said utterances
  to finish transcribing** first (new `Transcriber.wait_idle`), fixing the "it answered in the next
  message instead" race. **(M)** persona balance: lead the scene actively (introduce NSCs/events that
  follow from the group's actions) without railroading — counterweight to the "don't auto-advance"
  rule. **(N)** transient Discord `503` on send (seen mid-session) now retried once (`_send_with_retry`).
  Suite **29/29**.

**(Earlier same day) GPU XTTS via CUDA torch + portable per-machine GPU profiles (non-Phase work, ADR 009).** The
GPU rebalance (whisper→CPU, XTTS→cuda) crashed at first: the venv's torch was the **CPU-only**
build, so `TTS_DEVICE=cuda` raised `Torch not compiled with CUDA enabled` and left the DM mute.
Fixed end to end:

- **CUDA torch:** `torch`/`torchaudio`/`torchcodec` now pulled from the PyTorch **cu130** index
  (CUDA 13.0; `[tool.uv.sources]` + `[[tool.uv.index]]`). Verified live: `torch 2.12.0+cu130`,
  `cuda available: True`, XTTS `loaded on cuda`, RTF **0.34** (≈3× realtime; CPU was ~1.9).
  _(Started on cu126, but that tops out at sm_90 and failed on a colleague's **RTX 5080**
  (Blackwell, sm_120) — moved to cu130, which covers Ada (4070) + Blackwell (5080); re-verified
  on the 4070.)_ Then GPU whisper on the 5080 died at `encode()` with **`cublas64_12.dll cannot
  be loaded`**: `nvidia-cuda-runtime-cu12` (cudart64_12.dll, a cuBLAS dependency) was missing.
  Added it as a win32 dep. **But that alone still failed on the 5080** — root cause: `os.add_dll_directory`
  is not enough, CTranslate2's loader doesn't reliably search the added user dirs, so it only worked
  on the 4070 because that box has a **system CUDA toolkit (v12.3) on PATH**; the fresh 5080 box has
  none. Fix: `transcriber._register_cuda_dll_dirs` now **preloads the CUDA-12 DLLs by full path**
  (`ctypes.WinDLL`, in dep order cudart→cublasLt→cublas→cudnn). **Verified on the 4070 with the system
  CUDA stripped from PATH** (simulating the 5080) — GPU whisper runs. Lesson: ctranslate2's CUDA-12
  trio (cublas + cudnn + **cudart**) must be self-complete *and explicitly preloaded*, independent of
  torch's CUDA version and of any system CUDA install. **Result: the 5080 runs everything on GPU**
  (XTTS cuda + whisper cuda), full voice receive + transcription confirmed by the colleague.
- **Log noise tamed:** voice-recv's benign `Error unpacking packet` RTP-parse flood (alpha lib,
  drops the odd packet, audio keeps flowing) is now throttled in `logsetup.py` — first occurrence
  logged, then a running count every 500th, tracebacks suppressed (console + file).
- **Diagnostic tool:** `tools/diag_stt.py` — one-shot CUDA/STT check (commit, wheels, DLL preload,
  torch GPU, a real cuda transcription) for debugging a fresh box remotely.
- **Resolver fix:** CUDA torch pins `nvidia-cudnn-cu12==9.10.2.21` on linux, clashing with
  faster-whisper's `>=9.23`. Resolved by locking **win32-only** (`environments = ["sys_platform
  == 'win32'"]`, legit per D16) + `requires-python` pinned to the 3.12 line + win32 markers on
  the cudnn/cublas wheels. Lock is now Windows-only.
- **Robust device:** `dmbot/tts/xtts.py` `_resolve_device` + load-time fallback → XTTS degrades to
  CPU (warns, never crashes) when CUDA is absent or the GPU OOMs. Same `.env` is portable.
- **httpx bug:** found `httpx` was an **undeclared direct dep** (used by `llm/client.py` +
  `bridge.py`); the dep churn dropped it. Now declared `httpx>=0.28.1`.
- **Profiles + docs:** `.env` = 4070 dev profile; `.env.example` documents both (4070 dev / 5080
  full-GPU); `architecture.md` §3 updated; **ADR 009** written; README gained a "Running on
  another machine" section; `docs/SETUP.md` token-var line corrected (`DISCORD_TOKEN_DMBOT`, Bot A
  token lives in the music bot repo). Voice-stack smoke test re-run after the dep change: **5/5**.

**Then (same session) — playability + ops polish:**
- **XTTS is now the default engine** (Piper = fallback); D21 flipped once XTTS ran on GPU.
- **Answer length capped** (`DM_NUM_PREDICT`, env, default 220) + sentence-trim on a cut turn +
  persona tightened ("2–4 Sätze, keine Monologe") — XTTS-GPU made monologues the latency, not TTS.
- **Prompt shutdown:** transcriber `stop()` drops its backlog + short join (daemon), run off the
  loop in `cog_unload` → one Ctrl+C, no "heartbeat blocked" hang.
- **Bridge debuggability:** `!say` reports playback failure instead of a false 🔊; `bridge.speak`
  surfaces the bridge's real reason (401/404/409/unreachable). This pinned the colleague's issue to
  Bot A not reachable / not in voice (not a WAV/path bug).
- **Network bridge (ADR 010, D23):** hybrid `/speak` — loopback sends the WAV *path* (unchanged),
  remote sends the WAV *bytes* + shared secret (`DM_BRIDGE_SECRET`) over Tailscale; Bot A plays its
  own copy. **Both repos changed** (DMbot + the music bot's `cogs/dm_bridge.py`, its own commit).
  Localhost path mode verified unchanged; the remote/Tailscale path is **implemented but not yet
  live-tested** (they run both bots on one machine for now). Split-hosting documented in the README.
- **Lean logging:** console shows only `dmbot.*` lines + WARN/ERROR (timestamps kept); the
  full file log `logs/dmbot.log` is **off by default**, opt-in via `DM_LOG_FILE=1`; the benign
  voice-recv unpack notice is kept off the console (file-only).

_(Prior session — voice-stack hardening, ADR 006 — and Phases 3–6 (the playable loop) are captured
in ADR 006 and each phase's VERIFY EVIDENCE below.)_

---

## Phase status — abgeschlossene Phasen (volle Details)

### ✅ Phase 0 — Foundation & setup
- [x] Repo + project structure (skeleton per `architecture.md` §12; uv/Python-3.12, `.gitignore`, `.env.example`)
- [x] Discord DMbot app + token (in `.env`). _(Bot A token already exists in the music bot repo.)_
- [x] Ollama installed locally on the 4070 + models pulled (`mistral-nemo`, `nomic-embed-text`) + reachable
- [x] Model taste test → primary model chosen: **mistral-nemo**
- **Manual setup (outside the agent): see `SETUP.md`.**
- **Gate:** `curl` to Ollama from Tobi's machine → German answer.
- **VERIFY EVIDENCE:** Gate met 2026-06-04 — `curl http://localhost:11434/api/generate` with
  `mistral-nemo` returned a plausible grimdark German answer ("Die Finsternis hat sich über die
  Welt gelegt wie ein Grabtuch aus Eisen…"). Tooling: git 2.42, Python 3.12.10, uv 0.11.19,
  Ollama 0.30.4 on `:11434`, models `mistral-nemo` + `nomic-embed-text` pulled, NVIDIA 596.49
  (RTX 4070). Discord DMbot created, token in `.env`. **Primary model: `mistral-nemo`**, chosen
  via taste test (scene description + NSC dialogue) over gemma3:12b / qwen3.5:9b / glm-4.7-flash
  (glm 19 GB doesn't fit 12 GB; nemo gave the most idiomatic German + dialogue). Deferred to
  later phases (flagged, not blocking): cuDNN/cuBLAS DLLs (B3→Phase 4), Piper voice (B5→Phase 6),
  Opus DLL + mic (B6→Phase 2), rulebook/adventure PDFs (B7→Phase 10).

### ✅ Phase 1 — Bridge: Bot A `/speak`  (Bot A side done, out of order)
- [x] `POST /speak` (aiohttp) in the music bot
- [x] `/speak` blocks until playback ends (return = resume signal)
- [x] `/health` + `!dm` status command; localhost only; serialized by lock; music stopped first
- **Gate:** `curl -X POST .../speak` with a test WAV → audible.
- **VERIFY EVIDENCE:** Implemented & code-reviewed — `Pr0degie/musicbot` branch
  `dungeon_master`, commit `249cc38`. Contract in `architecture.md` §3. Music cogs untouched.
  **Gate met 2026-06-04:** `GET /health` → `{"status":"ok","bot":"EarRape#8961"}`;
  `curl -X POST :8765/speak` with a 2 s test WAV (both bots in voice channel `circlejerk`) →
  `HTTP 200 {"status":"played"}`, the call **blocked 2.09 s** (= the WAV's full length,
  confirming the blocking-return contract D15), and Tobi confirmed the tone was **audible**.

### ✅ Phase 2 — DMbot scaffold: voice receive
- [x] Voice join + `discord-ext-voice-recv` sink (`!join`/`!j`/`!leave`/`!vstatus`)
- [x] per-user PCM log (decoded 48 kHz stereo s16le; heartbeat every 2 s)
- [x] Bot A's user-ID filtered (protection layer 1) — explicit `BOT_A_USER_ID` + `.bot` flag
- [x] Windows: Opus loaded via discord.py's bundled DLL (B6 satisfied, no manual install)
- [x] _(unforeseen)_ DAVE/E2EE layer decrypted on receive → clean Opus (ADR 006)
- **Gate:** PCM frames in the log; Bot A's own voice absent.
- **VERIFY EVIDENCE:** Gate met 2026-06-04. Live test in voice channel `circlejerk`: two human
  speakers (`Pr0degie`, `Timo`) logged with `▶ receiving audio` + `PCM ⟳` heartbeats; **Bot A
  ("EarRape", id 1361375360784273409) filtered** — `layer-1: filtering out …`, never tallied.
  After wiring the DAVE/E2EE decrypt (ADR 006): consistent Opus TOC `0x78…`, **~100 % decode,
  0 dropped**; a captured WAV analysed as real speech (ZCR 0.061, 13 % silent frames). Stack:
  `discord.py 2.7.1`, `discord-ext-voice-recv 0.5.2a179`, `davey 0.1.4`, Opus bundled DLL.
  Remaining `lost being flushed` jitter (sender voice-activation) is benign, quieted in logs.

### ✅ Phase 3 — VAD segmentation
- [x] Resample 48k/stereo → 16k/mono (`voice/resample.py`, `soxr.ResampleStream` per user)
- [x] silero-vad → cut utterances (`voice/vad.py`; onnx via onnxruntime, ADR 007; wired as `VadSink`)
- [x] **Live gate met** — clean per-speaker utterances; Tobi confirmed the WAVs sound right
- **Gate:** one sentence = one utterance, start/end correct.
- **VERIFY EVIDENCE:** _Offline (2026-06-04):_ resample ratio ≈ 16000 samples/s; pure silence →
  **0 utterances** (no false trigger); `UtteranceSegmenter` state machine verified with a
  scripted fake model — clean utterance cut=1, sub-250 ms blip dropped, mid-sentence pause
  <600 ms not split, real >600 ms gap splits into 2, flush mid-speech emits. Stack:
  `onnxruntime 1.26.0`, `soxr 1.1.0`, `numpy 2.4.6`, vendored silero v5 onnx (~2 MB).
  _Live (2026-06-04):_ first live run surfaced **two bugs, both fixed + offline-reproduced:**
  (1) silero v5 needs a **64-sample context** prepended (576-sample input, not bare 512) — bare
  512 scored prob≈0 on clear speech (0/1874 frames), fixed → 1451/1874 voiced; (2) **voice
  activation** means clients send no RTP while silent, so utterances never closed — fixed by
  wrapping in `SilenceGeneratorSink` (injects silence; lock-guarded sink). After the fixes a
  live utterance + WAV was produced. _Final gate met (2026-06-04):_ clean run (bot start
  18:56:56) segmented **both** speakers per sentence — Pr0degie 9 utterances (0.99–5.06 s),
  Timo 4 (1.06–8.51 s), each dumped as a 16 kHz mono WAV; **Tobi listened to the WAVs and
  confirmed they sound clean/correct**. Utterances also close now while a speaker is silent
  (silence injection), so separate sentences no longer merge. Stack live: `discord.py 2.7.1`,
  `discord-ext-voice-recv 0.5.2a179`, `onnxruntime 1.26.0`, `soxr 1.1.0`.

### ✅ Phase 4 — STT (faster-whisper)
- [x] faster-whisper wrapper (`dmbot/stt/transcriber.py`): worker thread + queue (off the audio
      path), 16k mono s16le → German text via `WhisperModel`, CPU-int8 fallback
- [x] Windows cuDNN/cuBLAS: `os.add_dll_directory()` for the `nvidia-*-cu12` wheel `bin` dirs in
      `stt/transcriber.py` — no manual `PATH` (SETUP B3 done)
- [x] Wired into `VoiceReceiveCog`: `_on_utterance` → `transcriber.submit`; transcript logged
      as `📝 <name> | <clip>·<ms> | <text>`; model via `WHISPER_MODEL/DEVICE/COMPUTE` env
- [x] **`medium` is the default** (beat `small` clearly in the live German test)
- [x] Hallucination guard: drop segments with high `no_speech_prob` / low `avg_logprob`
      (kills the "Vielen Dank für's Zuhören" phantoms on short/quiet clips)
- **Gate:** German sentence transcribed correctly.
- **VERIFY EVIDENCE:** _Live (2026-06-04):_ a ~16-min two-speaker session transcribed German
  correctly throughout — long, complex, well-punctuated sentences (e.g. *"Nichtsdestotrotz steht
  mir der Christoph, Markos Vater im Wege."*; a 60-word run captured verbatim). Players confirmed
  in-channel: *"ihr habt's perfekt transkribiert"* + *"ging echt schnell"*. `medium` clearly beat
  `small` (small mis-heard the quieter speaker; medium got him). GPU: `faster-whisper 'medium'
  loaded on cuda (float16)` via in-code DLL registration; ~0.77 s to transcribe 8 s audio.
  Remaining: rare stock-phrase hallucinations on short/near-silent clips → now filtered by
  confidence. Stack: `faster-whisper 1.2.1`, `ctranslate2 4.7.2`, `nvidia-cudnn-cu12 9.23`.

### ✅ Phase 5 — LLM wiring + DM persona
- [x] Ollama client (`llm/client.py`, async httpx, `/api/chat`; host+model from config — ADR 002)
- [x] `prompts/dm_core_de.md` (generic GM persona, German) + `campaign_tone_de.md` (Eisenhorn overlay) — layered loader `llm/persona.py` (ADR 005)
- [x] `DMBrain` (`orchestrator.py`): per-channel history (in-memory) + lock-guarded player-line buffer
- [x] Wired: voice transcripts buffer per channel; `!dm` / `!dm <Text>` triggers a turn → answer logged `🎭` + posted to the text channel
- [x] Output hygiene for TTS: strip role labels/markdown; `stop` sequences + truncation so the model plays **one** DM turn and never fabricates player replies
- **Gate:** text prompt → German DM answer in the campaign's tone.
- **VERIFY EVIDENCE:** _Offline (2026-06-04), real Ollama + `mistral-nemo` + the real persona:_ a
  German player line ("Ich öffne die schwere Eisentür…") yields an atmospheric grimdark DM answer
  in Eisenhorn tone (flackernde Lumen, Rost/Weihrauch, ein Adept-NSC mit Stimme), addresses players
  by name, ends with "Was tut ihr?"; a follow-up turn correctly uses the history. After hardening:
  exactly one DM turn, no fabricated player lines, no "Spielleitung:"/markdown leakage.
  _Tuning (2026-06-05, after live play):_ nemo added a "Als Spielleitung beschreibe ich:" preamble
  and drifted off the players' actions → **mitigated** — persona sharpened (top "Worauf du
  reagierst" directive), buffer capped to the recent `DM_MAX_LINES`, `_sanitize` strips the
  preamble (`tests/test_orchestrator.py`). _Still open:_ the **nemo vs gemma3:12b** taste test with
  this persona, if the tone/responsiveness still needs more.

### ✅ Phase 6 — TTS + first full loop ⭐  (PLAYABLE)
- [x] Piper wrapper (`tts/piper.py`): `de_DE-thorsten-medium` → WAV in the OS temp dir
      (`tempfile.gettempdir()`, not `/tmp`); loaded once, synth off the event loop
- [x] Bridge client (`bridge.py`): async httpx `GET /health` + blocking `POST /speak`
      (architecture §3 contract); WAV deleted after playback so temp doesn't fill
- [x] Wired: `!dm` answer → Piper → `/speak` (spoken); `!say <Text>` smoke test; LLM + TTS
      times logged (`⏱`, `🔊`). Piper missing → text-only, bot still runs
- [x] **Live full loop confirmed** (2026-06-04, 21:37): `!dm` → German DM answer → spoken aloud,
      Tobi heard it; no self-hearing (layer-1 filters Bot A)
- **Gate:** speak → DM answers audibly; latency measured; no self-hearing.
- **VERIFY EVIDENCE:** Live full loop works end to end and is **audible** (player line → nemo →
  Piper → Bot A `/speak`). Piper: voice loads ~1.3 s, synth ~130–1250 ms (length-dependent).
  **Latency caveat (the Phase-6 tuning target):** `⏱ LLM = 15.2 s` on the first turn. Root cause
  is **VRAM pressure** — `ollama ps` shows nemo at **9.5 GB / 100% GPU with a 16384 context**, and
  total VRAM sat at **11.8/12.3 GB** (nemo + whisper-medium 2.5 GB + desktop apps), so nemo
  cold-loads/runs under near-full memory. _Mitigations applied in code:_ `num_ctx=8192` (smaller
  KV cache) + `keep_alive=30m` (no cold reload between turns). _Biggest remaining lever (Tobi):_
  run whisper on CPU or `small` to free ~2.5 GB, and/or offload Ollama to the 5080 via Tailscale
  (ADR 002). Bridge fix this session: Bot A had to be on the `dungeon_master` branch (the `main`
  branch has no DMBridge → "All connection attempts failed").

### ✅ Phase 7 — Turn-taking & feedback protection layer 2  (live-validated)
- [x] VAD pause while Bot A speaks — `VadSink.mute()/unmute()` (`voice/recv.py`); `_speak()` mutes
      around the **blocking** `/speak` and unmutes in `finally` (D15: blocking return = Bot A quiet).
      `mute()` flushes in-progress utterances first. **Now opt-in, off by default** (D25,
      `DM_PAUSE_VAD_WHILE_SPEAKING=0`): redundant beside layer 1 + the routing gate, and it blocked
      transcribing the table during narration — which players wanted recorded. Mechanism kept for
      mic-bleed cases. Layer 1 (Bot-A user-ID filter) stays mandatory (golden rule #4).
- [x] Session state per channel — cog keeps the `self._sink` handle (set on `!join`); `!leave`
      now `self._brain.reset(channel)` + drops the sink + clears the per-user counters, so a
      re-join starts a fresh session.
- [x] **Push-to-talk DM-routing gate (D24/ADR 011)** — a shared Discord mic button (`discord_ui/mic.py`,
      the project's first View). The whole table is **always transcribed + logged** (full record,
      Tobi wanted it — recap/memory groundwork); the button gates only **what reaches the DM**:
      utterances are tagged `for_dm` when cut (carried through the STT worker) and only those are
      buffered. `→DM` marks routed lines in the log. `!mic` re-posts; `DM_PUSH_TO_TALK=0` routes all.
- [x] **Latency + quality fixes from the first live session** — GPU whisper (`WHISPER_DEVICE=cuda`,
      D24); buffer capped to recent `DM_MAX_LINES` (default 8) so table talk doesn't drown the action;
      persona sharpened (action-resolution as the top directive); `_sanitize`/`_strip_leading_label`
      kill the "Als Spielleitung beschreibe ich:" preamble and a leaked leading "Name:" (the DM was
      answering **as** a player — `tests/test_orchestrator.py`).
- [x] **Unit tests** (deterministic parts): `tests/test_feedback_layer2.py` (mute + listen gate)
      + `tests/test_orchestrator.py` (sanitize, label strip, buffer cap). **20/20 green.**
- **Gate:** two people speak → orderly reaction, no feedback loop.
- **VERIFY EVIDENCE:** _Live, four real multi-player sessions (2026-06-05/06, 3 players: Timo,
  Sezgin/SezBoss69, Pr0degie)._ Confirmed in the transcripts: multiple speakers captured per-user;
  **push-to-talk routing works** — only button-window speech carries the `→DM` marker and reaches
  the DM, the rest is log-only (`push-to-talk → 🎙 an die Spielleitung` / `⏸ nur Protokoll`);
  **no feedback loop** — Bot A filtered every turn (`layer-1: filtering out EarRape`), the DM never
  re-transcribed its own voice; the DM answers the routed lines **in order**; players confirmed
  "transkribiert er unsre Zeug trotzdem noch" while the DM spoke (layer-2 opt-out working). GPU
  whisper kept up (~100–1000 ms/clip). Quality tuning (preamble, POV, no-advance, TTS chunking) was
  done from these transcripts and is in the unit suite (**29/29**) — but is **persona/model-limited**
  (nemo); residual drift is the gemma3 lever, not a Phase-7 gate failure.

### ✅ Phase 8 — Dice engine, system profile & turn-order buttons  (live-validated)
- [x] `rules/engine.py` — generic dice + resolution engine (profile-driven, seeded RNG) **+ unit tests**.
      Dice parser (`XdY±N`, `d5`), `resolve_test` via a resolver registry (IM `roll_under` first), SL =
      tens-difference, crit/fumble on doubles, 01–05 / 96–00 auto-bands, `describe_result_de` (the
      "🎲 Tobi auf Wahrnehmung … — Erfolg, 2 EG" line that feeds back into the prompt).
- [x] `data/systems/imperium_maledictum.json` — first hand-written profile (1d100 roll-under, SL =
      tens-difference) + the **difficulty ladder** (name → modifier) + aliases. Loader/validator
      `rules/profile.py`. **Numbers now VERIFIED against the IM Core Rulebook** (Difficulty Table p.188,
      Success Levels, Automatic Success/Failure) — ladder Very Easy +60 … Very Hard −30, auto-bands
      01–05/96–00 (Marginal → SL 0), crit/fumble-on-doubles noted as IM's combat rule, damage =
      weapon Damage + SL (not d10/d5). Done via `tools/pdf_to_md.py` on the bought PDF (2026-06-07).
- [x] `rules/characters.py` — lean character JSON store (schema follows the profile) + display-name→
      character **alias map** (fixes F) + pure `resolve_target` (skill value + difficulty → target, all
      in code). Example party `data/sessions/_example/characters.json` ships so it runs out of the box.
- [x] `rules/marker.py` — tolerant `<<TEST skill [difficulty|±N] [für name]>>` parser; strips markers
      from the spoken text; unparseable marker → generic manual button (ADR 004 fallback).
- [x] Text-channel views (`discord_ui/dice.py` + `turnorder.py`, the `mic.py` View→cog pattern):
      dice button rolls via the engine + narrates the consequence; turn-order rotates over the voice
      members. New commands `!roll` / `!test` / `!turn`(`!order`); `DM_SYSTEM` env.
- [x] LLM marker flow wired: persona documents the marker + difficulty words; orchestrator extracts
      tests (before the sentence-trim), posts a dice button per test, feeds the result back so the next
      DM turn narrates the outcome.
- [x] **Roll-detection router (D29 / ADR 014)** — the inline `<<TEST>>` proved unreliable live (the model
      self-resolves; only 2 good markers/session, model-size-independent per research). Added a separate,
      stateless **constrained-JSON classifier** (`llm/roll_router.py` + `DMBrain.classify_test`, skill enum
      = the character's sheet) that picks the test after narration and posts the button; the inline marker
      stays as fallback. Behind `DM_ROLL_ROUTER` (off by default, A/B). Verified: nemo **8/8** offline,
      full path smoke-tested end-to-end vs Ollama. _Live A/B pending Tobi (`DM_ROLL_ROUTER=1`)._
- [x] **Unit tests (deterministic core):** `tests/test_rules_engine.py`, `test_profile.py`,
      `test_marker.py`, `test_characters.py`. **Suite 63/63 green** (34 new + 29 existing).
- **Gate:** button roll correct (result + degrees for the profile); turn order rotates; tests green.
- **VERIFY EVIDENCE:** _Code + unit level (2026-06-07):_ the engine's correctness is unit-proven with a
  seeded RNG (success/fail boundaries, SL tens-difference, crit/fumble on doubles, auto-bands, the
  d100-as-"00" case) and the full marker→resolve→roll path verified end to end against the real IM
  profile + example party (`<<TEST Wahrnehmung Schwer für Tobi>>` → Mortn, Wahrnehmung 44 − Schwer 20 =
  target 24 → roll 42 → "Fehlschlag, 2 EG").
  _Live (Tobi, Discord, 2026-06-08):_ **(2a)** `!test … Schwer für Tobi` → the dice button posts and the
  result + degrees match the engine (verified live across several rolls, incl. the doubles-crit on 44);
  **(2c)** `!turn` rotates over the voice members with ▶/◀; **(3)** the voice loop + push-to-talk
  auto-send work; **(4)** the **auto-test now fires reliably via the roll-detection router (D29/ADR 014)**
  — the inline `<<TEST>>` was unreliable live (the model self-resolves; root-caused from the debug log),
  so a separate constrained-JSON classifier picks the test after narration and posts the button. Tobi:
  "funktioniert jetzt besser." **Suite 81/81.** Router is the default auto-test path; inline marker stays
  as fallback.


---

## Open questions (erledigt/archiviert)

**From the Phase-7 playtests (2026-06-06):**
- ✅ **(gemma3) Taste test done (2026-06-08).** gemma3:12b narrates cleaner than nemo (no
  meta-ramble/English-leak/"Was-tut-ihr"-tic) but its **dice markers were no better** (still
  self-resolves), and nemo's tone is preferred → **kept nemo**. The marker problem was *not* the model
  (documented LLM-GM failure) — fixed architecturally by the roll-detection router (D29/ADR 014). The
  residual narration drift (POV, attribution) stays nemo's ceiling; a tone-LoRA is the Part-2 lever.
- ✅ **(F) Player → character name mapping — addressed in Phase 8 (ADR 012).** The character JSON
  carries a display-name→character **alias map**, injected as a light prompt hint
  (`CharacterStore.alias_hint_de`), and turn order shows character names. _Verify live whether nemo
  actually stops confusing them; a fuller fix is still character registration (D13/ADR 003)._
- ✅ **(K) Dice/skill-check design — realised in Phase 8 (ADR 012).** The GM rolls **for** the player
  and the difficulty number comes from the profile ladder, never the LLM: marker names a skill +
  difficulty *word* → `rules/characters.resolve_target` (skill value + ladder modifier) → engine.
  _The IM ladder/SL/auto-bands are verified against the bought rulebook (2026-06-07); verify the live feel._

**Only empirical, to decide in Phase 0 (try it, not design):**
- ✅ **Model:** decided — **mistral-nemo** as primary (taste test 2026-06-04 vs gemma3:12b /
  qwen3.5:9b / glm-4.7-flash: best idiomatic German + NSC dialogue; glm too big for 12 GB).
  `gemma3:12b` is the atmospheric runner-up — worth re-checking against nemo in Phase 5 with the
  real persona prompt if the tone needs more richness.
- **TTS voice:** `de_DE-thorsten-medium` vs. `thorsten_emotional` — listen. _(Phase 6.)_

**From the streaming/robustness session (2026-06-10):**
- ✅ **Gate prerequisite resolved (2026-06-10) — party registered + session reset.** The first run
  couldn't run the HP-gate because the PC wasn't in `characters.json` (raw rolls, no damage
  persisted). Now the `circlejerk` channel has a hand-authored sheet (Garran Vex / Eli Castor / Magos
  Yann, three different builds + aliases) and its old `state.json`/`history.jsonl`/`recap.md` were
  deleted so `!join` re-seeds fresh. (Channel files are git-ignored; only the `_example` party is
  checked in.)

**Loose ends / housekeeping (from the Phase 2 session):**
- ✅ `docs/pipeline-diagram.*` removed (Tobi, 2026-06-05) — no longer a loose end.
- ✅ **Voice stack now safeguarded against silent breakage (2026-06-05).** The version
  sensitivity (DAVE decrypt into `_connection.dave_session`; voice-recv alpha) is now caught,
  not just documented: the three voice dists are pinned `==` in `pyproject.toml`;
  `voice/preflight.py` checks versions + attribute paths at boot and the live `dave_session`
  at join (loud warnings on drift); `recv.py` warns+skips a DAVE frame (magic `0xFAFA`) when no
  session is reachable instead of decoding garbage; `tests/test_voice_stack.py` is the offline
  canary (5/5 green). Verified-stack table added to ADR 006. **Still required on any upgrade:**
  run the smoke test + a live re-verify, then bump `KNOWN_GOOD` + the pins + the ADR table.
- DAVE decrypt skips frames received before the MLS group is `ready` (brief startup gap), and
  single-packet RTP jitter ("lost being flushed", sender voice-activation) is benign for STT.

**Resolved design questions (now in the decision log / ADRs):**
- ✅ Ollama host → D6 / ADR 002
- ✅ Conversational control (when the DM speaks) → D10 / ADR 003
- ✅ VAD vs. push-to-talk → resolved: VAD segments, button triggers the DM turn (D10)
- ✅ Dice test trigger → D11 / ADR 004
- ✅ Character stats in the JSON state → D12 / ADR 004
- ✅ Character registration → D13 / ADR 003
- ✅ Recap trigger → D14
- ✅ Bot A status signal → D15
