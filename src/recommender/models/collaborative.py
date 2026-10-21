"""Bias baseline and reproducible matrix factorization for explicit ratings."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, RANDOM_SEED

MODEL_FORMAT_VERSION = 1
RATING_COLUMNS = ("userId", "movieId", "rating")


@dataclass(frozen=True)
class MoviePrediction:
    """A movie and its predicted user rating."""

    movie_id: int
    predicted_rating: float


@dataclass(frozen=True)
class RatingMetrics:
    """Explicit-rating prediction errors over one held-out split."""

    count: int
    rmse: float
    mae: float


def _validate_ratings(ratings: pd.DataFrame, *, unique_pairs: bool = True) -> pd.DataFrame:
    missing_columns = sorted(set(RATING_COLUMNS) - set(ratings.columns))
    if missing_columns:
        raise ValueError(f"Ratings table is missing required columns: {missing_columns}")
    if ratings.empty:
        raise ValueError("Ratings table must contain at least one row")

    data = ratings.loc[:, RATING_COLUMNS].copy()
    for column in ("userId", "movieId"):
        values = pd.to_numeric(data[column], errors="coerce")
        invalid = values.isna() | (values <= 0) | ((values % 1) != 0)
        if invalid.any():
            raise ValueError(f"{column} must contain positive integer IDs")
        data[column] = values.astype("int64")
    values = pd.to_numeric(data["rating"], errors="coerce")
    invalid = values.isna() | (values < 0.5) | (values > 5.0)
    if invalid.any():
        raise ValueError("rating values must be numeric and between 0.5 and 5.0")
    data["rating"] = values.astype("float64")
    if unique_pairs and data.duplicated(["userId", "movieId"]).any():
        raise ValueError("Ratings table has duplicate userId/movieId pairs")
    return data


class CollaborativeRecommender:
    """Predict ratings from regularized biases and seeded latent factors.

    The bias model is the cold-start and sparse-user fallback. Factorization is
    used only when both the user and movie have enough training observations.
    """

    def __init__(
        self,
        *,
        seed: int = RANDOM_SEED,
        n_factors: int = 32,
        epochs: int = 20,
        learning_rate: float = 0.015,
        factor_regularization: float = 0.05,
        bias_regularization: float = 10.0,
        min_user_ratings: int = 5,
        min_item_ratings: int = 2,
        popularity_regularization: float = 10.0,
    ) -> None:
        if n_factors < 1 or epochs < 1:
            raise ValueError("n_factors and epochs must be positive")
        if learning_rate <= 0 or factor_regularization < 0 or bias_regularization < 0:
            raise ValueError("learning rate must be positive and regularization non-negative")
        if min_user_ratings < 1 or min_item_ratings < 1 or popularity_regularization < 0:
            raise ValueError(
                "minimum rating counts must be positive and regularization non-negative"
            )
        self.params = {
            "seed": int(seed),
            "n_factors": int(n_factors),
            "epochs": int(epochs),
            "learning_rate": float(learning_rate),
            "factor_regularization": float(factor_regularization),
            "bias_regularization": float(bias_regularization),
            "min_user_ratings": int(min_user_ratings),
            "min_item_ratings": int(min_item_ratings),
            "popularity_regularization": float(popularity_regularization),
        }
        self.global_mean: float | None = None
        self._user_ids: np.ndarray | None = None
        self._movie_ids: np.ndarray | None = None
        self._user_index: dict[int, int] = {}
        self._movie_index: dict[int, int] = {}
        self._user_counts: np.ndarray | None = None
        self._movie_counts: np.ndarray | None = None
        self._user_bias: np.ndarray | None = None
        self._movie_bias: np.ndarray | None = None
        self._user_factors: np.ndarray | None = None
        self._movie_factors: np.ndarray | None = None
        self._popularity_scores: np.ndarray | None = None
        self._seen_by_user: dict[int, set[int]] = {}

    @property
    def is_fitted(self) -> bool:
        return self.global_mean is not None and self._user_factors is not None

    @property
    def user_count(self) -> int:
        self._require_fitted()
        assert self._user_ids is not None
        return len(self._user_ids)

    @property
    def movie_count(self) -> int:
        self._require_fitted()
        assert self._movie_ids is not None
        return len(self._movie_ids)

    @property
    def movie_ids(self) -> np.ndarray:
        """Return a copy of movie IDs observed in the training ratings."""
        self._require_fitted()
        assert self._movie_ids is not None
        return self._movie_ids.copy()

    @property
    def training_rating_count(self) -> int:
        self._require_fitted()
        assert self._user_counts is not None
        return int(self._user_counts.sum())

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise RuntimeError("CollaborativeRecommender must be fitted before use")

    def fit(self, ratings: pd.DataFrame) -> CollaborativeRecommender:
        """Fit biases and latent factors from a training ratings table only."""
        data = _validate_ratings(ratings)
        self._user_ids = np.sort(data["userId"].unique())
        self._movie_ids = np.sort(data["movieId"].unique())
        self._user_index = {int(value): index for index, value in enumerate(self._user_ids)}
        self._movie_index = {int(value): index for index, value in enumerate(self._movie_ids)}
        user_indices = data["userId"].map(self._user_index).to_numpy(dtype=np.int64)
        movie_indices = data["movieId"].map(self._movie_index).to_numpy(dtype=np.int64)
        values = data["rating"].to_numpy(dtype=np.float64)
        self._user_counts = np.bincount(user_indices, minlength=len(self._user_ids))
        self._movie_counts = np.bincount(movie_indices, minlength=len(self._movie_ids))
        self.global_mean = float(values.mean())

        user_bias = np.zeros(len(self._user_ids), dtype=np.float64)
        movie_bias = np.zeros(len(self._movie_ids), dtype=np.float64)
        bias_reg = self.params["bias_regularization"]
        for _ in range(10):
            user_residuals = values - self.global_mean - movie_bias[movie_indices]
            user_bias = np.bincount(
                user_indices, weights=user_residuals, minlength=len(self._user_ids)
            ) / (self._user_counts + bias_reg)
            movie_residuals = values - self.global_mean - user_bias[user_indices]
            movie_bias = np.bincount(
                movie_indices, weights=movie_residuals, minlength=len(self._movie_ids)
            ) / (self._movie_counts + bias_reg)
        self._user_bias = user_bias
        self._movie_bias = movie_bias

        popularity_reg = self.params["popularity_regularization"]
        movie_sums = np.bincount(
            movie_indices, weights=values, minlength=len(self._movie_ids)
        )
        self._popularity_scores = (movie_sums + popularity_reg * self.global_mean) / (
            self._movie_counts + popularity_reg
        )
        self._seen_by_user = {
            int(user_id): set(group["movieId"].astype(int))
            for user_id, group in data.groupby("userId", sort=True)
        }

        # Stable ordering makes the same seed produce the same factors across runs.
        order = np.lexsort((movie_indices, user_indices))
        user_indices = user_indices[order]
        movie_indices = movie_indices[order]
        values = values[order]
        rng = np.random.default_rng(self.params["seed"])
        scale = 0.05
        user_factors = rng.normal(
            0.0, scale, size=(len(self._user_ids), self.params["n_factors"])
        )
        movie_factors = rng.normal(
            0.0, scale, size=(len(self._movie_ids), self.params["n_factors"])
        )
        learning_rate = self.params["learning_rate"]
        regularization = self.params["factor_regularization"]
        baseline = self.global_mean + user_bias[user_indices] + movie_bias[movie_indices]
        for _ in range(self.params["epochs"]):
            for row_index in rng.permutation(len(values)):
                user_index = user_indices[row_index]
                movie_index = movie_indices[row_index]
                user_vector = user_factors[user_index]
                movie_vector = movie_factors[movie_index]
                old_user_vector = user_vector.copy()
                error = values[row_index] - baseline[row_index] - user_vector @ movie_vector
                user_vector += learning_rate * (
                    error * movie_vector - regularization * user_vector
                )
                movie_vector += learning_rate * (
                    error * old_user_vector - regularization * movie_vector
                )
        self._user_factors = user_factors
        self._movie_factors = movie_factors
        return self

    def predict(
        self,
        user_ids: Iterable[int],
        movie_ids: Iterable[int],
        *,
        algorithm: str = "auto",
    ) -> np.ndarray:
        """Predict ratings; unknown or sparse IDs fall back to regularized biases."""
        self._require_fitted()
        if algorithm not in {"auto", "baseline", "mf"}:
            raise ValueError("algorithm must be one of: auto, baseline, mf")
        users = list(user_ids)
        movies = list(movie_ids)
        if len(users) != len(movies):
            raise ValueError("user_ids and movie_ids must have the same length")
        assert self.global_mean is not None
        assert self._user_bias is not None and self._movie_bias is not None
        assert self._user_counts is not None and self._movie_counts is not None
        assert self._user_factors is not None and self._movie_factors is not None

        user_indices = np.fromiter(
            (self._user_index.get(int(user_id), -1) for user_id in users),
            dtype=np.int64,
            count=len(users),
        )
        movie_indices = np.fromiter(
            (self._movie_index.get(int(movie_id), -1) for movie_id in movies),
            dtype=np.int64,
            count=len(movies),
        )
        predictions = np.full(len(users), self.global_mean, dtype=np.float64)
        known_users = user_indices >= 0
        known_movies = movie_indices >= 0
        predictions[known_users] += self._user_bias[user_indices[known_users]]
        predictions[known_movies] += self._movie_bias[movie_indices[known_movies]]
        minimum_user_count = self.params["min_user_ratings"]
        minimum_movie_count = self.params["min_item_ratings"]
        has_factors = known_users & known_movies
        has_factors[known_users] &= (
            self._user_counts[user_indices[known_users]] >= minimum_user_count
        )
        has_factors[known_movies] &= (
            self._movie_counts[movie_indices[known_movies]] >= minimum_movie_count
        )
        if algorithm != "baseline" and has_factors.any():
            selected_users = user_indices[has_factors]
            selected_movies = movie_indices[has_factors]
            predictions[has_factors] += np.sum(
                self._user_factors[selected_users] * self._movie_factors[selected_movies], axis=1
            )
        return np.clip(predictions, 0.5, 5.0)

    def evaluate(self, ratings: pd.DataFrame, *, algorithm: str = "auto") -> RatingMetrics:
        """Measure RMSE and MAE on a held-out ratings table."""
        data = _validate_ratings(ratings, unique_pairs=False)
        predictions = self.predict(data["userId"], data["movieId"], algorithm=algorithm)
        errors = predictions - data["rating"].to_numpy(dtype=np.float64)
        return RatingMetrics(
            count=len(data),
            rmse=float(np.sqrt(np.mean(np.square(errors)))),
            mae=float(np.mean(np.abs(errors))),
        )

    def popular_movies(
        self,
        top_k: int = 10,
        *,
        exclude_movie_ids: Iterable[int] = (),
    ) -> list[MoviePrediction]:
        """Return items ranked by training-only, shrinkage-adjusted mean rating."""
        self._require_fitted()
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k must be a non-negative integer")
        if top_k == 0:
            return []
        assert self._movie_ids is not None and self._popularity_scores is not None
        excluded = {int(movie_id) for movie_id in exclude_movie_ids}
        candidate_indices = np.flatnonzero(~np.isin(self._movie_ids, list(excluded)))
        order = np.lexsort(
            (self._movie_ids[candidate_indices], -self._popularity_scores[candidate_indices])
        )
        return [
            MoviePrediction(
                movie_id=int(self._movie_ids[index]),
                predicted_rating=float(self._popularity_scores[index]),
            )
            for index in candidate_indices[order[:top_k]]
        ]

    def popularity_scores(self, movie_ids: Iterable[int]) -> np.ndarray:
        """Return shrinkage-adjusted training rating means in the requested order."""
        self._require_fitted()
        assert self._popularity_scores is not None and self.global_mean is not None
        return np.asarray(
            [
                self._popularity_scores[self._movie_index[int(movie_id)]]
                if int(movie_id) in self._movie_index
                else self.global_mean
                for movie_id in movie_ids
            ],
            dtype=np.float64,
        )

    def recommend_for_user(
        self,
        user_id: int,
        top_k: int = 10,
        *,
        candidate_movie_ids: Iterable[int] | None = None,
        exclude_movie_ids: Iterable[int] = (),
    ) -> list[MoviePrediction]:
        """Recommend unseen items, using popularity for cold-start and sparse users."""
        self._require_fitted()
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k must be a non-negative integer")
        if top_k == 0:
            return []
        user_id = int(user_id)
        assert self._movie_ids is not None and self._movie_counts is not None
        candidates = (
            self._movie_ids.tolist()
            if candidate_movie_ids is None
            else sorted({int(movie_id) for movie_id in candidate_movie_ids})
        )
        excluded = set(exclude_movie_ids) | self._seen_by_user.get(user_id, set())
        candidates = [movie_id for movie_id in candidates if movie_id not in excluded]
        if not candidates:
            return []

        user_index = self._user_index.get(user_id)
        sparse_user = (
            user_index is None
            or self._user_counts is None
            or self._user_counts[user_index] < self.params["min_user_ratings"]
        )
        if sparse_user:
            assert self._popularity_scores is not None and self.global_mean is not None
            scores = np.asarray(
                [
                    self._popularity_scores[self._movie_index[movie_id]]
                    if movie_id in self._movie_index
                    else self.global_mean
                    for movie_id in candidates
                ],
                dtype=np.float64,
            )
        else:
            scores = self.predict([user_id] * len(candidates), candidates)
        movie_array = np.asarray(candidates, dtype=np.int64)
        order = np.lexsort((movie_array, -scores))[:top_k]
        return [
            MoviePrediction(movie_id=candidates[index], predicted_rating=float(scores[index]))
            for index in order
        ]

    def save(self, path: Path) -> None:
        """Persist the fitted model and its training configuration."""
        self._require_fitted()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"format_version": MODEL_FORMAT_VERSION, "model": self}, path)

    @classmethod
    def load(cls, path: Path) -> CollaborativeRecommender:
        """Load a model saved by :meth:`save`."""
        payload = joblib.load(Path(path))
        if not isinstance(payload, dict) or payload.get("format_version") != MODEL_FORMAT_VERSION:
            raise ValueError(f"Unsupported collaborative model format in {path}")
        model = payload.get("model")
        if not isinstance(model, cls) or not model.is_fitted:
            raise ValueError(f"Invalid fitted collaborative model in {path}")
        return model


def _train_and_report(
    train_path: Path, validation_path: Path, model_path: Path
) -> dict[str, object]:
    train = pd.read_csv(train_path)
    validation = pd.read_csv(validation_path)
    model = CollaborativeRecommender().fit(train)
    metrics = {
        "training_ratings": model.training_rating_count,
        "users": model.user_count,
        "movies": model.movie_count,
        "validation_ratings": len(validation),
        "baseline": asdict(model.evaluate(validation, algorithm="baseline")),
        "matrix_factorization": asdict(model.evaluate(validation, algorithm="mf")),
        "configuration": model.params,
    }
    model.save(model_path)
    report_path = model_path.with_name("collaborative_metrics.json")
    report_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    """Train on the prepared training split and compare both models on validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, default=PROCESSED_DATA_DIR / "train_ratings.csv")
    parser.add_argument(
        "--validation", type=Path, default=PROCESSED_DATA_DIR / "validation_ratings.csv"
    )
    parser.add_argument(
        "--output", type=Path, default=ARTIFACTS_DIR / "collaborative_recommender.joblib"
    )
    args = parser.parse_args()
    metrics = _train_and_report(args.train, args.validation, args.output)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
