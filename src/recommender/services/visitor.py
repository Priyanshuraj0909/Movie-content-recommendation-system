"""One visitor-ranking policy shared by serving and unseen-user experiments."""

from dataclasses import dataclass

import numpy as np

from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender


@dataclass(frozen=True)
class VisitorPick:
    movie_id: int
    score: float
    predicted_rating: float | None
    reason: str


def normalize(scores):
    scores = np.asarray(scores, dtype=float)
    if not len(scores) or np.ptp(scores) == 0:
        return np.zeros_like(scores)
    return (scores - scores.min()) / np.ptp(scores)


def recommend_visitor(
    content: ContentRecommender,
    collaborative: CollaborativeRecommender,
    ratings: dict[int, float],
    catalog: dict[int, dict],
    *,
    limit: int = 10,
    diversity: float = 0.12,
) -> list[VisitorPick]:
    """Content-first recommendations, followed by bounded genre diversification.

    The ramp to 50% collaborative at ten ratings is a serving heuristic, not the
    validation-tuned weight for known MovieLens users. Report it separately.
    """
    if limit < 1 or not 0 <= diversity <= 1:
        raise ValueError("limit must be positive and diversity between zero and one")
    candidates = sorted(set(catalog) - set(ratings))
    if not candidates:
        return []
    liked = [mid for mid, rating in ratings.items() if rating >= 4 and mid in catalog]
    popularity = normalize(collaborative.popularity_scores(candidates))
    predictions = collaborative.predict_profile(ratings, candidates)
    if liked or any(r <= 2.5 for r in ratings.values()):
        signals = content.score_preferences(ratings, candidates)
        # Preserve the sign of negative feedback rather than shifting dislikes positive.
        signals = signals / max(float(np.max(np.abs(signals))), 1e-12)
        weight = min(0.5, len(ratings) / 20)
        scores = (1 - weight) * signals + weight * normalize(predictions) + 0.1 * popularity
    else:
        scores = popularity
    scores = normalize(scores)
    indices = np.lexsort((np.asarray(candidates), -scores))[: max(100, limit * 5)].tolist()
    selected = []
    genres = {
        mid: set(str(catalog[mid].get("genres", "")).split("|")) - {"", "(no genres listed)"}
        for mid in candidates
    }
    while indices and len(selected) < limit:

        def utility(index):
            group = genres[candidates[index]]
            redundancy = max(
                (
                    len(group & genres[candidates[previous]])
                    / max(len(group | genres[candidates[previous]]), 1)
                    for previous in selected
                ),
                default=0,
            )
            return float(scores[index]) - diversity * redundancy, -candidates[index]

        best = max(indices, key=utility)
        indices.remove(best)
        selected.append(best)
    seed_scores = {
        mid: content.score_profile([mid], [candidates[index] for index in selected])
        for mid in liked
    }
    result = []
    for position, index in enumerate(selected):
        reason = "Popular with the MovieLens community while we learn your taste."
        if liked:
            seed = max(liked, key=lambda mid: (seed_scores[mid][position], -mid))
            reason = (
                f"Shares content with {catalog[seed]['title']}, which you rated highly."
                if seed_scores[seed][position] > 0
                else "Selected from your saved rating preferences."
            )
        elif ratings:
            reason = "Balances community preferences with your saved feedback."
        result.append(
            VisitorPick(
                candidates[index],
                float(scores[index]),
                float(predictions[index]) if len(ratings) >= 3 else None,
                reason,
            )
        )
    return result
