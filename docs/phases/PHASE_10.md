# Phase 10: Visitor personalization and profile ownership

## Goal
Give visitors recommendations based on their own ratings without borrowing
MovieLens identities, and protect browser profiles with unguessable credentials.

## Deliverables
- Regularized visitor factor estimation with fixed offline item factors.
- Shared visitor ranker with content-first cold start, negative preference signals,
  factual explanations, and bounded diversity reranking.
- Server-issued profiles, hashed bearer credentials, rating history and watchlist.
- Browser onboarding and restore using a private recovery code.
- Integration tests for isolation, ownership, persistence and feedback behavior.

## Verification
Run pytest, Ruff, JavaScript syntax checks, and the real Playwright journeys.
No old rating rows or browser-local watchlists are deleted. Legacy numeric
profiles remain local-only; hosted profile access requires a credential.
