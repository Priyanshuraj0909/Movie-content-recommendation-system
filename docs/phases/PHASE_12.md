# Phase 12: Attributed plots and semantic discovery

## Goal
Search by story concepts using the Sentence Transformers all-MiniLM-L6-v2 model,
with exact NumPy retrieval and an ONNX CPU runtime suitable for Apple Silicon and
serverless deployments.

## Deliverables
- CMU Movie Summary Corpus ingestion using exact normalized title/year matching,
  ambiguous-match rejection, original Wikipedia links and CC BY-SA attribution.
- Pinned model revision, download hashes, normalized embeddings and model metadata.
- Structured runtime/language/genre filters, semantic search, and catalog details.
- Build-time preparation; no network model downloads in serving requests.
- Visible missing-summary states; no invented movie metadata.

## Checks
Fixture matching/rejection tests, numerical pooling/ranking tests, actual model
retrieval checks, API/UI integration tests and Playwright journeys.
