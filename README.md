# Movie Recommendation System

A local-first, phase-driven project for building and evaluating content-based,
collaborative, and hybrid movie recommendations. It is designed to run on Apple
Silicon and uses MovieLens latest-small as the initial dataset. MovieLens genres
and tags are treated as metadata, not plot descriptions.

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

The command prints the configured local data and artifact paths. It does not
download data or create model files.

## Download and prepare MovieLens

```bash
python -m recommender.data.movielens download
python -m recommender.data.movielens prepare
```

The downloader uses the official [GroupLens MovieLens latest-small archive](https://files.grouplens.org/datasets/movielens/ml-latest-small.zip)
and verifies its companion [MD5 checksum](https://files.grouplens.org/datasets/movielens/ml-latest-small.zip.md5)
before writing the CSV files to `data/raw/`. It refuses to overwrite existing
CSV files. Preparation validates the schemas, IDs, required values, rating
scale, timestamps and movie references, then writes `movies_with_tags.csv`,
`links.csv`, per-user chronological rating splits, and `dataset_manifest.json`
to `data/processed/`. A small `download_metadata.json` sidecar records the
verified archive checksum so the processed manifest can preserve provenance.

The validation and test rows are the newest interactions per user; timestamp
ties are ordered by `movieId`. Users with fewer than three ratings stay entirely
in training. The manifest records source, checksum (when downloaded through the
CLI), data counts and timestamp range. `latest-small` is a development dataset
that GroupLens may update; its license restricts commercial use without prior
permission. Raw and processed dataset files are excluded from Git.

## Quality checks

```bash
python -m pytest -q
python -m ruff check .
```

## Project layout

- `src/recommender/data/`: dataset loading and preprocessing
- `src/recommender/models/`: recommendation algorithms
- `src/recommender/evaluation/`: offline evaluation
- `src/recommender/services/`: shared application services
- `backend/app/`: API application
- `tests/`: automated checks and privacy-safe fixtures
- `docs/phases/`: phase contracts and acceptance criteria
- `data/raw/`, `data/processed/`, `artifacts/`: local generated files, excluded from Git

See `AGENTS.md`, `MASTER_ORCHESTRATOR.md`, `PLAN.md`, and `PROGRESS.md` for the
project workflow and current verified status. No dataset, model, API key, or
`.env` file belongs in Git.
