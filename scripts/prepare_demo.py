"""Prepare reproducible demo artifacts, rebuilding only when their inputs change."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, PROJECT_ROOT, RAW_DATA_DIR
from recommender.data.movielens import REQUIRED_FILES, download_dataset, prepare_dataset


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(Path(path).relative_to(PROJECT_ROOT)).encode())
        with Path(path).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument(
        "--skip-semantic", action="store_true", help="Prepare a smaller title-only demo"
    )
    args = parser.parse_args()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    state_path = ARTIFACTS_DIR / "preparation.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    present = [name for name in REQUIRED_FILES if (RAW_DATA_DIR / name).is_file()]
    if not present:
        download_dataset()
    elif len(present) != len(REQUIRED_FILES):
        raise SystemExit("Raw dataset is incomplete; existing files have been preserved")
    data_inputs = [RAW_DATA_DIR / name for name in REQUIRED_FILES]
    data_inputs.append(PROJECT_ROOT / "src/recommender/data/movielens.py")
    data_hash = fingerprint(data_inputs)
    if (
        state.get("data") != data_hash
        or not (PROCESSED_DATA_DIR / "dataset_manifest.json").is_file()
    ):
        prepare_dataset()
        state["data"] = data_hash
    for model, inputs in (
        ("content", [PROCESSED_DATA_DIR / "movies_with_tags.csv"]),
        ("collaborative", [PROCESSED_DATA_DIR / "train_ratings.csv"]),
    ):
        inputs.append(PROJECT_ROOT / f"src/recommender/models/{model}.py")
        signature = fingerprint(inputs)
        if (
            state.get(model) != signature
            or not (ARTIFACTS_DIR / f"{model}_recommender.joblib").is_file()
        ):
            subprocess.run([sys.executable, "-m", f"recommender.models.{model}"], check=True)
            state[model] = signature
    if not args.skip_semantic:
        signature = fingerprint(
            [
                PROCESSED_DATA_DIR / "movies_with_tags.csv",
                PROJECT_ROOT / "src/recommender/data/plots.py",
            ]
        )
        if (
            state.get("plots") != signature
            or not (PROCESSED_DATA_DIR / "movie_plots.csv").is_file()
        ):
            subprocess.run([sys.executable, "-m", "recommender.data.plots"], check=True)
            state["plots"] = signature
        signature = fingerprint(
            [
                PROCESSED_DATA_DIR / "movie_plots.csv",
                PROJECT_ROOT / "src/recommender/models/semantic.py",
            ]
        )
        if (
            state.get("semantic") != signature
            or not (ARTIFACTS_DIR / "semantic/manifest.json").is_file()
        ):
            subprocess.run([sys.executable, "-m", "recommender.models.semantic"], check=True)
            state["semantic"] = signature
    if not args.skip_evaluation:
        signature = fingerprint(
            [
                PROCESSED_DATA_DIR / "dataset_manifest.json",
                ARTIFACTS_DIR / "content_recommender.joblib",
                ARTIFACTS_DIR / "collaborative_recommender.joblib",
                PROJECT_ROOT / "src/recommender/evaluation/ranking.py",
            ]
        )
        if (
            state.get("ranking") != signature
            or not (ARTIFACTS_DIR / "ranking_metrics.json").is_file()
        ):
            subprocess.run([sys.executable, "-m", "recommender.evaluation.ranking"], check=True)
            state["ranking"] = signature
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print("Demo artifacts are ready; visitor ratings and raw source files were preserved.")


if __name__ == "__main__":
    main()
