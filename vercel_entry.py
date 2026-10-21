"""Vercel Services entrypoint for the FastAPI backend."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from backend.app.main import app  # noqa: E402

__all__ = ["app"]
