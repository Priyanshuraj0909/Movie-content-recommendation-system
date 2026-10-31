"""Adopt legacy ratings and add visitor profiles without changing existing rows."""

import sqlalchemy as sa
from alembic import op

revision = "0001_visitor_profiles"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "user_ratings" not in existing:
        op.create_table(
            "user_ratings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("movie_id", sa.Integer(), nullable=False),
            sa.Column("rating", sa.Float(), nullable=False),
            sa.UniqueConstraint("user_id", "movie_id", name="uq_user_rating_movie"),
            sa.CheckConstraint("user_id > 0", name="ck_user_rating_user_positive"),
            sa.CheckConstraint("movie_id > 0", name="ck_user_rating_movie_positive"),
            sa.CheckConstraint("rating >= 0.5 AND rating <= 5.0", name="ck_user_rating_scale"),
        )
        op.create_index("ix_user_ratings_user_id", "user_ratings", ["user_id"])
    else:
        columns = {row["name"] for row in sa.inspect(op.get_bind()).get_columns("user_ratings")}
        if not {"id", "user_id", "movie_id", "rating"}.issubset(columns):
            raise RuntimeError(
                "Unexpected legacy ratings schema; migration stopped without deleting data"
            )
    if "visitor_profiles" not in existing:
        op.create_table(
            "visitor_profiles",
            sa.Column("user_id", sa.BigInteger(), primary_key=True),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "watchlist_entries" not in existing:
        op.create_table(
            "watchlist_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("movie_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "movie_id", name="uq_watchlist_movie"),
        )
        op.create_index("ix_watchlist_entries_user_id", "watchlist_entries", ["user_id"])
    if "feedback_events" not in existing:
        op.create_table(
            "feedback_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("movie_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_feedback_events_user_id", "feedback_events", ["user_id"])


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore an approved database backup")
