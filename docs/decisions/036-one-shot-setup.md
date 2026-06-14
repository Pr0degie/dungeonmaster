# ADR 036 — One-shot setup: install everything + persistent PATH + robust Ollama/exec-policy

- **Status:** Accepted (code-complete; full live run on a fresh machine pending — the colleague's box)
- **Date:** 2026-06-14
- **Refs:** decision log D75 in `progress.md`; builds on the original `setup.ps1` (D-level, no ADR)
  and SETUP.md §B1–B9; relates to **ADR 002** (deployment topology — local vs remote Ollama),
  **ADR 009** (CUDA torch wheels → DLLs come via `uv sync`, no PATH editing), **ADR 019**
  (`bge-m3` replaced `nomic-embed-text` as the RAG embedder). Suite **319 green** (scripts/docs only).

## Context

Tobi: `setup.ps1` should *really take care of everything* — download, install, **put uv + Python
on the PATH**, make the bot ready to run, and be idempotent (skip what's present, but still ensure
installed/on-PATH/ready). His colleague additionally hit two fresh-machine walls: **winget** (missing
/ wants source+package agreements / prompts) and the **PowerShell script-execution policy** blocking
`setup.ps1` from running at all.

The old script fell short in concrete ways: it set only the **process** PATH (`setup.ps1:80-81`), so
nothing persisted for new terminals; it ran `uv python install 3.12` **without `--default`**, so no
global `python` shim was ever created; and it pulled the **stale `nomic-embed-text`** embedder, which
ADR 019 had already replaced with `bge-m3` for German→English rulebook retrieval.

Verified facts the design rests on: uv 0.11.19 supports `uv python install … --default` (no
`--preview`); `uv python dir --bin` = `~/.local/bin` — the **same** dir as `uv.exe`, already on the
persistent PATH on Tobi's box — so the `--default` python shim lands somewhere PATH already covers;
`[Environment]::SetEnvironmentVariable("Path", …, "User")` persists and broadcasts WM_SETTINGCHANGE.

## Decision

Make `setup.ps1` the single end-to-end, idempotent installer, plus a one-click `setup.bat`.

1. **Persistent PATH** — new `Add-ToUserPath($dir)`: reads the registry user PATH, appends `$dir` only
   if absent (normalised `TrimEnd('\')`, case-insensitive dedup, **never reorders**), writes it back,
   and also updates `$env:PATH` for the running process. Used for uv's bin (`uv python dir --bin`) and
   the Ollama install dir.
2. **Global `python`** — `uv python install 3.12 --default` creates the unversioned `python`/`python3`
   shim in `~/.local/bin`. An existing matching 3.12 earlier on PATH keeps winning (append-only), so a
   set-up box is unchanged; a fresh box gets a working `python`.
3. **Ollama full-auto** (local host only; remote stays a TODO per ADR 002): robust winget
   (`--disable-interactivity` + accept-flags, in try/catch — any snag falls through) → **official
   installer fallback** (`OllamaSetup.exe /VERYSILENT /NORESTART`) → `Add-ToUserPath` the install dir →
   boot service → pull `$OLLAMA_MODEL` + **`bge-m3`** (fixes the stale embedder) → warm-up generation.
4. **Prefetch on by default** — STT (faster-whisper) + XTTS weights download during setup unless
   `-SkipPrefetch`; the old `-Prefetch` switch is kept as an accepted no-op so existing calls don't break.
5. **Fresh-machine hardening at the top** — force TLS 1.2 (PS 5.1 default breaks HTTPS downloads);
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (try/catch); `Unblock-File` the repo's scripts
   (clears mark-of-the-web). New **`setup.bat`** launches `powershell -NoProfile -ExecutionPolicy Bypass
   -File setup.ps1 %*` so a double-click sidesteps the policy entirely — the colleague's #1 snag.
6. **Surface, don't fake, the un-automatable** — the end summary lists Discord token, PDFs, Bot A, and
   (when `data/pdfs/*.pdf` exist but `data/vectordb/rag.db` is missing) the exact RAG-build commands.

## Alternatives

- **Make the project `.venv` python global / add `.venv\Scripts` to PATH:** fragile (breaks outside the
  project, dies on `.venv` rebuild). The project runs via `uv run`; a uv-managed `--default` python is
  the clean "global python" without coupling to one project. (Tobi's explicit choice.)
- **winget-only (status quo):** exactly what failed for the colleague. The installer fallback makes the
  install independent of winget's presence/health.
- **Auto-build the RAG store:** rejected — the PDFs are the user's (legal) and the ingest is a calibrated,
  non-idempotent pipeline (ADR 019). Surfacing the commands is honest; silently running them is not.
- **Prepend the uv python ahead of an existing 3.12 (force it to win):** rejected — reordering a dev
  machine's PATH is surprising and risky; append-only leaves a working setup untouched.

## Consequences

- **Positive:** one run (or one double-click of `setup.bat`) on a fresh *or* partial Windows box ends
  with uv + python(3.12) + ollama installed and on the **persistent** PATH, `.venv` synced, models
  pulled (incl. the correct `bge-m3`), weights prefetched, `.env` seeded — then `start_dmbot.bat` works.
  Idempotent and safe to re-run.
- **Binding:** PATH writes are append-only via `Add-ToUserPath` (no reordering/dedup drift); new
  abandon-nothing setup steps should reuse it. Ollama embedder is `bge-m3` (keep in sync with ADR 019 /
  the store's `meta` table). New terminals (not the current one) see the PATH/`python` changes.
- **Risk / not verified:** the full installer was **deliberately not run** on Tobi's main machine
  (persistent PATH/ExecutionPolicy/`--default` side effects) — validated read-only (parser OK,
  `Add-ToUserPath` dedup dry-run, `uv python find`). The winget→installer fallback and the
  ExecutionPolicy path want one real fresh-machine run (the colleague's box) to confirm end-to-end.
- **To verify live:** double-click `setup.bat` on a clean machine → no policy prompt; a new terminal
  has `uv`/`python`/`ollama`; `ollama list` shows the LLM + `bge-m3`; `start_dmbot.bat` launches.
