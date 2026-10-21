# Project Progress
Current phase: Phase 4 — COMPLETE

| Phase | Status | Evidence |
|---|---|---|
| 1 Foundation | Complete | Python 3.12.7 ARM64; `python -m pytest -q` (2 passed); `python -m ruff check .` (passed); `python -m recommender` (passed). |
| 2 Data | Complete | Python 3.12 ARM64; `python -m pytest -q` (8 passed); `python -m ruff check .` (passed); official archive checksum verified. |
| 3 Content model | Complete | Python 3.12 ARM64; `python -m pytest -q` (14 passed); `python -m ruff check .` (passed); trained and loaded artifact on all 9,742 movies. |
| 4 Collaborative | Complete | Python 3.12 ARM64; `python -m pytest -q` (21 passed); `python -m ruff check .` (passed); compared models on 9,818 validation ratings. |
| 5 Hybrid & evaluation | Not started | |
| 6 API & database | Not started | |
| 7 UI | Not started | |
| 8 Deployment | Not started | |

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
