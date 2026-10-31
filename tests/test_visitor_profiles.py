"""Regression tests for benchmark isolation, ownership, and visitor fold-in."""

import numpy as np
import pytest


def test_private_profile_requires_its_secret_and_restores_history(client):
    profile = client.post("/api/profiles").json()
    user_id = profile["user_id"]
    headers = {"X-Profile-Token": profile["token"]}
    payload = {"user_id": user_id, "movie_id": 1, "rating": 5}
    assert client.post("/api/ratings", json=payload).status_code == 401
    assert client.post("/api/ratings", json=payload, headers=headers).status_code == 201
    assert client.get(f"/api/profiles/{user_id}/ratings").status_code == 401
    history = client.get(f"/api/profiles/{user_id}/ratings", headers=headers).json()
    assert len(history) == 1 and history[0]["movie_id"] == 1
    wrong = {"X-Profile-Token": "wrong"}
    assert client.get(f"/api/recommendations/users/{user_id}", headers=wrong).status_code == 401
    recommendations = client.get(f"/api/recommendations/users/{user_id}", headers=headers).json()
    assert recommendations and all(row["movie_id"] != 1 for row in recommendations)
    assert all(row["reason"] for row in recommendations)


def test_hosted_rejects_unowned_numeric_profiles(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert client.get("/api/recommendations/users/10").status_code == 401
    assert (
        client.post("/api/ratings", json={"user_id": 10, "movie_id": 1, "rating": 5}).status_code
        == 401
    )
    assert client.get("/api/recommendations/popular").status_code == 200


def test_visitor_never_inherits_movielens_seen_items(client):
    # Training user 10 has seen every fixture movie; a new local visitor 10 has not.
    assert client.app.state.collaborative_model.seen_movie_ids(10) == {1, 2, 3, 4, 5}
    a = client.get("/api/recommendations/users/10").json()
    b = client.get("/api/recommendations/users/99999").json()
    assert a and a == b


def test_private_watchlist_is_idempotent_and_isolated(client):
    profile = client.post("/api/profiles").json()
    other = client.post("/api/profiles").json()
    path = f"/api/profiles/{profile['user_id']}/watchlist"
    headers = {"X-Profile-Token": profile["token"]}
    assert client.put(path, json={"movie_id": 1}).status_code == 401
    for _ in range(2):
        assert client.put(path, json={"movie_id": 1}, headers=headers).status_code == 200
    assert len(client.get(path, headers=headers).json()) == 1
    assert client.get(path, headers={"X-Profile-Token": other["token"]}).status_code == 401
    assert client.delete(path + "/1", headers=headers).status_code == 200
    assert client.get(path, headers=headers).json() == []


def test_fold_in_changes_with_feedback_and_preserves_model(client):
    model = client.app.state.collaborative_model
    before = model.predict([10] * 5, range(1, 6))
    liked = model.predict_profile({1: 5, 2: 5, 3: 4.5}, range(1, 6))
    disliked = model.predict_profile({1: 0.5, 2: 1, 3: 1}, range(1, 6))
    assert not np.allclose(liked, disliked)
    assert np.array_equal(before, model.predict([10] * 5, range(1, 6)))
    assert np.array_equal(liked, model.predict_profile({1: 5, 2: 5, 3: 4.5}, range(1, 6)))
    with pytest.raises(ValueError):
        model.predict_profile({1: float("nan")}, [2])


def test_low_ratings_reduce_related_content_scores(client):
    content = client.app.state.content_model
    positive = content.score_preferences({1: 5}, [2, 3, 4, 5])
    negative = content.score_preferences({1: 1}, [2, 3, 4, 5])
    assert positive[0] > 0 and negative[0] < 0


def test_profile_writes_are_bounded_and_private_responses_are_not_cached(client):
    from backend.app.models import FeedbackEvent

    profile = client.post("/api/profiles").json()
    headers = {"X-Profile-Token": profile["token"]}
    with client.app.state.session_factory() as session:
        session.add_all(
            [
                FeedbackEvent(user_id=profile["user_id"], movie_id=1, event_type="rating")
                for _ in range(60)
            ]
        )
        session.commit()
    response = client.post(
        "/api/ratings",
        headers=headers,
        json={"user_id": profile["user_id"], "movie_id": 1, "rating": 5},
    )
    assert response.status_code == 429
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.post(
            "/api/ratings", json={"user_id": 10**30, "movie_id": 1, "rating": 5}
        ).status_code
        == 422
    )


def test_private_profile_and_watchlist_survive_application_restart(client):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    profile = client.post("/api/profiles").json()
    headers = {"X-Profile-Token": profile["token"]}
    uid = profile["user_id"]
    assert (
        client.post(
            "/api/ratings", headers=headers, json={"user_id": uid, "movie_id": 1, "rating": 4.5}
        ).status_code
        == 201
    )
    path = f"/api/profiles/{uid}/watchlist"
    assert client.put(path, headers=headers, json={"movie_id": 2}).status_code == 200
    state = client.app.state
    with state.session_factory() as session:
        url = str(session.get_bind().url)
    restarted = create_app(
        content_model=state.content_model,
        collaborative_model=state.collaborative_model,
        movies=state.movies.reset_index(drop=True),
        database_url=url,
    )
    with TestClient(restarted) as restored:
        history = restored.get(f"/api/profiles/{uid}/ratings", headers=headers).json()
        assert history[0]["rating"] == 4.5
        assert restored.get(path, headers=headers).json()[0]["movie_id"] == 2
        assert restored.get(path).status_code == 401
