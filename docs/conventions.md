# Entwickler-Konventionen — Detailreferenz

Lade diese Datei **bei Bedarf**, nicht jeden Turn. Sie enthält die per-Modul-How-tos (DMbot,
Rules, Memory, RAG), Testing-, Runtime-/Operations-Details, das Troubleshooting („When you're
stuck on reality") und den Style-Detailteil. Die **nicht verhandelbaren Kurzfassungen** stehen
in [`../CLAUDE.md`](../CLAUDE.md) (Golden rules + Key gotchas) — dort wird auch hierher verwiesen.

## Bot A — the bridge (separate repo, already done)

Bot A is the existing music bot in its **own repo** (`Pr0degie/musicbot`, branch
`dungeon_master`, commit `249cc38`). It is **not** edited from this repo. What matters
here is its contract, which DMbot calls:

- `GET /health` → liveness. `POST /speak` with JSON `{"path","guild_id?"}` plays the WAV
  and **blocks until playback ends** — the return is the resume signal (no callback, no
  shared state). Localhost only, default `127.0.0.1:8765`. Full contract in `architecture.md` §3.
- **Two-bot isolation:** never propose changes to the music bot from here. If the bridge
  ever genuinely needs a change, that's a separate task in the music bot repo — keep it
  minimal there (the music/queue logic stays untouched).

## DMbot — DM conventions (`dmbot/`)

- **`discord-ext-voice-recv` is the only research part.** Less well-trodden than plain
  discord.py. Check against the *installed* version (the sink callback signature may
  differ), keep it isolated in `voice/`.
- **Audio reality:** per-user PCM arrives as 48 kHz **stereo**. VAD/STT need 16 kHz
  **mono** → resample before anything else. Wrong sample rate = garbage transcript,
  **not** an error — it won't surface on its own.
- **LLM wiring:** Ollama runs as its own process — in development **locally** (Tobi's
  4070, Nemo 12B), later optionally on the 5080 via Tailscale. **Never hardcode the
  host** — use env/config (`OLLAMA_HOST`), so the switch is a one-liner. Before blaming
  the client: `ollama list` — is the model even pulled?
- **Prompt building (`llm/`):** order = generic GM core → campaign tone overlay → recap →
  **adventure summary + current scene card** (code-owned pointer `state.scene_id`, ADR 019) →
  JSON state → Regelwerk hits (threshold-gated rulebook RAG) → recent history. Pass state and
  RAG as structured data, don't boil them into prose.
- **TTS:** Piper outputs a specific WAV format — confirm Bot A can play it.
- **Discord UI (`discord_ui/`):** buttons via `View`/`Button`. Dice buttons call the rules
  engine, never inline their own dice logic.

## Rules engine (`dmbot/rules/`)

- Pure Python, **fully decoupled** from the LLM. A **generic** engine: it rolls dice (RNG)
  and resolves them per the **active system profile** (`data/systems/<system>.json`) — it
  does not hardcode any one game. Profiles declare dice type, resolution (roll-under/over/
  pool/…), target source, degrees rule, and the character schema.
- IM is the first profile: `1d100`, roll-under, success level = tens-difference, damage
  d10/d5. Other systems are just other profiles.
- **Profile bootstrap:** on a new ruleset the DM proposes a draft profile from the rulebook
  (RAG) and the user confirms it; then the engine applies it. See `architecture.md` §9 + ADR 005.
- Pure functions, fixed seed in tests. The engine is unit-tested against each profile (IM
  first). This is the only part that is deterministically testable — use that.

## Memory (`dmbot/memory/`)

- JSON world state per voice channel in `data/sessions/`. Schema in `architecture.md` §7.
- Advancement is **deterministic in code** (e.g. HP after damage), never from LLM free text.
- Recaps: the LLM summarizes, code stores & re-injects at the front next time.

## RAG (`dmbot/rag/`)

- Ingestion: PDF → chunks → `bge-m3` → vector store. **40k rulebooks are
  multi-column/table-heavy** — extracted text comes out scrambled. Inspect a real chunk
  before trusting retrieval.
- Answer rule questions from rulebook chunks; attach the source to the context.

## Testing

- **`rules/`:** pytest, deterministic — mandatory (see above).
- **Voice/VAD/STT/TTS/full loop:** verified manually per phase gate, proof in the
  `VERIFY EVIDENCE` field of the phase in `progress.md`. (Real-time audio can't be
  meaningfully unit-tested.)
- **Memory:** persistence test — a state change survives a restart.
- **RAG:** sanity check — a concrete IM rule question answered correctly from a PDF.

## Code-Review-, Simplify- & Lint-Gates (was automatisch läuft vs. was du gezielt ziehst)

Zwei Ebenen, bewusst getrennt — die billige läuft von selbst, die teure nach Urteil.

**Automatisch, nach jeder Antwort** (Stop-Hook `tools/hooks/test-on-change.sh`): wenn etwas
unter `dmbot/` `tests/` `data/systems/` geändert wurde, laufen **`ruff --select F`** (pyflakes:
ungenutzte Importe/Namen, undefinierte Namen — fängt den Dead-Import-Cruft, den eine
Auslagerung hinterlässt) **+ die Test-Suite**. Still bei grün, Ausgabe nur bei Fehler
(nicht-blockierend, `exit 1` im Terminal; der Fix-Befehl steht in der Meldung). _Zeilenlänge/
Style (`E*`) bleibt bewusst aus — lange Doc-Zeilen sind Absicht, Re-Export-Shims tragen
`# noqa: F401`._

**Manuell, gezielt — `/code-review`** ist abgerechnet + langsam, also **nicht vor jedem
Commit**, sondern wenn ein Commit/Batch eine heiße Zone anfasst. Trigger-Checkliste (greift
mind. eins → Review lohnt sich):
- [ ] **Echte Logik** geändert (engine / orchestrator / delivery / memory / rag) — nicht nur
  Docs, byte-exakte Moves, Renames, Konstanten.
- [ ] Eine der **vier Golden-Rule-Zonen** berührt: dice=code, memory-split, Feedback-Schutz
  (L1 Sink-User-ID-Filter / L2 VAD-Pause), Two-Bot-Isolation.
- [ ] **Nebenläufigkeit / Ressourcen-Lebenszyklus** (asyncio-Tasks, Threads, Temp-WAVs,
  Mute-Tiefenzähler) — da verstecken sich Regressionen, die die Suite selten fängt.
- [ ] **Neue Datei** oder nennenswert neue, nicht-triviale Logik (nicht bloß „verschoben").

Greift **kein** Kästchen → Suite + Lint-Hook reichen. **Tagesende / vor einem Meilenstein**
mit viel akkumulierter Arbeit → der schwere Fan-out (`/code-review ultra` bzw. ein
Fan-out-Workflow über den Commit-Range): der **gibt verhaltenserhaltende Refactors verifiziert
frei**, statt einzelne Bugs zu suchen — genau dort liegt sein Wert. _Beleg D76: 14 Findings, 3
bestätigt, alle in neuem Logik-/Test-Code, kein einziger in den byte-exakten Move-Commits._

**Manuell, schreibend — `/simplify`** ist ein Sonderfall: es findet nicht nur, es **schreibt
deinen Code um** (es *applied* die Cleanups). Darum **nie automatisch** und nur bewusst + mit
Blick auf den Diff — das Sicherheitsnetz (Stop-Hook + pre-commit: ruff + Suite) fängt danach ab,
ob der Umbau etwas gebrochen hat. Andere Auslöser als bei `/code-review`:
- [ ] Gerade **fast-duplikaten** Code geschrieben (Copy-Paste über Branches/Dateien) oder die
  **dritte** Instanz eines Musters (rule of three → extrahieren).
- [ ] Eine Funktion wurde **lang / stark verzweigt / tief verschachtelt**.
- [ ] Nach einem Feature, **vor dem Commit**, ein bewusster Aufräum-Pass.

**Nicht** auf: byte-exakte **Moves**/Renames, **race-/nebenläufigkeitssensiblen** Code (dort von
Hand vereinfachen statt `/simplify` drüberlassen — D72-Lektion: der D40/D43-sensible Delivery-Tail
wurde absichtlich per Hand vereinheitlicht), winzige Diffs/Docs. _Deterministisch ist „vereinfachbar"
nicht messbar (anders als ein ungenutzter Import) — der Hook flaggt das nicht, das Urteil kommt
hier (ich schlage `/simplify` vor, wenn ein Batch die Trigger trifft)._

## Runtime / operations

- Python 3.12, managed with **uv**. No direct `pip`; `uv add`.
- **Runtime: Windows.** Both bots + pipeline run on Windows. Never hardcode POSIX paths —
  WAV temp via `tempfile.gettempdir()`, **never `/tmp`**.
- **Two processes, two tokens** — both bots must join the voice channel. Tokens in
  env/`.env`, **never commit them**.
- Ollama runs as its own process, not bundled with DMbot — in development locally on the
  4070, later optionally on the 5080 (Tailscale). Switchable via `OLLAMA_HOST`.
- Keep the latency chain lean (LAN/Tailscale). Streaming TTS is a later optimization, not
  an MVP must.

## When you're stuck on reality

The pipeline doesn't lie about itself — but real-time audio and foreign libs do:
- **`discord-ext-voice-recv`:** check the sink callback signature against the installed version.
- **No sound?** First check: are *both* bots actually connected to the voice channel?
- **Garbage transcript?** Suspect the sample rate (16 kHz mono?) before the model.
- **LLM not answering?** `ollama list` + reachability of the host (ping/curl) before the client.
- **RAG hallucinating?** Look at a real extracted PDF chunk — probably layout garbage.
- **No sound despite correct code (Windows)?** Is the Opus DLL loaded for discord.py voice?
- **faster-whisper won't start (Windows)?** Are the cuDNN/cuBLAS DLLs on the `PATH`?
- **`FileNotFoundError` for the WAV?** `/tmp` hardcoded instead of `tempfile.gettempdir()` — Windows has no `/tmp`.

## Style

- Commit messages: imperative, scoped (`dmbot(stt): resample to 16k mono`,
  `rules(im): success-level calculation`).
- Small functions; prefer pure functions in `rules/` and `memory/` so they stay testable.
- Comments explain *why*, not *what*.
- For small manual edits, use an editor (nano/vim) rather than clever sed/awk one-liners.
