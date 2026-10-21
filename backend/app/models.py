"""SQLAlchemy models for local user ratings."""

from sqlalchemy import BigInteger, CheckConstraint, Integer, UniqueConstraint
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
