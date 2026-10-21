"""Content-based movie similarity using TF-IDF and cosine similarity."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR

MODEL_FORMAT_VERSION = 1
REQUIRED_COLUMNS = ("movieId", "title", "genres")


@dataclass(frozen=True)
class Recommendation:
    """One movie ranked by content similarity to a query movie."""

    movie_id: int
    title: str
    score: float


def _parse_tags(value: object, movie_id: int) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            tags = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"Movie {movie_id} has invalid tags_json") from error
    elif isinstance(value, (list, tuple)):
        tags = list(value)
    else:
        raise ValueError(f"Movie {movie_id} tags_json must be a JSON array of strings")

    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError(f"Movie {movie_id} tags_json must be a JSON array of strings")
    cleaned = {tag.strip() for tag in tags if tag.strip()}
    return sorted(cleaned, key=lambda tag: (tag.casefold(), tag))


def _feature_documents(movies: pd.DataFrame) -> tuple[np.ndarray, list[str], list[str]]:
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(movies.columns))
    if missing_columns:
        raise ValueError(f"Movie table is missing required columns: {missing_columns}")
    if movies.empty:
        raise ValueError("Movie table must contain at least one movie")

    ids = pd.to_numeric(movies["movieId"], errors="coerce")
    invalid_ids = ids.isna() | (ids <= 0) | ((ids % 1) != 0)
    if invalid_ids.any():
        invalid_count = int(invalid_ids.sum())
        raise ValueError(f"movieId must contain positive integer IDs ({invalid_count} invalid)")
    movie_ids = ids.astype("int64").to_numpy()
    if len(np.unique(movie_ids)) != len(movie_ids):
        raise ValueError("movieId values must be unique")

    titles = movies["title"].fillna("").astype(str).str.strip().tolist()
    genres = movies["genres"].fillna("").astype(str).str.strip().tolist()
    if any(not title for title in titles):
        raise ValueError("Movie titles must not be blank")

    tag_values = movies["tags_json"].tolist() if "tags_json" in movies else [None] * len(movies)
    documents: list[str] = []
    for movie_id, title, genre_text, tags_value in zip(
        movie_ids, titles, genres, tag_values, strict=True
    ):
        tags = _parse_tags(tags_value, int(movie_id))
        genre_tokens = genre_text.replace("|", " ")
        documents.append(" ".join((title, genre_tokens, " ".join(tags))))
    return movie_ids, titles, documents


class ContentRecommender:
    """Rank movies using normalized title, genre, and user-tag text features."""

    def __init__(self) -> None:
        self.vectorizer: TfidfVectorizer | None = None
        self._tfidf: csr_matrix | None = None
        self._movie_ids: np.ndarray | None = None
        self._titles: tuple[str, ...] = ()
        self._index_by_id: dict[int, int] = {}

    @property
    def is_fitted(self) -> bool:
        return self.vectorizer is not None and self._tfidf is not None

    @property
    def movie_count(self) -> int:
        self._require_fitted()
        assert self._movie_ids is not None
        return len(self._movie_ids)

    def _require_fitted(self) -> None:
        if not self.is_fitted:
            raise RuntimeError("ContentRecommender must be fitted before use")

    def fit(self, movies: pd.DataFrame) -> ContentRecommender:
        """Fit TF-IDF features from movie titles, genres, and aggregated tag arrays."""
        movie_ids, titles, documents = _feature_documents(movies)
        vectorizer = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            token_pattern=r"(?u)\b[\w][\w'-]*\b",
            ngram_range=(1, 2),
            sublinear_tf=True,
            norm="l2",
        )
        try:
            tfidf = vectorizer.fit_transform(documents).tocsr()
        except ValueError as error:
            raise ValueError("Movie metadata produced no usable text features") from error

        self.vectorizer = vectorizer
        self._tfidf = tfidf
        self._movie_ids = movie_ids
        self._titles = tuple(titles)
        self._index_by_id = {int(movie_id): index for index, movie_id in enumerate(movie_ids)}
        return self

    @classmethod
    def from_csv(cls, path: Path) -> ContentRecommender:
        """Load a prepared ``movies_with_tags.csv`` file and fit the model."""
        return cls().fit(pd.read_csv(path))

    def score_profile(
        self,
        seed_movie_ids: Iterable[int],
        candidate_movie_ids: Iterable[int],
    ) -> np.ndarray:
        """Score candidates by cosine similarity to a profile of liked movies.

        Scores are returned in candidate order. Unknown candidates score zero;
        unknown seed IDs raise ``KeyError``. An empty seed list returns zeros.
        """
        self._require_fitted()
        seeds = sorted({int(movie_id) for movie_id in seed_movie_ids})
        candidates = [int(movie_id) for movie_id in candidate_movie_ids]
        if not seeds:
            return np.zeros(len(candidates), dtype=np.float64)
        unknown_seeds = [movie_id for movie_id in seeds if movie_id not in self._index_by_id]
        if unknown_seeds:
            raise KeyError(f"Unknown seed movie IDs: {unknown_seeds[:5]}")

        assert self._tfidf is not None
        seed_indices = [self._index_by_id[movie_id] for movie_id in seeds]
        profile = np.asarray(self._tfidf[seed_indices].sum(axis=0)).ravel()
        profile_norm = np.linalg.norm(profile)
        if profile_norm == 0:
            return np.zeros(len(candidates), dtype=np.float64)
        profile /= profile_norm
        scores = np.zeros(len(candidates), dtype=np.float64)
        known_positions = [
            (position, self._index_by_id[movie_id])
            for position, movie_id in enumerate(candidates)
            if movie_id in self._index_by_id
        ]
        if known_positions:
            positions, indices = zip(*known_positions, strict=True)
            scores[list(positions)] = np.asarray(self._tfidf[list(indices)] @ profile).ravel()
        return scores

    def similar_movies(
        self,
        movie_id: int,
        top_k: int = 10,
        exclude_movie_ids: Iterable[int] = (),
    ) -> list[Recommendation]:
        """Return the highest-scoring similar movies, excluding seed and watched IDs.

        Results are ordered by descending cosine similarity, then ascending movie ID
        for stable ties. Zero-similarity candidates are omitted.
        """
        self._require_fitted()
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k must be a non-negative integer")
        if top_k == 0:
            return []
        try:
            query_id = int(movie_id)
            query_index = self._index_by_id[query_id]
        except (KeyError, TypeError, ValueError) as error:
            raise KeyError(f"Unknown movieId: {movie_id}") from error

        assert self._tfidf is not None and self._movie_ids is not None
        scores = (self._tfidf[query_index] @ self._tfidf.T).toarray().ravel()
        excluded = {query_id, *(int(excluded_id) for excluded_id in exclude_movie_ids)}
        candidate_indices = np.flatnonzero((scores > 0) & ~np.isin(self._movie_ids, list(excluded)))
        order = np.lexsort((self._movie_ids[candidate_indices], -scores[candidate_indices]))
        ranked_indices = candidate_indices[order[:top_k]]
        return [
            Recommendation(
                movie_id=int(self._movie_ids[index]),
                title=self._titles[index],
                score=float(scores[index]),
            )
            for index in ranked_indices
        ]

    def save(self, path: Path) -> None:
        """Persist the fitted sparse model with a format version."""
        self._require_fitted()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"format_version": MODEL_FORMAT_VERSION, "model": self}, path)

    @classmethod
    def load(cls, path: Path) -> ContentRecommender:
        """Load a model saved by :meth:`save`."""
        payload = joblib.load(Path(path))
        if not isinstance(payload, dict) or payload.get("format_version") != MODEL_FORMAT_VERSION:
            raise ValueError(f"Unsupported content model format in {path}")
        model = payload.get("model")
        if not isinstance(model, cls) or not model.is_fitted:
            raise ValueError(f"Invalid fitted content model in {path}")
        return model


def main() -> None:
    """Fit and save the model from locally prepared movie features."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movies", type=Path, default=PROCESSED_DATA_DIR / "movies_with_tags.csv")
    parser.add_argument("--output", type=Path, default=ARTIFACTS_DIR / "content_recommender.joblib")
    args = parser.parse_args()
    model = ContentRecommender.from_csv(args.movies)
    model.save(args.output)
    print(f"Saved content model for {model.movie_count} movies to {args.output}")


if __name__ == "__main__":
    main()
