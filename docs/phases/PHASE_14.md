# Phase 14: Validation-selected visitor recommendations

## Goal
Replace fixed visitor weights with an explicitly evaluated policy and make plot
embeddings available as a personalized content signal without adding services.

## Deliverables
- Shared component scoring and policy selection used identically in evaluation
  and serving, with balanced and broader-discovery modes.
- Fixed, disjoint fitting/validation/test user partitions; withheld-user tags
  excluded; validation-only selection before held-out test scoring.
- Identical candidate catalogs and exclusions across compared methods.
- Versioned small policy configuration, exact semantic profile scoring, honest
  missing-metadata fallbacks and explanations.
- Build-time policy loading without training or network requests while serving.

## Verification
Run unit/API checks, ranking parity and partition-isolation tests, then execute
one real-data validation/test report. Do not advertise improvements unless the
executed results support them. Static plot metadata is not historically filtered;
this experiment is separate from the chronological known-user benchmark.

The owner authorized this phase and the subsequent UX/deployment work on
2026-10-31. Existing ratings, raw data, profile credentials and access settings
must be preserved. The protected production verification gate remains open.
