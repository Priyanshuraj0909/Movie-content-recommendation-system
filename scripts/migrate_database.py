"""Apply additive migrations using DATABASE_URL; never print database credentials."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.database import make_session_factory  # noqa: E402

if __name__ == "__main__":
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Export DATABASE_URL before running migrations")
    make_session_factory(database_url)
    print("Database migrations completed; existing ratings preserved.")
