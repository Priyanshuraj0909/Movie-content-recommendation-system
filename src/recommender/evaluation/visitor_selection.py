"""Select visitor policies using validation users, then score disjoint test users."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR
from recommender.data.movielens import _movie_features, training_tags
from recommender.evaluation.ranking import _ndcg
from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender
from recommender.models.semantic import DEFAULT_DIRECTORY, SemanticIndex
from recommender.services.policy import DISCOVERY_POLICY, POPULARITY_POLICY, RankPolicy
from recommender.services.visitor import rank_signals, recommend_legacy_visitor, score_visitor

SEED = 20261031
# Fixed before reading validation or test results. Each policy sums to one.
POLICIES = {
    "popularity": POPULARITY_POLICY,
    "pop_cf_05": RankPolicy(0.95, 0, 0.05, 0),
    "pop_cf_15": RankPolicy(0.85, 0, 0.15, 0),
    "pop_cf_30": RankPolicy(0.7, 0, 0.3, 0),
    "pop_content_05": RankPolicy(0.95, 0.05, 0, 0),
    "pop_content_15": RankPolicy(0.85, 0.15, 0, 0),
    "pop_story_05": RankPolicy(0.95, 0, 0, 0.05),
    "pop_story_15": RankPolicy(0.85, 0, 0, 0.15),
    "mixed_light": RankPolicy(0.8, 0.05, 0.1, 0.05),
    "mixed_story": RankPolicy(0.7, 0.05, 0.1, 0.15),
    "mixed_content": RankPolicy(0.7, 0.15, 0.1, 0.05),
    "mixed_diverse": RankPolicy(0.8, 0.05, 0.1, 0.05, 0.03),
    "discovery": DISCOVERY_POLICY,
}


def partition_users(user_ids, *, seed=SEED):
    users = np.asarray(sorted(set(user_ids)), dtype=np.int64)
    if len(users) < 5:
        raise ValueError("At least five users are required for three disjoint partitions")
    shuffled = np.random.default_rng(seed).permutation(users)
    size = max(1, len(users) // 5)
    return {
        "validation": set(shuffled[:size].tolist()),
        "test": set(shuffled[size : 2 * size].tolist()),
        "fitting": set(shuffled[2 * size :].tolist()),
    }


def summarize(rows, recommended, catalog_size):
    if not rows:
        raise ValueError("No eligible users in this evaluation cohort")
    values = np.asarray(rows)
    rng = np.random.default_rng(SEED)
    bootstrap = rng.choice(values[:, 2], (1000, len(values)), replace=True).mean(axis=1)
    return {
        "eligible_users": len(values),
        "precision_at_10": float(values[:, 0].mean()),
        "recall_at_10": float(values[:, 1].mean()),
        "ndcg_at_10": float(values[:, 2].mean()),
        "coverage": len(recommended) / catalog_size,
        "ndcg_95_percent_bootstrap_interval": np.quantile(bootstrap, [0.025, 0.975]).tolist(),
    }


def evaluate_cohort(interactions, users, count, content, model, catalog, policies, semantic):
    rows = {name: [] for name in policies}
    items = {name: set() for name in policies}
    rows["legacy_v02"] = []
    items["legacy_v02"] = set()
    for uid in sorted(users):
        history = interactions.loc[interactions.userId.eq(uid)].sort_values(
            ["timestamp", "movieId"], kind="stable"
        )
        observed = history.iloc[:count]
        feedback = dict(zip(observed.movieId.astype(int), observed.rating, strict=True))
        remaining = history.iloc[count:]
        relevant = set(remaining.loc[remaining.rating.ge(4), "movieId"].astype(int))
        relevant &= set(catalog) - set(feedback)
        if not relevant:
            continue
        signals = score_visitor(content, model, feedback, catalog, semantic_index=semantic)
        for name in rows:
            if name == "legacy_v02":
                picks = [
                    pick.movie_id
                    for pick in recommend_legacy_visitor(
                        content, model, feedback, catalog, limit=10
                    )
                ]
            else:
                positions, _ = rank_signals(signals, catalog, policies[name], limit=10)
                picks = signals.movie_ids[positions].tolist()
            hits = len(set(picks) & relevant)
            rows[name].append((hits / 10, hits / len(relevant), _ndcg(picks, relevant, 10)))
            items[name].update(picks)
    return {name: summarize(values, items[name], len(catalog)) for name, values in rows.items()}


def select_policy(metrics):
    """Select exclusively from validation metrics; favor simplicity on exact ties."""
    return max(
        POLICIES,
        key=lambda name: (
            metrics[name]["ndcg_at_10"],
            metrics[name]["recall_at_10"],
            -sum(value > 0 for value in asdict(POLICIES[name]).values()),
            name,
        ),
    )


def run_selection(
    training,
    interactions,
    movie_metadata,
    tags,
    *,
    semantic=None,
    counts=(1, 3, 5, 10),
    export_path=None,
):
    partitions = partition_users(training.userId)
    fitting = training.loc[training.userId.isin(partitions["fitting"])]
    movies = _movie_features(movie_metadata, training_tags(tags, fitting))
    model = CollaborativeRecommender(seed=SEED).fit(fitting)
    content = ContentRecommender().fit(movies)
    catalog = movies.set_index("movieId").to_dict("index")
    validation, selections = {}, {}
    # No test-user histories are inspected until all policies have been frozen.
    validation_interactions = interactions.loc[interactions.userId.isin(partitions["validation"])]
    for count in counts:
        metrics = evaluate_cohort(
            validation_interactions,
            partitions["validation"],
            count,
            content,
            model,
            catalog,
            POLICIES,
            semantic,
        )
        validation[str(count)] = metrics
        selections[str(count)] = select_policy(metrics)
    config = {
        "format_version": 1,
        "seed": SEED,
        "selection": "validation users only; NDCG@10 then recall then simplicity",
        "semantic_available_during_selection": semantic is not None,
        "policies": {count: asdict(POLICIES[name]) for count, name in selections.items()},
    }
    if export_path is not None:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(config, indent=2) + "\n")
    policy_digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    test_interactions = interactions.loc[interactions.userId.isin(partitions["test"])]
    test = {}
    for count in counts:
        test[str(count)] = evaluate_cohort(
            test_interactions,
            partitions["test"],
            count,
            content,
            model,
            catalog,
            {
                "selected": POLICIES[selections[str(count)]],
                "popularity": POPULARITY_POLICY,
                "discovery": DISCOVERY_POLICY,
            },
            semantic,
        )
    return {
        "protocol": {
            "seed": SEED,
            "user_partitions": {name: sorted(ids) for name, ids in partitions.items()},
            "catalog_movies": len(catalog),
            "counts": list(counts),
            "candidates": "shared catalog excluding onboarding-rated items",
            "relevance": "later visitor rating >= 4; K=10",
            "training_tags": "only fitting authors, before their last training-rating timestamp",
            "plots": "static attributed corpus; not a global historical simulation",
            "test_use": "scored after all validation selections and configuration export",
            "limitations": "one fixed user partition on a previously explored benchmark dataset",
            "policy_sha256_before_test": policy_digest,
        },
        "selected_policies": selections,
        "configuration": config,
        "validation": validation,
        "test": test,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ARTIFACTS_DIR / "visitor_selection_metrics.json"
    )
    parser.add_argument(
        "--export-policy", type=Path, default=ARTIFACTS_DIR / "selected_visitor_policy.json"
    )
    args = parser.parse_args()
    semantic = SemanticIndex() if (DEFAULT_DIRECTORY / "manifest.json").is_file() else None
    report = run_selection(
        pd.read_csv(PROCESSED_DATA_DIR / "train_ratings.csv"),
        pd.read_csv(RAW_DATA_DIR / "ratings.csv"),
        pd.read_csv(RAW_DATA_DIR / "movies.csv"),
        pd.read_csv(RAW_DATA_DIR / "tags.csv"),
        semantic=semantic,
        export_path=args.export_policy,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"selected_policies": report["selected_policies"], "test": report["test"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
