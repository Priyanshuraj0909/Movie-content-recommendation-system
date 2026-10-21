import numpy as np
import pandas as pd
import pytest

from recommender.models.collaborative import CollaborativeRecommender, MoviePrediction


@pytest.fixture
def ratings() -> pd.DataFrame:
    rows = [
        (1, 10, 5.0),
        (1, 20, 4.0),
        (1, 30, 1.0),
        (1, 40, 5.0),
        (1, 50, 4.0),
        (1, 60, 1.0),
        (2, 10, 4.5),
        (2, 20, 4.0),
        (2, 30, 1.5),
        (2, 40, 4.5),
        (2, 50, 4.0),
        (2, 60, 1.5),
        (3, 10, 1.0),
        (3, 20, 2.0),
        (3, 30, 5.0),
        (3, 40, 1.0),
        (3, 50, 2.0),
        (3, 60, 5.0),
        (4, 10, 4.0),
        (5, 70, 3.0),
    ]
    return pd.DataFrame(rows, columns=["userId", "movieId", "rating"])


@pytest.fixture
def model(ratings: pd.DataFrame) -> CollaborativeRecommender:
    return CollaborativeRecommender(
        seed=17,
        n_factors=8,
        epochs=12,
        min_user_ratings=5,
        min_item_ratings=2,
    ).fit(ratings)


def test_fit_builds_bias_and_popularity_fallbacks(model: CollaborativeRecommender) -> None:
    predictions = model.predict([999, 4], [10, 70], algorithm="baseline")

    assert model.training_rating_count == 20
    assert model.user_count == 5
    assert model.movie_count == 7
    assert np.all((predictions >= 0.5) & (predictions <= 5.0))
    assert predictions[0] > 0.5
    assert model.popular_movies(top_k=2)[0].movie_id == 10


def test_matrix_factorization_is_reproducible(ratings: pd.DataFrame) -> None:
    params = {"seed": 17, "n_factors": 8, "epochs": 12, "min_user_ratings": 5}
    first = CollaborativeRecommender(**params).fit(ratings)
    second = CollaborativeRecommender(**params).fit(ratings.sample(frac=1, random_state=4))

    first_predictions = first.predict([1, 1, 2], [10, 30, 60], algorithm="mf")
    second_predictions = second.predict([1, 1, 2], [10, 30, 60], algorithm="mf")
    np.testing.assert_allclose(first_predictions, second_predictions, rtol=0, atol=1e-12)


def test_sparse_and_new_users_fall_back_to_baseline(model: CollaborativeRecommender) -> None:
    sparse_baseline = model.predict([4], [30], algorithm="baseline")
    sparse_matrix_factorization = model.predict([4], [30], algorithm="mf")
    unknown_baseline = model.predict([999], [10], algorithm="baseline")
    unknown_matrix_factorization = model.predict([999], [10], algorithm="mf")

    np.testing.assert_array_equal(sparse_matrix_factorization, sparse_baseline)
    np.testing.assert_array_equal(unknown_matrix_factorization, unknown_baseline)


def test_recommendations_use_popularity_for_cold_start_and_filter_seen(
    model: CollaborativeRecommender,
) -> None:
    cold_start = model.recommend_for_user(999, top_k=3, exclude_movie_ids={10})
    known_user = model.recommend_for_user(1, top_k=10)

    assert all(isinstance(item, MoviePrediction) for item in cold_start)
    assert [item.movie_id for item in cold_start][0] == 40
    assert {item.movie_id for item in known_user}.isdisjoint({10, 20, 30, 40, 50, 60})
    assert [item.movie_id for item in known_user] == [70]


def test_evaluate_reports_rmse_and_mae(model: CollaborativeRecommender) -> None:
    held_out = pd.DataFrame(
        [(1, 70, 4.0), (999, 10, 3.0)], columns=["userId", "movieId", "rating"]
    )

    metrics = model.evaluate(held_out, algorithm="mf")

    expected = model.predict(held_out.userId, held_out.movieId, algorithm="mf")
    errors = expected - held_out.rating.to_numpy()
    assert metrics.count == 2
    assert metrics.rmse == pytest.approx(np.sqrt(np.mean(errors**2)))
    assert metrics.mae == pytest.approx(np.mean(np.abs(errors)))


def test_save_and_load_preserve_predictions(tmp_path, model: CollaborativeRecommender) -> None:
    artifact = tmp_path / "nested" / "collaborative.joblib"

    model.save(artifact)
    restored = CollaborativeRecommender.load(artifact)

    assert restored.params == model.params
    np.testing.assert_array_equal(
        restored.predict([1, 999], [30, 10], algorithm="mf"),
        model.predict([1, 999], [30, 10], algorithm="mf"),
    )


def test_invalid_training_ratings_and_parameters_are_rejected(ratings: pd.DataFrame) -> None:
    invalid = ratings.copy()
    invalid.loc[0, "rating"] = 7.0

    with pytest.raises(ValueError, match="between 0.5 and 5.0"):
        CollaborativeRecommender().fit(invalid)
    with pytest.raises(ValueError, match="positive"):
        CollaborativeRecommender(n_factors=0)
