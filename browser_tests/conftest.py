"""Run the real web frontend and API against an isolated fixture database."""

import os
import socket
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
import uvicorn
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright

from backend.app.main import create_app
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender


@pytest.fixture(scope="session")
def site_url(tmp_path_factory):
    movies = pd.DataFrame(
        {
            "movieId": list(range(1, 13)),
            "title": [f"Toy Space Adventure {i} (2000)" for i in range(1, 13)],
            "genres": ["Adventure|Sci-Fi"] * 12,
            "tags_json": ['["space"]'] * 12,
            "summary": ["A fictional space adventure for this isolated browser test."] * 12,
            "runtime_minutes": [95] * 12,
            "languages_json": ['["English"]'] * 12,
            "source_url": ["https://en.wikipedia.org/"] * 12,
            "license_url": ["https://creativecommons.org/licenses/by-sa/3.0/us/"] * 12,
        }
    )
    ratings = pd.DataFrame(
        [(user, movie, float(3 + movie % 3)) for user in range(1, 5) for movie in range(1, 13)],
        columns=["userId", "movieId", "rating"],
    )

    class FixtureSemanticIndex:
        movie_ids = list(range(1, 13))

        def search(self, query, *, limit, allowed_ids):
            return [(mid, 0.8) for mid in sorted(allowed_ids)[:limit]]

    app = create_app(
        content_model=ContentRecommender().fit(movies),
        collaborative_model=CollaborativeRecommender(epochs=2).fit(ratings),
        movies=movies,
        database_url=f"sqlite:///{tmp_path_factory.mktemp('browser') / 'ratings.db'}",
        semantic_index=FixtureSemanticIndex(),
    )
    app.mount(
        "/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend/web", html=True)
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Browser fixture API did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def page(site_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        )
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(site_url)
        yield page
        assert not errors, errors
        context.close()
        browser.close()
