import json
from pathlib import Path

import pandas as pd
import pytest

from recommender.data.movielens import (
    DataValidationError,
    chronological_split,
    prepare_dataset,
    validate_dataset,
)


def sample_frames() -> dict[str, pd.DataFrame]:
    return {
        "movies.csv": pd.DataFrame(
            {
                "movieId": [1, 2, 3, 4, 5],
                "title": ["One (2000)", "Two (2001)", "Three (2002)", "Four (2003)", "Five (2004)"],
                "genres": ["Drama", "Comedy", "Action", "Mystery", "(no genres listed)"],
            }
        ),
        "ratings.csv": pd.DataFrame(
            {
                "userId": [10, 10, 10, 10, 10, 20, 20, 30],
                "movieId": [1, 2, 3, 4, 5, 1, 2, 3],
                "rating": [5.0, 4.0, 3.5, 4.5, 2.0, 3.0, 3.5, 4.0],
                "timestamp": [100, 200, 300, 400, 500, 100, 200, 100],
            }
        ),
        "tags.csv": pd.DataFrame(
            {
                "userId": [10, 20, 30],
                "movieId": [1, 1, 3],
                "tag": ["Space", "space", "Misérables"],
                "timestamp": [101, 102, 103],
            }
        ),
        "links.csv": pd.DataFrame(
            {
                "movieId": [1, 2, 3, 4, 5],
                "imdbId": ["00001", "2", "3", "4", "5"],
                "tmdbId": [11, 12, 13, 14, 15],
            }
        ),
    }


def test_validate_dataset_accepts_optional_catalog_links() -> None:
    frames = sample_frames()
    frames["links.csv"].loc[0, "tmdbId"] = pd.NA

    validated = validate_dataset(frames)

    assert validated["movies.csv"]["movieId"].is_unique
    assert validated["links.csv"]["tmdbId"].isna().sum() == 1


@pytest.mark.parametrize(
    ("file_name", "mutate", "message"),
    [
        (
            "ratings.csv",
            lambda frame: frame.assign(rating=[5.0, 4.0, 3.5, 4.5, 2.0, 3.0, 3.5, 7.0]),
            "half-star values",
        ),
        (
            "tags.csv",
            lambda frame: frame.assign(movieId=[1, 1, 99]),
            "absent from movies.csv",
        ),
        (
            "movies.csv",
            lambda frame: frame.assign(title=[None, "Two", "Three", "Four", "Five"]),
            "null values",
        ),
    ],
)
def test_validate_dataset_rejects_invalid_rows(file_name, mutate, message) -> None:
    frames = sample_frames()
    frames[file_name] = mutate(frames[file_name])

    with pytest.raises(DataValidationError, match=message):
        validate_dataset(frames)


def test_chronological_split_is_per_user_and_has_no_leakage() -> None:
    ratings = sample_frames()["ratings.csv"]

    train, validation, test = chronological_split(ratings)

    train_pairs = set(zip(train.userId, train.movieId, strict=True))
    validation_pairs = set(zip(validation.userId, validation.movieId, strict=True))
    test_pairs = set(zip(test.userId, test.movieId, strict=True))
    assert not train_pairs & validation_pairs
    assert not train_pairs & test_pairs
    assert not validation_pairs & test_pairs
    assert len(train) + len(validation) + len(test) == len(ratings)
    assert set(validation.userId) == {10}
    assert set(test.userId) == {10}
    assert set(train.loc[train.userId.eq(10), "timestamp"]) == {100, 200, 300}


def test_prepare_dataset_saves_tag_features_splits_and_manifest(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    for name, frame in sample_frames().items():
        frame.to_csv(raw_dir / name, index=False)

    manifest = prepare_dataset(raw_dir, processed_dir, archive_md5="abc123")

    movies = pd.read_csv(processed_dir / "movies_with_tags.csv")
    links = pd.read_csv(processed_dir / "links.csv", dtype={"imdbId": "string"})
    tag_lists = dict(zip(movies.movieId, movies.tags_json, strict=True))
    assert json.loads(tag_lists[1]) == ["Space", "space"]
    assert json.loads(tag_lists[2]) == []
    assert json.loads(tag_lists[3]) == ["Misérables"]
    assert manifest["archive_md5"] == "abc123"
    assert manifest["counts"]["ratings"] == 8
    assert manifest["counts"]["train_ratings"] == 6
    assert manifest["counts"]["validation_ratings"] == 1
    assert manifest["counts"]["test_ratings"] == 1
    assert links.loc[0, "imdbId"] == "00001"
    assert (processed_dir / "dataset_manifest.json").is_file()
    assert len(pd.read_csv(processed_dir / "train_ratings.csv")) == 6
