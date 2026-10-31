# Visitor policy selection — CineMatch 0.3

Executed on 2026-10-31 using MovieLens latest-small, seed 20261031, 366 fitting users, 122 validation users and 122 disjoint test users. This is one fixed partition of a previously explored benchmark, not a claim of performance on new real visitors.

Policies were selected by validation NDCG@10, then recall, then simplicity. All four onboarding policies were frozen and exported before test-user histories were scored. A regression test verifies that changing test feedback cannot change the exported configuration.

Every method uses the entire 9,742-film catalog, excludes onboarding-rated films and treats later ratings >= 4 as relevant. Fitting tags exclude validation/test authors and tags after each fitting author’s training cutoff. Static CMU plots are not historically filtered, so this experiment is separate from the chronological known-user benchmark.

| Onboarding ratings | Selected NDCG@10 | Popularity | Legacy v0.2 | Discover more |
|---|---:|---:|---:|---:|
| 1 | 0.3108 | 0.3060 | 0.1596 | 0.2619 |
| 3 | 0.2996 | 0.2925 | 0.0924 | 0.2557 |
| 5 | 0.2989 | 0.2847 | 0.0826 | 0.2648 |
| 10 | 0.2814 | 0.2643 | 0.1441 | 0.2413 |

At five ratings the selected policy improves observed NDCG over popularity by approximately 5%. Statistical significance has not been established. Results do not prove production improvements or generalization to different onboarding choices.

| Five-rating policy | Catalog coverage |
|---|---:|
| selected | 0.51% |
| popularity | 0.14% |
| legacy_v02 | 7.57% |
| discovery | 1.53% |

The default favors accuracy; discovery offers a broader mix with a measured accuracy tradeoff. The legacy policy reaches more of the catalog but scores much lower on accuracy in this experiment.

## Frozen serving policy

- Zero ratings: training-derived community popularity.
- One through nine ratings: 0.85 popularity + 0.15 signed TF-IDF preferences.
- Ten or more ratings: 0.70 popularity + 0.15 TF-IDF + 0.10 visitor collaborative factors + 0.05 plot similarity.
- Discover more after feedback: fixed 0.50 popularity + 0.15 TF-IDF + 0.10 collaborative + 0.25 plot similarity, with genre diversity 0.08. Collaborative contributions fall back to popularity below three ratings.

Plot profiles use stored vectors, with positive and negative preference signals and zero contribution for missing plots. No encoder inference or network download runs to construct a visitor plot profile.

Recommendation IDs are selected by the same `score_visitor` and `rank_signals` functions in serving and evaluation. Explanations use real metadata or actual shared-content/plot scores. Explicit watched/dismissed states affect serving exclusions independently of numeric ratings; they were not simulated in this rating-only benchmark.

Reproduce with `python -m recommender.evaluation.visitor_selection`. Its default export stays in ignored artifacts. Use `--export-policy src/recommender/services/visitor_policy.json` only when intentionally promoting a newly validated policy. Do not tune against the reported test results.

The full report, user partition IDs, bootstrap intervals and configuration digest remain in `artifacts/visitor_selection_metrics.json`. The tracked JSON contains only policy configuration.
