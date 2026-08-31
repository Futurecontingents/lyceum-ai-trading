from datetime import UTC, datetime

import pytest

from lyceum.models import ConsensusMetrics, MarketSnapshot, OptionContract, ProbabilityDistribution, StrategyType
from lyceum.strategies import select_strategy


def option(symbol: str, option_type: str, strike: float, bid: float, ask: float) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        underlying="SPY",
        expiration="2026-09-18",
        strike=strike,
        option_type=option_type,
        bid=bid,
        ask=ask,
        bid_size=10,
        ask_size=10,
        implied_volatility=0.3,
        quote_timestamp=datetime.now(UTC),
    )


def test_iron_condor_max_loss_uses_wing_width_not_outer_strike_span():
    snapshot = MarketSnapshot(symbol="SPY", price=100, previous_close=100, realized_volatility=0.2)
    consensus = ConsensusMetrics(
        distribution=ProbabilityDistribution(strong_down=0.05, down=0.15, flat=0.6, up=0.15, strong_up=0.05),
        entropy=0.7,
        pairwise_js_divergence={},
        disagreement=0.05,
        directional_conviction=0,
        expected_direction=0,
    )
    contracts = [
        option("SPYP92", "put", 92, 0.9, 1.0),
        option("SPYP94", "put", 94, 1.5, 1.6),
        option("SPYC106", "call", 106, 1.5, 1.6),
        option("SPYC108", "call", 108, 0.9, 1.0),
    ]
    candidate = select_strategy(snapshot, consensus, contracts)
    assert candidate.strategy is StrategyType.IRON_CONDOR
    assert candidate.max_loss == pytest.approx(100)
