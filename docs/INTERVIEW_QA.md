# Interview notes

## Why use content-based and collaborative models together?

Content similarity can use movie metadata and a new user's explicit likes.
Collaborative filtering captures patterns shared across users but is weak for
new users and rarely rated movies. Their normalized scores provide complementary
signals; a popularity fallback keeps cold-start requests useful.

## How did you prevent evaluation leakage?

Ratings are split chronologically per user. The model fits only on training
ratings; tags must also satisfy each author's training cutoff. The unseen-user
experiment additionally removes withheld visitors from fitting. Blend weights are selected against validation NDCG@10; test data is
loaded only after selection. Each evaluated user receives the same candidate
catalog, with their training history removed.

## Why is the blend weight 0.75 collaborative?

I evaluated a fixed grid of five weights on validation, using NDCG@10 as the
primary selection metric and recall/precision as tie breakers. The test split
was not used to choose the blend. A new dataset or training policy would need
new validation tuning. This weight describes the known-user experiment; the
visitor serving policy is separate and does not inherit this weight.

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

The known-user benchmark excludes each MovieLens user's training history.
Application visitors are a separate identity space: serving excludes that
visitor's submitted ratings and explicit watched/dismissed states, never an
unrelated benchmark user's history.

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

The browser now has bearer-secret profile ownership, persistent watchlists,
additive Alembic migrations and reproducible model inputs. A broader production
service still needs stronger account recovery, edge controls for anonymous
profile creation, retention policies, concurrent load tests and online evaluation.
Protected hosted rating persistence must be verified with authorized access.

## What did you measure for performance?

The repository benchmark records model load time and warm in-process title
search, similarity, prediction and ranking latency on the local demo hardware.
Those numbers exclude network and concurrent traffic and are not production
service-level objectives.

## What did the new experiments teach you?

Correcting tag availability lowered the old hybrid result. The historical v0.2 visitor
heuristic improved breadth but trailed popularity. The v0.3 default was selected
on separate validation users, then scored about 5% above popularity in observed
five-rating NDCG on a new held-out user partition. This is not evidence of
statistical significance or production quality. An experimental BPR baseline did better on the known-user task, but
that does not establish that it should replace the visitor model. These results
are reported separately with their actual candidate sets and limitations.

## Why use ONNX and exact NumPy search?

The Sentence Transformers MiniLM model provides semantic representations without
shipping the research PyTorch stack in the serverless application. The published
quantized model and index occupy about 31 MB locally. Exact retrieval is practical
for 5,952 verified plots; a separate vector database is not currently required.

## How do visitors get collaborative personalization?

A small ridge-regression solve estimates a visitor bias and latent vector from
submitted ratings against fixed movie factors. It updates no global model arrays
and reads no MovieLens user identity. The private profile's ID is used only for
application persistence and ownership checks.

## How are watched films different from low ratings?

Watched and not-interested are reversible exclusions stored independently of
numeric ratings. They do not insert fake half-star feedback. Clearing a state
keeps existing ratings and watchlists intact. The private taste library exposes
these distinctions and allows rating edits.
