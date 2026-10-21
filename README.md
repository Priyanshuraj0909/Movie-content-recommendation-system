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

## Train the content model

After preparing the dataset, fit and save the TF-IDF model:

```bash
python -m recommender.models.content
```

This reads `data/processed/movies_with_tags.csv` and writes
`artifacts/content_recommender.joblib`. To query it from Python:

```python
from recommender.models.content import ContentRecommender

model = ContentRecommender.load("artifacts/content_recommender.joblib")
results = model.similar_movies(movie_id=1, top_k=10, exclude_movie_ids={2, 3})
```

The model combines title, genres and aggregated tags. Results are ordered by
cosine similarity with movie ID as a deterministic tie-breaker; the seed and
excluded watched movies are omitted.

## Train the collaborative model

Fit the regularized bias baseline and seeded matrix factorization on the
training split, then compare rating predictions on validation data:

```bash
python -m recommender.models.collaborative
```

The command saves `artifacts/collaborative_recommender.joblib` and validation
RMSE/MAE to `artifacts/collaborative_metrics.json`. The model falls back to
regularized user/item biases for sparse or unknown users and uses a
shrinkage-adjusted popularity ranking for cold-start recommendation requests.
Recommendations exclude items present in the training history and any
additional IDs supplied by the caller.

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
