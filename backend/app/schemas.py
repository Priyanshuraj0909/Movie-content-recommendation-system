"""Typed API request and response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    movies_loaded: int


class MovieResponse(BaseModel):
    movie_id: int
    title: str
    genres: str


class RecommendationResponse(MovieResponse):
    score: float
    predicted_rating: float | None = None


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
    user_id: int = Field(gt=0)
    movie_id: int = Field(gt=0)
    rating: float = Field(ge=0.5, le=5.0, multiple_of=0.5)


class RatingResponse(RatingCreate):
    model_config = ConfigDict(from_attributes=True)

