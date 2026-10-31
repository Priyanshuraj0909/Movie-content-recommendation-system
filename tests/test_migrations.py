from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend.app.database import make_session_factory


def test_migration_adopts_legacy_database_without_losing_ratings(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE user_ratings (id INTEGER PRIMARY KEY, user_id BIGINT NOT NULL, "
                "movie_id INTEGER NOT NULL, rating FLOAT NOT NULL, UNIQUE(user_id, movie_id))"
            )
        )
        connection.execute(text("INSERT INTO user_ratings VALUES (1, 7, 42, 4.5)"))
    for _ in range(2):
        factory = make_session_factory(url)
        with factory() as session:
            assert session.execute(
                text("SELECT user_id, movie_id, rating FROM user_ratings")
            ).all() == [(7, 42, 4.5)]
            assert session.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                "0002_movie_preferences"
            )
    assert {"visitor_profiles", "watchlist_entries", "feedback_events"}.issubset(
        inspect(engine).get_table_names()
    )


def test_state_migration_preserves_existing_private_profiles_ratings_and_watchlists(tmp_path):
    from backend.app.models import UserRating, VisitorProfile, WatchlistEntry

    url = f"sqlite:///{tmp_path / 'v02.db'}"
    engine = create_engine(url)
    configuration = Config()
    configuration.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "backend/migrations")
    )
    with engine.begin() as connection:
        configuration.attributes["connection"] = connection
        command.upgrade(configuration, "0001_visitor_profiles")
        connection.execute(
            VisitorProfile.__table__.insert().values(user_id=77, token_hash="0" * 64)
        )
        connection.execute(UserRating.__table__.insert().values(user_id=77, movie_id=1, rating=4.5))
        connection.execute(WatchlistEntry.__table__.insert().values(user_id=77, movie_id=2))
    factory = make_session_factory(url)
    with factory() as session:
        assert session.get(VisitorProfile, 77).token_hash == "0" * 64
        assert (
            session.execute(text("SELECT rating FROM user_ratings WHERE user_id=77")).scalar()
            == 4.5
        )
        assert (
            session.execute(
                text("SELECT movie_id FROM watchlist_entries WHERE user_id=77")
            ).scalar()
            == 2
        )
        assert session.execute(text("SELECT count(*) FROM movie_preferences")).scalar() == 0
