# Phase 05: Hybrid engine and evaluation
## Goal
Blend recommenders and measure ranking quality without leakage.
## Tasks
Normalize component scores; tune blending on validation only; evaluate on untouched test split; add optional MLflow logging.
## Deliverables
Working code, tests, documentation and a verified PROGRESS.md entry.
## Verification
`python -m pytest -q`
## Acceptance criteria
Precision@10, Recall@10, NDCG@10, coverage reported with reproducible splits.
## Guardrails
Read AGENTS.md and PLAN.md first. Avoid scope creep. Do not proceed to the next phase without approval.
