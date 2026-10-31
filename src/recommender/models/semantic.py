"""Sentence Transformers MiniLM embeddings served with a small ONNX CPU runtime."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from recommender.config import ARTIFACTS_DIR, PROCESSED_DATA_DIR
from recommender.data.plots import download_file

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_HASHES = {
    "tokenizer.json": "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
    "model.onnx": "b941bf19f1f1283680f449fa6a7336bb5600bdcd5f84d10ddc5cd72218a0fd21",
}
DEFAULT_DIRECTORY = ARTIFACTS_DIR / "semantic"


def mean_pool(tokens: np.ndarray, mask: np.ndarray) -> np.ndarray:
    weights = mask[..., None].astype(np.float32)
    pooled = (tokens * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
    return pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)


class SentenceEncoder:
    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        ort.disable_telemetry_events()
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        settings = ort.SessionOptions()
        settings.intra_op_num_threads = 2
        settings.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(directory / "model.onnx"), sess_options=settings, providers=["CPUExecutionProvider"]
        )

    def encode(self, texts: list[str], batch_size=16) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        batches = []
        for start in range(0, len(texts), batch_size):
            encoded = self.tokenizer.encode_batch(texts[start : start + batch_size])
            values = {
                "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
                "attention_mask": np.asarray(
                    [item.attention_mask for item in encoded], dtype=np.int64
                ),
                "token_type_ids": np.asarray([item.type_ids for item in encoded], dtype=np.int64),
            }
            inputs = {item.name: values[item.name] for item in self.session.get_inputs()}
            tokens = self.session.run(None, inputs)[0]
            batches.append(mean_pool(tokens, values["attention_mask"]))
        return np.concatenate(batches).astype(np.float32)


class SemanticIndex:
    def __init__(self, directory=DEFAULT_DIRECTORY, *, encoder=None):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        self.movie_ids = np.load(self.directory / "movie_ids.npy", allow_pickle=False)
        self.embeddings = np.load(self.directory / "embeddings.npy", allow_pickle=False)
        if self.embeddings.shape != (len(self.movie_ids), 384):
            raise ValueError("Invalid semantic index shape")
        if not np.isfinite(self.embeddings).all():
            raise ValueError("Non-finite semantic embeddings")
        if len(set(self.movie_ids.tolist())) != len(self.movie_ids):
            raise ValueError("Duplicate semantic movie IDs")
        self._positions = {int(mid): position for position, mid in enumerate(self.movie_ids)}
        self.encoder = encoder or SentenceEncoder(self.directory)

    def score_preferences(self, ratings: dict[int, float], candidate_ids) -> np.ndarray:
        """Compare stored plot vectors with a signed visitor preference profile.

        Missing descriptions contribute zero, never an invented embedding. The
        encoder is not called: all film vectors were prepared offline.
        """
        profile = np.zeros(self.embeddings.shape[1], dtype=np.float32)
        for mid, rating in ratings.items():
            position = self._positions.get(int(mid))
            if position is None or 2.5 < rating < 4:
                continue
            weight = rating - 3 if rating >= 4 else 0.5 * (rating - 3)
            profile += weight * self.embeddings[position]
        norm = np.linalg.norm(profile)
        candidates = list(candidate_ids)
        scores = np.zeros(len(candidates), dtype=np.float64)
        if norm == 0:
            return scores
        similarities = self.embeddings @ (profile / norm)
        for i, mid in enumerate(candidates):
            position = self._positions.get(int(mid))
            if position is not None:
                scores[i] = float(similarities[position])
        return scores

    def search(self, query: str, *, limit=20, allowed_ids=None):
        vector = self.encoder.encode([query])[0]
        scores = self.embeddings @ vector
        mask = np.ones(len(scores), dtype=bool)
        if allowed_ids is not None:
            mask = np.isin(self.movie_ids, list(allowed_ids))
        positions = np.flatnonzero(mask & (scores > 0))
        order = np.lexsort((self.movie_ids[positions], -scores[positions]))[:limit]
        return [(int(self.movie_ids[i]), float(scores[i])) for i in positions[order]]


def prepare_encoder(directory=DEFAULT_DIRECTORY):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for remote, local in (
        ("tokenizer.json", "tokenizer.json"),
        ("onnx/model_quint8_avx2.onnx", "model.onnx"),
    ):
        target = directory / local
        if not target.is_file():
            download_file(
                f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{remote}", target
            )
        with target.open("rb") as stream:
            hashes[local] = hashlib.file_digest(stream, "sha256").hexdigest()
        if hashes[local] != MODEL_HASHES[local]:
            raise ValueError(f"Pinned semantic model digest mismatch: {local}")
    license_path = directory / "LICENSE.txt"
    if not license_path.is_file():
        download_file(
            "https://www.apache.org/licenses/LICENSE-2.0.txt", license_path, max_bytes=20000
        )
    (directory / "NOTICE.txt").write_text(
        f"Sentence Transformers model: {MODEL_ID}\nRevision: {MODEL_REVISION}\n"
        f"Source: https://huggingface.co/{MODEL_ID}\nLicense: Apache-2.0 (LICENSE.txt)\n"
    )
    return hashes


def prepare_semantic(directory=DEFAULT_DIRECTORY):
    directory = Path(directory)
    hashes = prepare_encoder(directory)
    movies = pd.read_csv(PROCESSED_DATA_DIR / "movies_with_tags.csv")
    plots = pd.read_csv(PROCESSED_DATA_DIR / "movie_plots.csv")
    enriched = movies.merge(plots, on="movieId", validate="one_to_one").sort_values("movieId")
    texts = [
        f"{row.title}. {row.genres.replace('|', ', ')}. {row.summary}"
        for row in enriched.itertuples()
    ]
    encoder = SentenceEncoder(directory)
    vectors = encoder.encode(texts)
    np.save(directory / "embeddings.npy", vectors, allow_pickle=False)
    np.save(
        directory / "movie_ids.npy", enriched.movieId.to_numpy(dtype=np.int64), allow_pickle=False
    )
    with (PROCESSED_DATA_DIR / "movie_plots.csv").open("rb") as stream:
        plot_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {
        "model_id": MODEL_ID,
        "model_file": "onnx/model_quint8_avx2.onnx",
        "revision": MODEL_REVISION,
        "license": "Apache-2.0",
        "backend": "ONNX CPU; attention-mask mean pooling; L2 normalized",
        "model_files_sha256": hashes,
        "plots_sha256": plot_digest,
        "movies_indexed": len(enriched),
        "dimensions": 384,
        "max_tokens": 256,
        "metadata_scope": "verified static CMU plot matches; not temporal benchmark features",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    print(json.dumps(prepare_semantic(args.output), indent=2))


if __name__ == "__main__":
    main()
