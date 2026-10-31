from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.main import create_app
from backend.app.models import MoviePreference, UserRating


def profile(client):
    value = client.post("/api/profiles").json()
    return value["user_id"], {"X-Profile-Token": value["token"]}


def test_watched_and_dismissed_states_are_owned_reversible_and_not_ratings(client):
    uid, headers = profile(client)
    path = f"/api/profiles/{uid}/preferences"
    assert client.put(path, json={"movie_id": 1, "state": "watched"}).status_code == 401
    for state in ("watched", "not_interested", "none"):
        for _ in range(2):
            saved = client.put(path, headers=headers, json={"movie_id": 1, "state": state})
            assert saved.status_code == 200
        rows = client.get(f"/api/recommendations/users/{uid}", headers=headers).json()
        assert (1 in {row["movie_id"] for row in rows}) == (state == "none")
    assert client.get(f"/api/profiles/{uid}/ratings", headers=headers).json() == []
    with client.app.state.session_factory() as session:
        assert session.scalars(select(UserRating).where(UserRating.user_id == uid)).all() == []
        assert (
            len(
                session.scalars(select(MoviePreference).where(MoviePreference.user_id == uid)).all()
            )
            == 1
        )


def test_library_pagination_filtering_and_rating_edits_preserve_other_data(client):
    uid, headers = profile(client)
    for mid, rating in ((1, 5), (2, 4), (3, 2)):
        assert (
            client.post(
                "/api/ratings",
                headers=headers,
                json={"user_id": uid, "movie_id": mid, "rating": rating},
            ).status_code
            == 201
        )
    path = f"/api/profiles/{uid}"
    client.put(path + "/preferences", headers=headers, json={"movie_id": 4, "state": "watched"})
    client.put(
        path + "/preferences", headers=headers, json={"movie_id": 5, "state": "not_interested"}
    )
    first = client.get(path + "/library?limit=2", headers=headers).json()
    second = client.get(path + "/library?limit=2&offset=2", headers=headers).json()
    assert first["total"] == 5 and first["rated_count"] == 3
    assert first["watched_count"] == first["dismissed_count"] == 1
    assert not {row["movie_id"] for row in first["items"]} & {
        row["movie_id"] for row in second["items"]
    }
    assert len(client.get(path + "/library?view=rated", headers=headers).json()["items"]) == 3
    hidden = client.get(path + "/library?view=not_interested", headers=headers).json()["items"]
    assert hidden[0]["movie_id"] == 5 and hidden[0]["rating"] is None
    client.post(
        "/api/ratings", headers=headers, json={"user_id": uid, "movie_id": 1, "rating": 3.5}
    )
    edited = client.get(path + "/library?view=rated", headers=headers).json()
    assert edited["rated_count"] == 3
    assert next(row for row in edited["items"] if row["movie_id"] == 1)["rating"] == 3.5
    assert client.get(path + "/library").status_code == 401


def test_feedback_validation_and_restart_persistence(client):
    uid, headers = profile(client)
    path = f"/api/profiles/{uid}"
    assert (
        client.put(
            path + "/preferences", headers=headers, json={"movie_id": 1, "state": "unknown"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            path + "/preferences", headers=headers, json={"movie_id": 999, "state": "watched"}
        ).status_code
        == 404
    )
    assert client.get(path + "/library?offset=-1", headers=headers).status_code == 422
    client.put(path + "/preferences", headers=headers, json={"movie_id": 1, "state": "watched"})
    state = client.app.state
    with state.session_factory() as session:
        url = str(session.get_bind().url)
    app = create_app(
        content_model=state.content_model,
        collaborative_model=state.collaborative_model,
        movies=state.movies.reset_index(drop=True),
        database_url=url,
    )
    with TestClient(app) as restarted:
        assert restarted.get(path + "/preferences", headers=headers).json() == [
            {"movie_id": 1, "state": "watched"}
        ]
        assert restarted.get(path + "/library", headers=headers).json()["watched_count"] == 1
        assert all(
            row["movie_id"] != 1
            for row in restarted.get(f"/api/recommendations/users/{uid}", headers=headers).json()
        )


def test_dedicated_profile_deployment_verifier_exercises_library_and_feedback(client):
    from scripts.verify_deployment import verify, verify_private_features

    uid, headers = profile(client)
    client.headers.update(headers)
    verify(client, write_user_id=uid)
    assert verify_private_features(client, uid) == [
        "private taste library",
        "watched feedback exclusion",
        "feedback undo preserves ratings",
    ]
