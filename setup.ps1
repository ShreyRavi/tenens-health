# Tenens Health Coverage Gap Index - one-shot local setup (Windows).
# Idempotent: safe to re-run.
#
# Usage:
#   .\setup.ps1            # install deps, build, render, then serve at :8000
#   .\setup.ps1 -NoServe   # install deps, build, render, exit
#   .\setup.ps1 -Quick     # skip download + build (use existing data\processed\)
#
# Requires: PowerShell 5.1+, internet connection, ~12 GB free disk.
# If you see "running scripts is disabled on this system":
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

[CmdletBinding()]
param(
    [switch]$NoServe,
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "[setup] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[setup] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[setup] $msg" -ForegroundColor Red }

# --- Step 1: ensure uv is installed -----------------------------------------
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Step "uv not found. Installing via the official installer."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # The installer adds uv to %USERPROFILE%\.local\bin. Make this session see it.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Err "uv install failed. Install manually: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

Write-Step "uv $((uv --version).Split()[1]) found."

# --- Step 2: install Python deps --------------------------------------------
Write-Step "Installing dependencies (uv sync --all-extras)."
uv sync --all-extras
if ($LASTEXITCODE -ne 0) { Write-Err "uv sync failed."; exit 1 }

# --- Step 3: pipeline --------------------------------------------------------
$matrixPath = Join-Path $RepoRoot "data\processed\gap_matrix.parquet"

if (-not $Quick) {
    if (-not (Test-Path $matrixPath)) {
        Write-Step "Downloading source data. NPPES is roughly 8 GB; this can take a few minutes."
        uv run coverage-gap download
        if ($LASTEXITCODE -ne 0) { Write-Err "Download failed."; exit 1 }
    } else {
        Write-Step "Source data already downloaded."
    }

    Write-Step "Building the gap matrix."
    uv run coverage-gap build
    if ($LASTEXITCODE -ne 0) { Write-Err "Build failed."; exit 1 }
} else {
    Write-Step "Quick mode: skipping download and build."
    if (-not (Test-Path $matrixPath)) {
        Write-Err "Quick mode requires an existing data\processed\gap_matrix.parquet."
        Write-Err "Re-run without -Quick to fetch and build the data first."
        exit 1
    }
}

# --- Step 4: render ----------------------------------------------------------
Write-Step "Rendering the static site."
# --skip-gate is appropriate for local dev; production deploys still go through
# coverage-gap verify -> signoffs in audit\verification-log.md.
uv run coverage-gap render --skip-gate
if ($LASTEXITCODE -ne 0) { Write-Err "Render failed."; exit 1 }

# --- Step 5: serve -----------------------------------------------------------
if ($NoServe) {
    Write-Step "Setup complete. Site is in $RepoRoot\site"
    Write-Step "Run 'uv run coverage-gap serve' to preview at http://localhost:8000."
    exit 0
}

Write-Step "Starting local server at http://localhost:8000 (Ctrl-C to stop)."
uv run coverage-gap serve
