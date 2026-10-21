"""SQLite persistence for locally submitted user ratings."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for local persistence models."""


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create tables and return a session factory for a SQLite database URL."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
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
