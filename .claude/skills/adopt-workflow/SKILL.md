---
name: adopt-workflow
description: Use when Tobi wants to carry this repo's way of working (session ritual, progress.md with State header, ADRs, lessons, decision log, check command with stamp hook, report rules) into a new project — "/adopt-workflow <target folder> <stack>", "Arbeitsablauf übernehmen", "Workflow ins neue Projekt". Reads the current CLAUDE.md, skills, hook and docs structure, splits them into general / project-specific / stack-dependent, shows the split and waits for OK, then scaffolds the target with a check command and stamp hook for the named stack. Keeps an exclusion list that is never carried over.
---

# adopt-workflow — carry the working method into a new project

Arguments: **target folder** and **stack** (e.g. `C:\Users\tobo2\repos\foo python-uv`,
`... node-ts`, `... dotnet`). If either is missing, ask once, then go on.

The source is always **this repo as it stands now** — read the files below fresh at every run,
never from a copy in this skill. The target gets the *method*, not this project's content.

## 1. Read the current state (source repo)

Read compactly (headings first, grep before read):

- `CLAUDE.md` — whole file (it is short).
- `.claude/skills/README.md` and every `.claude/skills/*/SKILL.md` (frontmatter + headings; body
  only for skills that could be general).
- `.claude/agents/*.md`, `.claude/settings.json`.
- `tools/hooks/pre-commit` and `dmbot/tools/dm_check.py` (the stamp logic: `fingerprint()`,
  `run_checks()`, `is_fresh()`).
- `progress.md` — only the heading list (`grep -n "^## " progress.md`) and the State header.
- Folder structure and format: `docs/decisions/` (ADR naming + the template in the
  `session-ritual` skill), `docs/lessons/README.md` (index format), `docs/decision-log.md`
  (header and one row), `docs/progress-archive.md` (headings only).
- `docs/conventions.md`, section "Code-Review-, Simplify- & Lint-Gates" (review triggers and the
  rule for handling findings).
- `.gitattributes` and the `.gitignore` lines for `.claude/` and the stamp.

## 2. Split into three groups

| Group | Meaning | Typical content |
|---|---|---|
| **General** | carries over as is, wording made project-neutral | session handshake scaled to the task, State header + size caps + rotation, ADR template + numbering, lessons index, decision log, "docs follow code in the same commit", final-report rules, rule for review findings, test-first only where it pays, grep-first, assessment-only when Tobi thinks out loud, `grill-me`, `to-prd`, `improve-architecture` (minus the project's ADR references) |
| **Project-specific** | stays here | everything on the exclusion list below, plus project names, people, phases, D-numbers, ADR content, domain skills (`playtest-triage`, `rules-subsystem`, `rag-ingest`, `character-build`, `author-adventure`), the `log-reader` agent |
| **Stack-dependent** | carries over as a *pattern*, rebuilt for the named stack | check command (lint + tests + any regression replay), stamp + pre-commit hook, the permission allowlist, test commands named in `tdd` |

Anything matching the **exclusion list** is project-specific, no matter how general it looks.

**Show Tobi the split** as one table (item, source file, group, what changes in the target) and
**stop for his OK**. He may move items between groups. No file in the target is written before
the OK.

## 3. Scaffold the target (after OK)

Write into the target folder; don't overwrite an existing file without asking (show the diff).

1. `CLAUDE.md` — session ritual short form, while-working rules, final-report rules, docs-follow-
   code, the stack's check command under "Key gotchas"; a "What this project is" stub for Tobi.
2. `progress.md` — State header (Phase, Newest round, Suite, Live-unverifiziert or the target's
   equivalent, Next concrete step), `## Current focus`, `## Last session`, `## Next concrete step`,
   `## Open questions`; empty phase → ADR map. Plus `docs/progress-archive.md` with the matching
   `(Verlauf)` headings.
3. `docs/decisions/` (empty, naming `NNN-short-title.md`), `docs/decision-log.md` (header + table
   head), `docs/lessons/README.md` (index header).
4. `docs/conventions.md` — review triggers + the findings rule, check command and hook section.
5. `.claude/skills/` — the general skills, adapted (`session-ritual`, `tdd` with the stack's test
   commands, and whichever of `grill-me` / `to-prd` / `improve-architecture` Tobi kept) + a
   `README.md` index. `.claude/settings.json` with an allowlist for read-only and check commands
   only (nothing that writes, pushes or costs model calls). `.gitignore`: ignore `.claude/**`
   except `skills/`, `agents/`, `settings.json`; ignore the stamp file.
6. **Check command + stamp hook for the stack.** Same contract as `dm-check` here, rebuilt in
   the stack's own tooling (a package script / task / small script in the stack's language, or a
   POSIX shell script if the stack has no natural place):
   - runs lint + tests (+ regression replay if the project has one), reports one overall verdict;
   - on green writes a stamp (git-ignored) with the **git tree hash of the watched paths** taken
     from the working tree: `git add -A -- <paths>` into a throwaway `GIT_INDEX_FILE`, then
     `git write-tree`, inherited `GIT_*` variables dropped (copy `fingerprint()` from
     `dmbot/tools/dm_check.py`);
   - deletes the stamp **before** the checks, writes it only if the hash after the run equals
     the hash before; a missing, unreadable or foreign stamp means "not fresh";
   - `tools/hooks/pre-commit` (LF line endings, `tools/hooks/* text eol=lf` in `.gitattributes`):
     exits 0 if no watched path is staged; exits 0 if the stamp is fresh; else runs the check and
     blocks on red. Activate with `git config core.hooksPath tools/hooks`. Must run under Git for
     Windows' bash.
   - Watched paths: source, tests and any data the checks read — ask Tobi if unclear.
   - A small test for the stamp guarantees in the stack's test framework (throwaway git repo).
7. **Verify in the target**, with tool output: the check command runs green once; then the three
   probes — (a) a commit right after a green check passes the hook without a test run, (b) after
   editing a watched file the hook runs again, (c) after a deliberately red run the hook doesn't
   let a commit through without a test run. Report each probe with its output line. Commit in the
   target only if Tobi asks.

## 4. Close: grow the exclusion list

Ask Tobi: **"Hat im neuen Projekt etwas gestört, das von hier kam?"** For every item he names,
append a line to the exclusion list below (in *this* repo), with the date and the target project,
and commit it here (`skills(adopt-workflow): exclude <item>`). If he can't say yet, tell him to
come back with `/adopt-workflow` after a few sessions in the new project — this step can run on
its own.

## Exclusion list — never carried over

- The golden rules (all of them, including their numbering).
- Live gates and the Beipackzettel (`docs/phase-11-abend.md`, live-run scripts, `VERIFY EVIDENCE`).
- Everything about dice (engine, profiles, markers, rolls).
- Everything about RAG (ingest, retrieval, calibration, spoiler control).
- Everything about Discord (bots, voice, bridge, panels, commands).
- A WIP rule of any kind (limits on open gates, open tasks or parallel work, overrides).
