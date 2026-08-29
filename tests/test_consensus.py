from datetime import UTC, datetime

from lyceum.consensus import calculate_consensus
from lyceum.models import AgentOpinion, ProbabilityDistribution


def opinion(name, values, confidence=1):
    return AgentOpinion(
        agent=name,
        symbol="SPY",
        timestamp=datetime.now(UTC),
        horizon="1h",
        probabilities=ProbabilityDistribution(**dict(zip(("strong_down", "down", "flat", "up", "strong_up"), values, strict=True))),
        expected_return=0,
        confidence=confidence,
        reasoning_summary="test",
        data_freshness=datetime.now(UTC),
    )


def test_identical_agents_have_zero_disagreement():
    result = calculate_consensus([opinion("a", (0, 0, 1, 0, 0)), opinion("b", (0, 0, 1, 0, 0))])
    assert result.disagreement == 0
    assert result.expected_direction == 0


def test_opposed_agents_have_large_disagreement():
    result = calculate_consensus([opinion("bull", (0, 0, 0, 0, 1)), opinion("bear", (1, 0, 0, 0, 0))])
    assert result.disagreement > 0.9
    assert result.entropy > 0.4


def test_confidence_weights_consensus():
    result = calculate_consensus([opinion("bull", (0, 0, 0, 0, 1), 1), opinion("bear", (1, 0, 0, 0, 0), 0.1)])
    assert result.expected_direction > 0.7
