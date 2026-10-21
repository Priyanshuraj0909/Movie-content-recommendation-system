from dataclasses import replace

import pandas as pd
import pytest

from recommender.evaluation.ranking import (
    evaluate_rankers,
    hybrid_name,
    select_hybrid_weight,
)
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender


@pytest.fixture
def ranking_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    training = pd.DataFrame(
        [
            (1, 1, 5.0),
            (1, 2, 1.0),
            (1, 4, 4.0),
            (2, 2, 5.0),
            (2, 3, 1.0),
            (3, 3, 5.0),
            (3, 4, 2.0),
        ],
        columns=["userId", "movieId", "rating"],
    )
    heldout = pd.DataFrame(
        [(1, 3, 5.0), (2, 4, 5.0), (3, 1, 4.0)],
        columns=["userId", "movieId", "rating"],
    )
    movies = pd.DataFrame(
        {
            "movieId": [1, 2, 3, 4],
            "title": ["Space Hero", "Space Villain", "Hero Returns", "Love Story"],
            "genres": ["Sci-Fi|Action", "Sci-Fi|Action", "Sci-Fi|Action", "Romance"],
            "tags_json": ['["hero", "space"]', '["villain", "space"]', '["hero", "space"]', "[]"],
        }
    )
    return training, heldout, movies


def test_evaluate_rankers_uses_identical_candidates_and_users(ranking_data) -> None:
    training, heldout, movies = ranking_data
    content = ContentRecommender().fit(movies)
    collaborative = CollaborativeRecommender(seed=3, n_factors=4, epochs=5).fit(training)

    metrics = evaluate_rankers(
        training,
        heldout,
        content,
        collaborative,
        k=2,
        hybrid_weights=(0.0, 0.5, 1.0),
    )

    assert set(metrics) == {
        "popularity",
        "content",
        "collaborative",
        hybrid_name(0.0),
        hybrid_name(0.5),
        hybrid_name(1.0),
    }
    assert {metric.eligible_users for metric in metrics.values()} == {3}
    assert {metric.candidate_movies for metric in metrics.values()} == {4}
    assert all(0 <= metric.precision_at_k <= 1 for metric in metrics.values())
    assert all(0 <= metric.recall_at_k <= 1 for metric in metrics.values())
    assert all(0 <= metric.ndcg_at_k <= 1 for metric in metrics.values())
    assert all(0 < metric.coverage <= 1 for metric in metrics.values())
    assert all(metric.novelty > 0 for metric in metrics.values())


def test_validation_selection_uses_ndcg_then_prefers_balanced_tie(ranking_data) -> None:
    training, heldout, movies = ranking_data
    content = ContentRecommender().fit(movies)
    collaborative = CollaborativeRecommender(seed=3, n_factors=4, epochs=5).fit(training)
    metrics = evaluate_rankers(
        training,
        heldout,
        content,
        collaborative,
        k=2,
        hybrid_weights=(0.0, 0.5, 1.0),
    )
    ndcg = metrics[hybrid_name(0.5)].ndcg_at_k
    for weight in (0.0, 1.0):
        key = hybrid_name(weight)
        metrics[key] = replace(
            metrics[key],
            ndcg_at_k=ndcg,
            recall_at_k=metrics[hybrid_name(0.5)].recall_at_k,
            precision_at_k=metrics[hybrid_name(0.5)].precision_at_k,
        )

    selected = select_hybrid_weight(metrics, (0.0, 0.5, 1.0))

    assert selected == 0.5


def test_ranking_rejects_invalid_protocol(ranking_data) -> None:
    training, heldout, movies = ranking_data
    content = ContentRecommender().fit(movies)
    collaborative = CollaborativeRecommender(n_factors=2, epochs=2).fit(training)

    with pytest.raises(ValueError, match="k must be positive"):
        evaluate_rankers(training, heldout, content, collaborative, k=0)
    with pytest.raises(ValueError, match="relevance_threshold"):
        evaluate_rankers(training, heldout, content, collaborative, relevance_threshold=6)
