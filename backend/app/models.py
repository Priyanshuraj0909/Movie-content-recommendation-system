"""SQLAlchemy models for local user ratings."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class UserRating(Base):
    """The latest explicit rating a local user gave a movie."""

    __tablename__ = "user_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_user_rating_movie"),
        CheckConstraint("user_id > 0", name="ck_user_rating_user_positive"),
        CheckConstraint("movie_id > 0", name="ck_user_rating_movie_positive"),
        CheckConstraint("rating >= 0.5 AND rating <= 5.0", name="ck_user_rating_scale"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    movie_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[float] = mapped_column(nullable=False)


class VisitorProfile(Base):
    """Anonymous profile; possession of its random bearer secret grants access."""

    __tablename__ = "visitor_profiles"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"
    __table_args__ = (UniqueConstraint("user_id", "movie_id", name="uq_watchlist_movie"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    movie_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class FeedbackEvent(Base):
    """Minimal explicit interactions; never stores IP addresses or bearer secrets."""

    __tablename__ = "feedback_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    movie_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
