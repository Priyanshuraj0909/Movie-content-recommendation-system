# Phase 01: Foundation
## Goal
Create reproducible M2-compatible project scaffolding, dependency installation and smoke tests.
## Tasks
Confirm arm64 Python 3.11/3.12; create virtualenv; configure Ruff/Pytest; create src package, config, sample tests; document run commands.
## Deliverables
Working code, tests, documentation and a verified PROGRESS.md entry.
## Verification
`python -m pytest -q; python -m ruff check .`
## Acceptance criteria
Clean checkout installs and tests pass; no secrets committed.
## Guardrails
Read AGENTS.md and PLAN.md first. Avoid scope creep. Do not proceed to the next phase without approval.
