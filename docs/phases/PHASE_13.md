# Phase 13: Reproducibility, migrations and experiments

## Goal
Make runtime dependencies repeatable, preserve existing ratings through additive
schema migrations, and provide opt-in experiment tracking and implicit feedback
benchmarks without burdening production with research dependencies.

## Deliverables
Universal hashed lockfiles, CI browser journeys, Alembic upgrades that adopt the
existing ratings table without deleting rows, optional MLflow logging with data
fingerprints, and an isolated implicit BPR/ALS experiment using a documented
positive-event conversion. pgvector remains a documented opt-in storage upgrade;
exact NumPy search stays the deployed retrieval implementation.

## Checks
Migration preservation tests, pytest, Ruff, browser journeys, locked dependency
resolution, JavaScript/config checks and a fresh checkout simulation. Never claim
an optional experiment was executed unless it was actually run.
