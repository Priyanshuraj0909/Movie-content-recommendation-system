"""Add independent movie states; preserve all existing profile data."""

import sqlalchemy as sa
from alembic import op

revision = "0002_movie_preferences"
down_revision = "0001_visitor_profiles"
branch_labels = None
depends_on = None


def upgrade():
    if "movie_preferences" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "movie_preferences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("movie_id", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(20), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "movie_id", name="uq_movie_preference"),
            sa.CheckConstraint(
                "state IN ('watched', 'not_interested', 'none')", name="ck_movie_state"
            ),
        )
        op.create_index("ix_movie_preferences_user_id", "movie_preferences", ["user_id"])


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; preserve profile feedback")
