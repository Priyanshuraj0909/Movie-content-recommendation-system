"""FastAPI application for searching movies and serving recommendations."""

import os
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_session, make_session_factory, sqlite_url
from backend.app.models import UserRating
from backend.app.schemas import (
    ExternalMovieRatings,
    HealthResponse,
    MovieResponse,
    RatingCreate,
    RatingResponse,
    RecommendationResponse,
)
from backend.app.services.external_ratings import get_movie_ratings
from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores.astype(np.float64)
    low, high = float(np.min(scores)), float(np.max(scores))
    if high <= low:
        return np.zeros(scores.shape, dtype=np.float64)
    return (scores - low) / (high - low)


def _load_default_state() -> tuple[ContentRecommender, CollaborativeRecommender, pd.DataFrame]:
    """Load artifacts produced by the Phase 3–5 training commands."""
    required_files = (
        ARTIFACTS_DIR / "content_recommender.joblib",
        ARTIFACTS_DIR / "collaborative_recommender.joblib",
        PROCESSED_DATA_DIR / "movies_with_tags.csv",
    )
    missing = [path for path in required_files if not path.is_file()]
    if missing:
        paths = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"Demo files are missing ({paths}). Run `bash scripts/setup_demo.sh`.")
    content = ContentRecommender.load(ARTIFACTS_DIR / "content_recommender.joblib")
    collaborative = CollaborativeRecommender.load(
        ARTIFACTS_DIR / "collaborative_recommender.joblib"
    )
    movies = pd.read_csv(PROCESSED_DATA_DIR / "movies_with_tags.csv")
    links_path = PROCESSED_DATA_DIR / "links.csv"
    if links_path.is_file():
        links = pd.read_csv(links_path, dtype={"imdbId": "string", "tmdbId": "string"})
        movies = movies.merge(links, on="movieId", how="left", validate="one_to_one")
    return content, collaborative, movies


def _movie_table(movies: pd.DataFrame) -> pd.DataFrame:
    columns = ["movieId", "title", "genres"]
    for optional in ("tmdbId", "imdbId"):
        if optional in movies.columns:
            columns.append(optional)
    table = movies.loc[:, columns].copy()
    table["movieId"] = pd.to_numeric(table["movieId"], errors="raise").astype(int)
    table["title"] = table["title"].fillna("").astype(str)
    table["genres"] = table["genres"].fillna("").astype(str)
    return table.drop_duplicates("movieId").set_index("movieId", drop=False)


