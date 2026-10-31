"""Small, versioned ranking policies; no tuning or network access while serving."""

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class RankPolicy:
    popularity: float = 0.8
    content: float = 0.1
    collaborative: float = 0.1
    semantic: float = 0.0
    diversity: float = 0.0

    def __post_init__(self):
        weights = (self.popularity, self.content, self.collaborative, self.semantic)
        if any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights):
            raise ValueError("Policy weights must be finite and between zero and one")
        if not math.isclose(sum(weights), 1, abs_tol=1e-8):
            raise ValueError("Policy weights must sum to one")
        if not math.isfinite(self.diversity) or not 0 <= self.diversity <= 0.5:
            raise ValueError("Policy diversity must be between zero and 0.5")


DISCOVERY_POLICY = RankPolicy(0.5, 0.15, 0.1, 0.25, 0.08)
POPULARITY_POLICY = RankPolicy(1, 0, 0, 0, 0)
POLICY_PATH = Path(__file__).with_name("visitor_policy.json")


@lru_cache(maxsize=1)
def load_policies():
    if not POLICY_PATH.is_file():
        return {}
    payload = json.loads(POLICY_PATH.read_text())
    if payload.get("format_version") != 1:
        raise ValueError("Unsupported visitor policy configuration")
    return {int(count): RankPolicy(**values) for count, values in payload["policies"].items()}


def resolve_policy(rating_count: int, mode="balanced") -> RankPolicy:
    if mode not in {"balanced", "discovery"}:
        raise ValueError("Unknown recommendation mode")
    if rating_count == 0:
        return POPULARITY_POLICY
    if mode == "discovery":
        return DISCOVERY_POLICY
    policies = load_policies()
    buckets = [count for count in policies if count <= rating_count]
    return policies[max(buckets)] if buckets else RankPolicy()
