"""Typed API request and response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    movies_loaded: int


class MovieResponse(BaseModel):
    movie_id: int
    title: str
    genres: str


class MovieDetails(MovieResponse):
    summary: str | None = None
    runtime_minutes: float | None = None
    languages: list[str] = []
    source_url: str | None = None
    license_url: str | None = None
    attribution: str | None = None


class RecommendationResponse(MovieResponse):
    score: float
    predicted_rating: float | None = None
    reason: str = ""


class ProfileCreated(BaseModel):
    user_id: int
    token: str


class WatchlistChange(BaseModel):
    movie_id: int = Field(gt=0)


class PublicRatingSource(BaseModel):
    rating: float | None = None
    vote_count: int | None = None
    tmdb_id: str | None = None
    imdb_id: str | None = None
    url: str | None = None


class ExternalMovieRatings(BaseModel):
    movie_id: int
    title: str
    tmdb: PublicRatingSource
    imdb: PublicRatingSource


class RatingCreate(BaseModel):
    user_id: int = Field(gt=0, le=9_007_199_254_740_991)
    movie_id: int = Field(gt=0)
    rating: float = Field(ge=0.5, le=5.0, multiple_of=0.5)


class RatingResponse(RatingCreate):
    model_config = ConfigDict(from_attributes=True)
