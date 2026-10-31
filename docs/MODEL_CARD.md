# Model card: CineMatch 0.3

## Scope

Educational movie discovery with three separately evaluated tasks: known-user
ranking, unseen-visitor personalization and plot-based semantic retrieval.
MovieLens benchmark users and application visitor identities are independent.
Scores are ranking signals, not calibrated match probabilities.

## Training features and temporal policy

MovieLens latest-small: 9,742 films, 610 users and 100,836 explicit ratings.
Per-user chronological partitions contain 81,200 training, 9,818 validation and
9,818 test interactions. Training tags must precede their author's final training
rating; authors absent from fitting contribute no training tags. This retains
1,419 of 3,683 applications in the main training features. It is a per-author
availability approximation, not a globally time-consistent historical replay.

Content TF-IDF uses titles, genres and eligible tags. Collaborative fitting uses
regularized biases and 32-factor seeded SGD. Plot summaries are not used in this
chronological benchmark. New catalog items can participate in visitor content
ranking without having trained collaborative factors.

## Known-user result, rerun 2026-10-31

Identical training-rated candidate sets, training-history exclusion, relevance
rating >= 4, K=10. Validation selects collaborative weight 0.75. Test includes
557 eligible users and 8,255 candidate movies.

| Method | Precision@10 | Recall@10 | NDCG@10 |
|---|---:|---:|---:|
| Popularity | 0.0187 | 0.0330 | 0.0317 |
| Content | 0.0066 | 0.0160 | 0.0104 |
| Collaborative | 0.0224 | 0.0326 | 0.0326 |
| Selected hybrid | 0.0226 | 0.0350 | 0.0323 |

Hybrid catalog coverage is 4.80%. It does not beat collaborative-only NDCG on
this split. Earlier all-tag metrics in historical progress notes are superseded.
The blend was not retuned against this test result.

## Historical v0.2 visitor policy and evaluation

Serving uses only submitted visitor ratings. A regularized least-squares solve
estimates the visitor's bias and factors against fixed item vectors. Content
includes liked films and a negative contribution for ratings <= 2.5. Neutral
ratings exclude watched films without being counted as likes. Collaborative
weight ramps to 0.5 at ten ratings, with a small popularity term; a shortlist
reranker applies genre diversity 0.12. These are documented heuristics.

The unseen-visitor experiment withholds 122 users (seed 42) entirely from
collaborative fitting, removes their tags from fitting features, and reveals the
earliest 1/3/5/10 ratings. All catalog films except onboarding-rated films are
candidates. Relevant items are later ratings >= 4. A user's remaining history
can be much longer than in the known-user test, so the two tasks' absolute scores
are not comparable. Bootstrap intervals are descriptive user-resampling intervals,
not evidence of production improvement.

| Onboarding ratings | Popularity NDCG@10 | Visitor NDCG@10 | Visitor coverage |
|---|---:|---:|---:|
| 1 | 0.2161 | 0.1104 | 4.93% |
| 3 | 0.2113 | 0.0726 | 6.68% |
| 5 | 0.2040 | 0.0811 | 7.32% |
| 10 | 0.1918 | 0.1341 | 6.52% |

The visitor policy increases discovery breadth but underperforms popularity on
accuracy in this experiment. More personalization is not automatically better.
A future policy selection should use separate validation visitors before a fresh
user-held-out test, and should report accuracy and diversity together.

## Current v0.3 visitor policy

The serving default now uses frozen validation-selected configuration; the
historical heuristic above is retained only as an explicit experimental baseline.
Selection uses 366 fitting users and 122 validation users; all policies are
exported before scoring 122 separate test users. This is a new partition of an
already explored dataset, not an entirely new dataset.

At five onboarding ratings, selected NDCG@10 is 0.2989 versus popularity 0.2847
and legacy v0.2 0.0826 on identical test users and candidates. These observed
results do not establish statistical significance or production quality.
Discovery mode scores 0.2648 with 1.53% coverage, versus 0.51% for the default.
See [the complete selection protocol](VISITOR_EVALUATION.md).

The default uses popularity and signed TF-IDF for one through nine ratings,
then adds fixed-item visitor factor estimation and a small plot-profile signal
at ten or more. Discovery uses a larger plot contribution and genre reranking.
Semantic preference profiles are constructed from stored embeddings; no text
encoder is called for that operation. Missing plots contribute zero. Watched and
not-interested states are independent, reversible exclusions, not star ratings.

## Semantic retrieval

CMU Movie Summary Corpus plots from Wikipedia, attributed to its contributors
and Bamman, O'Connor and Smith, are distributed under CC BY-SA 3.0 US. Exact
normalized title/year matching yields 5,952 catalog matches and rejects 12
ambiguous records. Corpus and model file digests are pinned in code.

`sentence-transformers/all-MiniLM-L6-v2`, Apache-2.0, revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, uses its published quantized ONNX
model, masked mean pooling and L2 normalization. Input is title, genres and plot,
truncated at 256 tokens. Exact NumPy similarity search is filtered by catalog
metadata. Quantized CPU inference was executed on Apple Silicon ARM64. The
encoder and index occupy approximately 31 MB locally.

Two illustrative real-model smoke cases passed. There is no human-judged
semantic retrieval benchmark, plot accuracy audit or guarantee for nuanced mood
queries. The summaries may contain spoilers and historical errors. The frontend
requires an explicit disclosure to read a plot.

## Optional implicit experiment

Implicit BPR, 32 factors, 30 iterations, seed 42, converts training ratings >= 4
into positive interactions and excludes all training-rated films from results.
On the known-user test protocol, the recorded NDCG@10 is 0.0472 versus popularity
0.0317; Precision@10 0.0284 and Recall@10 0.0524. It remains an experimental
baseline. Multithreaded training can vary, and this test result was not used to
select or deploy a replacement visitor model.

## Updates and limitations

Rebuild artifacts when inputs change. Keep generated reports, raw data, model
weights, visitor feedback and credentials out of Git. MLflow optionally logs
report metrics, dataset-manifest fingerprints and the current Git revision.
No online A/B test or production personalization study has been performed.
Profile recovery is bearer-secret possession, not email/password authentication.
MovieLens and corpus populations, catalog dates and metadata coverage limit
representativeness. Preserve explicit missing-data states and source attribution.
