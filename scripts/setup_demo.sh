#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

run_evaluation=1
if [[ "${1:-}" == "--skip-evaluation" ]]; then
  run_evaluation=0
fi

if [[ ! -f data/processed/dataset_manifest.json ]]; then
  source_files=(movies.csv ratings.csv tags.csv links.csv)
  source_count=0
  for filename in "${source_files[@]}"; do
    if [[ -f "data/raw/$filename" ]]; then
      source_count=$((source_count + 1))
    fi
  done
  if [[ "$source_count" == "0" ]]; then
    python -m recommender.data.movielens download
  elif [[ "$source_count" != "${#source_files[@]}" ]]; then
    echo "Found a partial raw dataset in data/raw; complete all four CSVs before setup." >&2
    exit 1
  fi
  python -m recommender.data.movielens prepare
fi

if [[ ! -f artifacts/content_recommender.joblib ]]; then
  python -m recommender.models.content
fi

if [[ ! -f artifacts/collaborative_recommender.joblib ]]; then
  python -m recommender.models.collaborative
fi

if [[ "$run_evaluation" == "1" && ! -f artifacts/ranking_metrics.json ]]; then
  python -m recommender.evaluation.ranking
fi

echo "Demo data and models are ready. Start the API and UI in separate terminals."
