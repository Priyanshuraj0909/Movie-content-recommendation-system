import tomllib
from pathlib import Path

from recommender import __version__
from recommender.config import ARTIFACTS_DIR, DATA_DIR, RANDOM_SEED


def test_project_settings_are_reproducible() -> None:
    metadata = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert __version__ == metadata["project"]["version"]
    assert RANDOM_SEED == 42
    assert DATA_DIR == Path(__file__).resolve().parents[1] / "data"
    assert ARTIFACTS_DIR == Path(__file__).resolve().parents[1] / "artifacts"


def test_sensitive_and_generated_files_are_ignored() -> None:
    gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text()
    for pattern in (".env", "data/raw/*", "data/processed/*", "artifacts/*"):
        assert pattern in gitignore
