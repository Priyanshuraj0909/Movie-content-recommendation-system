"""A small semantic retrieval smoke check, not a recommendation accuracy benchmark."""

import json

import pandas as pd

from recommender.config import PROCESSED_DATA_DIR
from recommender.models.semantic import SemanticIndex


def main():
    index = SemanticIndex()
    catalog = pd.read_csv(PROCESSED_DATA_DIR / "movies_with_tags.csv").set_index("movieId")
    cases = [
        ("a computer hacker discovers the world is a simulated reality", {2571}),
        ("toys come alive when children leave the room", {1, 3114, 78499}),
    ]
    results = []
    for query, expected in cases:
        matches = index.search(query, limit=5)
        passed = bool({mid for mid, _ in matches} & expected)
        results.append(
            {
                "query": query,
                "passed": passed,
                "titles": [str(catalog.loc[mid, "title"]) for mid, _ in matches],
            }
        )
    print(
        json.dumps(
            {"method": "two illustrative smoke cases; not quality evaluation", "cases": results},
            indent=2,
        )
    )
    if not all(row["passed"] for row in results):
        raise SystemExit("Semantic smoke check failed")


if __name__ == "__main__":
    main()
