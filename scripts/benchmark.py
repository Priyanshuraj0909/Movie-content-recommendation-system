"""Measure local model startup and inference timings for the MovieLens demo."""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from collections.abc import Callable

import pandas as pd

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender


def measure(function: Callable[[], object], repeats: int = 40) -> dict[str, float]:
    """Return warm median and p95 elapsed time in milliseconds."""
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(float(pd.Series(samples).quantile(0.95)), 3),
        "repeats": repeats,
    }


def timed_load(label: str, loader: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    result = loader()
    return result, round(time.perf_counter() - started, 3)


def main() -> None:
    """Load local artifacts and print reproducible, warm in-process timings."""
    content_path = ARTIFACTS_DIR / "content_recommender.joblib"
    collaborative_path = ARTIFACTS_DIR / "collaborative_recommender.joblib"
    movies_path = PROCESSED_DATA_DIR / "movies_with_tags.csv"
    for path in (content_path, collaborative_path, movies_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing benchmark input {path}; complete setup first")

    content, content_load = timed_load("content", lambda: ContentRecommender.load(content_path))
    collaborative, collaborative_load = timed_load(
        "collaborative", lambda: CollaborativeRecommender.load(collaborative_path)
    )
    movies = pd.read_csv(movies_path)
    candidate_ids = collaborative.movie_ids[:1000]

    report = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
        "dataset": {
            "movie_metadata_rows": len(movies),
            "training_catalog_movies": collaborative.movie_count,
        },
        "model_artifacts": {
            "content_bytes": content_path.stat().st_size,
            "collaborative_bytes": collaborative_path.stat().st_size,
            "content_load_seconds": content_load,
            "collaborative_load_seconds": collaborative_load,
        },
        "warm_operations": {
            "title_search_9742_rows": measure(
                lambda: movies[movies["title"].str.contains("star", case=False, regex=False)]
            ),
            "similar_movies_top_10": measure(lambda: content.similar_movies(1, top_k=10)),
            "predict_1000_user_movie_pairs": measure(
                lambda: collaborative.predict([1] * len(candidate_ids), candidate_ids),
                repeats=20,
            ),
            "recommend_for_user_top_10": measure(
                lambda: collaborative.recommend_for_user(1, top_k=10), repeats=20
            ),
        },
        "method": (
            "Single local process, artifacts already on disk, timings warmed by repeated calls. "
            "No network latency or concurrent traffic included."
        ),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
