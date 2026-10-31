"""Check a running API; rating writes require an explicit dedicated test profile."""

from __future__ import annotations

import argparse
import json
import os

import httpx


def verify(client: httpx.Client, *, write_user_id: int | None = None) -> list[str]:
    """Exercise API contracts without treating an HTML login page as success."""
    if write_user_id is not None and write_user_id <= 0:
        raise ValueError("The test profile ID must be positive")
    checks: list[str] = []

    def request(method: str, path: str, *, expected: int = 200, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code != expected:
            raise ValueError(f"{method} {path}: expected {expected}, got {response.status_code}")
        if "application/json" not in response.headers.get("content-type", ""):
            raise ValueError(f"{method} {path}: expected JSON; check deployment authentication")
        return response.json()

    health = request("GET", "/api/health")
    if health.get("status") != "ok" or health.get("movies_loaded", 0) <= 0:
        raise ValueError("Health response does not describe a loaded catalog")
    checks.append("health")
    movies = request("GET", "/api/movies/search", params={"q": "Toy", "limit": 5})
    if not movies:
        raise ValueError("Search returned no test movie for 'Toy'")
    movie_id = movies[0]["movie_id"]
    checks.append("search")
    similar = request("GET", f"/api/recommendations/similar/{movie_id}")
    if not similar or any(item["movie_id"] == movie_id for item in similar):
        raise ValueError("Similar-film results are empty or include the seed")
    checks.append("similar films")
    profile_id = write_user_id if write_user_id is not None else 2_000_000_001
    recommendations = request(
        "GET",
        f"/api/recommendations/users/{profile_id}"
        if write_user_id is not None
        else "/api/recommendations/popular",
    )
    if not recommendations:
        raise ValueError("Profile recommendations are empty")
    checks.append("recommendations")
    if write_user_id is not None:
        for rating in (5.0, 4.5):
            payload = {"user_id": write_user_id, "movie_id": movie_id, "rating": rating}
            saved = request("POST", "/api/ratings", expected=201, json=payload)
            if any(saved.get(key) != value for key, value in payload.items()):
                raise ValueError("Saved rating does not match the submitted rating")
        checks.append("rating create/update")
        # A separate request must observe the committed rating and exclude it.
        after = request("GET", f"/api/recommendations/users/{write_user_id}")
        if not after or any(item["movie_id"] == movie_id for item in after):
            raise ValueError("Recommendations did not exclude the saved rating")
        checks.append("saved-rating exclusion")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Origin, without the /api suffix")
    parser.add_argument(
        "--write-user-id",
        type=int,
        help="Dedicated disposable profile: creates/updates one rating and leaves it saved",
    )
    parser.add_argument(
        "--create-private-profile",
        action="store_true",
        help="Create a private test profile and verify writes without printing its secret",
    )
    args = parser.parse_args()
    try:
        headers = {}
        bypass = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")
        if bypass:
            headers["x-vercel-protection-bypass"] = bypass
        with httpx.Client(
            base_url=args.base_url, timeout=30, follow_redirects=False, headers=headers
        ) as client:
            write_user_id = args.write_user_id
            if args.create_private_profile:
                if write_user_id is not None:
                    raise ValueError("Choose a private profile or a legacy write ID, not both")
                created = client.post("/api/profiles")
                created.raise_for_status()
                profile = created.json()
                write_user_id = profile["user_id"]
                client.headers["X-Profile-Token"] = profile["token"]
            checks = verify(client, write_user_id=write_user_id)
            if args.create_private_profile:
                history = client.get(f"/api/profiles/{write_user_id}/ratings")
                history.raise_for_status()
                if not any(row["rating"] == 4.5 for row in history.json()):
                    raise ValueError("Fresh request did not observe the saved rating")
                checks.append("private profile rating history")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Verification failed: {error}\n")
    print(json.dumps({"passed": checks, "rating_writes_checked": write_user_id is not None}))


if __name__ == "__main__":
    main()
