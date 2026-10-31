"""Attribute and conservatively join the public CMU Movie Summary Corpus."""

import argparse
import hashlib
import io
import json
import re
import tarfile
import unicodedata
from pathlib import Path

import httpx
import pandas as pd

from recommender.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from recommender.data.movielens import TLS_VERIFY

CORPUS_URL = "https://www.cs.cmu.edu/~ark/personas/data/MovieSummaries.tar.gz"
CORPUS_PAGE = "https://www.cs.cmu.edu/~ark/personas/"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/us/"
CORPUS_SHA256 = "6c3bd3d42046c4b87e2267f2e2599ba6f651b8ad23a8998237c3d2bb338ac559"


def download_file(url: str, path: Path, *, max_bytes: int = 200_000_000) -> str:
    """Bounded atomic public download; retain the content digest for provenance."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    digest = hashlib.sha256()
    total = 0
    try:
        with httpx.stream(
            "GET", url, follow_redirects=True, timeout=120, verify=TLS_VERIFY
        ) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Public download exceeded its size limit")
                    digest.update(chunk)
                    output.write(chunk)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


def normalized_title(title: str) -> str:
    title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    match = re.match(r"^(.*), (The|A|An)$", title, re.IGNORECASE)
    if match:
        title = match[2] + " " + match[1]
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def join_plots(movies: pd.DataFrame, metadata: pd.DataFrame, summaries: dict[str, str]):
    """Exact normalized title + year; reject ambiguous matches rather than guess."""
    records = {}
    for row in metadata.itertuples(index=False, name=None):
        wiki_id, _, title, released, _, runtime, languages, *_ = row
        year = str(released)[:4]
        if not year.isdigit() or str(wiki_id) not in summaries:
            continue
        key = normalized_title(str(title)), year
        records.setdefault(key, []).append((str(wiki_id), runtime, languages))
    result = []
    ambiguous = 0
    for movie in movies.itertuples():
        match = re.search(r"\((\d{4})\)\s*$", movie.title)
        candidates = records.get((normalized_title(movie.title), match[1] if match else ""), [])
        if len(candidates) != 1:
            ambiguous += int(len(candidates) > 1)
            continue
        wiki_id, runtime, languages = candidates[0]
        runtime = pd.to_numeric(runtime, errors="coerce")
        try:
            language_names = sorted(
                {
                    str(value).removesuffix(" Language")
                    for value in json.loads(languages or "{}").values()
                }
            )
        except (ValueError, AttributeError, TypeError):
            language_names = []
        result.append(
            {
                "movieId": int(movie.movieId),
                "summary": summaries[wiki_id].strip(),
                "runtime_minutes": float(runtime)
                if pd.notna(runtime) and 0 < runtime < 1000
                else None,
                "languages_json": json.dumps(language_names),
                "source_url": f"https://en.wikipedia.org/?curid={wiki_id}",
                "source": "Wikipedia via CMU Movie Summary Corpus",
                "license_url": LICENSE_URL,
            }
        )
    return pd.DataFrame(
        result,
        columns=[
            "movieId",
            "summary",
            "runtime_minutes",
            "languages_json",
            "source_url",
            "source",
            "license_url",
        ],
    ), ambiguous


def prepare_plots():
    archive = RAW_DATA_DIR / "MovieSummaries.tar.gz"
    if not archive.is_file():
        download_file(CORPUS_URL, archive)
    with archive.open("rb") as stream:
        archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if archive_hash != CORPUS_SHA256:
        raise ValueError("CMU archive digest changed; review the source before updating its digest")
    with tarfile.open(archive, "r:gz") as corpus:

        def read_member(name):
            member = next(
                member for member in corpus.getmembers() if member.name.endswith("/" + name)
            )
            if not member.isfile() or member.size > 150_000_000:
                raise ValueError("Unexpected corpus member")
            stream = corpus.extractfile(member)
            if stream is None:
                raise ValueError("Missing corpus member")
            return stream.read().decode("utf-8")

        metadata = pd.read_csv(
            io.StringIO(read_member("movie.metadata.tsv")),
            sep="\t",
            header=None,
            dtype=str,
            keep_default_na=False,
        )
        summaries = dict(
            line.split("\t", 1) for line in read_member("plot_summaries.txt").splitlines()
        )
    movies = pd.read_csv(PROCESSED_DATA_DIR / "movies_with_tags.csv")
    enriched, ambiguous = join_plots(movies, metadata, summaries)
    if enriched.empty:
        raise ValueError("No verified title/year matches; refusing to publish an empty catalog")
    enriched.to_csv(PROCESSED_DATA_DIR / "movie_plots.csv", index=False)
    report = {
        "corpus_url": CORPUS_URL,
        "corpus_page": CORPUS_PAGE,
        "license_url": LICENSE_URL,
        "attribution": "David Bamman, Brendan O'Connor, Noah A. Smith; Wikipedia contributors",
        "archive_sha256": archive_hash,
        "matched_movies": len(enriched),
        "catalog_movies": len(movies),
        "ambiguous_matches_rejected": ambiguous,
        "join": "exact normalized title and release year; no fuzzy matching",
        "temporal_note": "static corpus metadata; not historically time-filtered",
    }
    (PROCESSED_DATA_DIR / "plots_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(prepare_plots(), indent=2))


if __name__ == "__main__":
    main()
