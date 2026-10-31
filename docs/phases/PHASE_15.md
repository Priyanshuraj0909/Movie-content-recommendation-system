# Phase 15: Taste onboarding, library management and explicit feedback

## Goal
Help visitors establish and manage preferences without confusing watched or
unwanted films with numeric ratings.

## Deliverables
- An accessible five-film onboarding dialog with search, saved-rating progress
  and an early exit to recommendations.
- A private, paginated taste library with editable ratings and reversible
  watched/not-interested states. No existing rating or watchlist is deleted.
- Additive state-table migration; owned feedback routes and persistent exclusions.
- Balanced/discovery controls with understandable labels and no accuracy promises.
- Atomic recovery-code restoration that leaves the active profile unchanged
  when validation fails, and bounded public-ratings batches for larger lists.

## Verification
API ownership, persistence, status-versus-rating semantics, pagination and
migration preservation tests. Playwright onboarding, edit/undo, profile-restore
failure and mobile journeys. Re-run the complete suite and update progress only
from executed results. Preserve the unresolved protected production gate.
