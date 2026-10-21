# Project Progress
Current phase: Phase 9 — IN PROGRESS

| Phase | Status | Evidence |
|---|---|---|
| 1 Foundation | Complete | Python 3.12.7 ARM64; `python -m pytest -q` (2 passed); `python -m ruff check .` (passed); `python -m recommender` (passed). |
| 2 Data | Complete | Python 3.12 ARM64; `python -m pytest -q` (8 passed); `python -m ruff check .` (passed); official archive checksum verified. |
| 3 Content model | Complete | Python 3.12 ARM64; `python -m pytest -q` (14 passed); `python -m ruff check .` (passed); trained and loaded artifact on all 9,742 movies. |
| 4 Collaborative | Complete | Python 3.12 ARM64; `python -m pytest -q` (21 passed); `python -m ruff check .` (passed); compared models on 9,818 validation ratings. |
| 5 Hybrid & evaluation | Complete | Python 3.12 ARM64; `python -m pytest -q` (25 passed); `python -m ruff check .` (passed); validation-tuned blend evaluated on untouched test split. |
| 6 API & database | Complete | Python 3.12 ARM64; `python -m pytest -q` (29 passed); `python -m ruff check .` (passed); FastAPI routes verified with temporary SQLite integration tests. |
| 7 UI | Complete | Python 3.12 ARM64; `python -m pytest -q` (33 passed); `python -m ruff check .` (passed); live Streamlit walkthrough covered search, rating, cold-start, similar films and offline states. |
| 8 Deployment | Complete | Python 3.12 ARM64; `python -m pytest -q` (34 passed); `python -m ruff check .` (passed); 34 tests also passed in a fresh-clone simulation with datasets and artifacts excluded. |
| 9 Vercel deployment | Deployed; rating POST verification pending | Commit `c9ea803` is live on Vercel production. Production page, `/api/health` (9,742 movies), and `/api/movies/search?q=matrix` returned HTTP 200. Local API integration tests cover rating create/update; the available hosted fetch tool supports GET only, so a production rating write was not exercised. |

## Decisions
- Python 3.11/3.12 ARM64 environment preferred.
- MovieLens latest-small for initial MVP.

## Blockers
None recorded.

## Phase 1 Notes
- Installed the project requirements and editable package in `.venv`.
- Added reproducible path and random-seed settings and a package entry point.
- Verified generated data, artifacts, and environment files remain ignored by Git.

## Phase 2 Notes
- Downloaded GroupLens MovieLens latest-small; verified MD5 `31a303aabbc519bd33d025e44d6c2570`.
- Validated 9,742 movies, 100,836 ratings from 610 users, 3,683 tag applications and 9,742 links.
- Chronological per-user split: 81,200 train, 9,818 validation and 9,818 test ratings; every user retains at least one training interaction.
- Raw CSVs, processed files and the generated manifest remain local and ignored by Git.

## Phase 3 Notes
- Added a sparse TF-IDF content model using movie titles, genres and aggregated tags.
- Similarity ranking is deterministic, excludes the seed and caller-provided watched IDs, and handles unknown IDs.
- Saved and loaded `artifacts/content_recommender.joblib`; the generated artifact remains ignored by Git.
- The model uses MovieLens metadata and tags; it does not have plot descriptions.

## Phase 4 Notes
- Added a regularized bias baseline, shrinkage-adjusted popularity fallback and seeded SGD matrix factorization.
- Trained only on 81,200 training ratings; validation comparison used 9,818 ratings (the test split was not used).
- Validation bias baseline: RMSE 0.8914, MAE 0.6854. Matrix factorization: RMSE 0.8808, MAE 0.6742.
- Saved `artifacts/collaborative_recommender.joblib` and `artifacts/collaborative_metrics.json`; both remain ignored by Git.
- Verified unknown and sparse-user fallbacks, seen-item exclusion, deterministic training and artifact reload.

