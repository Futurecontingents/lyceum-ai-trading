"""Mathematically explicit consensus and disagreement metrics."""

from __future__ import annotations

import math
from itertools import combinations

from lyceum.models import AgentOpinion, ConsensusMetrics, ProbabilityDistribution


def _entropy(values: tuple[float, ...]) -> float:
    return -sum(value * math.log(value) for value in values if value > 0) / math.log(len(values))


def _js_divergence(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    midpoint = tuple((a + b) / 2 for a, b in zip(left, right, strict=True))

    def kl(source: tuple[float, ...], target: tuple[float, ...]) -> float:
        return sum(a * math.log(a / b) for a, b in zip(source, target, strict=True) if a > 0)

    return (kl(left, midpoint) + kl(right, midpoint)) / (2 * math.log(2))


def calculate_consensus(opinions: list[AgentOpinion]) -> ConsensusMetrics:
    if not opinions:
        raise ValueError("at least one opinion is required")
    total_weight = sum(max(opinion.confidence, 0.05) for opinion in opinions)
    vectors = [opinion.probabilities.vector() for opinion in opinions]
    consensus = tuple(
        sum(vector[index] * max(opinion.confidence, 0.05) for vector, opinion in zip(vectors, opinions, strict=True)) / total_weight
        for index in range(5)
    )
    pairwise = {
        f"{left.agent}__{right.agent}": _js_divergence(left.probabilities.vector(), right.probabilities.vector())
        for left, right in combinations(opinions, 2)
    }
    disagreement = sum(pairwise.values()) / len(pairwise) if pairwise else 0.0
    expected_direction = sum(value * score for value, score in zip(consensus, (-1.0, -0.5, 0.0, 0.5, 1.0), strict=True))
    return ConsensusMetrics(
        distribution=ProbabilityDistribution(
            strong_down=consensus[0], down=consensus[1], flat=consensus[2], up=consensus[3], strong_up=consensus[4]
        ),
        entropy=_entropy(consensus),
        pairwise_js_divergence=pairwise,
        disagreement=disagreement,
        directional_conviction=min(1.0, abs(expected_direction)),
        expected_direction=expected_direction,
    )
