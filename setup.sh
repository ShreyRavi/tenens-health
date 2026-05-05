#!/usr/bin/env bash
# Tenens Health Coverage Gap Index - one-shot local setup (macOS / Linux).
# Idempotent: safe to re-run.
#
# Usage:
#   ./setup.sh            # install deps, build, render, then serve at :8000
#   ./setup.sh --no-serve # install deps, build, render, exit
#   ./setup.sh --quick    # skip download + build (use existing data/processed/)
#
# Requires: bash, curl, an internet connection, ~12 GB free disk.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

NO_SERVE=0
QUICK=0
for arg in "$@"; do
  case "$arg" in
    --no-serve) NO_SERVE=1 ;;
    --quick)    QUICK=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

log() { printf "\033[1;36m[setup]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[setup]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[setup]\033[0m %s\n" "$*" >&2; }

# --- Step 1: ensure uv is installed -----------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  log "uv not found. Installing via the official installer."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # The installer adds uv to ~/.local/bin or ~/.cargo/bin. Source the right shell file
  # so this script sees uv in PATH for the remaining steps.
  if [ -f "$HOME/.local/bin/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.local/bin/env"
  fi
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  err "uv install failed. Install manually: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

log "uv $(uv --version | awk '{print $2}') found."

# --- Step 2: install Python deps --------------------------------------------
log "Installing dependencies (uv sync --all-extras)."
uv sync --all-extras

# --- Step 3: pipeline --------------------------------------------------------
if [ "$QUICK" -eq 0 ]; then
  if [ ! -f "data/processed/gap_matrix.parquet" ]; then
    log "Downloading source data. NPPES is roughly 8 GB; this can take a few minutes."
    uv run coverage-gap download
  else
    log "Source data already downloaded. Skip --quick to force a fresh download."
  fi

  log "Building the gap matrix."
  uv run coverage-gap build
else
  log "Quick mode: skipping download and build."
  if [ ! -f "data/processed/gap_matrix.parquet" ]; then
    err "Quick mode requires an existing data/processed/gap_matrix.parquet."
    err "Re-run without --quick to fetch and build the data first."
    exit 1
  fi
fi

# --- Step 4: render the static site -----------------------------------------
log "Rendering the static site."
# --skip-gate is appropriate for local dev; production deploys still go through
# coverage-gap verify -> signoffs in audit/verification-log.md.
uv run coverage-gap render --skip-gate

# --- Step 5: serve -----------------------------------------------------------
if [ "$NO_SERVE" -eq 1 ]; then
  log "Setup complete. Site is in $REPO_ROOT/site"
  log "Run 'uv run coverage-gap serve' to preview at http://localhost:8000."
  exit 0
fi

log "Starting local server at http://localhost:8000 (Ctrl-C to stop)."
exec uv run coverage-gap serve
