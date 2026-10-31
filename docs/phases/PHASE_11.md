# Phase 11: Temporal features and unseen-visitor evaluation

## Goal
Measure the deployed visitor policy separately from known-user benchmarks and
prevent later tag applications from entering temporal training features.

## Deliverables
Filter each tag against its author's training-history cutoff. This is a per-user
availability approximation, not a global historical deployment simulation.
Record excluded tag counts and feature-policy versions in the dataset manifest.
Hold out entire users from collaborative fitting, reveal their earliest 1/3/5/10
ratings, and compare popularity, content and deployed visitor ranking on identical
candidates. Report eligible counts, NDCG@10, recall, precision and coverage.

## Checks
Timestamp regression tests, shared-policy evaluation tests, complete pytest and
Ruff checks, and an executed real-data report before publishing new metrics.
