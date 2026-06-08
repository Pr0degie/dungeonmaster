# ============================================================================
#  setup.ps1 - one-shot installer for DMbot (the DM brain).
#
#  Automates the machine-side steps from SETUP.md: uv, dependencies (uv sync),
#  the .env file, and the local Ollama models. What it CANNOT do for you (a
#  human still must) is printed in the summary at the end: the Discord token,
#  starting Bot A, and dropping the rulebook/adventure PDFs in.
#
#  Runtime is Windows (D16). Safe to re-run - every step is idempotent.
#
#  Usage:
#    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#    .\setup.ps1 -StartBot        # run the bot when setup succeeds
#    .\setup.ps1 -SkipOllama      # skip the LLM steps (e.g. remote Ollama)
#    .\setup.ps1 -SkipSync        # skip 'uv sync' (deps already installed)
# ============================================================================

[CmdletBinding()]
param(
    [switch]$StartBot,    # launch DMbot after a successful setup
    [switch]$SkipOllama,  # skip pulling/warming the local LLM models
    [switch]$SkipSync,    # skip 'uv sync' (dependency install)
    [switch]$NoInstallUv  # do NOT auto-install uv if it's missing (just fail)
)

# --- console: UTF-8 so German text + log glyphs render ----------------------
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONUTF8 = "1"

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

# Make sure a 3.12 interpreter is available (pyproject pins >=3.12,<3.13).
# uv fetches a managed one if the system has none - idempotent.
Write-Info "Ensuring Python 3.12 is available (uv-managed if needed) ..."
uv python install 3.12 | Out-Null

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
        Add-Todo "Make sure the remote Ollama at $ollamaHost is reachable and has '$ollamaModel' + nomic-embed-text."
    } elseif (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        # try winget if available, otherwise hand it back to the user
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Warn "ollama not found - installing via winget ..."
            winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
        }
        if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
            Write-Warn "Ollama is not installed. Get it from https://ollama.com/download (Windows)."
            Add-Todo "Install Ollama, then re-run setup.ps1 (or 'ollama pull $ollamaModel; ollama pull nomic-embed-text')."
        }
    }

    if ($isLocal -and (Get-Command ollama -ErrorAction SilentlyContinue)) {
        # 'ollama list' boots the Windows service if it isn't running yet
        ollama list | Out-Null
        Write-Info "Pulling models (skips any already present) ..."
        ollama pull $ollamaModel
        ollama pull nomic-embed-text   # embeddings for RAG (Phase 10)

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
