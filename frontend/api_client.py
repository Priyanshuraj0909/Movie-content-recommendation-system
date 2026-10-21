"""Small typed HTTP client for the local recommendation API."""

from __future__ import annotations

from typing import Any

import httpx


class APIError(RuntimeError):
    """A readable error returned when the recommendation API is unavailable."""


class RecommendationAPI:
    """Call search, recommendation and rating endpoints on the FastAPI service."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, params=params, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            try:
                detail = error.response.json().get("detail", error.response.text)
            except ValueError:
                detail = error.response.text
            raise APIError(f"API returned {error.response.status_code}: {detail}") from error
        except httpx.RequestError as error:
            raise APIError(
                f"Could not reach the API at {self.base_url}. Start it with "
                "`uvicorn backend.app.main:app --reload`."
            ) from error

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health")

    def search_movies(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return self._request("GET", "/api/movies/search", params={"q": query, "limit": limit})

    def similar_movies(self, movie_id: int, *, limit: int = 8) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"/api/recommendations/similar/{movie_id}", params={"limit": limit}
        )

    def recommendations(self, user_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"/api/recommendations/users/{user_id}", params={"limit": limit}
        )

    def save_rating(self, user_id: int, movie_id: int, rating: float) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/ratings",
            payload={"user_id": user_id, "movie_id": movie_id, "rating": rating},
        )
