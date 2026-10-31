"""SQLite/PostgreSQL persistence for submitted user ratings."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for local persistence models."""


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create tables and return a session factory for SQLite or PostgreSQL."""
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    configuration = Config()
    configuration.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Serialize concurrent serverless startup migrations without retaining a lock.
            connection.execute(text("SELECT pg_advisory_xact_lock(742100031)"))
        configuration.attributes["connection"] = connection
        command.upgrade(configuration, "head")
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def sqlite_url(path: Path) -> str:
    """Convert a filesystem path to a SQLite URL, creating its parent directory."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def get_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Yield and close one request-scoped database session."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
