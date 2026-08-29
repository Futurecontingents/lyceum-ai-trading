"""Shared implementation for deterministic, independently biased minds."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import UTC

from lyceum.models import AgentOpinion, MarketSnapshot, ProbabilityDistribution


def distribution_from_score(score: float, uncertainty: float = 0.35) -> ProbabilityDistribution:
    score = max(-1.0, min(1.0, score))
    centers = (-1.0, -0.5, 0.0, 0.5, 1.0)
    scale = max(0.12, uncertainty)
    weights = [math.exp(-((score - center) ** 2) / (2 * scale**2)) for center in centers]
    total = sum(weights)
    values = [value / total for value in weights]
    return ProbabilityDistribution(strong_down=values[0], down=values[1], flat=values[2], up=values[3], strong_up=values[4])


class BaseMind(ABC):
    name: str

    @abstractmethod
    def score(self, snapshot: MarketSnapshot) -> tuple[float, float, str, list[str]]:
        """Return direction, confidence, summary, and evidence."""

    def evaluate(self, snapshot: MarketSnapshot) -> AgentOpinion:
        direction, confidence, summary, evidence = self.score(snapshot)
        confidence = max(0.05, min(1.0, confidence))
        return AgentOpinion(
            agent=self.name,
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            horizon="1 trading day",
            probabilities=distribution_from_score(direction, uncertainty=0.55 - 0.35 * confidence),
            expected_return=direction * snapshot.realized_volatility / math.sqrt(252),
            confidence=confidence,
            reasoning_summary=summary,
            evidence=evidence,
            data_freshness=snapshot.timestamp.astimezone(UTC),
        )
