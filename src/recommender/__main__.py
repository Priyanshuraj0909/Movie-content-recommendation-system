"""Provide a small environment smoke check via ``python -m recommender``."""

from recommender import __version__
from recommender.config import ARTIFACTS_DIR, DATA_DIR


def main() -> None:
    """Print project paths without creating files or downloading data."""
    print(f"Movie recommender {__version__}")
    print(f"Data directory: {DATA_DIR}")
    print(f"Artifacts directory: {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