## Phase 5 Notes
- Added normalized popularity, content-profile and collaborative ranking scores with a weighted hybrid blend.
- Tuned collaborative weight on validation only; selected `0.75` by NDCG@10 over weights 0.00, 0.25, 0.50, 0.75 and 1.00.
- Candidates are the 8,255 training-rated movies; each user's training history is excluded. Relevance is a held-out rating of at least 4.0.
- Validation at the selected weight (553 eligible users): Precision@10 0.0306, Recall@10 0.0532, NDCG@10 0.0530, coverage 0.0497, novelty 10.0032.
- Untouched test at the selected weight (557 eligible users): Precision@10 0.0264, Recall@10 0.0435, NDCG@10 0.0381, coverage 0.0492, novelty 9.9970.
- Test NDCG@10 comparison: popularity 0.0317, content 0.0112, collaborative 0.0326, hybrid 0.0381.
- Saved the full protocol and metric report to `artifacts/ranking_metrics.json`; generated artifacts remain ignored by Git.

## Phase 6 Notes
- Added documented FastAPI health, title search, similar movie, personalized recommendation and rating routes.
- Added request/response schemas and SQLAlchemy SQLite persistence. Repeated ratings for the same user/movie update the saved value; invalid ratings and unknown movies are rejected.
- Personalized recommendations exclude movies from the trained user's history and locally saved ratings. Positive local ratings seed the content/collaborative blend; users without positive ratings receive training-only popularity recommendations.
- Added integration coverage using temporary SQLite databases; API tests cover all required routes, rating updates, validation and unknown movie handling.
- Fixed model serialization when training via `python -m` and regenerated local content and collaborative artifacts. A fresh API import successfully loaded both artifacts. Generated model and database files remain ignored by Git.
- Verification: `.venv/bin/python -m pytest -q` (29 passed) and `.venv/bin/python -m ruff check .` (passed). TestClient reports a Starlette deprecation warning about the installed httpx integration; tests pass and no extra dependency was installed.

## Phase 7 Notes
- Added a dark, responsive Streamlit interface with title search, similar-film discovery, profile-based recommendations and half-star rating controls.
- Added a small API client with readable service errors, loading states, API connection status and configurable API URL/profile ID. The UI makes no third-party poster or metadata requests.
- Added HTTP client tests and Streamlit AppTest flows for discovery/rating, recommendations and similar films.
- Live walkthrough against the FastAPI service verified search, popularity fallback for a cold-start profile, similar-film results, saving a rating to a temporary SQLite database and excluding the rated movie from the next personalized list. The API-offline message was also verified.
- Verification: `.venv/bin/python -m pytest -q` (33 passed) and `.venv/bin/python -m ruff check .` (passed). The existing Starlette/httpx deprecation warning remains; no dependency was added.

## Phase 8 Notes
- Fixed Streamlit's entrypoint import so `streamlit run frontend/app.py` works whether launched from the repository root or the `frontend/` directory; both launch modes returned HTTP 200 during verification.
- Added GitHub Actions CI for Python 3.11 and 3.12, running pytest and Ruff without any dataset or model artifact.
- Moved default API model/data loading into FastAPI startup. Imports and CI collection work on a fresh checkout; startup reports missing setup files if the local demo has not been prepared.
- Added `scripts/setup_demo.sh` for reproducible data preparation, model training and offline ranking evaluation. Added optional Docker Compose with separate API/UI ports and named volumes for generated data and ratings.
- Verified the lazy API startup with the trained local artifacts; `/health` returned `{"status":"ok","movies_loaded":9742}`. Missing model/data files now point to the setup command.
- Added architecture diagram, model card, benchmark script and measured performance notes, and interview Q&A.
- Benchmark run on macOS 27.0.1 ARM64 with Python 3.12.7: content and collaborative artifact loads 0.046s and 0.030s; warm title search p95 1.219ms; similar movie p95 0.867ms; 1,000 predictions p95 0.273ms; full-catalog top-10 ranking p95 2.876ms. Measurements exclude network and concurrency; see `docs/PERFORMANCE.md`.
- Verification: `.venv/bin/python -m pytest -q` (34 passed), `.venv/bin/python -m ruff check .` (passed), shell syntax and demo setup passed. A temporary fresh-clone copy without `data/` or `artifacts/` also passed all 34 tests after the CI editable install.
- Docker build was not run because this machine has no Docker, Podman or nerdctl CLI. Docker support is optional; source and compose files are included but need a Docker host to verify.
