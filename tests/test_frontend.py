from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import frontend.api_client as api_client_module
from frontend.api_client import APIError, RecommendationAPI


def test_api_client_search_and_rating_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/movies/search":
            return httpx.Response(200, json=[{"movie_id": 1, "title": "Star Voyage"}])
        return httpx.Response(201, json={"user_id": 7, "movie_id": 1, "rating": 4.5})

    api = RecommendationAPI(transport=httpx.MockTransport(handler))
    results = api.search_movies("star")
    saved = api.save_rating(7, 1, 4.5)

    assert results[0]["movie_id"] == 1
    assert saved["rating"] == 4.5
    assert requests[0].url.params["q"] == "star"
    assert requests[1].read() == b'{"user_id":7,"movie_id":1,"rating":4.5}'


def test_api_client_surfaces_api_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Movie not found"})

    api = RecommendationAPI(transport=httpx.MockTransport(handler))
    with pytest.raises(APIError, match="Movie not found"):
        api.similar_movies(999)


class FakeAPI:
    """In-memory API fixture used to exercise the Streamlit page flow."""

    saved_ratings: list[tuple[int, int, float]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        self.saved_ratings = []

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "movies_loaded": 2}

    def search_movies(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if query.casefold() in "star voyage" or query.casefold() == "star":
            return [{"movie_id": 1, "title": "Star Voyage", "genres": "Adventure|Sci-Fi"}][:limit]
        return []

    def similar_movies(self, movie_id: int, *, limit: int = 8) -> list[dict[str, Any]]:
        assert movie_id == 1
        return [{"movie_id": 2, "title": "Galaxy Journey", "genres": "Sci-Fi", "score": 0.8}][
            :limit
        ]

    def recommendations(self, user_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
        assert user_id == 1001
        return [{"movie_id": 2, "title": "Galaxy Journey", "genres": "Sci-Fi", "score": 0.7}][
            :limit
        ]

    def save_rating(self, user_id: int, movie_id: int, rating: float) -> dict[str, Any]:
        self.saved_ratings.append((user_id, movie_id, rating))
        return {"user_id": user_id, "movie_id": movie_id, "rating": rating}


def test_streamlit_discover_rating_and_recommendation_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_client_module, "RecommendationAPI", FakeAPI)
    script = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
    app = AppTest.from_file(script).run()
    assert not app.exception
    assert any("Connected" in message.value for message in app.success)

    app.text_input(key="movie_search").set_value("star").run()
    assert any(button.label == "Save rating" for button in app.button)
    app.button(key="save_search_1").click().run()
    assert app.session_state["last_saved"] == (1001, "Star Voyage", 5.0)

    app.radio[0].set_value("For you").run()
    assert any("Picked for your profile" in header.value for header in app.subheader)
    assert not app.exception


def test_streamlit_similar_films_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_client_module, "RecommendationAPI", FakeAPI)
    script = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
    app = AppTest.from_file(script).run()
    app.radio[0].set_value("Similar films").run()
    app.text_input(key="similar_search").set_value("star").run()
    app.button(key="show_similar").click().run()
    assert app.session_state["similar_seed_id"] == 1
    assert not app.exception
