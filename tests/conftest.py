from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    movies = pd.DataFrame(
        {
            "movieId": [1, 2, 3, 4, 5],
            "title": [
                "Toy Star Voyage (2000)",
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
