# Interview notes

## Why use content-based and collaborative models together?

Content similarity can use movie metadata and a new user's explicit likes.
Collaborative filtering captures patterns shared across users but is weak for
new users and rarely rated movies. Their normalized scores provide complementary
signals; a popularity fallback keeps cold-start requests useful.

## How did you prevent evaluation leakage?

Ratings are split chronologically per user. The model fits only on training
ratings. Blend weights are selected against validation NDCG@10; test data is
loaded only after selection. Each evaluated user receives the same candidate
catalog, with their training history removed.

## Why is the blend weight 0.75 collaborative?

I evaluated a fixed grid of five weights on validation, using NDCG@10 as the
primary selection metric and recall/precision as tie breakers. The test split
was not used to choose the blend. A new dataset or training policy would need
new validation tuning.

## What does the content model use?

It builds sparse TF-IDF vectors from normalized titles, genres and aggregated
MovieLens tags, then ranks with cosine similarity. Tags and genres are metadata,
not plot summaries.

## How does matrix factorization work here?

The model learns seeded low-dimensional user and movie vectors from training
ratings with stochastic gradient updates. A regularized global/user/movie
bias estimate anchors predictions. Unknown or low-activity users fall back to
the popularity baseline.

## How are watched items excluded?

The collaborative model records each user's training history. The API also
loads locally submitted ratings from SQLite and removes both sets before
ranking candidates.

## Why store ratings in SQLite?

It gives the local demo durable feedback without adding a cloud database or
credentials. A unique user/movie constraint makes a new rating replace the
previous rating for that pair.

## How would you improve the offline evaluation?

I would add confidence intervals or repeated temporal cutoffs, test a larger
and more recent licensed dataset, measure subgroup and long-tail behavior, and
run a user study. I would keep hyperparameter selection isolated from the final
test partition.

## What is missing for production use?

Authentication, authorization, privacy and retention policies, abuse controls,
observability, robust migrations, deployment-specific storage, load testing,
and model/data versioning. The current numeric profile IDs are not identity.

## What did you measure for performance?

The repository benchmark records model load time and warm in-process title
search, similarity, prediction and ranking latency on the local demo hardware.
Those numbers exclude network and concurrent traffic and are not production
service-level objectives.
