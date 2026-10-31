"""FastAPI application for searching movies and serving recommendations."""

import hashlib
import json
import os
import secrets
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database import get_session, make_session_factory, sqlite_url
from backend.app.models import FeedbackEvent, UserRating, VisitorProfile, WatchlistEntry
from backend.app.schemas import (
    ExternalMovieRatings,
    HealthResponse,
    MovieDetails,
    MovieResponse,
    ProfileCreated,
    RatingCreate,
    RatingResponse,
    RecommendationResponse,
    WatchlistChange,
)
from backend.app.services.external_ratings import get_movie_ratings
from recommender import __version__
from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender
from recommender.models.semantic import DEFAULT_DIRECTORY, SemanticIndex
from recommender.services.visitor import recommend_visitor


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
    plots_path = PROCESSED_DATA_DIR / "movie_plots.csv"
    if plots_path.is_file():
        movies = movies.merge(
            pd.read_csv(plots_path), on="movieId", how="left", validate="one_to_one"
        )
    return content, collaborative, movies


def _movie_table(movies: pd.DataFrame) -> pd.DataFrame:
    columns = ["movieId", "title", "genres"]
    for optional in (
        "tmdbId",
        "imdbId",
        "summary",
        "runtime_minutes",
        "languages_json",
        "source_url",
        "license_url",
    ):
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
    semantic_index: SemanticIndex | None = None,
) -> FastAPI:
    """Build an app, optionally injecting fitted models and a test database."""
    use_default_semantic = content_model is None and movies is None
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
        nonlocal content_model, collaborative_model, movie_table, semantic_index
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
        if use_default_semantic and (DEFAULT_DIRECTORY / "manifest.json").is_file():
            semantic_index = semantic_index or SemanticIndex()
        app.state.semantic_index = semantic_index
        yield

    app = FastAPI(
        title="Movie Recommendation API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.session_factory = factory
    app.state.semantic_index = semantic_index
    if content_model is not None and collaborative_model is not None and movie_table is not None:
        app.state.content_model = content_model
        app.state.collaborative_model = collaborative_model
        app.state.movies = movie_table

    def session_dependency() -> Iterable[Session]:
        yield from get_session(factory)

    SessionDep = Annotated[Session, Depends(session_dependency)]
    router = APIRouter()

    @app.middleware("http")
    async def private_response_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(
            ("/api/profiles", "/api/ratings", "/api/recommendations/users")
        ):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    def authorize(user_id: int, session: Session, token: str | None) -> None:
        if not 0 < user_id <= 9_007_199_254_740_991:
            raise HTTPException(status_code=422, detail="Invalid profile identifier")
        profile = session.get(VisitorProfile, user_id)
        if profile is None:
            if os.environ.get("VERCEL") or token:
                raise HTTPException(
                    status_code=401, detail="Create or restore your private profile"
                )
            return  # Existing numeric profiles remain supported for local Streamlit use only.
        digest = hashlib.sha256((token or "").encode()).hexdigest()
        if not secrets.compare_digest(profile.token_hash, digest):
            raise HTTPException(status_code=401, detail="A valid profile recovery code is required")

    def check_write_budget(user_id: int, session: Session):
        recent = session.scalar(
            select(func.count())
            .select_from(FeedbackEvent)
            .where(
                FeedbackEvent.user_id == user_id,
                FeedbackEvent.created_at >= datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        if recent is not None and recent >= 60:
            raise HTTPException(
                status_code=429, detail="Please wait a minute before saving more feedback"
            )

    @router.post("/profiles", response_model=ProfileCreated, status_code=201)
    def create_profile(session: SessionDep) -> ProfileCreated:
        user_id = 1_000_000_000_000 + secrets.randbelow(8_000_000_000_000_000)
        token = secrets.token_urlsafe(32)
        session.add(
            VisitorProfile(user_id=user_id, token_hash=hashlib.sha256(token.encode()).hexdigest())
        )
        session.commit()
        return ProfileCreated(user_id=user_id, token=token)

    @router.get("/profiles/{user_id}/ratings", response_model=list[RatingResponse])
    def rating_history(
        user_id: int,
        session: SessionDep,
        x_profile_token: Annotated[str | None, Header(max_length=128)] = None,
    ):
        authorize(user_id, session, x_profile_token)
        return session.scalars(
            select(UserRating).where(UserRating.user_id == user_id).order_by(UserRating.movie_id)
        ).all()

    @router.get("/profiles/{user_id}/watchlist", response_model=list[MovieResponse])
    def watchlist(
        user_id: int,
        request: Request,
        session: SessionDep,
        x_profile_token: Annotated[str | None, Header(max_length=128)] = None,
    ):
        authorize(user_id, session, x_profile_token)
        rows = session.scalars(
            select(WatchlistEntry)
            .where(WatchlistEntry.user_id == user_id)
            .order_by(WatchlistEntry.created_at.desc(), WatchlistEntry.movie_id)
        ).all()
        table = request.app.state.movies
        return [
            MovieResponse(
                movie_id=row.movie_id,
                title=str(table.loc[row.movie_id, "title"]),
                genres=str(table.loc[row.movie_id, "genres"]),
            )
            for row in rows
            if row.movie_id in table.index
        ]

    @router.put("/profiles/{user_id}/watchlist", response_model=WatchlistChange)
    def add_watchlist(
        user_id: int,
        payload: WatchlistChange,
        request: Request,
        session: SessionDep,
        x_profile_token: Annotated[str | None, Header(max_length=128)] = None,
    ):
        authorize(user_id, session, x_profile_token)
        check_write_budget(user_id, session)
        if payload.movie_id not in request.app.state.movies.index:
            raise HTTPException(status_code=404, detail="Movie not found")
        existing = session.scalar(
            select(WatchlistEntry).where(
                WatchlistEntry.user_id == user_id, WatchlistEntry.movie_id == payload.movie_id
            )
        )
        if existing is None:
            session.add(WatchlistEntry(user_id=user_id, movie_id=payload.movie_id))
            session.add(
                FeedbackEvent(user_id=user_id, movie_id=payload.movie_id, event_type="watchlist")
            )
            try:
                session.commit()
            except IntegrityError:
                # Concurrent saves of the same valid item are idempotent.
                session.rollback()
                persisted = session.scalar(
                    select(WatchlistEntry).where(
                        WatchlistEntry.user_id == user_id,
                        WatchlistEntry.movie_id == payload.movie_id,
                    )
                )
                if persisted is None:
                    raise HTTPException(
                        status_code=409, detail="Could not save watchlist item"
                    ) from None
        return payload

    @router.delete("/profiles/{user_id}/watchlist/{movie_id}")
    def remove_watchlist(
        user_id: int,
        movie_id: int,
        session: SessionDep,
        x_profile_token: Annotated[str | None, Header(max_length=128)] = None,
    ):
        authorize(user_id, session, x_profile_token)
        existing = session.scalar(
            select(WatchlistEntry).where(
                WatchlistEntry.user_id == user_id, WatchlistEntry.movie_id == movie_id
            )
        )
        if existing is not None:
            session.delete(existing)
            session.commit()
        return {"removed": movie_id}

    @router.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        return HealthResponse(status="ok", movies_loaded=len(request.app.state.movies))

    @router.get("/capabilities")
    def capabilities(request: Request):
        index = request.app.state.semantic_index
        return {
            "semantic_search": index is not None,
            "semantic_movies": len(index.movie_ids) if index is not None else 0,
            "private_profiles": True,
        }

    @router.get("/movies/semantic-search", response_model=list[RecommendationResponse])
    def semantic_search(
        request: Request,
        q: Annotated[str, Query(min_length=3, max_length=500)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        genre: Annotated[str | None, Query(max_length=40)] = None,
        language: Annotated[str | None, Query(max_length=40)] = None,
        max_runtime: Annotated[float | None, Query(gt=0, le=1000)] = None,
    ):
        index = request.app.state.semantic_index
        if index is None:
            raise HTTPException(
                status_code=503, detail="Story search is not prepared; title search is available"
            )
        table = request.app.state.movies
        allowed = set(table.index)
        if genre:
            allowed &= set(
                table.index[table.genres.str.split("|").apply(lambda parts: genre in parts)]
            )
        if max_runtime is not None:
            allowed &= set(
                table.index[
                    pd.to_numeric(
                        table.get("runtime_minutes", pd.Series(index=table.index, dtype=float)),
                        errors="coerce",
                    ).le(max_runtime)
                ]
            )
        if language:
            languages = table.get("languages_json", pd.Series("[]", index=table.index)).fillna("[]")
            allowed &= set(
                table.index[
                    languages.apply(
                        lambda value: (
                            language.casefold() in {name.casefold() for name in json.loads(value)}
                        )
                    )
                ]
            )
        return [
            RecommendationResponse(
                movie_id=mid,
                title=str(table.loc[mid, "title"]),
                genres=str(table.loc[mid, "genres"]),
                score=score,
                reason="Story similarity to your search, using an attributed plot summary.",
            )
            for mid, score in index.search(q.strip(), limit=limit, allowed_ids=allowed)
        ]

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
            values = list(
                pool.map(
                    lambda row: get_movie_ratings(
                        int(row.movieId),
                        str(row.title),
                        getattr(row, "tmdbId", None),
                        getattr(row, "imdbId", None),
                    ),
                    rows,
                )
            )
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
                reason=(
                    f"Shares title, genre or tag features with {movie_row.loc[movie_id, 'title']}."
                ),
            )
            for item in recommendations
        ]

    @router.get("/recommendations/popular", response_model=list[RecommendationResponse])
    def popular_recommendations(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 10):
        table = request.app.state.movies.to_dict("index")
        return [
            RecommendationResponse(
                movie_id=pick.movie_id,
                title=table[pick.movie_id]["title"],
                genres=table[pick.movie_id]["genres"],
                score=pick.score,
                reason=pick.reason,
            )
            for pick in recommend_visitor(
                request.app.state.content_model,
                request.app.state.collaborative_model,
                {},
                table,
                limit=limit,
            )
        ]

    @router.get("/recommendations/users/{user_id}", response_model=list[RecommendationResponse])
    def user_recommendations(
        user_id: int,
        request: Request,
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
        diversity: Annotated[float, Query(ge=0, le=0.5)] = 0.12,
        x_profile_token: Annotated[str | None, Header(max_length=128)] = None,
    ) -> list[RecommendationResponse]:
        if user_id <= 0:
            raise HTTPException(status_code=422, detail="user_id must be positive")
        authorize(user_id, session, x_profile_token)
        content: ContentRecommender = request.app.state.content_model
        collaborative: CollaborativeRecommender = request.app.state.collaborative_model
        rated_rows = session.scalars(select(UserRating).where(UserRating.user_id == user_id)).all()
        user_ratings = {row.movie_id: row.rating for row in rated_rows}
        movie_table = request.app.state.movies
        catalog = movie_table.to_dict("index")
        return [
            RecommendationResponse(
                movie_id=pick.movie_id,
                title=catalog[pick.movie_id]["title"],
                genres=catalog[pick.movie_id]["genres"],
                score=pick.score,
                predicted_rating=pick.predicted_rating,
                reason=pick.reason,
            )
            for pick in recommend_visitor(
                content, collaborative, user_ratings, catalog, limit=limit, diversity=diversity
            )
        ]

    @router.post("/ratings", response_model=RatingResponse, status_code=201)
    def save_rating(
        payload: RatingCreate,
        request: Request,
        session: SessionDep,
        x_profile_token: Annotated[str | None, Header(max_length=128)] = None,
    ) -> RatingResponse:
        authorize(payload.user_id, session, x_profile_token)
        check_write_budget(payload.user_id, session)
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
        session.add(
            FeedbackEvent(user_id=payload.user_id, movie_id=payload.movie_id, event_type="rating")
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(UserRating).where(
                    UserRating.user_id == payload.user_id, UserRating.movie_id == payload.movie_id
                )
            )
            if existing is None:
                raise HTTPException(
                    status_code=409, detail="Could not save rating; please retry"
                ) from None
            existing.rating = payload.rating
            session.add(
                FeedbackEvent(
                    user_id=payload.user_id, movie_id=payload.movie_id, event_type="rating"
                )
            )
            session.commit()
        session.refresh(existing)
        return RatingResponse.model_validate(existing)

    @router.get("/movies/{movie_id}", response_model=MovieDetails)
    def movie_details(movie_id: int, request: Request):
        table = request.app.state.movies
        if movie_id not in table.index:
            raise HTTPException(status_code=404, detail="Movie not found")
        row = table.loc[movie_id]

        def optional(name):
            value = row.get(name)
            return None if value is None or pd.isna(value) else value

        languages = optional("languages_json")
        return MovieDetails(
            movie_id=movie_id,
            title=row.title,
            genres=row.genres,
            summary=optional("summary"),
            runtime_minutes=optional("runtime_minutes"),
            languages=json.loads(languages) if languages else [],
            source_url=optional("source_url"),
            license_url=optional("license_url"),
            attribution="Wikipedia contributors via CMU Movie Summary Corpus"
            if optional("summary")
            else None,
        )

    app.include_router(router, prefix="/api")
    return app


app = create_app()
