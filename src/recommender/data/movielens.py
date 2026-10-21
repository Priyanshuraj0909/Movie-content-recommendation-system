"""Download, validate, and prepare the MovieLens latest-small dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
import pandas as pd

from recommender.config import PROCESSED_DATA_DIR, RAW_DATA_DIR

DATASET_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
CHECKSUM_URL = f"{DATASET_URL}.md5"
DATASET_DIRECTORY = "ml-latest-small"
REQUIRED_FILES = ("movies.csv", "ratings.csv", "tags.csv", "links.csv")
TLS_VERIFY: bool | str = (
    "/etc/ssl/cert.pem"
    if os.name == "posix" and Path("/etc/ssl/cert.pem").is_file()
    else True
)
EXPECTED_COLUMNS = {
    "movies.csv": ("movieId", "title", "genres"),
    "ratings.csv": ("userId", "movieId", "rating", "timestamp"),
    "tags.csv": ("userId", "movieId", "tag", "timestamp"),
    "links.csv": ("movieId", "imdbId", "tmdbId"),
}


class DataValidationError(ValueError):
    """Raised when a source file violates the expected MovieLens schema."""


def download_dataset(raw_dir: Path = RAW_DATA_DIR) -> str:
    """Download and checksum-verify the official archive into ``raw_dir``.

    Existing dataset files are preserved: the function refuses to overwrite them.
    Returns the verified archive's MD5 digest.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    targets = [raw_dir / name for name in REQUIRED_FILES]
    existing = [path.name for path in targets if path.exists()]
    if existing:
        raise FileExistsError(
            f"Dataset files already exist in {raw_dir}: {', '.join(existing)}. "
            "Move them elsewhere before downloading a fresh copy."
        )

    headers = {"User-Agent": "movie-recommender/0.1"}
    checksum_response = httpx.get(
        CHECKSUM_URL, headers=headers, timeout=30, verify=TLS_VERIFY
    )
    checksum_response.raise_for_status()
    checksum_text = checksum_response.text
    digest_match = re.search(r"\b[0-9a-fA-F]{32}\b", checksum_text)
    if digest_match is None:
        raise ValueError(f"Unexpected MD5 checksum response from {CHECKSUM_URL}")
    expected_digest = digest_match.group().lower()

    with tempfile.TemporaryDirectory(dir=raw_dir) as temp_dir:
        archive_path = Path(temp_dir) / "ml-latest-small.zip"
        with (
            httpx.stream(
                "GET", DATASET_URL, headers=headers, timeout=60, verify=TLS_VERIFY
            ) as response,
            archive_path.open("wb") as archive_file,
        ):
            response.raise_for_status()
            for block in response.iter_bytes():
                archive_file.write(block)

        digest = hashlib.md5(usedforsecurity=False)
        with archive_path.open("rb") as archive_file:
            for block in iter(lambda: archive_file.read(1024 * 1024), b""):
                digest.update(block)
        actual_digest = digest.hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(
                "MovieLens archive checksum mismatch: "
                f"expected {expected_digest}, received {actual_digest}"
            )

        with zipfile.ZipFile(archive_path) as archive:
            members: dict[str, zipfile.ZipInfo] = {}
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"Unsafe path in MovieLens archive: {info.filename}")
                if path.parts[:1] == (DATASET_DIRECTORY,) and path.name in REQUIRED_FILES:
                    members[path.name] = info
            missing = sorted(set(REQUIRED_FILES) - members.keys())
            if missing:
                raise ValueError(f"MovieLens archive is missing required files: {missing}")
            contents = {name: archive.read(members[name]) for name in REQUIRED_FILES}

    for name, content in contents.items():
        (raw_dir / name).write_bytes(content)
    metadata = {
        "dataset": "MovieLens latest-small",
        "source_url": DATASET_URL,
        "checksum_url": CHECKSUM_URL,
        "checksum_algorithm": "MD5",
        "archive_md5": actual_digest,
        "downloaded_at_utc": datetime.now(UTC).isoformat(),
    }
    (raw_dir / "download_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return actual_digest


def _read_source_files(raw_dir: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for name, required_columns in EXPECTED_COLUMNS.items():
        path = raw_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Required MovieLens file not found: {path}")
        if name == "links.csv":
            frame = pd.read_csv(path, dtype={"imdbId": "string", "tmdbId": "string"})
        else:
            frame = pd.read_csv(path)
        missing_columns = sorted(set(required_columns) - set(frame.columns))
        if missing_columns:
            raise DataValidationError(f"{name} is missing required columns: {missing_columns}")
        frames[name] = frame
    return frames


def _require_non_null(frame: pd.DataFrame, columns: tuple[str, ...], filename: str) -> None:
    missing = {column: int(frame[column].isna().sum()) for column in columns}
    missing = {column: count for column, count in missing.items() if count}
    if missing:
        raise DataValidationError(f"{filename} has null values in required columns: {missing}")


def _require_positive_integer_ids(
    frame: pd.DataFrame, columns: tuple[str, ...], filename: str
) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = values.isna() | (values <= 0) | ((values % 1) != 0)
        if invalid.any():
            raise DataValidationError(
                f"{filename}.{column} must contain positive integer IDs "
                f"({int(invalid.sum())} invalid rows)"
            )
        frame[column] = values.astype("int64")


def validate_dataset(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Validate IDs, keys, nulls, rating values, and references across the CSVs."""
    missing_files = sorted(set(EXPECTED_COLUMNS) - frames.keys())
    if missing_files:
        raise DataValidationError(f"Missing source tables: {missing_files}")
    data = {name: frame.copy() for name, frame in frames.items()}
    for name, columns in EXPECTED_COLUMNS.items():
        missing_columns = sorted(set(columns) - set(data[name].columns))
        if missing_columns:
            raise DataValidationError(f"{name} is missing required columns: {missing_columns}")

    movies = data["movies.csv"]
    ratings = data["ratings.csv"]
    tags = data["tags.csv"]
    links = data["links.csv"]
    _require_non_null(movies, ("movieId", "title", "genres"), "movies.csv")
    _require_non_null(ratings, ("userId", "movieId", "rating", "timestamp"), "ratings.csv")
    _require_non_null(tags, ("userId", "movieId", "tag", "timestamp"), "tags.csv")
    _require_non_null(links, ("movieId",), "links.csv")

    _require_positive_integer_ids(movies, ("movieId",), "movies.csv")
    _require_positive_integer_ids(ratings, ("userId", "movieId"), "ratings.csv")
    _require_positive_integer_ids(tags, ("userId", "movieId"), "tags.csv")
    _require_positive_integer_ids(links, ("movieId",), "links.csv")

    for name, frame, key in (
        ("movies.csv", movies, "movieId"),
        ("links.csv", links, "movieId"),
    ):
        if frame[key].duplicated().any():
            raise DataValidationError(f"{name}.{key} must be unique")
    if ratings.duplicated(["userId", "movieId"]).any():
        raise DataValidationError("ratings.csv contains duplicate userId/movieId interactions")

    titles = movies["title"].astype("string").str.strip()
    genres = movies["genres"].astype("string").str.strip()
    if titles.eq("").any() or genres.eq("").any():
        raise DataValidationError("movies.csv title and genres values must not be blank")
    movies["title"] = titles
    movies["genres"] = genres

    rating_values = pd.to_numeric(ratings["rating"], errors="coerce")
    invalid_rating = (
        rating_values.isna()
        | (rating_values < 0.5)
        | (rating_values > 5.0)
        | ~((rating_values * 2).mod(1).abs() < 1e-9)
    )
    if invalid_rating.any():
        raise DataValidationError(
            f"ratings.csv.rating must use half-star values from 0.5 to 5.0 "
            f"({int(invalid_rating.sum())} invalid rows)"
        )
    ratings["rating"] = rating_values.astype("float64")

    for name, frame in (("ratings.csv", ratings), ("tags.csv", tags)):
        timestamps = pd.to_numeric(frame["timestamp"], errors="coerce")
        invalid_timestamp = timestamps.isna() | (timestamps < 0) | ((timestamps % 1) != 0)
        if invalid_timestamp.any():
            raise DataValidationError(
                f"{name}.timestamp must contain non-negative Unix-second integers "
                f"({int(invalid_timestamp.sum())} invalid rows)"
            )
        frame["timestamp"] = timestamps.astype("int64")

    tags["tag"] = tags["tag"].astype("string").str.strip()
    if tags["tag"].eq("").any():
        raise DataValidationError("tags.csv.tag values must not be blank")

    movie_ids = set(movies["movieId"])
    for name, frame in (("ratings.csv", ratings), ("tags.csv", tags), ("links.csv", links)):
        orphan_ids = sorted(set(frame["movieId"]) - movie_ids)
        if orphan_ids:
            raise DataValidationError(
                f"{name} references {len(orphan_ids)} movie IDs absent from movies.csv "
                f"(examples: {orphan_ids[:5]})"
            )

    for column in ("imdbId", "tmdbId"):
        values = pd.to_numeric(links[column], errors="coerce")
        invalid = links[column].notna() & (values.isna() | (values <= 0) | ((values % 1) != 0))
        if invalid.any():
            raise DataValidationError(f"links.csv.{column} must be blank or a positive integer ID")
    return data


def chronological_split(
    ratings: pd.DataFrame,
    validation_fraction: float = 0.1,
    test_fraction: float = 0.1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split each user's ratings chronologically, with deterministic tie-breaking.

    Users with fewer than three interactions remain in training so each held-out
    user has at least one training interaction and validation/test stay meaningful.
    """
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("validation_fraction and test_fraction must be between 0 and 1")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("validation_fraction + test_fraction must be less than 1")
    required = {"userId", "movieId", "timestamp"}
    if not required.issubset(ratings.columns):
        raise ValueError(f"ratings must contain columns: {sorted(required)}")
    if ratings.duplicated(["userId", "movieId"]).any():
        raise ValueError("ratings must have at most one interaction per user/movie pair")

    ordered = ratings.sort_values(["userId", "timestamp", "movieId"], kind="mergesort")
    train_indices: list[Any] = []
    validation_indices: list[Any] = []
    test_indices: list[Any] = []
    for _, group in ordered.groupby("userId", sort=True):
        indices = group.index.tolist()
        count = len(indices)
        if count < 3:
            train_indices.extend(indices)
            continue
        validation_count = max(1, math.floor(count * validation_fraction))
        test_count = max(1, math.floor(count * test_fraction))
        if validation_count + test_count >= count:
            validation_count = test_count = 1
        train_count = count - validation_count - test_count
        train_indices.extend(indices[:train_count])
        validation_indices.extend(indices[train_count : train_count + validation_count])
        test_indices.extend(indices[train_count + validation_count :])

    def ordered_subset(indices: list[Any]) -> pd.DataFrame:
        return ratings.loc[indices].sort_values(
            ["userId", "timestamp", "movieId"], kind="mergesort"
        ).reset_index(drop=True)

    return (
        ordered_subset(train_indices),
        ordered_subset(validation_indices),
        ordered_subset(test_indices),
    )


def _movie_features(movies: pd.DataFrame, tags: pd.DataFrame) -> pd.DataFrame:
    tags_by_movie = (
        tags.groupby("movieId", sort=True)["tag"]
        .agg(lambda values: json.dumps(sorted(set(values), key=lambda tag: (tag.casefold(), tag))))
        .rename("tags_json")
    )
    return movies.merge(tags_by_movie, on="movieId", how="left", validate="one_to_one").assign(
        tags_json=lambda frame: frame["tags_json"].fillna("[]")
    )


def _date_range(timestamps: pd.Series) -> dict[str, str | None]:
    if timestamps.empty:
        return {"first_utc": None, "last_utc": None}
    dates = pd.to_datetime(timestamps, unit="s", utc=True)
    return {
        "first_utc": dates.min().isoformat(),
        "last_utc": dates.max().isoformat(),
    }


def prepare_dataset(
    raw_dir: Path = RAW_DATA_DIR,
    processed_dir: Path = PROCESSED_DATA_DIR,
    archive_md5: str | None = None,
) -> dict[str, Any]:
    """Validate raw CSVs, create movie features and chronological splits, and save outputs."""
    raw_dir = Path(raw_dir)
    processed_dir = Path(processed_dir)
    metadata_path = raw_dir / "download_metadata.json"
    if archive_md5 is None and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        archive_md5 = metadata.get("archive_md5")
    frames = validate_dataset(_read_source_files(raw_dir))
    train, validation, test = chronological_split(frames["ratings.csv"])
    processed_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "movies_with_tags.csv": _movie_features(frames["movies.csv"], frames["tags.csv"]),
        "links.csv": frames["links.csv"],
        "train_ratings.csv": train,
        "validation_ratings.csv": validation,
        "test_ratings.csv": test,
    }
    for name, frame in outputs.items():
        frame.to_csv(processed_dir / name, index=False)

    counts = {
        "movies": int(len(frames["movies.csv"])),
        "users_with_ratings": int(frames["ratings.csv"]["userId"].nunique()),
        "ratings": int(len(frames["ratings.csv"])),
        "tag_applications": int(len(frames["tags.csv"])),
        "links": int(len(frames["links.csv"])),
        "train_ratings": int(len(train)),
        "validation_ratings": int(len(validation)),
        "test_ratings": int(len(test)),
    }
    manifest: dict[str, Any] = {
        "dataset": "MovieLens latest-small",
        "source_url": DATASET_URL,
        "checksum_url": CHECKSUM_URL,
        "source_readme_url": "https://files.grouplens.org/datasets/movielens/ml-latest-small-README.html",
        "archive_md5": archive_md5,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "counts": counts,
        "rating_timestamp_range": _date_range(frames["ratings.csv"]["timestamp"]),
        "split_policy": {
            "type": "per-user chronological",
            "ordering": ["timestamp", "movieId"],
            "validation_fraction": 0.1,
            "test_fraction": 0.1,
            "users_with_fewer_than_three_ratings": "kept entirely in training",
        },
        "outputs": sorted(outputs),
    }
    (processed_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    """Expose the ingestion workflow as ``python -m recommender.data.movielens``."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    download_parser = subparsers.add_parser(
        "download", help="download/checksum the official archive"
    )
    download_parser.add_argument("--raw-dir", type=Path, default=RAW_DATA_DIR)
    prepare_parser = subparsers.add_parser(
        "prepare", help="validate CSVs and create processed outputs"
    )
    prepare_parser.add_argument("--raw-dir", type=Path, default=RAW_DATA_DIR)
    prepare_parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DATA_DIR)
    args = parser.parse_args()

    if args.command == "download":
        digest = download_dataset(args.raw_dir)
        print(f"Downloaded MovieLens latest-small to {args.raw_dir} (MD5 {digest})")
        return
    manifest = prepare_dataset(args.raw_dir, args.processed_dir)
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
