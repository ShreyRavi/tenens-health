# Coverage Gap Index

Specialist coverage data for Mississippi's 40 Critical Access Hospitals, built from public CMS data.

## What this is

Pulls NPPES (the federal physician registry), the CAH Provider of Services file, and HRSA HPSA designations. Joins them by geography. Computes for each Mississippi CAH which of 15 core specialties have zero in-network coverage within 60 miles. Outputs a static HTML dashboard at `site/`.

This is V1 of the Tenens 30-day sprint deliverable. Full design and motivation lives in `../tenens/docs/`. Most relevant: `30-day-sprint.md` (what we're shipping) and `design.md` (why).

## Getting started

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it:

```
brew install uv
```

Then install all dependencies (including pytest and dev tools):

```
uv sync --all-extras
```

Run the pipeline:

```
uv run coverage-gap download    # pulls CMS files into data/raw/
uv run coverage-gap build       # filters, joins, scores into data/processed/
uv run coverage-gap verify      # human spot-check gate, writes audit/verification-log.md
uv run coverage-gap render      # writes site/ from templates
uv run coverage-gap serve       # local preview at localhost:8000
```

Tests:

```
uv run pytest
```

## How we guided AI

This codebase was scaffolded with Claude Code. Every Claude judgment that mattered is logged in `audit/decisions.md` along with the human input that shaped or corrected it. Every gap claim that goes on the dashboard passes through `audit/verification-log.md` before render. The audit trail exists because if we publish "zero cardiologists within 60 miles" and there are actually 3, we lose a hospital relationship and a YC slide.

## Status

V1, pre-deploy, local-only. Repo private during voice review. Vercel deploy follows.
