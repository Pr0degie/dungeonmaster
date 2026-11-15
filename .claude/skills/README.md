# Project skills

Reusable, invocable procedures for this repo (`.claude/skills/<name>/SKILL.md`). Each one
packages a recurring multi-step workflow so it survives context clears and model switches
instead of living only as prose in `CLAUDE.md` / `progress.md`.

**How a skill runs** (it is *not* an event trigger like a hook):
- You type the slash command (e.g. `/playtest-triage`), **or**
- Claude invokes it on its own when your request clearly matches the skill's `description`
  (e.g. you paste a session log → it reaches for `playtest-triage`). That's a judgment call,
  not a guaranteed trigger — type the slash command if you want to be sure.

Token cost is negligible at rest: only the name + description sits in context (~200 tokens for
all of them); the full body loads only when the skill is actually used.

## The skills

| Skill | Command | What it does |
|---|---|---|
| **playtest-triage** | `/playtest-triage` or "werte den letzten Lauf aus" | Evaluate a run without touching code: the last run in `logs/` plus the evening's earlier bot starts (`dmbot.tools.logruns`) → every check item of "Nächster Lauf" in `docs/phase-11-abend.md` with log line and time → fixed metrics (rolls per narrator request, characters per turn/sentence, cuts, `cache=`, duplicate/misplaced figures) → the unexpected → new vs. already so → propose pinning, record in the Beipackzettel and `progress.md`. On request, a fix round: diagnose the failure *chain* → **deterministic** fixes → suite → commit per round. The signature loop. |
| **rules-subsystem** | `/rules-subsystem` | Add a new profile-driven rules subsystem in the psyker/augmetics pattern: data block in `data/systems/<system>.json` → pure engine functions → fixed-seed tests → optional `<<MARKER>>` + button (or passive) → state-summary block + German persona hint. The main "build the bot out" lever. |
| **rag-ingest** | `/rag-ingest` | Ingest a PDF/source into the RAG store: `pdf_to_md.py` (page/spoiler control) → inspect a real chunk → `dmbot.rag.ingest` → wire into `retrieve.py` `_SOURCES` → `rag_calibrate.py` → verify a question hits and a spoiler probe stays silent. |
| **character-build** | `/character-build` | Validate + deploy an IM character (incoming JSON / from scratch / backstory backfill): recompute budgets, wounds, psyker powers, augmetics against the profile → write `data/party/<player>.json` → generate the PDF sheet → propose (confirm-first) the merge into the session `characters.json` + aliases. |
| **session-ritual** | `/session-ritual` | Start handshake scaled to the task (`CLAUDE.md` + the `progress.md` State header; ADRs + lessons only for subsystem/phase work) + wrap-up for bigger rounds (`progress.md` fields, 40 KB cap, rotation) + scaffold the next-numbered ADR in the README format. |
| **tdd** | `/tdd` | Drive a change to the deterministic core test-first where it is worth it (real logic, invariants, bugs): failing fixed-seed test(s) → confirm red → minimal green → refactor. Says when a test alongside is enough. Guardrails against rewriting tests to pass. For existing code; new subsystems use `rules-subsystem`. |
| **grill-me** | `/grill-me` | Stress-test a plan before building: walk the decision tree one fork at a time, answer from docs/ADRs/code where possible, recommend an answer per question, grill in German until the design is unambiguous → offer an ADR. Adapted from Matt Pocock's grill-me. |
| **improve-architecture** | `/improve-architecture` | Whole-codebase deepening review: find shallow pass-through modules (deletion test) and propose turning them deep, for testability/AI-navigability. Markdown report → pick one → settle the design (grill only if it has real forks; + architecture.md/ADR updates). Informed by architecture.md + docs/decisions/; not diff-scoped (use /simplify or /code-review for that). Adapted from Matt Pocock. |
| **author-adventure** | `/author-adventure <md> <id>` | Draft a new adventure compendium from a converted book md: structure pass (scene cut — **stops for confirmation**) → cards/NPCs/summary in profile-aligned German → spoiler self-check → `validate.py` against the real `Adventure.load` → review checklist of its own weak spots. Output under untracked `data/adventures/<id>/`; never commits. |
| **adopt-workflow** | `/adopt-workflow <target folder> <stack>` | Carry this repo's working method into a new project: read the current CLAUDE.md, skills, hook, `progress.md` and the ADR/lessons/decision-log structure → split into general / project-specific / stack-dependent → **stop for OK** → scaffold the target with a check command + stamp hook for the stack → three hook probes. Keeps an exclusion list (golden rules, live gates/Beipackzettel, dice, RAG, Discord, any WIP rule) that grows from Tobi's feedback after the move. |
| **to-prd** | `/to-prd` | Synthesize a grilled-out plan into a PRD written to `docs/plans/<slug>.md` (no interview — companion to `/grill-me`). Explores code + architecture.md + ADRs, sketches test seams at the engine boundary, writes Problem/Solution/User-Stories/Impl-/Testing-Decisions/Scope, points `progress.md`'s next step at it. Adapted from Matt Pocock. |

## Related: the check command and the commit hook (not skills)

`uv run dm-check` runs ruff (F) + the test suite + `dm-eval` with one verdict and, on green,
stamps the checked tree of `dmbot/`, `tests/`, `data/systems/` in `.dm-check.stamp`. The git
`tools/hooks/pre-commit` runs only when those paths are in the commit and skips the re-run while
the stamp matches the working tree (`docs/conventions.md`). No `Stop` hook (dropped 2026-10-31).

## Related: subagents (`.claude/agents/`)

| Agent | Model | What it does |
|---|---|---|
| **log-reader** | opus (cheaper than Fable; tools Read/Grep/Glob only) | Read-only reading for `playtest-triage`: greps the run logs (`logs/`, `logs/archive/runs/`), the journal and the game state for given patterns and returns the lines with time and run. Never edits, never pins, never judges. |

## Maintenance

When you add a skill, add a folder `<name>/SKILL.md` **and a row to the table above** so this
index stays the single place to see what exists. `settings.local.json` stays local; the skills
and `settings.json` are committed (`.gitignore` allowlist).
