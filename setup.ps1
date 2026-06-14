# ============================================================================
#  setup.ps1 - one-shot installer for DMbot (the DM brain).
#
#  Does the whole machine side end-to-end, idempotently (re-run any time; it
#  re-downloads nothing that's already present): installs uv + a uv-managed
#  Python 3.12 and puts both on the PERSISTENT user PATH; 'uv sync' (deps + .venv);
#  the .env file; installs Ollama fully automatically (winget, else the official
#  installer) + pulls the LLM + the bge-m3 RAG embedder; and pre-downloads the
#  STT + XTTS model weights. What it CANNOT do (printed as TODOs at the end):
#  the Discord token, the rulebook/adventure PDFs, the RAG store build, Bot A.
#
#  Runtime is Windows (D16).
#
#  EASIEST: double-click  setup.bat  (it bypasses the script-execution policy).
#
#  Usage (PowerShell):
#    .\setup.bat                  # one-click; recommended (no policy snag)
#    .\setup.ps1 -StartBot        # run the bot when setup succeeds
#    .\setup.ps1 -SkipOllama      # skip the LLM steps (e.g. remote Ollama)
#    .\setup.ps1 -SkipSync        # skip 'uv sync' (deps already installed)
#    .\setup.ps1 -SkipPrefetch    # skip pre-downloading STT + XTTS (else: on by default)
# ============================================================================

[CmdletBinding()]
param(
    [switch]$StartBot,      # launch DMbot after a successful setup
    [switch]$SkipOllama,    # skip pulling/warming the local LLM models
    [switch]$SkipSync,      # skip 'uv sync' (dependency install)
    [switch]$SkipPrefetch,  # skip pre-downloading STT (faster-whisper) + XTTS weights (else: on by default)
    [switch]$Prefetch,      # deprecated no-op (prefetch is the default now) - kept so old calls don't break
    [switch]$NoInstallUv    # do NOT auto-install uv if it's missing (just fail)
)

# --- console: UTF-8 so German text + log glyphs render ----------------------
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONUTF8 = "1"

# --- make this script able to run AND download on a stock machine -----------
# Two things snag fresh Windows installs: (1) TLS - PowerShell 5.1 may default to
# TLS 1.0/1.1, so HTTPS downloads (uv installer, Ollama) fail; force TLS 1.2.
# (2) Script-execution policy - if you launched via setup.bat we're already in a
# Bypass'd process, but persist RemoteSigned for CurrentUser so a later direct
# '.\setup.ps1' doesn't get blocked, and clear the "downloaded from internet"
# mark-of-the-web on the repo's scripts (the thing that pops the block prompt).
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
try { Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force -ErrorAction Stop } catch {}
try { Get-ChildItem -Path $PSScriptRoot -Include *.ps1, *.bat -Recurse -ErrorAction Stop | Unblock-File -ErrorAction Stop } catch {}

# --- pretty output helpers --------------------------------------------------
function Write-Section($t) { Write-Host ""; Write-Host "== $t ==" -ForegroundColor Cyan }
function Write-Ok($t)      { Write-Host "[ok]   $t" -ForegroundColor Green }
function Write-Info($t)    { Write-Host "[i]    $t" -ForegroundColor Gray }
function Write-Warn($t)    { Write-Host "[warn] $t" -ForegroundColor Yellow }
function Write-Err($t)     { Write-Host "[ERR]  $t" -ForegroundColor Red }

# things the human still has to do, collected and printed at the very end
$script:todo = New-Object System.Collections.Generic.List[string]
function Add-Todo($t) { $script:todo.Add($t) }

# --- 0. work from the repo root (this script's folder) ----------------------
Set-Location $PSScriptRoot
if (-not (Test-Path "pyproject.toml")) {
    Write-Err "pyproject.toml not found next to setup.ps1 - is the script in the repo root?"
    exit 1
}
Write-Host "DMbot setup  -  project: $PSScriptRoot" -ForegroundColor Green

# --- helper: read a value out of .env (falls back to a default) -------------
function Get-EnvValue($key, $default) {
    if (-not (Test-Path ".env")) { return $default }
    $line = Get-Content ".env" | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
    if (-not $line) { return $default }
    $val = ($line -split "=", 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($val)) { return $default }
    return $val
}

