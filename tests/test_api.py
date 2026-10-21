from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import backend.app.main as api_main
from backend.app.main import create_app
from backend.app.models import UserRating
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    movies = pd.DataFrame(
        {
            "movieId": [1, 2, 3, 4, 5],
            "title": [
                "Star Voyage (2000)",
                "Galaxy Journey (2001)",
                "Space Mystery (2002)",
                "Ocean Story (2003)",
                "Deep Sea (2004)",
            ],
            "genres": [
                "Adventure|Sci-Fi",
                "Adventure|Sci-Fi",
                "Mystery|Sci-Fi",
                "Adventure|Drama",
                "Drama",
            ],
            "tags_json": ["[]"] * 5,
        }
    )
    ratings = pd.DataFrame(
        [
            {"userId": user_id, "movieId": movie_id, "rating": float(3 + movie_id % 3)}
            for user_id in (10, 11, 12)
            for movie_id in (1, 2, 3, 4, 5)
        ]
    )
    app = create_app(
        content_model=ContentRecommender().fit(movies),
        collaborative_model=CollaborativeRecommender(epochs=2).fit(ratings),
        movies=movies,
        database_url=f"sqlite:///{tmp_path / 'ratings.db'}",
    )
    return TestClient(app)


def test_health_and_movie_search(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "movies_loaded": 5}

    search = client.get("/api/movies/search", params={"q": "galaxy"})
    assert search.status_code == 200
    assert search.json()[0]["movie_id"] == 2
    assert client.get("/api/movies/search", params={"q": "no match"}).json() == []


def test_similar_recommendations_and_unknown_movie(client: TestClient) -> None:
    response = client.get("/api/recommendations/similar/1", params={"limit": 5})
    assert response.status_code == 200
    assert response.json()
    assert all(item["movie_id"] != 1 for item in response.json())
    assert client.get("/api/recommendations/similar/999").status_code == 404


def test_rating_create_update_and_personalized_recommendations(client: TestClient) -> None:
    before = client.get("/api/recommendations/users/99").json()
    assert before

    payload = {"user_id": 99, "movie_id": 1, "rating": 5.0}
    created = client.post("/api/ratings", json=payload)
    assert created.status_code == 201
    assert created.json()["rating"] == 5.0

    recommendations = client.get("/api/recommendations/users/99", params={"limit": 5})
    assert recommendations.status_code == 200
    assert recommendations.json()
    assert all(item["movie_id"] != 1 for item in recommendations.json())

    payload["rating"] = 4.0
    updated = client.post("/api/ratings", json=payload)
    assert updated.status_code == 201
    assert updated.json()["rating"] == 4.0
    with client.app.state.session_factory() as session:
        saved_ratings = session.scalars(
            select(UserRating).where(UserRating.user_id == 99)
        ).all()
    assert len(saved_ratings) == 1


def test_rating_input_validation_and_unknown_movie(client: TestClient) -> None:
    invalid_scale = client.post(
        "/api/ratings", json={"user_id": 3, "movie_id": 1, "rating": 3.2}
    )
    assert invalid_scale.status_code == 422

    unknown_movie = client.post(
        "/api/ratings", json={"user_id": 3, "movie_id": 999, "rating": 4.0}
    )
    assert unknown_movie.status_code == 404


def test_default_app_loads_models_during_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    movies = pd.DataFrame(
        {
            "movieId": [1, 2, 3],
            "title": ["First Film", "Second Film", "Third Film"],
            "genres": ["Adventure", "Adventure", "Drama"],
            "tags_json": ["[]"] * 3,
        }
    )
    ratings = pd.DataFrame(
        [
            {"userId": user_id, "movieId": movie_id, "rating": 4.0}
            for user_id in (1, 2)
            for movie_id in (1, 2, 3)
        ]
    )
    monkeypatch.setattr(
        api_main,
        "_load_default_state",
        lambda: (
            ContentRecommender().fit(movies),
            CollaborativeRecommender(epochs=1).fit(ratings),
            movies,
        ),
    )
    app = create_app(database_url=f"sqlite:///{tmp_path / 'startup.db'}")
    with TestClient(app) as startup_client:
        assert startup_client.get("/api/health").json() == {
            "status": "ok",
            "movies_loaded": 3,
        }
