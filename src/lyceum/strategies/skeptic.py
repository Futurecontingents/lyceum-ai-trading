"""Adversarial, deterministic review that cannot submit orders."""

from lyceum.models import MarketSnapshot, SkepticReview, StrategyType, TradeCandidate


def review_candidate(candidate: TradeCandidate, snapshot: MarketSnapshot) -> SkepticReview:
    worst_spread = max((leg.contract.spread_pct for leg in candidate.legs), default=0.0)
    veto = 1.0 if candidate.strategy is StrategyType.NO_TRADE else 0.15
    if worst_spread > 0.18:
        veto = max(veto, 0.85)
    if snapshot.catalyst_risk > 0.7:
        veto = max(veto, 0.75)
    return SkepticReview(
        strongest_argument_against="The council signal may be noise rather than a stable short-horizon edge.",
        hidden_assumption="Agent errors are sufficiently independent for disagreement to be informative.",
        liquidity_concern=f"Worst leg bid/ask width is {worst_spread:.1%}.",
        iv_concern="Implied volatility may already price the expected move.",
        event_concern="Known catalyst coverage is incomplete."
        if snapshot.catalyst_risk == 0
        else f"Catalyst risk score is {snapshot.catalyst_risk:.2f}.",
        veto_confidence=veto,
    )