# --- helper: add a directory to the PERSISTENT user PATH (idempotent) --------
# The old script only touched the process PATH, so new terminals saw nothing.
# This writes the user PATH in the registry (SetEnvironmentVariable broadcasts
# WM_SETTINGCHANGE, so new shells pick it up) AND updates the current process so
# the rest of this run + a -StartBot launch see it immediately. Appends only -
# never reorders existing entries, never duplicates.
function Add-ToUserPath($dir) {
    if ([string]::IsNullOrWhiteSpace($dir)) { return }
    $dir = $dir.Trim().TrimEnd('\')
    if (-not (Test-Path $dir)) { Write-Info "PATH: skip (not found) $dir"; return }
    $cur = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($null -eq $cur) { $cur = "" }
    $parts = $cur -split ';' | Where-Object { $_ -ne "" } | ForEach-Object { $_.TrimEnd('\') }
    if ($parts -contains $dir) {
        Write-Info "PATH already has: $dir"
    } else {
        $new = if ($cur.TrimEnd(';') -eq "") { $dir } else { $cur.TrimEnd(';') + ";" + $dir }
        [Environment]::SetEnvironmentVariable("Path", $new, "User")
        Write-Ok "PATH (persistent) += $dir"
    }
    # make it visible to THIS process too (covers the rest of the run)
    $procParts = $env:PATH -split ';' | ForEach-Object { $_.TrimEnd('\') }
    if ($procParts -notcontains $dir) { $env:PATH = "$env:PATH;$dir" }
}

# ============================================================================
#  1. uv (the package/Python manager)
# ============================================================================
Write-Section "uv (package manager)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if ($NoInstallUv) {
        Write-Err "uv not found and -NoInstallUv was set. Install it: https://astral.sh/uv"
        exit 1
    }
    Write-Warn "uv not found - installing the official build from astral.sh ..."
    try {
        Invoke-Expression (Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1")
    } catch {
        Write-Err "uv install failed: $($_.Exception.Message)"
        exit 1
    }
    # the installer updates the user PATH, but THIS process won't see it yet -
    # add the default install dir so the rest of the script can call uv.
    $uvBin = Join-Path $env:USERPROFILE ".local\bin"
    if (Test-Path (Join-Path $uvBin "uv.exe")) { $env:PATH = "$uvBin;$env:PATH" }
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Err "uv still not on PATH. Open a new shell and re-run, or install manually."
    exit 1
}
Write-Ok "uv: $((uv --version) 2>&1)"

# Persist uv's bin dir (where uv.exe lives AND where 'uv python --default' drops the
# python shim) so new terminals find uv + python without re-running this script.
$uvBinDir = (uv python dir --bin 2>$null)
if ([string]::IsNullOrWhiteSpace($uvBinDir)) { $uvBinDir = Split-Path (Get-Command uv).Source }
Add-ToUserPath $uvBinDir

# ============================================================================
#  1b. Python 3.12 (uv-managed) + a global 'python' on PATH
# ============================================================================
Write-Section "Python 3.12 (uv-managed, on PATH)"
# pyproject pins >=3.12,<3.13. '--default' installs the unversioned python/python3
# shim into uv's bin dir so a bare 'python' works in every shell. Idempotent: uv
# only downloads the managed build if it's missing. An existing matching 3.12
# already earlier on PATH keeps winning (we append, never reorder).
Write-Info "Installing/ensuring Python 3.12 (uv-managed) and a global 'python' shim ..."
uv python install 3.12 --default
if ($LASTEXITCODE -ne 0) { Write-Warn "uv python install reported exit $LASTEXITCODE (continuing)." }
Add-ToUserPath $uvBinDir
$managedPy = (uv python find 3.12 2>$null)
if ($managedPy) { Write-Ok "Python 3.12 in use: $managedPy" }
$globalPy = (Get-Command python -ErrorAction SilentlyContinue)
if ($globalPy) { Write-Info "Global 'python' currently resolves to: $($globalPy.Source)" }
else { Write-Info "Global 'python' will resolve once a new shell picks up the updated PATH." }

# ============================================================================
#  2. dependencies (uv sync) - creates .venv and installs everything
# ============================================================================
Write-Section "Dependencies (uv sync)"
if ($SkipSync) {
    Write-Info "-SkipSync set, leaving the existing .venv untouched."
} else {
    Write-Info "Installing all dependencies - first run pulls CUDA torch + XTTS, can take a while ..."
    uv sync
    if ($LASTEXITCODE -ne 0) {
        Write-Err "'uv sync' failed (exit $LASTEXITCODE). Fix the error above, then re-run."
        exit 1
    }
    Write-Ok "Dependencies installed (.venv ready)."
}

# ============================================================================
#  3. .env configuration
# ============================================================================
Write-Section ".env configuration"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Ok "Created .env from .env.example."
    Add-Todo "Open .env and fill in DISCORD_TOKEN_DMBOT (required) + BOT_A_USER_ID (recommended)."
} else {
    Write-Info ".env already exists - leaving it as-is."
}
# warn if the one truly required value is still blank
$token = Get-EnvValue "DISCORD_TOKEN_DMBOT" ""
if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Warn "DISCORD_TOKEN_DMBOT is empty in .env - the bot can't log in without it."
    Add-Todo "Set DISCORD_TOKEN_DMBOT in .env (Discord app token, privileged intents on)."
} else {
    Write-Ok "DISCORD_TOKEN_DMBOT is set."
}

# data dirs the bot/RAG expect (most exist; create the ones that may not)
foreach ($d in @("data\pdfs", "data\sessions", "logs")) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null; Write-Info "Created $d\" }
}

# ============================================================================
#  4. GPU driver (informational only - DLLs are handled in code)
# ============================================================================
Write-Section "GPU (informational)"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpu = (nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>&1 | Select-Object -First 1)
    Write-Ok "NVIDIA GPU detected: $gpu"
    Write-Info "cuDNN/cuBLAS DLLs come from the wheels and are loaded in code - no PATH editing needed."
} else {
    Write-Warn "nvidia-smi not found - no usable NVIDIA GPU? STT/TTS will auto-degrade to CPU (slower)."
}

