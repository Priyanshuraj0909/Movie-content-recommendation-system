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
                "0001_visitor_profiles"
            )
    assert {"visitor_profiles", "watchlist_entries", "feedback_events"}.issubset(
        inspect(engine).get_table_names()
    )
