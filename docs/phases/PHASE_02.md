# Phase 02: Data ingestion and preprocessing
## Goal
Load MovieLens latest-small and prepare validated movie, rating and tag datasets.
## Tasks
Add download instructions and checksum/source notes; validate IDs and missing values; merge tags safely; create chronological splits; save processed outputs.
## Deliverables
Working code, tests, documentation and a verified PROGRESS.md entry.
## Verification
`python -m pytest -q; python -m ruff check .`
## Acceptance criteria
Dataset statistics recorded; no user/item leakage; tests cover preprocessing.
## Guardrails
Read AGENTS.md and PLAN.md first. Avoid scope creep. Do not proceed to the next phase without approval.
