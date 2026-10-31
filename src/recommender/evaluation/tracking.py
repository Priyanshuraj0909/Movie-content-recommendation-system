"""Optional MLflow tracking; serving never imports or requires MLflow."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, PROJECT_ROOT


def flatten_metrics(value, prefix=""):
    metrics = {}
    if isinstance(value, dict):
        for key, item in value.items():
            metrics.update(flatten_metrics(item, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, int | float) and not isinstance(value, bool):
        metrics[prefix] = float(value)
    return metrics


def log_report(report_path: Path, *, tracking_uri: str | None = None) -> str:
    try:
        import mlflow
    except ImportError as error:
        raise RuntimeError("Install requirements-research.txt to enable MLflow tracking") from error
    report = json.loads(report_path.read_text())
    mlflow.set_tracking_uri(tracking_uri or f"sqlite:///{ARTIFACTS_DIR / 'mlflow.db'}")
    mlflow.set_experiment("CineMatch recommendation experiments")
    with mlflow.start_run(run_name=report_path.stem) as run:
        mlflow.log_metrics(
            flatten_metrics({key: value for key, value in report.items() if key != "protocol"})
        )
        manifest = PROCESSED_DATA_DIR / "dataset_manifest.json"
        if manifest.is_file():
            mlflow.log_param(
                "dataset_manifest_sha256", hashlib.sha256(manifest.read_bytes()).hexdigest()
            )
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
        mlflow.set_tag("git_commit", revision.stdout.strip() or "unavailable")
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
        )
        mlflow.set_tag("git_dirty", bool(dirty.stdout.strip()))
        source_digest = hashlib.sha256()
        for folder in ("src", "backend", "scripts"):
            for path in sorted((PROJECT_ROOT / folder).rglob("*.py")):
                source_digest.update(str(path.relative_to(PROJECT_ROOT)).encode())
                source_digest.update(path.read_bytes())
        mlflow.set_tag("source_sha256", source_digest.hexdigest())
        mlflow.set_tag("purpose", "offline benchmark; not a production quality guarantee")
        mlflow.log_artifact(str(report_path))
        return run.info.run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--tracking-uri")
    args = parser.parse_args()
    print(json.dumps({"run_id": log_report(args.report, tracking_uri=args.tracking_uri)}))


if __name__ == "__main__":
    main()
