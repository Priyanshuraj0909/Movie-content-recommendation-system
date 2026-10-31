"""Shared visitor scoring, frozen policies and the historical evaluation baseline."""

from dataclasses import dataclass

import numpy as np

from recommender.models.collaborative import CollaborativeRecommender
from recommender.models.content import ContentRecommender
from recommender.services.policy import RankPolicy, resolve_policy


@dataclass(frozen=True)
class VisitorPick:
    movie_id: int
    score: float
    predicted_rating: float | None
    reason: str


@dataclass(frozen=True)
class VisitorSignals:
    movie_ids: np.ndarray
    popularity: np.ndarray
    content: np.ndarray
    collaborative: np.ndarray
    semantic: np.ndarray
    predictions: np.ndarray


def score_visitor(content, collaborative, ratings, catalog, *, semantic_index=None, excluded=()):
    """Compute components once; validation and serving share exactly this path."""
    ratings = {int(mid): float(rating) for mid, rating in ratings.items() if mid in catalog}
    if any(not np.isfinite(r) or not 0.5 <= r <= 5 for r in ratings.values()):
        raise ValueError("Visitor ratings must be finite and on the half-star scale")
    candidates = np.asarray(sorted(set(catalog) - set(ratings) - set(excluded)), dtype=np.int64)
    popularity = normalize(collaborative.popularity_scores(candidates))
    predictions = collaborative.predict_profile(ratings, candidates)
    content_scores = content.score_preferences(ratings, candidates)
    content_scores /= max(float(np.max(np.abs(content_scores), initial=0)), 1e-12)
    semantic_scores = np.zeros(len(candidates), dtype=float)
    if semantic_index is not None:
        semantic_scores = semantic_index.score_preferences(ratings, candidates)
    return VisitorSignals(
        candidates,
        popularity,
        content_scores,
        normalize(predictions) if len(ratings) >= 3 else popularity.copy(),
        semantic_scores,
        predictions,
    )


def rank_signals(signals: VisitorSignals, catalog: dict, policy: RankPolicy, *, limit=10):
    """Return positions after an optional, bounded genre diversity reranking."""
    if limit < 1:
        raise ValueError("limit must be positive")
    scores = (
        policy.popularity * signals.popularity
        + policy.content * signals.content
        + policy.collaborative * signals.collaborative
        + policy.semantic * signals.semantic
    )
    indices = np.lexsort((signals.movie_ids, -scores))[: max(100, limit * 5)].tolist()
    if policy.diversity == 0:
        return indices[:limit], scores
    genres = {
        i: set(str(catalog[int(signals.movie_ids[i])].get("genres", "")).split("|"))
        - {"", "(no genres listed)"}
        for i in indices
    }
    selected = []
    while indices and len(selected) < limit:

        def utility(i):
            redundancy = max(
                (len(genres[i] & genres[j]) / max(len(genres[i] | genres[j]), 1) for j in selected),
                default=0,
            )
            return float(scores[i]) - policy.diversity * redundancy, -int(signals.movie_ids[i])

        best = max(indices, key=utility)
        selected.append(best)
        indices.remove(best)
    return selected, scores


def recommend_visitor(
    content,
    collaborative,
    ratings,
    catalog,
    *,
    limit=10,
    diversity=None,
    semantic_index=None,
    policy=None,
    mode="balanced",
    excluded=(),
) -> list[VisitorPick]:
    """Rank with a frozen validation-selected policy, preserving factual reasons."""
    from dataclasses import replace

    valid_ratings = {mid: rating for mid, rating in ratings.items() if mid in catalog}
    policy = policy or resolve_policy(len(valid_ratings), mode)
    if diversity is not None:
        policy = replace(policy, diversity=diversity)
    signals = score_visitor(
        content,
        collaborative,
        valid_ratings,
        catalog,
        semantic_index=semantic_index,
        excluded=excluded,
    )
    selected, scores = rank_signals(signals, catalog, policy, limit=limit)
    displayed_scores = normalize(scores)
    liked = sorted(
        (mid for mid, rating in valid_ratings.items() if rating >= 4),
        key=lambda mid: (-valid_ratings[mid], mid),
    )[:5]
    selected_ids = [int(signals.movie_ids[i]) for i in selected]
    content_reasons = {mid: content.score_profile([mid], selected_ids) for mid in liked}
    semantic_reasons = (
        {mid: semantic_index.score_preferences({mid: 5}, selected_ids) for mid in liked}
        if semantic_index is not None and policy.semantic
        else {}
    )
    result = []
    for position, index in enumerate(selected):
        mid = int(signals.movie_ids[index])
        reason = "Highly rated by the community; excludes films already in your history."
        if semantic_reasons and policy.semantic * signals.semantic[index] > (
            policy.content * signals.content[index]
        ):
            seed = max(semantic_reasons, key=lambda seed: semantic_reasons[seed][position])
            if semantic_reasons[seed][position] > 0.2:
                reason = f"Plot themes similar to {catalog[seed]['title']}, which you rated highly."
        elif liked and policy.content and signals.content[index] > 0:
            seed = max(liked, key=lambda seed: content_reasons[seed][position])
            if content_reasons[seed][position] > 0:
                reason = f"Shares content with {catalog[seed]['title']}, which you rated highly."
        elif policy.collaborative and len(valid_ratings) >= 3:
            reason = "Combines your saved rating preferences with community ratings."
        result.append(
            VisitorPick(
                mid,
                float(displayed_scores[index]),
                float(signals.predictions[index]) if len(valid_ratings) >= 3 else None,
                reason,
            )
        )
    return result


def normalize(scores):
    scores = np.asarray(scores, dtype=float)
    if not len(scores) or np.ptp(scores) == 0:
        return np.zeros_like(scores)
    return (scores - scores.min()) / np.ptp(scores)


def recommend_legacy_visitor(
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
