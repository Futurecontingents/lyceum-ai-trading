import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from lyceum.models import AgentOpinion, ExecutionMode, ProbabilityDistribution


def test_probability_distribution_requires_unit_sum():
    with pytest.raises(ValidationError, match="sum to 1"):
        ProbabilityDistribution(strong_down=0.1, down=0.1, flat=0.1, up=0.1, strong_up=0.1)


def test_probability_distribution_rejects_nan():
    with pytest.raises(ValidationError):
        ProbabilityDistribution(strong_down=math.nan, down=0, flat=0, up=0, strong_up=1)


def test_agent_output_contract():
    opinion = AgentOpinion(
        agent="mind",
        symbol="SPY",
        timestamp=datetime.now(UTC),
        horizon="1h",
        probabilities=ProbabilityDistribution(strong_down=0.1, down=0.2, flat=0.4, up=0.2, strong_up=0.1),
        expected_return=0.01,
        confidence=0.6,
        reasoning_summary="bounded",
        evidence=["quote"],
        data_freshness=datetime.now(UTC),
    )
    assert opinion.probabilities.flat == 0.4


def test_execution_modes_have_no_live_member():
    assert {mode.value for mode in ExecutionMode} == {"READ_ONLY", "SIMULATED", "PAPER_AUTONOMOUS"}
