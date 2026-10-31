"""Evaluate wholly unseen users with the same visitor policy used by the API."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR
from recommender.data.movielens import _movie_features, training_tags
from recommender.evaluation.ranking import _ndcg
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender
from recommender.services.visitor import recommend_visitor


def evaluate_visitors(training, interactions, movies, *, seed=42, counts=(1, 3, 5, 10)):
    users = np.sort(training.userId.unique())
    if len(users) < 3:
        raise ValueError("At least three users are required for an unseen-user evaluation")
    visitor_ids = set(np.random.default_rng(seed).permutation(users)[: max(1, len(users) // 5)])
    fitting = training.loc[~training.userId.isin(visitor_ids)]
    if fitting.empty:
        raise ValueError("No fitting users remain")
    model = CollaborativeRecommender(seed=seed).fit(fitting)
    content = ContentRecommender().fit(movies)
    catalog = movies.set_index("movieId").to_dict("index")
    report = {}
    for count in counts:
        rows = {method: [] for method in ("popularity", "content", "visitor")}
        items = {method: set() for method in rows}
        for user_id in sorted(visitor_ids):
            history = interactions.loc[interactions.userId.eq(user_id)].sort_values(
                ["timestamp", "movieId"], kind="stable"
            )
            observed = history.iloc[:count]
            feedback = dict(zip(observed.movieId.astype(int), observed.rating, strict=True))
            relevant = set(
                history.iloc[count:].loc[history.iloc[count:].rating.ge(4), "movieId"].astype(int)
            ) & (set(catalog) - set(feedback))
            if not relevant:
                continue
            candidates = sorted(set(catalog) - set(feedback))
            popularity = model.popularity_scores(candidates)
            content_scores = content.score_preferences(feedback, candidates)
            for method in rows:
                if method == "visitor":
                    recs = [
                        pick.movie_id
                        for pick in recommend_visitor(content, model, feedback, catalog, limit=10)
                    ]
                else:
                    scores = popularity if method == "popularity" else content_scores
                    if method == "content" and not np.any(scores):
                        scores = popularity
                    order = np.lexsort((np.asarray(candidates), -scores))[:10]
                    recs = [candidates[i] for i in order]
                hits = len(set(recs) & relevant)
                rows[method].append((hits / 10, hits / len(relevant), _ndcg(recs, relevant, 10)))
                items[method].update(recs)
        report[str(count)] = {}
        for method, values in rows.items():
            array = np.asarray(values, dtype=float).reshape(-1, 3)
            interval = None
            if len(array):
                rng = np.random.default_rng(seed)
                bootstrap = rng.choice(array[:, 2], (1000, len(array)), replace=True).mean(axis=1)
                interval = np.quantile(bootstrap, [0.025, 0.975]).tolist()
            report[str(count)][method] = {
                "eligible_users": len(values),
                "precision_at_10": float(array[:, 0].mean()) if len(array) else None,
                "recall_at_10": float(array[:, 1].mean()) if len(array) else None,
                "ndcg_at_10": float(array[:, 2].mean()) if len(array) else None,
                "ndcg_95_percent_bootstrap_interval": interval,
                "coverage": len(items[method]) / len(catalog),
            }
    return {
        "protocol": {
            "seed": seed,
            "withheld_users": len(visitor_ids),
            "fitting_users": int(fitting.userId.nunique()),
            "visitor_ids": sorted(int(uid) for uid in visitor_ids),
            "candidates": "entire catalog excluding observed visitor ratings",
            "relevance": "rating >= 4 after earliest onboarding interactions",
            "visitor_policy": "shared API policy; heuristic CF ramp and genre diversity 0.12",
            "temporal_scope": "per-user ordering; not a global historical simulation",
        },
        "onboarding": report,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ARTIFACTS_DIR / "visitor_metrics.json")
    args = parser.parse_args()
    train = pd.read_csv(PROCESSED_DATA_DIR / "train_ratings.csv")
    interactions = pd.concat(
        [
            train,
            pd.read_csv(PROCESSED_DATA_DIR / "validation_ratings.csv"),
            pd.read_csv(PROCESSED_DATA_DIR / "test_ratings.csv"),
        ],
        ignore_index=True,
    )
    users = np.sort(train.userId.unique())
    visitors = set(np.random.default_rng(42).permutation(users)[: max(1, len(users) // 5)])
    fitting = train.loc[~train.userId.isin(visitors)]
    movies = _movie_features(
        pd.read_csv(RAW_DATA_DIR / "movies.csv"),
        training_tags(pd.read_csv(RAW_DATA_DIR / "tags.csv"), fitting),
    )
    report = evaluate_visitors(train, interactions, movies)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
