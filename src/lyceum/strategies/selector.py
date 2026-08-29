"""Defined-risk option structure selection from consensus and live quotes."""

from __future__ import annotations

import math

from lyceum.models import ConsensusMetrics, MarketSnapshot, OptionContract, OptionLeg, StrategyType, TradeCandidate


def _nearest(contracts: list[OptionContract], option_type: str, target: float, expiry: str) -> OptionContract | None:
    pool = [
        item for item in contracts if item.option_type == option_type and item.expiration == expiry and item.bid > 0 and item.ask > item.bid
    ]
    return min(pool, key=lambda item: abs(item.strike - target), default=None)


def select_strategy(snapshot: MarketSnapshot, consensus: ConsensusMetrics, contracts: list[OptionContract]) -> TradeCandidate:
    if not contracts:
        return TradeCandidate(symbol=snapshot.symbol, strategy=StrategyType.NO_TRADE, rationale="No usable option chain")
    expiry = min(item.expiration for item in contracts)
    ivs = [item.implied_volatility for item in contracts if item.implied_volatility]
    iv = sum(ivs) / len(ivs) if ivs else snapshot.realized_volatility
    expected_move = snapshot.price * iv * math.sqrt(14 / 365)
    direction = consensus.expected_direction
    if consensus.disagreement > 0.18 and consensus.entropy > 0.72 and iv <= snapshot.realized_volatility * 1.35:
        strategy, legs_data = StrategyType.LONG_STRADDLE, [("call", snapshot.price, "buy"), ("put", snapshot.price, "buy")]
    elif direction > 0.12 and consensus.directional_conviction > 0.12:
        strategy, legs_data = (
            StrategyType.BULL_CALL_SPREAD,
            [("call", snapshot.price, "buy"), ("call", snapshot.price + expected_move, "sell")],
        )
    elif direction < -0.12 and consensus.directional_conviction > 0.12:
        strategy, legs_data = (
            StrategyType.BEAR_PUT_SPREAD,
            [("put", snapshot.price, "buy"), ("put", snapshot.price - expected_move, "sell")],
        )
    elif consensus.entropy < 0.82 and iv > snapshot.realized_volatility * 1.1:
        strategy, legs_data = (
            StrategyType.IRON_CONDOR,
            [
                ("put", snapshot.price - 1.4 * expected_move, "buy"),
                ("put", snapshot.price - expected_move, "sell"),
                ("call", snapshot.price + expected_move, "sell"),
                ("call", snapshot.price + 1.4 * expected_move, "buy"),
            ],
        )
    else:
        return TradeCandidate(
            symbol=snapshot.symbol,
            strategy=StrategyType.NO_TRADE,
            expiry=expiry,
            expected_move=expected_move,
            rationale="Consensus and volatility do not justify defined-risk exposure",
        )
    chosen: list[OptionLeg] = []
    for option_type, target, side in legs_data:
        contract = _nearest(contracts, option_type, target, expiry)
        if contract is None or any(leg.contract.symbol == contract.symbol for leg in chosen):
            return TradeCandidate(
                symbol=snapshot.symbol,
                strategy=StrategyType.NO_TRADE,
                expiry=expiry,
                expected_move=expected_move,
                rationale=f"Incomplete or duplicate legs for {strategy}",
            )
        chosen.append(OptionLeg(contract=contract, side=side))
    debit = max(0.0, sum((leg.contract.ask if leg.side == "buy" else -leg.contract.bid) * 100 for leg in chosen))
    width = max(leg.contract.strike for leg in chosen) - min(leg.contract.strike for leg in chosen)
    max_loss = (
        debit
        if strategy in {StrategyType.LONG_STRADDLE, StrategyType.BULL_CALL_SPREAD, StrategyType.BEAR_PUT_SPREAD}
        else max(0.0, width * 100 - max(0, -debit))
    )
    return TradeCandidate(
        symbol=snapshot.symbol,
        strategy=strategy,
        legs=chosen,
        expiry=expiry,
        expected_move=expected_move,
        estimated_debit=debit,
        max_loss=max_loss,
        rationale=f"direction={direction:+.2f}, disagreement={consensus.disagreement:.2f}, entropy={consensus.entropy:.2f}, IV={iv:.1%}",
    )
