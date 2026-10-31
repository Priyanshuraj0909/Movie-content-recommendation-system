# Authorized upgrade roadmap

The owner authorized implementation, dependencies, GitHub updates and deployment
across the following phases on 2026-10-31. Work remains sequential; no additional
between-phase approval is needed. Existing datasets and visitor ratings must be
preserved. Production completion always requires actual deployment evidence.

1. Phase 9: finish release verification and add reproducible browser checks.
2. Phase 10: isolate visitors from benchmark users, personalize from submitted
   ratings, protect owned profiles, and add explanations and feedback controls.
3. Phase 11: improve temporal evaluation and evaluate unseen visitors separately.
4. Phase 12: enrich the catalog using attributed public movie summaries and add
   semantic discovery, without requiring paid APIs or external credentials.
5. Phase 13: lock dependencies, migrate databases, track experiments optionally,
   and add reproducible ranking experiments and operational documentation.
6. Release: run all checks, push to the existing GitHub repository, observe Vercel
   deployment status, and exercise production flows with a dedicated test profile.

The Phase 9 live gate currently redirects to Vercel Authentication and the local
Vercel CLI is logged out. This does not count as verification. Independent local
upgrade preparation may continue under the owner's all-phases authorization;
Phase 9 and the final release remain pending until live checks succeed.

pgvector and implicit/LightFM remain opt-in experiments. Exact NumPy retrieval is
appropriate for the current catalog; a new vector service is not a prerequisite.

## Authorized v0.3 iteration

The owner renewed implementation and deployment authorization on 2026-10-31.
Phase 14 validates and freezes visitor policies and adds semantic preferences.
Phase 15 delivers onboarding, a private editable library, and independent
watched/dismissed feedback through an additive migration. Production persistence
remains an explicit gate until authorized live verification is possible.
