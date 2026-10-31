# Local performance notes

Measured on 2026-10-31 with Python 3.12.7 on macOS-27.0.1-arm64-arm-64bit.

Warm, in-process operations; no network, concurrency, hosted cold starts or database transport is included.

| Operation | Median (ms) | p95 (ms) |
|---|---:|---:|
| title search 9742 rows | 1.195 | 1.353 |
| similar movies top 10 | 0.721 | 0.883 |
| predict 1000 user movie pairs | 0.268 | 0.279 |
| recommend for user top 10 | 2.624 | 2.869 |
| visitor top 10 five ratings | 24.117 | 43.557 |
| semantic query top 10 | 1.148 | 1.286 |

Content and collaborative artifact loads: 0.047 s and 0.031 s. Semantic encoder/index load: 0.266 s. These are single load observations.

The visitor operation includes fixed-item factor estimation and genre diversification over the full catalog, using five synthetic rating values. The semantic timing repeatedly queries the warmed real ONNX model and 5,952-vector index. Short repeated queries are illustrative and do not establish latency for longer prompts or concurrent traffic.

Reproduce after setup with `python scripts/benchmark.py`. Generated JSON remains in ignored local artifacts. These are measurements, not service-level guarantees.
