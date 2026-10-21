"""Validation-tuned hybrid ranking and held-out recommendation metrics."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender

DEFAULT_HYBRID_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
RELEVANCE_THRESHOLD = 4.0


@dataclass(frozen=True)
class RankingMetrics:
    """Top-K quality, catalog reach and novelty over eligible users."""

    precision_at_k: float
    recall_at_k: float
    ndcg_at_k: float
    coverage: float
    novelty: float
    eligible_users: int
    candidate_movies: int


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores.astype(np.float64)
    low = float(np.min(scores))
    high = float(np.max(scores))
    if high <= low:
        return np.zeros(scores.shape, dtype=np.float64)
    return (scores - low) / (high - low)


def _ndcg(recommended: list[int], relevant: set[int], k: int) -> float:
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, movie_id in enumerate(recommended[:k], start=1)
        if movie_id in relevant
    )
    ideal_count = min(k, len(relevant))
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def hybrid_name(collaborative_weight: float) -> str:
    """Return a stable result key for a content/collaborative blend weight."""
    return f"hybrid_cf_{collaborative_weight:.2f}"


def evaluate_rankers(
    training_ratings: pd.DataFrame,
    heldout_ratings: pd.DataFrame,
    content_model: ContentRecommender,
    collaborative_model: CollaborativeRecommender,
    *,
    k: int = 10,
    relevance_threshold: float = RELEVANCE_THRESHOLD,
    hybrid_weights: tuple[float, ...] = DEFAULT_HYBRID_WEIGHTS,
) -> dict[str, RankingMetrics]:
    """Compare popularity, content, collaborative and blended rankings.

    Candidates are movies observed in training. Each method sees the same
    per-user candidate set after the user's training items are removed. Users
    are eligible only when a relevant held-out item is in that candidate set.
    """
    required_columns = {"userId", "movieId", "rating"}
    if not required_columns.issubset(training_ratings.columns):
        raise ValueError("training_ratings must contain userId, movieId, and rating")
    if not required_columns.issubset(heldout_ratings.columns):
        raise ValueError("heldout_ratings must contain userId, movieId, and rating")
    if training_ratings.empty or heldout_ratings.empty:
        raise ValueError("training and held-out ratings must be non-empty")
    if k < 1:
        raise ValueError("k must be positive")
    if not 0.5 <= relevance_threshold <= 5:
        raise ValueError("relevance_threshold must be between 0.5 and 5.0")
    weights = tuple(sorted(set(float(weight) for weight in hybrid_weights)))
    if not weights or any(weight < 0 or weight > 1 for weight in weights):
        raise ValueError("hybrid_weights must contain values in [0, 1]")

    candidates = collaborative_model.movie_ids
    if not len(candidates):
        raise ValueError("collaborative model has no training candidate movies")
    train_by_user = {
        int(user_id): group for user_id, group in training_ratings.groupby("userId", sort=True)
    }
    relevant_by_user = {
        int(user_id): set(group.loc[group["rating"] >= relevance_threshold, "movieId"].astype(int))
        for user_id, group in heldout_ratings.groupby("userId", sort=True)
    }
    training_counts = training_ratings["movieId"].astype(int).value_counts().to_dict()
    total_training_ratings = len(training_ratings)
    result_names = ["popularity", "content", "collaborative"] + [
        hybrid_name(weight) for weight in weights
    ]
    accumulators = {
        name: {"precision": [], "recall": [], "ndcg": [], "novelty": [], "items": set()}
        for name in result_names
    }
    eligible_users = 0

    for user_id in sorted(relevant_by_user):
        history = train_by_user.get(user_id)
        if history is None:
            seen: set[int] = set()
            liked: list[int] = []
        else:
            seen = set(history["movieId"].astype(int))
            liked = sorted(
                set(history.loc[history["rating"] >= relevance_threshold, "movieId"].astype(int))
            )
        unseen_mask = ~np.isin(candidates, list(seen))
        unseen_candidates = candidates[unseen_mask]
        relevant = relevant_by_user[user_id] & set(unseen_candidates)
        if not relevant or not len(unseen_candidates):
            continue
        eligible_users += 1

        popularity = _normalize(collaborative_model.popularity_scores(unseen_candidates))
        collaborative = _normalize(
            collaborative_model.predict(
                [user_id] * len(unseen_candidates), unseen_candidates, algorithm="mf"
            )
        )
        content = _normalize(content_model.score_profile(liked, unseen_candidates))
        if not liked:
            content = popularity.copy()

        score_sets = {
            "popularity": popularity,
            "content": content,
            "collaborative": collaborative,
        }
        for weight in weights:
            score_sets[hybrid_name(weight)] = (
                (1.0 - weight) * content + weight * collaborative
            )

        for name, scores in score_sets.items():
            order = np.lexsort((unseen_candidates, -scores))[:k]
            recommended = unseen_candidates[order].astype(int).tolist()
            selected = accumulators[name]
            hits = len(set(recommended) & relevant)
            selected["precision"].append(hits / k)
            selected["recall"].append(hits / len(relevant))
            selected["ndcg"].append(_ndcg(recommended, relevant, k))
            selected["items"].update(recommended)
            selected["novelty"].append(
                float(
                    np.mean(
                        [
                            -math.log2(training_counts[movie_id] / total_training_ratings)
                            for movie_id in recommended
                        ]
                    )
                )
                if recommended
                else 0.0
            )

    if eligible_users == 0:
        raise ValueError(
            "No users have relevant held-out movies in the training candidate catalog"
        )
    return {
        name: RankingMetrics(
            precision_at_k=float(np.mean(values["precision"])),
            recall_at_k=float(np.mean(values["recall"])),
            ndcg_at_k=float(np.mean(values["ndcg"])),
            coverage=len(values["items"]) / len(candidates),
            novelty=float(np.mean(values["novelty"])),
            eligible_users=eligible_users,
            candidate_movies=len(candidates),
        )
        for name, values in accumulators.items()
    }


def select_hybrid_weight(
    validation_metrics: dict[str, RankingMetrics], weights: tuple[float, ...]
) -> float:
    """Choose blend weight by validation NDCG, then recall and precision.

    If results tie, prefer the weight closest to an even content/collaborative blend.
    """
    candidates = [
        (float(weight), validation_metrics.get(hybrid_name(float(weight)))) for weight in weights
    ]
    candidates = [(weight, metric) for weight, metric in candidates if metric is not None]
    if not candidates:
        raise ValueError("No validation metrics found for requested hybrid weights")
    return max(
        candidates,
        key=lambda entry: (
            entry[1].ndcg_at_k,
            entry[1].recall_at_k,
            entry[1].precision_at_k,
            -abs(entry[0] - 0.5),
        ),
    )[0]


def _run_evaluation(
    train_path: Path,
    validation_path: Path,
    test_path: Path,
    content_path: Path,
    collaborative_path: Path,
    output_path: Path,
    *,
    k: int,
    relevance_threshold: float,
) -> dict[str, object]:
    train = pd.read_csv(train_path)
    validation = pd.read_csv(validation_path)
    content_model = ContentRecommender.load(content_path)
    collaborative_model = CollaborativeRecommender.load(collaborative_path)
    validation_metrics = evaluate_rankers(
        train,
        validation,
        content_model,
        collaborative_model,
        k=k,
        relevance_threshold=relevance_threshold,
    )
    selected_weight = select_hybrid_weight(validation_metrics, DEFAULT_HYBRID_WEIGHTS)

    # Load and inspect the test split only after validation selected the blend weight.
    test = pd.read_csv(test_path)
    test_metrics = evaluate_rankers(
        train,
        test,
        content_model,
        collaborative_model,
        k=k,
        relevance_threshold=relevance_threshold,
        hybrid_weights=(selected_weight,),
    )
    report = {
        "protocol": {
            "k": k,
            "relevance_threshold": relevance_threshold,
            "candidate_catalog": "movies with at least one training rating",
            "candidate_filter": "remove each user's training-history movies",
            "content_profile": "training ratings >= relevance threshold",
            "blend": "(1 - collaborative_weight) * content + collaborative_weight * collaborative",
            "tuned_on": "validation only",
            "final_metrics_on": "untouched test split",
            "hybrid_weights_tested": list(DEFAULT_HYBRID_WEIGHTS),
        },
        "selected_collaborative_weight": selected_weight,
        "validation": {name: asdict(metric) for name, metric in validation_metrics.items()},
        "test": {name: asdict(metric) for name, metric in test_metrics.items()},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    """Tune the blend on validation and report ranking metrics on the test split."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, default=PROCESSED_DATA_DIR / "train_ratings.csv")
    parser.add_argument(
        "--validation", type=Path, default=PROCESSED_DATA_DIR / "validation_ratings.csv"
    )
    parser.add_argument("--test", type=Path, default=PROCESSED_DATA_DIR / "test_ratings.csv")
    parser.add_argument(
        "--content-model", type=Path, default=ARTIFACTS_DIR / "content_recommender.joblib"
    )
    parser.add_argument(
        "--collaborative-model",
        type=Path,
        default=ARTIFACTS_DIR / "collaborative_recommender.joblib",
    )
    parser.add_argument("--output", type=Path, default=ARTIFACTS_DIR / "ranking_metrics.json")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--relevance-threshold", type=float, default=RELEVANCE_THRESHOLD)
    args = parser.parse_args()
    report = _run_evaluation(
        args.train,
        args.validation,
        args.test,
        args.content_model,
        args.collaborative_model,
        args.output,
        k=args.k,
        relevance_threshold=args.relevance_threshold,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
