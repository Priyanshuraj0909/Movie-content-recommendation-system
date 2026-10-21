# Project Plan: Movie & Content Recommendation System
## Objective
Build a local-first personalized movie recommendation system with content-based, collaborative, and hybrid algorithms; reproducible evaluation; FastAPI; Streamlit; and optional MLflow.
## Architecture
MovieLens ratings + movies -> validated preprocessing -> feature store and train/validation/test split -> content TF-IDF / collaborative matrix factorization -> hybrid ranking -> FastAPI -> Streamlit.
SQLite persists local users and ratings; artifact files contain fitted models and metadata. Keep external movie-poster APIs optional.
## Dataset strategy
Start with GroupLens MovieLens latest-small (movies.csv, ratings.csv, tags.csv, links.csv). For richer descriptions/posters, add an optional legally accessible metadata source only after checking licensing and ID joins. Do not pretend MovieLens genres are plot descriptions.
## Ranking design
Content: normalized title/genres/tags; TF-IDF and cosine similarity. Collaborative: bias/popularity baseline and matrix factorization. Hybrid: normalized scores and weighted blending, with a popularity/content fallback for cold-start.
## Evaluation
Use per-user chronological splits when timestamps permit. Compare popularity, content, collaborative and hybrid baselines on identical eligible users/candidates. Measure Precision@10, Recall@10, NDCG@10, coverage, novelty; RMSE/MAE only for explicit rating prediction. Document candidate selection and leakage controls.
## API
GET /health; GET /movies/search?q=; GET /recommendations/similar/{movie_id}; GET /recommendations/users/{user_id}; POST /ratings. Define typed schemas and response errors.
## Nonfunctional goals
Repeatable runs, pinned dependency ranges, unit and integration tests, linting, clear README, privacy-safe sample data, no embedded API keys.
## Definition of done
A new developer can set up locally; models train and evaluate; user can search/rate/get recommendations; tests pass; architecture and metrics are documented; app can be demonstrated on an M2 Mac.
## Scope control
No scraping, paid APIs, production auth or distributed training in the initial MVP.
