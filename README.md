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

## Tune and evaluate hybrid rankings

```bash
python -m recommender.evaluation.ranking
```

This compares popularity, content-profile, collaborative and hybrid rankings.
It tunes the collaborative blend weight over `0.00, 0.25, 0.50, 0.75, 1.00`
using validation NDCG@10 (then Recall@10 and Precision@10 to break ties), and
evaluates the selected weight on the untouched test split. Relevance means a
rating of at least 4.0. Every method receives the same candidates: movies with
at least one training rating, after removing that user's training history.
Only users with at least one relevant held-out item in this candidate set are
included. Coverage is the fraction of the training item catalog recommended;
novelty is mean self-information from training item frequencies.

The protocol and metrics are written to `artifacts/ranking_metrics.json`.
Dataset splits and model artifacts must be prepared first. Metrics describe
this MovieLens development dataset and split; they are not a general
performance guarantee.

## Run the recommendation API

Prepare the data and model files first by running the Phase 2–5 commands above.
Then start the local API from the project root:

```bash
uvicorn backend.app.main:app --reload
```

The API documentation is available at `http://127.0.0.1:8000/docs`. The
available routes are:

- `GET /health` reports service status and the number of loaded movies.
- `GET /movies/search?q=star&limit=20` searches titles without interpreting the
  query as a regular expression.
- `GET /recommendations/similar/{movie_id}?limit=10` returns content matches.
- `GET /recommendations/users/{user_id}?limit=10` ranks unseen training-catalog
  movies from saved positive local ratings and the trained models. Users with
  no positive saved ratings receive the training-only popularity fallback.
- `POST /ratings` accepts `{"user_id": 7, "movie_id": 1, "rating": 4.5}`.
  Ratings from 0.5 to 5.0 are accepted in half-star steps; submitting the same
  user/movie pair updates its saved rating.

The default SQLite database is `artifacts/recommender.db`. It stores only local
ratings and is ignored by Git. Pass an alternate SQLite URL to `create_app` when
embedding the app or isolating it in tests. Unknown movie IDs return 404 and
invalid request values return 422.

## Run the Streamlit interface

With the API running in one terminal, open a second terminal at the project
root and start the UI:

```bash
streamlit run frontend/app.py
```

The browser opens CineMatch, a dark, cinema-inspired interface for title search,
similar-film discovery, half-star ratings and personalized recommendations.
Use the sidebar to set the API URL and local profile ID. A profile with no
positive ratings starts with the popularity fallback; saved ratings shape its
next personalized list. The UI uses the existing API and makes no poster or
metadata requests to third parties.

### UI walkthrough checklist

1. Start the API and Streamlit in separate terminals; check the sidebar reports
   the movie catalog as connected.
2. In Discover, search for a known title, save a rating, and confirm the saved
   message appears.
3. Open For you and confirm recommendations load for the current profile.
4. In Similar films, find a title and load its similar movies.
5. Stop the API, confirm the UI shows a connection message, then restart it and
   confirm requests work again.

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
- `frontend/`: Streamlit application and API client
- `tests/`: automated checks and privacy-safe fixtures
- `docs/phases/`: phase contracts and acceptance criteria
- `data/raw/`, `data/processed/`, `artifacts/`: local generated files, excluded from Git

See `AGENTS.md`, `MASTER_ORCHESTRATOR.md`, `PLAN.md`, and `PROGRESS.md` for the
project workflow and current verified status. No dataset, model, API key, or
`.env` file belongs in Git.
