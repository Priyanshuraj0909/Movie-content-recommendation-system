"""Serve the real API and browser frontend together for a local walkthrough."""

import sys
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.main import app  # noqa: E402

app.mount(
    "/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend/web", html=True)
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
