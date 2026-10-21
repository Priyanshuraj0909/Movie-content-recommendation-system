# Movie Recommendation System

A local-first, phase-driven project for building and evaluating content-based,
collaborative, and hybrid movie recommendations. It is designed to run on Apple
Silicon and uses MovieLens latest-small as the initial dataset. MovieLens genres
and tags are treated as metadata, not plot descriptions.

## Live app

Open the deployed CineMatch AI web app at **<https://cinematch-king-09.vercel.app>**.
The Vercel deployment serves the browser UI and the FastAPI endpoints under the
same domain. The deployed backend health check is available at
<https://cinematch-king-09.vercel.app/api/health> and reports the loaded movie
count.

The browser app includes Home, Movie search, AI picks, and Watchlist views. The
Movie search tab is in the top navigation; AI picks also has a Search movies
button. Search for a title such as `Matrix`; select a result to see its catalog
details or discover similar films. Movie cards let you save a half-star rating
for the current profile. Ratings go to the API and hosted PostgreSQL database.
The watchlist and profile ID are stored in the current browser, so they do not
sync across browsers or devices. There is no account login in this MVP.

The MovieLens catalog provides titles, genres, ratings, tags, and IDs. CineMatch
uses original CSS artwork; it does not currently include licensed posters, plot
summaries, cast lists, or trailers.

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

After installation, the one-time demo setup downloads and checksum-validates
MovieLens latest-small, prepares its chronological splits, trains both models,
and writes the ranking report:

```bash
bash scripts/setup_demo.sh
```

This step needs internet access to fetch the public GroupLens archive. Generated
datasets, model artifacts and local ratings stay on disk and are ignored by
Git. To omit the offline ranking report, run
`bash scripts/setup_demo.sh --skip-evaluation`.

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

The API documentation is available at `http://127.0.0.1:8000/api/docs`. The
available routes are:

- `GET /api/health` reports service status and the number of loaded movies.
- `GET /api/movies/search?q=star&limit=20` searches titles without interpreting the
  query as a regular expression.
- `GET /api/recommendations/similar/{movie_id}?limit=10` returns content matches.
- `GET /api/recommendations/users/{user_id}?limit=10` ranks unseen training-catalog
  movies from saved positive local ratings and the trained models. Users with
  no positive saved ratings receive the training-only popularity fallback.
- `POST /api/ratings` accepts `{"user_id": 7, "movie_id": 1, "rating": 4.5}`.
  Ratings from 0.5 to 5.0 are accepted in half-star steps; submitting the same
  user/movie pair updates its saved rating.

The default SQLite database is `artifacts/recommender.db` for local use and is
ignored by Git. Set `DATABASE_URL` to a PostgreSQL connection string on hosted
platforms; the app uses SQLAlchemy's Psycopg driver. Never commit the production
connection string. Unknown movie IDs return 404 and invalid request values
return 422.

The API loads its prepared movie metadata and models during application startup.
This keeps importing the application safe for tests and CI on a fresh clone;
run the setup command above before starting the service.

## Run the Streamlit interface

With the API running in one terminal, open a second terminal at the project
root and start the UI:

```bash
streamlit run frontend/app.py
```

The browser opens the local Streamlit version of CineMatch, a dark, cinema-inspired interface for title search,
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

## CI

GitHub Actions runs tests and Ruff on Python 3.11 and 3.12 for pushes to
`main`, pull requests and manual dispatch. No dataset or trained model is
needed for CI.

## Deploy to Vercel

The production project is deployed at
<https://cinematch-king-09.vercel.app>. The cinematic static browser frontend
lives in `frontend/web/`; the existing FastAPI backend runs as a Python service.
The browser sends same-origin requests to `/api/*`. The Vercel build downloads
MovieLens latest-small and prepares the data and model artifacts; generated
files remain out of Git.

The deployed API routes are available below (the examples can be opened in a
browser):

- [Health](https://cinematch-king-09.vercel.app/api/health)
- [Search for Matrix](https://cinematch-king-09.vercel.app/api/movies/search?q=matrix)
- [Similar films for The Matrix](https://cinematch-king-09.vercel.app/api/recommendations/similar/2571?limit=5)
- [Popular picks for profile 123456789](https://cinematch-king-09.vercel.app/api/recommendations/users/123456789?limit=10)

To set up or redeploy this project on Vercel, connect the GitHub repository,
configure `DATABASE_URL` as a Vercel environment secret for Preview and
Production, then push to `main`. The database URL must never be committed.
Vercel builds the API and frontend together. Hosted ratings use PostgreSQL;
SQLite is for local development only because serverless filesystems are
temporary.

Production checks verified the page, JavaScript, stylesheet, health, search,
similar-film, and recommendation GET routes return HTTP 200. Rating create and
update are covered by local API integration tests; a rating POST has not been
run against production.

Movie cards use original CSS artwork as a fallback. MovieLens supplies titles,
genres, ratings and tags, but this project does not currently provide licensed
poster URLs, plot summaries, cast or trailer links, so the UI does not invent
those details.

`vercel.json` defines the frontend and API services and routes `/api/*` requests
to FastAPI. Deployments require `DATABASE_URL`; they intentionally fail at API
startup if it is missing rather than silently writing ratings to ephemeral
storage. Once the repository is connected, pushes to `main` deploy
automatically.

## Optional Docker demo

Docker Compose builds a Python 3.12 image that works on Apple Silicon and
standard Linux hosts, prepares the demo data/models on first launch, and serves
the API and UI from one container:

```bash
docker compose up --build
```

Open `http://localhost:8501` for CineMatch and `http://localhost:8000/api/docs` for
the API. Named volumes keep MovieLens, models and SQLite ratings between
container restarts. The first launch downloads the public MovieLens archive;
no credentials or datasets are baked into the image. To stop the demo, press
Ctrl+C. Removing Docker volumes will remove the generated data and local
ratings.

## Portfolio and model documentation

- [System architecture](docs/ARCHITECTURE.md)
- [Model card and evaluation limits](docs/MODEL_CARD.md)
- [Measured local performance](docs/PERFORMANCE.md), generated by
  `python scripts/benchmark.py`
- [Interview questions and project decisions](docs/INTERVIEW_QA.md)

## Project layout

- `src/recommender/data/`: dataset loading and preprocessing
- `src/recommender/models/`: recommendation algorithms
- `src/recommender/evaluation/`: offline evaluation
- `src/recommender/services/`: shared application services
- `backend/app/`: API application
- `frontend/`: local Streamlit app, API client and Vercel browser UI
- `tests/`: automated checks and privacy-safe fixtures
- `docs/phases/`: phase contracts and acceptance criteria
- `data/raw/`, `data/processed/`, `artifacts/`: local generated files, excluded from Git

See `AGENTS.md`, `MASTER_ORCHESTRATOR.md`, `PLAN.md`, and `PROGRESS.md` for the
project workflow and current verified status. No dataset, model, API key, or
`.env` file belongs in Git.