def create_app(
    *,
    content_model: ContentRecommender | None = None,
    collaborative_model: CollaborativeRecommender | None = None,
    movies: pd.DataFrame | None = None,
    database_url: str | None = None,
) -> FastAPI:
    """Build an app, optionally injecting fitted models and a test database."""
    movie_table: pd.DataFrame | None = None
    if movies is not None:
        movie_table = _movie_table(movies)
    configured_database_url = database_url or os.environ.get("DATABASE_URL")
    if configured_database_url is None and os.environ.get("VERCEL"):
        raise RuntimeError("Set DATABASE_URL to a persistent PostgreSQL database for Vercel.")
    factory = make_session_factory(
        configured_database_url or sqlite_url(ARTIFACTS_DIR / "recommender.db")
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal content_model, collaborative_model, movie_table
        if content_model is None or collaborative_model is None or movie_table is None:
            loaded_content, loaded_collaborative, loaded_movies = _load_default_state()
            content_model = content_model or loaded_content
            collaborative_model = collaborative_model or loaded_collaborative
            if movie_table is None:
                movie_table = _movie_table(loaded_movies)
        assert content_model is not None and collaborative_model is not None
        assert movie_table is not None
        app.state.content_model = content_model
        app.state.collaborative_model = collaborative_model
        app.state.movies = movie_table
        yield

    app = FastAPI(
        title="Movie Recommendation API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.session_factory = factory
    if content_model is not None and collaborative_model is not None and movie_table is not None:
        app.state.content_model = content_model
        app.state.collaborative_model = collaborative_model
        app.state.movies = movie_table

    def session_dependency() -> Iterable[Session]:
        yield from get_session(factory)

    SessionDep = Annotated[Session, Depends(session_dependency)]
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        return HealthResponse(status="ok", movies_loaded=len(request.app.state.movies))

    @router.get("/movies/search", response_model=list[MovieResponse])
    def search_movies(
        request: Request,
        q: Annotated[str, Query(min_length=1, max_length=100)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> list[MovieResponse]:
        movies_table = request.app.state.movies
        matches = movies_table[
            movies_table["title"].str.contains(q.strip(), case=False, regex=False)
        ]
        return [
            MovieResponse(movie_id=int(row.movieId), title=row.title, genres=row.genres)
            for row in matches.head(limit).itertuples()
        ]

    @router.get("/movies/external-ratings", response_model=list[ExternalMovieRatings])
    def external_ratings(
        request: Request,
        movie_ids: Annotated[list[int], Query(min_length=1, max_length=30)],
    ) -> list[ExternalMovieRatings]:
        movie_table = request.app.state.movies
        unique_ids = list(dict.fromkeys(movie_ids))
        unknown = [movie_id for movie_id in unique_ids if movie_id not in movie_table.index]
        if unknown:
            raise HTTPException(status_code=404, detail="One or more movies were not found")
        rows = [movie_table.loc[movie_id] for movie_id in unique_ids]
        with ThreadPoolExecutor(max_workers=6) as pool:
            values = list(pool.map(
                lambda row: get_movie_ratings(
                    int(row.movieId), str(row.title),
                    getattr(row, "tmdbId", None), getattr(row, "imdbId", None),
                ),
                rows,
            ))
        return [ExternalMovieRatings.model_validate(value) for value in values]

    @router.get("/recommendations/similar/{movie_id}", response_model=list[RecommendationResponse])
    def similar_movies(
        movie_id: int,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
    ) -> list[RecommendationResponse]:
        movie_row = request.app.state.movies
        if movie_id not in movie_row.index:
            raise HTTPException(status_code=404, detail="Movie not found")
        try:
            recommendations = request.app.state.content_model.similar_movies(movie_id, top_k=limit)
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="Movie not found in recommendation model"
            ) from error
        return [
            RecommendationResponse(
                movie_id=item.movie_id,
                title=item.title,
                genres=str(movie_row.loc[item.movie_id, "genres"]),
                score=item.score,
            )
            for item in recommendations
        ]

    @router.get("/recommendations/users/{user_id}", response_model=list[RecommendationResponse])
    def user_recommendations(
        user_id: int,
        request: Request,
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
    ) -> list[RecommendationResponse]:
        if user_id <= 0:
            raise HTTPException(status_code=422, detail="user_id must be positive")
        content: ContentRecommender = request.app.state.content_model
        collaborative: CollaborativeRecommender = request.app.state.collaborative_model
        rated_rows = session.scalars(select(UserRating).where(UserRating.user_id == user_id)).all()
        user_ratings = {row.movie_id: row.rating for row in rated_rows}
        candidates = [int(movie_id) for movie_id in collaborative.movie_ids]
        excluded = set(user_ratings)
        excluded.update(collaborative.seen_movie_ids(user_id))
        candidates = [movie_id for movie_id in candidates if movie_id not in excluded]
        if not candidates:
            return []

        liked = sorted(movie_id for movie_id, rating in user_ratings.items() if rating >= 4.0)
        if not liked:
            scores = collaborative.popularity_scores(candidates)
            predictions = np.full(len(candidates), np.nan)
        else:
            content_scores = _normalize(content.score_profile(liked, candidates))
            collaborative_scores = _normalize(
                collaborative.predict([user_id] * len(candidates), candidates, algorithm="mf")
            )
            scores = 0.25 * content_scores + 0.75 * collaborative_scores
            predictions = collaborative.predict([user_id] * len(candidates), candidates)

        item_ids = np.asarray(candidates, dtype=np.int64)
        order = np.lexsort((item_ids, -scores))[:limit]
        movie_table = request.app.state.movies
        results = []
        for index in order:
            movie_id = candidates[index]
            if movie_id not in movie_table.index:
                continue
            results.append(
                RecommendationResponse(
                    movie_id=movie_id,
                    title=str(movie_table.loc[movie_id, "title"]),
                    genres=str(movie_table.loc[movie_id, "genres"]),
                    score=float(scores[index]),
                    predicted_rating=(
                        float(predictions[index]) if np.isfinite(predictions[index]) else None
                    ),
                )
            )
        return results

    @router.post("/ratings", response_model=RatingResponse, status_code=201)
    def save_rating(
        payload: RatingCreate,
        request: Request,
        session: SessionDep,
    ) -> RatingResponse:
        if payload.movie_id not in request.app.state.movies.index:
            raise HTTPException(status_code=404, detail="Movie not found")
        existing = session.scalar(
            select(UserRating).where(
                UserRating.user_id == payload.user_id,
                UserRating.movie_id == payload.movie_id,
            )
        )
        if existing is None:
            existing = UserRating(**payload.model_dump())
            session.add(existing)
        else:
            existing.rating = payload.rating
        session.commit()
        session.refresh(existing)
        return RatingResponse.model_validate(existing)

    app.include_router(router, prefix="/api")
    return app


app = create_app()
