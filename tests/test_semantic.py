import json

import numpy as np
import pandas as pd
import pytest

from recommender.data.plots import join_plots, normalized_title
from recommender.models.semantic import SemanticIndex, mean_pool


def test_plot_matches_require_exact_year_and_reject_ambiguity():
    movies = pd.DataFrame(
        {
            "movieId": [1, 2, 3],
            "title": ["Matrix, The (1999)", "Another Film (2000)", "Duplicate (2001)"],
        }
    )
    metadata = pd.DataFrame(
        [
            ["10", "", "The Matrix", "1999-01-01", "", "136", '{"en": "English Language"}', "", ""],
            ["20", "", "Another Film", "2002", "", "90", "{}", "", ""],
            ["30", "", "Duplicate", "2001", "", "90", "{}", "", ""],
            ["31", "", "Duplicate", "2001", "", "90", "{}", "", ""],
        ]
    )
    joined, rejected = join_plots(
        movies,
        metadata,
        {"10": "A real sourced plot.", "20": "Wrong year", "30": "Ambiguous", "31": "Ambiguous"},
    )
    assert joined.movieId.tolist() == [1]
    assert rejected == 1
    assert joined.iloc[0].runtime_minutes == 136
    assert json.loads(joined.iloc[0].languages_json) == ["English"]
    assert joined.iloc[0].source_url == "https://en.wikipedia.org/?curid=10"
    assert normalized_title("Matrix, The (1999)") == normalized_title("The Matrix")


def test_mean_pool_ignores_padding_and_normalizes():
    tokens = np.array([[[3.0, 4.0], [900.0, 900.0]]])
    actual = mean_pool(tokens, np.array([[1, 0]]))
    np.testing.assert_allclose(actual, [[0.6, 0.8]])
    np.testing.assert_array_equal(mean_pool(tokens, np.array([[0, 0]])), [[0, 0]])


class FakeEncoder:
    def encode(self, texts):
        values = np.zeros((len(texts), 384), dtype=np.float32)
        values[:, 0] = 1
        return values


def test_exact_semantic_retrieval_filters_and_breaks_ties(tmp_path):
    (tmp_path / "manifest.json").write_text("{}")
    np.save(tmp_path / "movie_ids.npy", [3, 1, 2])
    vectors = np.zeros((3, 384), dtype=np.float32)
    vectors[:, 0] = [0.8, 0.8, -1]
    np.save(tmp_path / "embeddings.npy", vectors)
    index = SemanticIndex(tmp_path, encoder=FakeEncoder())
    assert [mid for mid, _ in index.search("space")] == [1, 3]
    assert [mid for mid, _ in index.search("space", allowed_ids={3})] == [3]
    assert index.search("space", allowed_ids=set()) == []
    vectors[0, 0] = np.nan
    np.save(tmp_path / "embeddings.npy", vectors)
    with pytest.raises(ValueError, match="Non-finite"):
        SemanticIndex(tmp_path, encoder=FakeEncoder())


def test_semantic_api_reports_unavailable_and_details_remain_real(client):
    assert client.get("/api/capabilities").json()["semantic_search"] is False
    assert (
        client.get("/api/movies/semantic-search", params={"q": "space voyage"}).status_code == 503
    )
    details = client.get("/api/movies/1").json()
    assert details["title"] == "Toy Star Voyage (2000)"
    assert details["summary"] is None
    assert details["runtime_minutes"] is None
    assert client.get("/api/movies/999").status_code == 404


def test_semantic_api_enforces_structured_filters(client):
    class RecordingIndex:
        movie_ids = [1, 2, 3, 4, 5]

        def search(self, query, *, limit, allowed_ids):
            return [(mid, 0.8) for mid in sorted(allowed_ids)[:limit]]

    client.app.state.semantic_index = RecordingIndex()
    table = client.app.state.movies
    table["runtime_minutes"] = [90, 150, 120, 100, 85]
    table["languages_json"] = ['["English"]', '["French"]', '["English"]', "[]", "[]"]
    result = client.get(
        "/api/movies/semantic-search",
        params={"q": "space voyage", "genre": "Sci-Fi", "max_runtime": 100, "language": "English"},
    ).json()
    assert [row["movie_id"] for row in result] == [1]
    assert (
        client.get(
            "/api/movies/semantic-search", params={"q": "space voyage", "max_runtime": 0}
        ).status_code
        == 422
    )