# ============================================================================
#  5. Ollama (local LLM) + models
# ============================================================================
Write-Section "Ollama (LLM)"
if ($SkipOllama) {
    Write-Info "-SkipOllama set, skipping all LLM steps."
} else {
    $ollamaHost  = Get-EnvValue "OLLAMA_HOST"  "http://127.0.0.1:11434"
    $ollamaModel = Get-EnvValue "OLLAMA_MODEL" "mistral-nemo"
    $isLocal     = $ollamaHost -match "127\.0\.0\.1|localhost"

    if (-not $isLocal) {
        Write-Info "OLLAMA_HOST is remote ($ollamaHost) - that machine owns the models. Skipping local pulls."
        Add-Todo "Make sure the remote Ollama at $ollamaHost is reachable and has '$ollamaModel' + bge-m3."
    } elseif (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        # Full auto-install. (1) winget - non-interactive, accept agreements. winget is the
        # #1 snag on fresh machines (missing / wants source+package agreements / prompts), so
        # it's wrapped in try/catch and EVERY failure just falls through to the installer.
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Warn "ollama not found - trying winget ..."
            try {
                winget install --id Ollama.Ollama -e --silent `
                    --accept-package-agreements --accept-source-agreements --disable-interactivity
            } catch { Write-Warn "winget failed ($($_.Exception.Message)) - using the official installer instead." }
        } else {
            Write-Info "winget not available - using the official installer."
        }
        Add-ToUserPath "$env:LOCALAPPDATA\Programs\Ollama"  # winget's default install location

        # (2) official installer fallback (Inno Setup -> /VERYSILENT) if winget didn't land it
        if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
            try {
                $oll = Join-Path $env:TEMP "OllamaSetup.exe"
                Write-Info "Downloading OllamaSetup.exe (official) ..."
                Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $oll -UseBasicParsing
                Write-Info "Installing Ollama silently ..."
                Start-Process -FilePath $oll -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
                Add-ToUserPath "$env:LOCALAPPDATA\Programs\Ollama"
            } catch {
                Write-Warn "Automatic Ollama install failed: $($_.Exception.Message)"
            }
        }

        if (Get-Command ollama -ErrorAction SilentlyContinue) {
            Write-Ok "Ollama installed."
        } else {
            Write-Warn "Ollama still not on PATH - a new shell or reboot may be needed."
            Add-Todo "Finish Ollama: open a NEW terminal and re-run setup.bat (or install from https://ollama.com/download)."
        }
    }

    if ($isLocal -and (Get-Command ollama -ErrorAction SilentlyContinue)) {
        # 'ollama list' boots the Windows service if it isn't running yet
        ollama list | Out-Null
        Write-Info "Pulling models (skips any already present) ..."
        ollama pull $ollamaModel
        ollama pull bge-m3             # RAG embedder (multilingual; replaced nomic-embed-text, ADR 019)

        # Phase-0 gate: a real generation proves the LLM path end-to-end
        Write-Info "Warming up '$ollamaModel' and testing a German generation (cold start ~15s) ..."
        try {
            $body = @{ model = $ollamaModel; prompt = "Sag etwas Grimmiges auf Deutsch."; stream = $false } | ConvertTo-Json
            $resp = Invoke-RestMethod -Uri "$ollamaHost/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 120
            $preview = ($resp.response -replace "\s+", " ").Trim()
            if ($preview.Length -gt 120) { $preview = $preview.Substring(0, 120) + "..." }
            Write-Ok "LLM responded: $preview"
        } catch {
            Write-Warn "Could not reach $ollamaHost - is the Ollama service running? ($($_.Exception.Message))"
        }
    }
}

# ============================================================================
#  6. Model prefetch (optional) - removes the first-run download wait
# ============================================================================
Write-Section "Model prefetch (STT + XTTS)"
if ($SkipPrefetch) {
    Write-Info "-SkipPrefetch set - STT/XTTS weights will download on first use instead."
} elseif ($SkipSync -and -not (Test-Path ".venv")) {
    Write-Warn "-SkipSync set and no .venv yet - skipping prefetch (it needs the deps). Re-run without -SkipSync."
} else {
    Write-Info "Pre-downloading STT + XTTS weights on CPU (on by default; first run pulls several GB) ..."
    uv run python -m tools.prefetch_models
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Prefetch reported a problem - not fatal, the bot downloads on first use instead."
    } else {
        Write-Ok "Models cached - the first DM turn won't wait on a download."
    }
}

# ============================================================================
#  Summary
# ============================================================================
Write-Section "Done - what's left for you"
if ($script:todo.Count -eq 0) {
    Write-Ok "Machine setup is complete."
} else {
    Write-Warn "A few things only you can do:"
    $i = 1
    foreach ($t in $script:todo) { Write-Host "   $i. $t" -ForegroundColor Yellow; $i++ }
}
# RAG store: PDFs are yours (legal) and the ingest is a calibrated, non-idempotent pipeline,
# so we don't auto-run it - but if PDFs are present and the store is missing, surface the
# exact build commands so nothing is left implicit.
$havePdfs = (Test-Path "data\pdfs") -and (Get-ChildItem "data\pdfs" -Filter *.pdf -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($havePdfs -and -not (Test-Path "data\vectordb\rag.db")) {
    Write-Warn "PDFs found in data\pdfs\ but no RAG store (data\vectordb\rag.db). Build it (see SETUP.md B9):"
    Write-Host "     uv run python tools/pdf_to_md.py   # PDF -> markdown (args per SETUP.md B9)" -ForegroundColor Gray
    Write-Host "     uv run python -m dmbot.rag.ingest  # markdown -> bge-m3 embeddings -> sqlite-vec" -ForegroundColor Gray
}

# these are always external (separate repo / your own files) - list them every time
Write-Host ""
Write-Info "Also required for the full voice loop (not automatable here):"
Write-Host "   - Start Bot A (the music bot, separate repo) on its 'dungeon_master' branch," -ForegroundColor Gray
Write-Host "     and get BOTH bots into the same Discord voice channel." -ForegroundColor Gray
Write-Host "   - Put your rulebook + adventure PDFs into data\pdfs\ (Imperium Maledictum first)." -ForegroundColor Gray
Write-Host ""
Write-Host "Run the bot:  .\start_dmbot.bat   (or: uv run python -m dmbot)" -ForegroundColor Green

# ============================================================================
#  Optionally launch the bot
# ============================================================================
if ($StartBot) {
    if ([string]::IsNullOrWhiteSpace($token)) {
        Write-Warn "-StartBot was set, but DISCORD_TOKEN_DMBOT is empty - not starting."
    } else {
        Write-Section "Starting DMbot"
        uv run python -m dmbot
    }
}
