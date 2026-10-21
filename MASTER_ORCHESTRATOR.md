# Master Orchestrator
## Mission
Build a tested, explainable, portfolio-ready hybrid movie recommendation platform on Apple Silicon.
## Source of truth
1. AGENTS.md: permanent agent rules.
2. PLAN.md: architecture and acceptance criteria.
3. docs/phases/PHASE_XX.md: current phase execution contract.
4. PROGRESS.md: verified project status.
## Workflow
1. Read all four documents.
2. Identify the first unfinished phase; never skip prerequisites.
3. Propose a concise task breakdown and file changes.
4. Implement only the active phase in small, reviewable increments.
5. Run format/lint/tests appropriate to the phase; report exact commands and results.
6. Check acceptance criteria; document known limitations.
7. Update PROGRESS.md, and stop. Wait for approval to begin the next phase.
## Engineering rules
- Use a Python virtual environment; avoid global installs.
- Keep data loading, algorithms, evaluation, API and UI separate.
- Use deterministic seeds, versioned config, and test fixtures.
- Prevent train/test leakage and exclude watched items from recommendations.
- Never commit credentials, raw datasets, large model binaries or .env.
- Never claim an experiment metric without executing the experiment.
- Use content-based fallback for new users; collaborative ranking only when ratings are sufficient.
- Keep endpoints typed and validate user input.
## End-of-phase report
Summary; files changed; tests and results; blockers; next phase.
