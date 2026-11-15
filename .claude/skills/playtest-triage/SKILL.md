---
name: playtest-triage
description: Use after a live run — when Tobi says "werte den letzten Lauf aus" (or similar), pastes a session log/transcript, or brings annotated complaints from a play session. Reads the last run's logs from logs/ and the earlier bot starts of the same evening via dmbot.tools.logruns, checks every check item of the "Nächster Lauf" section in docs/phase-11-abend.md with log line and time, computes fixed per-run metrics, lists the unexpected, separates what may stem from recent changes from what was already so, and reports without touching code; then proposes pinning and records the result in the Beipackzettel and progress.md. A fix round (deterministic fixes, suite, commit per round) follows only when Tobi asks for it.
---

# Playtest triage — evaluate a run, then fix on request

A real round was played. The job is **evidence first**: what the log shows, check item by check
item, with a line and a time for every claim — never "the model got worse". Fixing is a second,
separate step that Tobi asks for.

## Golden rules that bind this work

Golden rules #2 (dice = code), #3 (hard state = code), #4 (feedback protection stays), and
#8 (German play language) bind every fix — full text in `CLAUDE.md`. The report is in German.

## Part 1 — Evaluation ("werte den letzten Lauf aus")

**Part 1 never changes code, prompts or config.** It reads, measures, reports, and at the end
writes only the result into the docs (step 8).

### 1. Find the runs of the evening

```
uv run python -m dmbot.tools.logruns
```

Every bot start is one run. Index `0` is `logs/` itself (the running or last stopped run); the
next start moves it to `logs/archive/runs/<start-stamp>/`. 📌 marks pinned runs. The evening is
run 0 plus the runs before it on the same date — name each run by its start time, keep their
numbers apart. Get a run's folder with `--path N`. Per run: `debug.log` (the evidence),
`transcript.log` (the conversation with times), `terminal.log` (the console incl. boot).

Logs are 100–300 KB: grep, never read a whole `debug.log` into context. A run without
`debug.log` (`DM_LOG_FILE=0`) → say which metrics cannot be computed. If run 0 has no
`DMbot starting` line or looks still running, say so before evaluating it.

### 2. What changed since the last evaluated run

From the State header of `progress.md` ("Live-unverifiziert", "Newest round") and
`git log --oneline --since="<start of the previous evaluated run>"`: the D-numbers and commits the
run was the first to see. The runtime's boot line names the model ids; the bot must have been
restarted after the last commit — compare the run's start time with the commit times and say
if it ran old code.

### 3. The check items, one by one

Read only the section `## Nächster Lauf` of `docs/phase-11-abend.md` (grep the heading, read to
the next `## `). For every item (F…, W…, the N… it lists, Teil B) give exactly one verdict:

- **bestanden** — the "Beweis im Log" line is there and says the good thing,
- **nicht bestanden** — the line says the bad thing, or a bad line from the table is there,
- **nicht eingetreten** — the situation never came up (no negotiation, no second player …),
- **nur am Tisch prüfbar** — ear-only items (voice, panel, table verdict): ask Tobi, don't guess.

Each verdict carries its evidence: the log line (shortened) with `HH:MM:SS` and the run. Use the
table's "Beweis im Log" column as the grep pattern; if the pattern finds nothing, write
"nicht im Log gefunden (gesucht: `<pattern>`)" — not a verdict made up from nearby lines.

### 4. Fixed metrics, per run

One table, one column per run, plus the reference values. Every number names how it was counted.

| Metric | How | Reference |
|---|---|---|
| **Würfe je Probenanforderung des Erzählers** | Requests: `🎲 Marker entscheidet`, `🎲 Marker … ungültig`, `🎲 Marker: … verworfen`, `🎲 Sicherheitsnetz`, and on old code `🎲 N Inline-Marker verworfen` (counts N). A request counts as rolled if a result line `🎲 <Name> auf <Fertigkeit>, … (Ziel NN): NN — …` (or `🌀 …`) follows before the next `LLM roh` line; a Fate reroll counts once. Router rolls (`🎲 router: …`) are listed apart, they are no narrator request | 12 von 13 am 25.10., 4 von 15 am 14.11. |
| **Zeichen je Zug und je Satz** | the command below on the run's `debug.log`; cross-check with the mean of `chars=` in `[latency]` | 14.11. Durchgang 1, same command: 555 je Zug, 166 je Satz (33 Antworten). Same scenes only (`docs/plans/textvergleich-2026-11-14.md`): 123 je Satz am 25.10., 176 am 14.11. |
| **Schnitte** | `[latency].* cut ` of all `[latency]` lines; each `✂ Antwort an der Ausgabegrenze abgeschnitten` with time | 8 von 33 am 14.11. |
| **`cache=` ab dem zweiten Zug** | the `cache=` values of `[latency]` from `turn=2` on: min, median, every turn with `cache=0` and its time; after an auto-recap (`🧵 Auto-Recap`) one high `cache_w=` is expected | 14.11.: every turn `cache=0` (D142) |
| **Doppelte oder falsch platzierte Figuren** | every `👥` line: a `(neu, …)` entry whose label describes a figure already known (card figure or earlier entry) is a duplicate; a card figure `anwesend in '<old scene>'` after a scene change, or one that should carry `gehört nach '<scene>', bleibt dort` but doesn't, is misplaced. List each with label and time; cross-check the NPC list in `data/sessions/<id>/state.debug.json` | 14.11.: „Blinder Greis“, „Türwächter“, „Frau hinter der Sichtklappe“ (D138/D144) |

