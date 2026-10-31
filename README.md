<div align="center">

# 🎬 CineMatch AI

### Find a story that feels like you.

Movie discovery with guided taste building, validation-selected recommendations, and semantic story search.

[![Python 3.11–3.12](https://img.shields.io/badge/Python-3.11%E2%80%933.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![CI](https://github.com/Priyanshuraj0909/Movie-content-recommendation-system/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Priyanshuraj0909/Movie-content-recommendation-system/actions/workflows/ci.yml)

[Open CineMatch](https://cinematch-king-09.vercel.app) · [API docs](https://cinematch-king-09.vercel.app/api/docs) · [Architecture](docs/ARCHITECTURE.md) · [Model card](docs/MODEL_CARD.md)

</div>

## What it does

- Search 9,742 MovieLens titles and explore similar films.
- Describe a story or mood and search 5,952 films with verified plot summaries.
- Filter story results by runtime and language; filter displayed results by genre.
- Build your taste with a five-film onboarding flow, search familiar titles, and edit saved half-star ratings in Your taste.
- Mark films watched or not interested independently of numeric ratings, and undo those choices.
- Choose For you or Discover more; the latter trades some measured accuracy for broader discovery.
- Read factual recommendation reasons and keep rated films out of new picks.
- Save ratings and a watchlist to a private browser profile. Restore it on another device with its recovery code.
- Read attributed plot summaries behind a spoiler disclosure, with available runtime and language information.
- Optionally display TMDB and IMDb community ratings when server-side provider credentials are configured.

**Release status:** the v0.3 ranking and taste-management implementation is locally verified. See [PROGRESS.md](PROGRESS.md) for the latest GitHub/deployment evidence. A Vercel build succeeding does not establish that protected production rating writes were verified. The existing production API currently requires Vercel Authentication.

## How recommendations work

**Content:** sparse TF-IDF over titles, genres and temporally filtered MovieLens tags. These features are separate from the static plot corpus used for story search.

**Collaborative:** regularized biases and a seeded, 32-factor matrix-factorization model trained offline. Serving estimates a visitor's bias and latent vector from their submitted ratings while keeping item factors fixed. A visitor ID never selects a MovieLens user's factors or history.

**Visitor policy:** default weights are selected on separate validation users and frozen before testing. At one through nine ratings, the selected blend is 0.85 popularity + 0.15 signed TF-IDF preferences. At ten or more, it adds visitor factors and plot similarity. Discover more uses a separately measured, broader mix. Numeric ratings, marked-watched states and not-interested states all exclude films from new picks. Explicit states never create artificial star ratings. See [the visitor evaluation](docs/VISITOR_EVALUATION.md).

**Story search:** the pinned Sentence Transformers `all-MiniLM-L6-v2` model runs through a compact quantized ONNX CPU runtime. Masked mean pooling and normalization produce 384-dimensional embeddings; NumPy performs exact similarity search. No model download occurs during a request. Relevance scores are ranking signals, not probabilities or match percentages.

## Data, attribution and evaluation

MovieLens latest-small contains 100,836 ratings from 610 benchmark users. Ratings are split chronologically per user: 81,200 training, 9,818 validation and 9,818 test interactions. Tags are retained only when their timestamps are no later than the author's last training rating. Authors absent from training contribute no training tags. This is a per-author availability policy, not one global historical simulation.

Movie plots come from the [CMU Movie Summary Corpus](https://www.cs.cmu.edu/~ark/personas/), by David Bamman, Brendan O'Connor and Noah A. Smith, and Wikipedia contributors. Corpus text is distributed under [CC BY-SA 3.0 US](https://creativecommons.org/licenses/by-sa/3.0/us/). Each displayed summary includes attribution and its original Wikipedia page link. Exact normalized title/year matching yields 5,952 matches; 12 ambiguous matches are rejected. Missing information remains missing. The corpus is a static historical snapshot and does not supply every current movie, poster, trailer or director.

Both the corpus archive and embedding model files have pinned SHA-256 digests. The model is pinned to revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, licensed Apache-2.0. Raw data, embeddings, trained models, ratings and credentials remain outside Git. Review source licenses before using datasets beyond their permitted scope.

### Measured results — 2026-10-31

After correcting tag availability, the known-user experiment selected 0.75 collaborative weight using validation NDCG@10. On 557 eligible test users and the same 8,255 training-rated candidate movies:

| Ranker | Precision@10 | Recall@10 | NDCG@10 |
|---|---:|---:|---:|
| Popularity | 0.0187 | 0.0330 | 0.0317 |
| Content | 0.0066 | 0.0160 | 0.0104 |
| Collaborative | 0.0224 | 0.0326 | 0.0326 |
| Validation-selected hybrid | 0.0226 | 0.0350 | 0.0323 |

The corrected hybrid does **not** outperform collaborative-only on this test split. Earlier results using all tags are historical and superseded.

The v0.3 visitor experiment uses 366 fitting users, 122 validation users and 122 disjoint test users. At five onboarding ratings, the validation-selected policy scored NDCG@10 **0.2989**, popularity **0.2847**, and the legacy v0.2 policy **0.0826** on the same cohort and candidates. The observed gain over popularity is about 5%; statistical significance and production quality have not been established. Default coverage was 0.51%; Discover more reached 1.53% with NDCG@10 0.2648. This is a different protocol from the known-user table and earlier visitor partition. [Full protocol and results](docs/VISITOR_EVALUATION.md).

An optional BPR experiment converting training ratings of at least 4 into positive interactions recorded NDCG@10 0.0472 versus popularity's 0.0317. It remains a research baseline, not the serving model. Multithreaded fitting can vary between runs.

Reports and complete protocols are generated under `artifacts/`; see [the model card](docs/MODEL_CARD.md) and [performance measurements](docs/PERFORMANCE.md).

## Run locally

Use native ARM64 Python 3.11 or 3.12 on Apple Silicon. Initial preparation needs internet access for public data and the pinned model; later launches use local artifacts.

```bash
git clone https://github.com/Priyanshuraj0909/Movie-content-recommendation-system.git
cd Movie-content-recommendation-system
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps -e .
bash scripts/setup_demo.sh
```

Preparation validates the sources, rebuilds changed artifacts, enriches movie records, generates embeddings, and runs the known-user evaluation. It preserves raw source files and visitor ratings. For a smaller title-only setup, use `bash scripts/setup_demo.sh --skip-semantic`; `--skip-evaluation` skips the ranking report. A full first build takes several minutes depending on download speed and CPU.

Start the API:

```bash
uvicorn backend.app.main:app --reload
```

For the static web experience locally, mount the frontend with the included preview server:

```bash
python scripts/preview.py
```

Open `http://127.0.0.1:8000`. Use one server at a time on that port. Alternatively, run `streamlit run frontend/app.py` alongside the API. Streamlit retains the local numeric-profile demo; the private-profile, watchlist, plot and story-search experience is in the browser frontend. Hosted deployments require private profile credentials.

If opening the app shows “Connection interrupted”, use **Try again** on the picks
panel. API requests time out after 15 seconds instead of leaving loading cards
on screen indefinitely. Retrying keeps your private profile and saved feedback.
If the message mentions deployment sign-in, the Vercel owner needs to check
deployment access; an API request must return JSON rather than a login page.

## Verify and reproduce

```bash
python -m pytest -q
python -m ruff check .
node --check frontend/web/app.js
python -m playwright install chromium --only-shell
python -m pytest browser_tests -q
python scripts/verify_semantic.py
python scripts/benchmark.py
python -m recommender.evaluation.visitor_selection
```

Browser tests use synthetic data, an isolated SQLite database and a fixture search index. They exercise the real DOM and HTTP routes without downloading movie data or model weights. `verify_semantic.py` separately checks the actual local model with two illustrative queries; it is a smoke test, not a semantic-search quality benchmark.

To use an existing Chrome installation instead of downloading test Chromium,
set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to its executable path when running browser
tests. On macOS:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' python -m pytest browser_tests -q
```

Production verification defaults to read-only:

```bash
python scripts/verify_deployment.py --base-url https://cinematch-king-09.vercel.app
```

After authorized access is available, verify writes with a dedicated newly created profile:

```bash
python scripts/verify_deployment.py --base-url https://cinematch-king-09.vercel.app --create-private-profile
```

The write check leaves a test profile, one updated rating and a cleared feedback-state row; it also verifies the library and watched/undo flow. It never prints the profile secret. If automation bypass is configured, export `VERCEL_AUTOMATION_BYPASS_SECRET` before running it. Neither an HTML authentication page nor an HTTP redirect counts as API success. Hosted restart persistence still requires a separate deployment/restart observation.

### Optional research tools

```bash
python -m pip install --require-hashes -r requirements-research.lock
python -m recommender.evaluation.implicit_feedback --algorithm bpr
python -m recommender.evaluation.tracking artifacts/ranking_metrics.json
python -m recommender.evaluation.tracking artifacts/visitor_metrics.json
```

The research environment includes Sentence Transformers, MLflow Skinny and Implicit. Production uses the same Sentence Transformers model through ONNX and does not install PyTorch, MLflow, or Implicit. Local MLflow tracking defaults to `artifacts/mlflow.db`; reports are logged as artifacts. An alternate tracking URI can be supplied with `--tracking-uri`. pgvector is a future storage option; exact NumPy search is the serving implementation, with no separate vector service required.

## Profiles and persistence

The browser creates an anonymous profile with a random ID and a 256-bit bearer secret. Only a SHA-256 digest of that secret is stored in the database. The browser keeps the recovery code locally; anyone possessing it can access that profile. There is no email/password account recovery. Save the code privately before clearing browser storage.

Ratings, explicit feedback events and watchlists persist in SQLite locally and PostgreSQL when `DATABASE_URL` is configured. Private responses are marked `no-store`. Feedback writes are limited to 60 per profile per minute using persisted events. This is not a global anonymous-profile creation limit; a public service should configure appropriate edge abuse controls. Legacy numeric-profile rows remain preserved but cannot be claimed by guessing an ID in the hosted app.

Alembic applies additive migrations, adopts an existing ratings table, and adds reversible movie states without deleting existing profiles, ratings or watchlists. PostgreSQL migrations serialize with a transaction-scoped advisory lock. Destructive downgrade is disabled. A manual migration reads its credential from the environment:

```bash
python scripts/migrate_database.py
```

Export `DATABASE_URL` first. The application does not load `.env` automatically.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Catalog health |
| GET | `/api/capabilities` | Semantic-search availability |
| GET | `/api/movies/search?q=matrix` | Title search |
| GET | `/api/movies/semantic-search?q=space+exploration` | Story search; optional `genre`, `language`, `max_runtime` |
| GET | `/api/movies/{movie_id}` | Real catalog details and attributed plots |
| GET | `/api/movies/external-ratings?movie_ids=1` | Optional TMDB/IMDb ratings |
| GET | `/api/recommendations/popular` | Public cold-start discovery |
| GET | `/api/recommendations/similar/{movie_id}` | Similar movies |
| POST | `/api/profiles` | Issue a private profile and recovery secret |
| GET | `/api/recommendations/users/{user_id}` | Visitor picks; `mode=balanced` or `mode=discovery` |
| POST | `/api/ratings` | Save/update a half-star rating |
| GET | `/api/profiles/{user_id}/ratings` | Private rating history |
| GET | `/api/profiles/{user_id}/library` | Paginated rating/state library; `view`, `limit`, `offset` |
| GET/PUT | `/api/profiles/{user_id}/preferences` | Read or set watched/not-interested/none state |
| GET/PUT | `/api/profiles/{user_id}/watchlist` | Read/add watchlist entries |
| DELETE | `/api/profiles/{user_id}/watchlist/{movie_id}` | Remove an owned watchlist entry |

Private requests use `X-Profile-Token` with the issued secret. A numeric ID alone is not authorization. Local legacy demo access is intentionally disabled when `VERCEL` is set.

## Deployment and configuration

The existing GitHub repository is connected to the `king-09/cinematch` Vercel project. Main-branch pushes trigger production builds. `vercel.json` preserves the static-web and FastAPI services and includes generated metadata, semantic assets and database migrations. Builds install the hashed production lockfile and run `scripts/setup_demo.sh --skip-evaluation`.

| Environment variable | Purpose |
|---|---|
| `DATABASE_URL` | Persistent PostgreSQL connection required on Vercel |
| `TMDB_API_READ_ACCESS_TOKEN` | Optional server-only TMDB ratings credential |
| `OMDB_API_KEY` | Optional server-only IMDb ratings through OMDb |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | Optional verification-client access to a protected deployment |

Provider keys are not configured in this workspace; numeric external ratings remain unavailable without them. Story search uses public, attributed data and needs no provider key. No paid service, new database or external credential is created automatically.

Docker Compose remains optional: `docker compose up --build`. Its named volumes preserve generated artifacts and local ratings. Docker has not been available for local build verification; source checks are not a substitute for a container build.

## Repository

```text
backend/app/                 API, ownership, schemas and persistence
backend/migrations/          Additive Alembic revisions
frontend/web/                Browser discovery app
frontend/app.py              Local Streamlit demo
src/recommender/data/        MovieLens and attributed plot ingestion
src/recommender/models/      Content, collaborative and semantic models
src/recommender/services/    Shared visitor-ranking policy
src/recommender/evaluation/  Known-user, unseen-user, BPR and MLflow tools
browser_tests/               Real-browser integration journeys
tests/                       Unit and API integration checks
scripts/                     Preparation, migration, preview and verification
docs/                        Architecture, model card, measurements and phases
data/, artifacts/            Generated local data; excluded from Git
```

Dependency ranges live in `requirements.in`, `requirements-dev.txt`, `requirements-ui.txt` and `requirements-research.txt`. Corresponding universal lockfiles pin versions and hashes. Use `uv pip compile --universal --python-version 3.11 --generate-hashes` to regenerate them, constraining optional environments against `requirements.lock`.
