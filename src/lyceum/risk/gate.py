"""Deterministic, non-overridable pre-trade risk gate."""

from __future__ import annotations

from datetime import UTC, datetime

from lyceum.config import Settings
from lyceum.models import PortfolioState, RiskDecision, RiskStatus, SkepticReview, StrategyType, TradeCandidate


def evaluate_risk(
    candidate: TradeCandidate,
    portfolio: PortfolioState,
    skeptic: SkepticReview,
    settings: Settings,
    *,
    duplicate: bool = False,
    last_symbol_trade_at: datetime | None = None,
    now: datetime | None = None,
) -> RiskDecision:
    now = now or datetime.now(UTC)
    reasons: list[str] = []
    if settings.emergency_halt_file.exists():
        reasons.append("EMERGENCY_HALT")
    if not settings.paper or settings.trading_base_url != "https://paper-api.alpaca.markets":
        reasons.append("PAPER_ASSERTION_FAILED")
    if candidate.strategy is StrategyType.NO_TRADE:
        reasons.append("NO_TRADE_SELECTED")
    if candidate.max_loss > settings.max_loss_per_trade:
        reasons.append("MAX_LOSS_PER_TRADE")
    if portfolio.daily_realized_pnl <= -settings.max_daily_realized_loss:
        reasons.append("MAX_DAILY_REALIZED_LOSS")
    if portfolio.open_risk + candidate.max_loss > settings.max_portfolio_heat:
        reasons.append("MAX_PORTFOLIO_HEAT")
    if portfolio.open_positions >= settings.max_simultaneous_positions:
        reasons.append("MAX_POSITIONS")
    if portfolio.symbol_exposure.get(candidate.symbol, 0) + candidate.max_loss > portfolio.equity * settings.max_symbol_concentration:
        reasons.append("SYMBOL_CONCENTRATION")
    if candidate.max_loss > portfolio.buying_power:
        reasons.append("BUYING_POWER")
    if duplicate:
        reasons.append("DUPLICATE_ORDER")
    if last_symbol_trade_at and (now - last_symbol_trade_at).total_seconds() < settings.cooldown_minutes * 60:
        reasons.append("COOLDOWN")
    if skeptic.veto_confidence >= 0.8:
        reasons.append("SKEPTIC_VETO")
    for leg in candidate.legs:
        age = (now - leg.contract.quote_timestamp.astimezone(UTC)).total_seconds()
        if leg.contract.spread_pct > settings.max_bid_ask_spread_pct:
            reasons.append("BID_ASK_SPREAD")
        if age > settings.max_quote_age_seconds:
            reasons.append("STALE_QUOTE")
        if min(leg.contract.bid_size, leg.contract.ask_size) < settings.min_quote_size:
            reasons.append("MIN_LIQUIDITY")
    unique = list(dict.fromkeys(reasons))
    return RiskDecision(status=RiskStatus.REJECTED if unique else RiskStatus.APPROVED, reason_codes=unique or ["ALL_CHECKS_PASSED"])
