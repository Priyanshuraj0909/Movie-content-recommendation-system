# Local performance notes — v0.3

Measured on 2026-10-31 with Python 3.12.7 on macOS-27.0.1-arm64-arm-64bit.

Warm, in-process operations; no network, concurrency, hosted cold starts or database transport is included.

| Operation | Median (ms) | p95 (ms) |
|---|---:|---:|
| title search 9742 rows | 1.331 | 1.559 |
| similar movies top 10 | 0.833 | 1.101 |
| predict 1000 user movie pairs | 0.273 | 0.399 |
| recommend for user top 10 | 3.051 | 3.713 |
| visitor top 10 five ratings | 23.083 | 30.285 |
| semantic query top 10 | 1.38 | 1.889 |

Content and collaborative loads: 0.065 s / 0.044 s. Semantic encoder/index load: 0.312 s. Loads are single observations.

The visitor operation uses the frozen five-rating policy and the actual semantic index, matching component scoring in serving. The semantic timing repeatedly queries the warmed ONNX model and 5,952-vector index. These are illustrative short-query measurements, not production latency or load-test results.

Reproduce with `python scripts/benchmark.py`. Generated JSON remains ignored under artifacts.
