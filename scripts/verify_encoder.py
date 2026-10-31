"""Download pinned assets and check actual ONNX inference without any movie dataset."""

import numpy as np

from recommender.models.semantic import DEFAULT_DIRECTORY, SentenceEncoder, prepare_encoder

if __name__ == "__main__":
    prepare_encoder()
    vectors = SentenceEncoder(DEFAULT_DIRECTORY).encode(
        [
            "toys come alive when the children leave",
            "living toys go on an adventure together",
            "a lawyer investigates an accounting fraud",
        ]
    )
    assert vectors.shape == (3, 384)
    assert np.isfinite(vectors).all()
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    assert vectors[0] @ vectors[1] > vectors[0] @ vectors[2]
    print("Pinned ONNX encoder: dimensions, normalization and semantic smoke checks passed.")
