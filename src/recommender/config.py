"""Shared, reproducible project settings."""

from pathlib import Path


def _find_project_root() -> Path:
    """Find the checkout root even when the package is installed in site-packages."""
    candidates = (Path.cwd(), *Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (candidate / "src/recommender").is_dir():
            return candidate
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
RANDOM_SEED = 42
