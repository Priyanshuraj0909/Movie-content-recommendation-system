# Local performance notes

## Measurement

Measured on 2026-10-21 with Python 3.12.7 on macOS 27.0.1, Apple Silicon
ARM64. The MovieLens latest-small files contained 9,742 movie metadata rows;
the training candidate catalog contained 8,255 movies. The fitted content and
collaborative artifacts were about 2.95 MB and 2.86 MB respectively.

Run the benchmark from the repository root after setup:

```bash
python scripts/benchmark.py
```

The script loads the same ignored model artifacts used by the app. Load times
are one local measurement each. Warm operation times are medians and p95 from
40 calls (20 for prediction and full-catalog ranking):

| Operation | Median | p95 |
| --- | ---: | ---: |
| Load content model | 0.046 s | one load |
| Load collaborative model | 0.030 s | one load |
| Search 9,742 titles | 1.145 ms | 1.219 ms |
| Similar movies, top 10 | 0.707 ms | 0.867 ms |
| Predict 1,000 user/movie pairs | 0.253 ms | 0.273 ms |
| Rank full catalog for one user, top 10 | 2.576 ms | 2.876 ms |

## Interpretation

These measurements are warm, in-process algorithm and data operations. They do
not include HTTP transport, cold filesystem caches, concurrent users, Docker
overhead or a hosted machine. They are local observations, not latency promises
or production service-level objectives. Re-run the script on the machine and
model artifacts you intend to demonstrate.
