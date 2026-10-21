# Phase 09: Vercel full-stack deployment

## Goal
Deploy CineMatch on Vercel while preserving its recommendation API and rating workflow.

## Tasks
- Keep the current Streamlit app available for local use and add a static browser frontend for Vercel.
- Route browser API requests to the existing FastAPI app through Vercel Services.
- Use SQLite for local development and `DATABASE_URL` for hosted PostgreSQL ratings.
- Generate MovieLens metadata and model artifacts during the backend build; keep generated data and secrets out of Git.
- Link the GitHub repository to the Vercel account and deploy after the database is configured.

## Deliverables
Vercel service configuration, static UI, hosted database support, deployment documentation and a verified deployment.

## Verification
Run the Python test and Ruff checks, validate the Vercel configuration, exercise the browser UI against the API locally, and verify the deployed health, search, similar-film, recommendation and rating flows.

## Guardrails
Keep credentials and generated datasets/models out of Git. Do not declare the phase complete until the hosted database is configured and the deployed app passes its end-to-end checks.
