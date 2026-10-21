# Model card: CineMatch movie recommendations

## Summary

- **Version:** project 0.1.0, Phase 5 hybrid ranker
- **Task:** rank movies a local user may want to watch
- **Components:** title/genre/tag TF-IDF with cosine similarity; regularized
  user/item bias estimates; seeded SGD matrix factorization; validation-tuned
  content/collaborative score blend; popularity fallback
- **Selected blend:** 0.75 collaborative and 0.25 content, chosen by validation
  NDCG@10 over weights 0, 0.25, 0.5, 0.75 and 1.0

## Intended use

This is a local-first educational and portfolio demonstration. It supports
movie search, similar-item discovery, explicit ratings and recommendation
experiments. It is not validated for commercial ranking, sensitive decisions,
or high-availability service.

## Training and data

The project uses GroupLens MovieLens latest-small. Its latest-small snapshot
contains 9,742 movies and 100,836 ratings from 610 users; the project validator
checks downloaded counts and references. The split is chronological per user:
81,200 training ratings, 9,818 validation ratings and 9,818 test ratings.
Models fit on the training split. Relevance for top-K ranking is a held-out
rating of 4.0 or more. Blend weight selection uses validation only; the final
report evaluates that selected blend once on the held-out test partition.

Content features are movie title, genres and aggregated user tags. MovieLens
does not provide plot descriptions in this project. Demographic features are
not used. Rating feedback is explicit and can be changed by resubmitting a
rating for the same local user/movie pair.

## Evaluation

On the recorded split, the selected hybrid achieved test Precision@10 0.0264,
Recall@10 0.0435 and NDCG@10 0.0381 over 557 eligible users. Test NDCG@10 was
0.0317 for popularity, 0.0112 for content-only, 0.0326 for collaborative-only
and 0.0381 for the hybrid. The complete report is created locally at
`artifacts/ranking_metrics.json` and is intentionally not committed.

These are offline results on a small public benchmark, not a user study or a
generalization guarantee. They depend on the dataset snapshot, temporal split,
relevance threshold, and candidate catalog.

## Limitations and risks

- MovieLens is sparse, has a narrow community and reflects its users' rating
  patterns. Popularity and matrix-factorization scores may reproduce that
  group's preferences.
- A movie with no training ratings is not in the collaborative candidate
  catalog. New users receive a popularity fallback until they submit positive
  ratings; then their content profile can contribute.
- Tags and genres are incomplete preference signals. The model cannot reason
  about plot, quality, availability, language preference or user context.
- Numeric profile IDs are local identifiers, not authentication. Do not expose
  this demo API to the public internet without adding identity, authorization,
  rate limits and privacy controls.
- GroupLens dataset licensing restricts commercial use without prior
  permission. Check the current dataset terms before any non-personal use.

## Monitoring and updates

Rerun the documented chronological split, validation tuning and untouched test
evaluation whenever the dataset or model code changes. Compare all rankers on
the same user and candidate sets, then review novelty and catalog coverage
alongside accuracy. Keep generated data, user ratings and fitted artifacts out
of source control.