Characters per turn and per sentence (spoken text, markers removed — the measure of the text comparison):

```
uv run python -c "from pathlib import Path; from dmbot.tools.text_replay import parse_turns, measure; t = parse_turns(Path(r'<run folder>\debug.log').read_text(encoding='utf-8', errors='replace'), until='99'); print(measure([x['spoken'] for x in t if x['spoken']]))"
```

### 5. The unexpected

Grep every run of the evening; list each hit with time and run, or write "keine":

- `Traceback` (with the line that led to it)
- `spoken narration call without a stable system-prompt head` — the D142 ERROR
- `echo guard`
- pause announcements: `the game is paused`, `answers again after`, `⏸`, `▶`
- `429`, `rate limit`
- any other `ERROR`, including `📦 LOG ARCHIVE FAILED`

### 6. New or old?

For every finding (failed item, bad metric, unexpected line) say which applies:

- **könnte auf eine Änderung seit dem letzten Lauf zurückgehen** — it touches an area of a
  D-number or commit from step 2 (name it);
- **war schon vorher so** — the same line or number shows in an earlier run (grep the pinned
  comparison runs, e.g. `logs/archive/pinned/2026-11-14_d1/`, and say where);
- **unklar** — neither can be shown. Say so; don't pick one.

### 7. The report

German, in this order: the runs (start, end, turns, which code); the check items (table: Punkt,
Urteil, Beleg mit Uhrzeit); the metrics (table vs references); the unexpected; new vs old;
questions for Tobi (ear-only items, F10 quotes, usage on claude.ai). What the log doesn't hold
is named as missing, never estimated.

### 8. After the report

- **Pinning:** if a run is usable as a comparison (played on the intended backend, enough turns
  to measure, no crash in the middle), propose it with the exact command:
  `uv run python -m dmbot.tools.logruns --pin N --name <kurz>`. Pin only on Tobi's yes. Run 0
  (still in `logs/`) is only marked: the next bot start files it under `pinned/` — say so.
- **Beipackzettel:** a section `## Ergebnis vom <Datum>` in `docs/phase-11-abend.md` (like the
  one for the 14.11.): runs with their folders, the check-item verdicts, the metrics, open points.
- **progress.md:** State header (move verified D-numbers out of "Live-unverifiziert", "Newest
  round", "Next concrete step") and one `## Last session` entry, rotation per `session-ritual`.
- Commit only these docs (`docs(phase-11): result of the <date> run`) and push.

## Part 2 — Fix round (only when Tobi asks for it)

1. **Classify each finding → root cause.** Past diagnoses to pattern-match against
   (`docs/decision-log.md`):
   - **D43 / ADR 018** — wrong channel → silent example-party fallback → echoed player line
     read aloud (a failure *chain*, not regression).
   - **D57 / ADR 027** — silent `num_ctx` truncation (8192 hardcoded) dropped persona +
     adventure from the prompt mid-session → "ignores the story", over-long answers, puppeting.
   - **D59 / ADR 028** — OCR/statblock junk leaking into the per-turn RAG block.
   - **D146** — text quality judged on replayed turns (`dmbot.tools.text_replay`) before a
     persona change goes live.
   Suspect the pipeline (sample rate, context budget, dedupe, channel) before the model.
2. **Fix deterministically.** Prefer a code guard over a prompt nudge. Prompt-only is allowed
   only when the failure is genuinely stylistic — and then note that a code guard is the
   fallback if the model doesn't adhere.
3. **Run the suite:** `uv run --with pytest python -m pytest`, plus `uv run dm-eval` for prompt
   or turn-path changes. Add fixed-seed tests for any new deterministic logic.
4. **Commit per round** with a scoped imperative message
   (e.g. `dmbot(memory): cumulative auto-recap so wrap-up can't drop the session start`).
5. **Record the round** per the `session-ritual` wrap-up (progress update + rotation; ADR if
   a real trade-off was weighed). Mark the result **live-unverified**, add a check item to the
   "Nächster Lauf" section, and name the concrete thing the next run should confirm.

## Notes

- Every log is *pre-change*: fixes are unproven until the next live run. Don't claim "fixed",
  claim "fix landed, live-unverified, gate = X".
- Cross-reference the `playtest-tuning-loop` memory and the relevant ADR before touching code
  in the area a finding points at.
