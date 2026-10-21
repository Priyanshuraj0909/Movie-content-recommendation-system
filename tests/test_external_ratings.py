from __future__ import annotations

from typing import Any

import httpx
import pytest

import backend.app.services.external_ratings as ratings


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    ratings.clear_ratings_cache()


def install_transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    transport = httpx.MockTransport(recording_handler)
    client_class = httpx.Client
    monkeypatch.setattr(
        ratings.httpx,
        "Client",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )
    return requests


def tmdb_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "id": 603,
        "title": "The Matrix",
        "release_date": "1999-03-30",
        "vote_average": 8.5,
        "vote_count": 25000,
        "imdb_id": "tt0133093",
        **overrides,
    }


def omdb_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "Response": "True",
        "Title": "The Matrix",
        "Year": "1999",
        "imdbID": "tt0133093",
        "imdbRating": "8.7",
        "imdbVotes": "2,100,000",
        **overrides,
    }


def test_both_public_sources_return_real_scores_and_vote_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "test-tmdb-token")
    monkeypatch.setenv("OMDB_API_KEY", "test-omdb-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.themoviedb.org":
            return httpx.Response(200, json=tmdb_payload())
        return httpx.Response(200, json=omdb_payload())

    requests = install_transport(monkeypatch, handler)
    result = ratings.get_movie_ratings(1, "The Matrix (1999)", "603", "0133093")

    assert result["tmdb"]["rating"] == 8.5
    assert result["tmdb"]["vote_count"] == 25000
    assert result["imdb"]["rating"] == 8.7
    assert result["imdb"]["vote_count"] == 2100000
    assert result["imdb"]["url"] == "https://www.imdb.com/title/tt0133093/"
    assert len(requests) == 2
    assert "test-omdb-key" not in str(result)


def test_tmdb_only_when_imdb_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    install_transport(monkeypatch, lambda _: httpx.Response(200, json=tmdb_payload()))
    result = ratings.get_movie_ratings(1, "The Matrix (1999)", "603", "0133093")
    assert result["tmdb"]["rating"] == 8.5
    assert result["imdb"]["rating"] is None


def test_imdb_only_when_tmdb_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMDB_API_READ_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    install_transport(monkeypatch, lambda _: httpx.Response(200, json=omdb_payload()))
    result = ratings.get_movie_ratings(1, "The Matrix (1999)", None, "0133093")
    assert result["tmdb"]["rating"] is None
    assert result["imdb"]["rating"] == 8.7


def test_tmdb_title_year_fallback_is_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("OMDB_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search/movie"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 603, "title": "The Matrix", "release_date": "1999-03-30"}
                    ]
                },
            )
        return httpx.Response(200, json=tmdb_payload())

    requests = install_transport(monkeypatch, handler)
    result = ratings.get_movie_ratings(9, "The Matrix (1999)")
    assert result["tmdb"]["rating"] == 8.5
    assert result["tmdb"]["tmdb_id"] == "603"
    assert len(requests) == 2


def test_tmdb_title_year_fallback_rejects_wrong_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    install_transport(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={"results": [{"id": 603, "title": "The Matrix", "release_date": "2000-03-30"}]},
        ),
    )
    result = ratings.get_movie_ratings(9, "The Matrix (1999)")
    assert result["tmdb"]["rating"] is None


def test_omdb_title_year_fallback_checks_returned_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    install_transport(monkeypatch, lambda _: httpx.Response(200, json=omdb_payload()))
    result = ratings.get_movie_ratings(9, "The Matrix (1999)")
    assert result["imdb"]["rating"] == 8.7
    assert result["imdb"]["imdb_id"] == "tt0133093"


def test_omdb_title_year_fallback_rejects_wrong_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, json=omdb_payload(Title="The Matrix Reloaded")),
    )
    result = ratings.get_movie_ratings(9, "The Matrix (1999)")
    assert result["imdb"]["rating"] is None


def test_missing_credentials_and_na_values_display_no_fake_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TMDB_API_READ_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    result = ratings.get_movie_ratings(1, "Unknown Film (2001)", "4", "0000001")
    assert result["tmdb"]["rating"] is None
    assert result["imdb"]["rating"] is None

    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    install_transport(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json=omdb_payload(
                Title="The Matrix", imdbRating="N/A", imdbVotes="N/A"
            ),
        ),
    )
    # Use a new id so the prior empty result is not served from cache.
    result = ratings.get_movie_ratings(2, "The Matrix (1999)", None, "0133093")
    assert result["imdb"]["rating"] is None
    assert result["imdb"]["vote_count"] is None


@pytest.mark.parametrize(
    ("response", "tmdb_id", "imdb_id"),
    [
        (tmdb_payload(title="Wrong Film"), "603", "0133093"),
        (tmdb_payload(release_date="2000-01-01"), "603", "0133093"),
        (tmdb_payload(id=604), "603", "0133093"),
    ],
)
def test_tmdb_identity_mismatch_is_not_displayed(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any], tmdb_id: str, imdb_id: str
) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    install_transport(monkeypatch, lambda _: httpx.Response(200, json=response))
    result = ratings.get_movie_ratings(1, "The Matrix (1999)", tmdb_id, imdb_id)
    assert result["tmdb"]["rating"] is None


@pytest.mark.parametrize(
    "response",
    [
        omdb_payload(Title="Another Film"),
        omdb_payload(Year="2000"),
        omdb_payload(imdbID="tt9999999"),
    ],
)
def test_omdb_identity_mismatch_is_not_displayed(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]
) -> None:
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    install_transport(monkeypatch, lambda _: httpx.Response(200, json=response))
    result = ratings.get_movie_ratings(1, "The Matrix (1999)", None, "0133093")
    assert result["imdb"]["rating"] is None


def test_timeout_and_invalid_api_key_fail_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("OMDB_API_KEY", "bad-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.themoviedb.org":
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(401, json={"Response": "False", "Error": "Invalid API key!"})

    install_transport(monkeypatch, handler)
    result = ratings.get_movie_ratings(1, "The Matrix (1999)", "603", "0133093")
    assert result["tmdb"]["rating"] is None
    assert result["imdb"]["rating"] is None


def test_response_cache_avoids_duplicate_api_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("OMDB_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = tmdb_payload() if request.url.host == "api.themoviedb.org" else omdb_payload()
        return httpx.Response(200, json=payload)

    requests = install_transport(monkeypatch, handler)
    first = ratings.get_movie_ratings(1, "The Matrix (1999)", "603", "0133093")
    second = ratings.get_movie_ratings(1, "The Matrix (1999)", "603", "0133093")
    assert first == second
    assert len(requests) == 2
