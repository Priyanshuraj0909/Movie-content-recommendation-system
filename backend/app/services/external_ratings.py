"""Read-only TMDB and OMDb ratings with identity checks and a small TTL cache."""

from __future__ import annotations

import os
import re
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx

TMDB_API = "https://api.themoviedb.org/3"
OMDB_API = "https://www.omdbapi.com/"
_CACHE_TTL_SECONDS = 60 * 60 * 12
_CACHE_MAX_ITEMS = 1000
_cache: OrderedDict[tuple[int, str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_cache_lock = threading.Lock()


def _clean_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.casefold() not in {"nan", "none", "<na>"} else None


def _imdb_id(value: Any) -> str | None:
    identifier = _clean_id(value)
    if identifier is None:
        return None
    if identifier.startswith("tt"):
        return identifier
    if identifier.isdigit():
        return "tt" + identifier.zfill(7)
    return None


def _normal_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _identity(title: str) -> tuple[str, str | None]:
    match = re.search(r"\((\d{4})\)\s*$", title)
    clean = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    return _normal_title(clean), match.group(1) if match else None


def _title_year(title: str) -> tuple[str, str | None]:
    match = re.search(r"\((\d{4})\)\s*$", title)
    clean = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    return clean, match.group(1) if match else None


def _matches(catalog_title: str, external_title: str, external_year: str | None) -> bool:
    expected_title, expected_year = _identity(catalog_title)
    actual_title = _normal_title(external_title)
    if not expected_title or expected_title != actual_title:
        return False
    return expected_year is None or expected_year == external_year


def _cached(key: tuple[int, str, str]) -> dict[str, Any] | None:
    now = time.monotonic()
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= now:
            del _cache[key]
            return None
        _cache.move_to_end(key)
        return value.copy()


def _store(key: tuple[int, str, str], value: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, value.copy())
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX_ITEMS:
            _cache.popitem(last=False)


def _rating(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 10 else None


def _votes(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _empty(movie_id: int, title: str) -> dict[str, Any]:
    return {
        "movie_id": movie_id,
        "title": title,
        "tmdb": {"rating": None, "vote_count": None, "tmdb_id": None, "url": None},
        "imdb": {"rating": None, "vote_count": None, "imdb_id": None, "url": None},
    }


def get_movie_ratings(
    movie_id: int, title: str, tmdb_id: Any = None, imdb_id: Any = None
) -> dict[str, Any]:
    """Fetch public ratings for one catalog entry; failures produce absent source values."""
    tmdb_key = _clean_id(tmdb_id)
    imdb_key = _imdb_id(imdb_id)
    cache_key = (movie_id, tmdb_key or "", imdb_key or "")
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    result = _empty(movie_id, title)
    configured_tmdb_id = tmdb_key
    configured_imdb_id = imdb_key
    tmdb_token = os.getenv("TMDB_API_READ_ACCESS_TOKEN", "").strip()
    omdb_key = os.getenv("OMDB_API_KEY", "").strip()

    with httpx.Client(timeout=httpx.Timeout(4.0, connect=2.0), follow_redirects=False) as client:
        catalog_title, catalog_year = _title_year(title)
        if tmdb_token and (configured_tmdb_id or catalog_year):
            try:
                if not configured_tmdb_id:
                    search_response = client.get(
                        f"{TMDB_API}/search/movie",
                        headers={
                            "Authorization": f"Bearer {tmdb_token}",
                            "Accept": "application/json",
                        },
                        params={
                            "query": catalog_title,
                            "primary_release_year": catalog_year,
                            "include_adult": "false",
                            "language": "en-US",
                        },
                    )
                    search_response.raise_for_status()
                    candidates = search_response.json().get("results", [])
                    for candidate in candidates:
                        candidate_release = str(candidate.get("release_date") or "")
                        candidate_year = (
                            candidate_release[:4]
                            if re.match(r"^\d{4}", candidate_release)
                            else None
                        )
                        if _matches(title, str(candidate.get("title") or ""), candidate_year):
                            configured_tmdb_id = _clean_id(candidate.get("id"))
                            if configured_tmdb_id:
                                break
                if not configured_tmdb_id:
                    raise ValueError("TMDB title/year search found no verified match")
                response = client.get(
                    f"{TMDB_API}/movie/{configured_tmdb_id}",
                    headers={"Authorization": f"Bearer {tmdb_token}", "Accept": "application/json"},
                    params={"language": "en-US"},
                )
                response.raise_for_status()
                data = response.json()
                returned_id = _clean_id(data.get("id"))
                external_title = str(data.get("title") or data.get("original_title") or "")
                release = str(data.get("release_date") or "")
                external_year = release[:4] if re.match(r"^\d{4}", release) else None
                if returned_id == configured_tmdb_id and _matches(
                    title, external_title, external_year
                ):
                    result["tmdb"] = {
                        "rating": _rating(data.get("vote_average")),
                        "vote_count": _votes(data.get("vote_count")),
                        "tmdb_id": configured_tmdb_id,
                        "imdb_id": _clean_id(data.get("imdb_id")) or configured_imdb_id,
                        "url": f"https://www.themoviedb.org/movie/{configured_tmdb_id}",
                    }
                    configured_imdb_id = configured_imdb_id or _clean_id(data.get("imdb_id"))
            except (httpx.HTTPError, ValueError, TypeError):
                pass

        if omdb_key and (configured_imdb_id or catalog_year):
            try:
                params: dict[str, str] = {"apikey": omdb_key}
                if configured_imdb_id:
                    params["i"] = configured_imdb_id
                else:
                    params.update({"t": catalog_title, "y": str(catalog_year)})
                response = client.get(
                    OMDB_API,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                returned_imdb_id = _clean_id(data.get("imdbID"))
                external_title = str(data.get("Title") or "")
                external_year_match = re.match(r"^(\d{4})", str(data.get("Year") or ""))
                external_year = external_year_match.group(1) if external_year_match else None
                if (
                    str(data.get("Response", "True")).casefold() != "false"
                    and returned_imdb_id is not None
                    and (configured_imdb_id is None or returned_imdb_id == configured_imdb_id)
                    and _matches(title, external_title, external_year)
                ):
                    configured_imdb_id = returned_imdb_id
                    result["imdb"] = {
                        "rating": _rating(data.get("imdbRating")),
                        "vote_count": _votes(data.get("imdbVotes")),
                        "imdb_id": configured_imdb_id,
                        "url": f"https://www.imdb.com/title/{configured_imdb_id}/",
                    }
            except (httpx.HTTPError, ValueError, TypeError):
                pass

    _store(cache_key, result)
    return result


def clear_ratings_cache() -> None:
    """Clear the process-local cache (used by tests and operational refreshes)."""
    with _cache_lock:
        _cache.clear()
