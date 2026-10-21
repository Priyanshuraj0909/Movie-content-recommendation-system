# Movie Recommendation System

A local-first, phase-driven project for building and evaluating content-based, collaborative, and hybrid movie recommendations. It is designed to run on Apple Silicon and uses MovieLens latest-small as the initial dataset. MovieLens genres and tags are treated as metadata, not plot descriptions.

## Requirements

- macOS on Apple Silicon or another supported platform
- Python 3.11 or 3.12 (ARM64 on Apple Silicon)
- Git

Check the interpreter before creating the environment:

```bash
python3 --version
python3 -c 'import platform; print(platform.machine())'
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

## Run

```bash
python -m recommender
```

The command prints the configured local data and artifact paths. It does not download data or create model files.

## Quality checks

```bash
python -m pytest -q
python -m ruff check .
```

See `AGENTS.md`, `MASTER_ORCHESTRATOR.md`, `PLAN.md`, and `PROGRESS.md` for the project workflow and current verified status. No dataset, model, API key, or `.env` file belongs in Git.
