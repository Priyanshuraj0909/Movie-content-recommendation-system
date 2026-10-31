"""Opt-in BPR/ALS benchmark; explicit ratings >= 4 become positive events."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR
from recommender.evaluation.ranking import _ndcg


def run_benchmark(train, test, *, algorithm="bpr", seed=42, iterations=30):
    try:
        from implicit.als import AlternatingLeastSquares
        from implicit.bpr import BayesianPersonalizedRanking
    except ImportError as error:
        raise RuntimeError(
            "Install requirements-research.txt for the implicit benchmark"
        ) from error
    users = sorted(train.userId.unique())
    items = sorted(train.movieId.unique())
    user_index = {uid: index for index, uid in enumerate(users)}
    item_index = {mid: index for index, mid in enumerate(items)}
    positive = train.loc[train.rating.ge(4)]
    matrix = csr_matrix(
        (
            np.ones(len(positive), dtype=np.float32),
            (positive.userId.map(user_index), positive.movieId.map(item_index)),
        ),
        shape=(len(users), len(items)),
    )
    cls = BayesianPersonalizedRanking if algorithm == "bpr" else AlternatingLeastSquares
    model = cls(factors=32, iterations=iterations, random_state=seed, num_threads=2, use_gpu=False)
    model.fit(matrix, show_progress=False)
    ratings_by_user = train.groupby("userId").movieId.agg(set).to_dict()
    metrics = []
    recommended_items = set()
    popularity_sum = train.groupby("movieId").rating.sum()
    popularity_count = train.groupby("movieId").size()
    popularity = ((popularity_sum + 10 * train.rating.mean()) / (popularity_count + 10)).to_dict()
    baseline_metrics = []
    for uid, heldout in test.groupby("userId", sort=True):
        if uid not in user_index:
            continue
        seen = ratings_by_user.get(uid, set())
        relevant = (set(heldout.loc[heldout.rating.ge(4), "movieId"]) & set(items)) - seen
        if not relevant:
            continue
        index = user_index[uid]
        ranked, _ = model.recommend(
            index,
            matrix[index],
            N=10,
            filter_items=np.array([item_index[mid] for mid in seen], dtype=np.int32),
            filter_already_liked_items=True,
        )
        picks = [int(items[i]) for i in ranked if items[i] not in seen]
        baseline = sorted(set(items) - seen, key=lambda mid: (-popularity[mid], mid))[:10]
        for results, values in ((picks, metrics), (baseline, baseline_metrics)):
            hits = len(set(results) & relevant)
            values.append((hits / 10, hits / len(relevant), _ndcg(results, relevant, 10)))
        recommended_items.update(picks)

    def summary(values):
        array = np.asarray(values).reshape(-1, 3)
        return dict(
            zip(
                ("precision_at_10", "recall_at_10", "ndcg_at_10"),
                array.mean(axis=0).tolist() if len(array) else [None] * 3,
                strict=True,
            )
        )

    return {
        "protocol": {
            "algorithm": algorithm,
            "iterations": iterations,
            "seed": seed,
            "positive_events": "training ratings >= 4 are positive events; lower ratings are not",
            "exclusion": "all training-rated movies, including low ratings",
            "candidate_catalog": "all training-rated movies; shared with popularity",
            "eligible_users": len(metrics),
            "note": "research benchmark; not selected or enabled as a production ranker",
        },
        algorithm: summary(metrics),
        "popularity": summary(baseline_metrics),
        "coverage": len(recommended_items) / len(items),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm", choices=("bpr", "als"), default="bpr")
    parser.add_argument("--output", type=Path, default=ARTIFACTS_DIR / "implicit_metrics.json")
    args = parser.parse_args()
    report = run_benchmark(
        pd.read_csv(PROCESSED_DATA_DIR / "train_ratings.csv"),
        pd.read_csv(PROCESSED_DATA_DIR / "test_ratings.csv"),
        algorithm=args.algorithm,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
