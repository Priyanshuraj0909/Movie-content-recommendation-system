import json

import pandas as pd
import pytest

from recommender.models.content import ContentRecommender, Recommendation


@pytest.fixture
def movies() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "movieId": [1, 2, 3, 4],
            "title": ["Toy Story", "Toy Story Two", "Toy Story Three", "Deep Space Horror"],
            "genres": [
                "Adventure|Animation|Comedy",
                "Adventure|Animation|Comedy",
                "Adventure|Animation|Comedy",
                "Horror|Thriller",
            ],
            "tags_json": [
                json.dumps(["pixar", "toys", "family"]),
                json.dumps(["pixar", "toys", "family"]),
                json.dumps(["pixar", "toys", "family"]),
                json.dumps(["haunted", "space"]),
            ],
        }
    )


def test_fit_returns_relevant_movies_in_deterministic_order(movies: pd.DataFrame) -> None:
    recommender = ContentRecommender().fit(movies)

    first = recommender.similar_movies(1, top_k=3)
    second = recommender.similar_movies(1, top_k=3)

    assert first == second
    assert [item.movie_id for item in first] == [2, 3]
    assert all(isinstance(item, Recommendation) for item in first)
    assert all(0 < item.score <= 1 for item in first)
    assert all("Toy Story" in item.title for item in first)


def test_similar_movies_excludes_seed_and_watched_ids(movies: pd.DataFrame) -> None:
    recommender = ContentRecommender().fit(movies)

    results = recommender.similar_movies(1, top_k=10, exclude_movie_ids=[2, 4])

    assert [item.movie_id for item in results] == [3]


def test_unknown_id_and_invalid_top_k_are_reported(movies: pd.DataFrame) -> None:
    recommender = ContentRecommender().fit(movies)

    with pytest.raises(KeyError, match="Unknown movieId"):
        recommender.similar_movies(99)
    with pytest.raises(ValueError, match="top_k"):
        recommender.similar_movies(1, top_k=-1)
    with pytest.raises(ValueError, match="top_k"):
        recommender.similar_movies(1, top_k=1.5)


def test_empty_results_when_no_positive_similarity(movies: pd.DataFrame) -> None:
    recommender = ContentRecommender().fit(movies)

    assert recommender.similar_movies(4, top_k=5) == []
    assert recommender.similar_movies(1, top_k=0) == []


def test_model_save_and_load_preserve_rankings(tmp_path, movies: pd.DataFrame) -> None:
    recommender = ContentRecommender().fit(movies)
    artifact_path = tmp_path / "nested" / "content_model.joblib"

    recommender.save(artifact_path)
    restored = ContentRecommender.load(artifact_path)

    assert restored.movie_count == 4
    assert restored.similar_movies(1, top_k=3) == recommender.similar_movies(1, top_k=3)


def test_fit_rejects_duplicate_ids_and_malformed_tags(movies: pd.DataFrame) -> None:
    duplicated = pd.concat([movies, movies.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        ContentRecommender().fit(duplicated)

    malformed = movies.copy()
    malformed.loc[0, "tags_json"] = "not-json"
    with pytest.raises(ValueError, match="invalid tags_json"):
        ContentRecommender().fit(malformed)
