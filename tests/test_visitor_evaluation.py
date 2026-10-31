import pandas as pd

from recommender.evaluation.visitors import evaluate_visitors


def test_unseen_user_protocol_keeps_fitting_and_visitor_users_separate():
    interactions = pd.DataFrame(
        [
            (user, movie, float(3 + movie % 3), movie * 100)
            for user in range(1, 11)
            for movie in range(1, 7)
        ],
        columns=["userId", "movieId", "rating", "timestamp"],
    )
    movies = pd.DataFrame(
        {
            "movieId": list(range(1, 7)),
            "title": [f"Movie {i}" for i in range(1, 7)],
            "genres": ["Adventure"] * 6,
            "tags_json": ["[]"] * 6,
        }
    )
    report = evaluate_visitors(interactions, interactions, movies, counts=(1, 3))
    assert report["protocol"]["withheld_users"] == 2
    assert report["protocol"]["fitting_users"] == 8
    for count in ("1", "3"):
        assert {value["eligible_users"] for value in report["onboarding"][count].values()} == {2}
        assert all(
            value["ndcg_95_percent_bootstrap_interval"] is not None
            for value in report["onboarding"][count].values()
        )
