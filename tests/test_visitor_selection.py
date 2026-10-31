import json

import numpy as np
import pandas as pd
import pytest

from recommender.evaluation.visitor_selection import POLICIES, partition_users, select_policy
from recommender.models.semantic import SemanticIndex
from recommender.services.policy import RankPolicy
from recommender.services.visitor import rank_signals, recommend_visitor, score_visitor


def test_fitting_validation_and_test_users_are_disjoint_and_reproducible():
    first = partition_users(range(1, 101))
    second = partition_users(reversed(range(1, 101)))
    assert first == second
    assert {key: len(ids) for key, ids in first.items()} == {
        "fitting": 60,
        "validation": 20,
        "test": 20,
    }
    assert not first["fitting"] & first["validation"]
    assert not first["fitting"] & first["test"]
    assert not first["validation"] & first["test"]
    assert set.union(*first.values()) == set(range(1, 101))


def test_policy_selection_uses_validation_results_and_rejects_invalid_weights():
    metrics = {name: {"ndcg_at_10": 0.1, "recall_at_10": 0.1} for name in POLICIES}
    metrics["pop_story_05"]["ndcg_at_10"] = 0.2
    assert select_policy(metrics) == "pop_story_05"
    for values in ({"popularity": float("nan")}, {"content": -0.1}, {"diversity": 0.6}):
        with pytest.raises(ValueError):
            RankPolicy(**values)


def test_semantic_preferences_use_stored_vectors_and_handle_missing_plots(tmp_path):
    class NoEncoder:
        def encode(self, texts):
            raise AssertionError("A preference profile must not invoke text inference")

    (tmp_path / "manifest.json").write_text(json.dumps({}))
    np.save(tmp_path / "movie_ids.npy", [1, 2, 3])
    vectors = np.zeros((3, 384), dtype=np.float32)
    vectors[0, 0] = 1
    vectors[1, 0] = 1
    vectors[2, 1] = 1
    np.save(tmp_path / "embeddings.npy", vectors)
    index = SemanticIndex(tmp_path, encoder=NoEncoder())
    positive = index.score_preferences({1: 5}, [2, 3, 999])
    negative = index.score_preferences({1: 1}, [2, 3, 999])
    np.testing.assert_allclose(positive, [1, 0, 0])
    np.testing.assert_allclose(negative, [-1, 0, 0])
    np.testing.assert_array_equal(index.score_preferences({999: 5}, [1, 2]), [0, 0])
    np.testing.assert_array_equal(index.embeddings, vectors)


def test_serving_and_evaluation_share_the_same_policy_and_exclusions(client):
    state = client.app.state
    catalog = state.catalog
    ratings = {1: 5, 2: 1, 3: 4}
    policy = RankPolicy(0.8, 0.1, 0.1, 0, 0.03)
    signals = score_visitor(
        state.content_model, state.collaborative_model, ratings, catalog, excluded={4}
    )
    expected, _ = rank_signals(signals, catalog, policy, limit=10)
    actual = recommend_visitor(
        state.content_model,
        state.collaborative_model,
        ratings,
        catalog,
        policy=policy,
        excluded={4},
    )
    assert [item.movie_id for item in actual] == signals.movie_ids[expected].tolist() == [5]
    assert (
        recommend_visitor(
            state.content_model, state.collaborative_model, {mid: 5 for mid in catalog}, catalog
        )
        == []
    )


def test_modes_are_validated_and_neutral_ratings_do_not_invent_likes(client):
    payload = {"user_id": 99, "movie_id": 1, "rating": 3}
    assert client.post("/api/ratings", json=payload).status_code == 201
    for mode in ("balanced", "discovery"):
        result = client.get("/api/recommendations/users/99", params={"mode": mode})
        assert result.status_code == 200
        assert all(row["movie_id"] != 1 for row in result.json())
        assert all("rated highly" not in row["reason"] for row in result.json())
    assert (
        client.get("/api/recommendations/users/99", params={"mode": "unknown"}).status_code == 422
    )


def test_changing_test_feedback_cannot_change_the_exported_validation_policy(tmp_path):
    from recommender.evaluation.visitor_selection import run_selection

    interactions = pd.DataFrame(
        [(uid, mid, float(3 + mid % 3), mid * 100) for uid in range(1, 11) for mid in range(1, 7)],
        columns=["userId", "movieId", "rating", "timestamp"],
    )
    movies = pd.DataFrame(
        {
            "movieId": list(range(1, 7)),
            "title": [f"Movie {i}" for i in range(1, 7)],
            "genres": ["Adventure"] * 6,
        }
    )
    tags = pd.DataFrame(columns=["userId", "movieId", "tag", "timestamp"])
    export = tmp_path / "policy.json"
    first = run_selection(
        interactions, interactions, movies, tags, counts=(1, 3), export_path=export
    )
    before = export.read_bytes()
    modified = interactions.copy()
    test_ids = partition_users(interactions.userId)["test"]
    modified.loc[modified.userId.isin(test_ids) & modified.movieId.eq(5), "rating"] = 1
    second = run_selection(interactions, modified, movies, tags, counts=(1, 3), export_path=export)
    assert export.read_bytes() == before
    assert first["selected_policies"] == second["selected_policies"]
    assert (
        first["protocol"]["policy_sha256_before_test"]
        == (second["protocol"]["policy_sha256_before_test"])
    )
