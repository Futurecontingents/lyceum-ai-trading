"""Resilient orchestration loop for the complete Lyceum vertical slice."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import UTC, datetime, timedelta

from lyceum.agents import market_council
from lyceum.config import Settings
from lyceum.consensus import calculate_consensus
from lyceum.data import AlpacaCliGateway
from lyceum.execution.paper import PaperExecutor
from lyceum.memory import Journal
from lyceum.models import MarketSnapshot, OptionContract, PortfolioState, RiskStatus, StrategyType
from lyceum.risk import evaluate_risk
from lyceum.strategies import review_candidate, select_strategy

LOGGER = logging.getLogger("lyceum.runner")


def _demo_contracts(symbol: str, price: float) -> list[OptionContract]:
    expiry, stamp, contracts = (datetime.now(UTC).date() + timedelta(days=14)).isoformat(), datetime.now(UTC), []
    for option_type, letter in (("call", "C"), ("put", "P")):
        for offset in (-10, -5, 0, 5, 10):
            strike = round(price + offset)
            intrinsic = max(0, price - strike) if option_type == "call" else max(0, strike - price)
            mid = max(1.0, intrinsic + 4.0 - abs(offset) * 0.12)
            contracts.append(
                OptionContract(
                    symbol=f"{symbol}DEMO{letter}{strike}",
                    underlying=symbol,
                    expiration=expiry,
                    strike=strike,
                    option_type=option_type,
                    bid=mid - 0.1,
                    ask=mid + 0.1,
                    bid_size=25,
                    ask_size=25,
                    implied_volatility=0.22,
                    delta=None,
                    quote_timestamp=stamp,
                )
            )
    return contracts


class AutonomousRunner:
    def __init__(self, settings: Settings, *, gateway: AlpacaCliGateway | None = None, journal: Journal | None = None) -> None:
        self.settings, self.gateway = settings, gateway or AlpacaCliGateway()
        self.journal = journal or Journal(settings.database_path)
        self.executor = PaperExecutor(settings, self.gateway)

    def run_cycle(self, *, demo: bool = False) -> list[int]:
        if demo:
            portfolio, symbols = PortfolioState(equity=100_000, buying_power=400_000), ("SPY",)
        else:
            self.gateway.assert_paper()
            portfolio = self.gateway.account()
            self.journal.record_pnl(portfolio.equity, portfolio.buying_power)
            if not bool(self.gateway.clock().get("is_open")):
                LOGGER.info("Market closed; cycle recorded without analysis or orders")
                return []
            symbols = self.settings.universe
        decision_ids: list[int] = []
        for symbol in symbols:
            try:
                snapshot = (
                    MarketSnapshot(
                        symbol=symbol,
                        price=770,
                        previous_close=765,
                        momentum_1h=0.006,
                        momentum_1d=0.018,
                        realized_volatility=0.2,
                        implied_volatility=0.22,
                    )
                    if demo
                    else self.gateway.market_snapshot(symbol)
                )
                contracts = _demo_contracts(symbol, snapshot.price) if demo else self.gateway.option_chain(symbol, snapshot.price)
                self.journal.record_observation(symbol, snapshot)
                opinions = [mind.evaluate(snapshot) for mind in market_council()]
                for opinion in opinions:
                    self.journal.record_opinion(symbol, opinion.agent, opinion)
                consensus = calculate_consensus(opinions)
                candidate = select_strategy(snapshot, consensus, contracts)
                candidate.client_order_id = (
                    "lyceum-" + hashlib.sha256(f"{symbol}:{candidate.strategy}:{candidate.expiry}".encode()).hexdigest()[:20]
                )
                skeptic = review_candidate(candidate, snapshot)
                risk = evaluate_risk(
                    candidate,
                    portfolio,
                    skeptic,
                    self.settings,
                    duplicate=self.journal.has_client_order(candidate.client_order_id),
                    last_symbol_trade_at=self.journal.last_symbol_decision(symbol),
                )
                result = self.executor.execute(candidate, risk) if risk.status is RiskStatus.APPROVED else None
                payload = {
                    "market": snapshot.model_dump(mode="json"),
                    "opinions": [item.model_dump(mode="json") for item in opinions],
                    "consensus": consensus.model_dump(mode="json"),
                    "candidate": candidate.model_dump(mode="json"),
                    "skeptic": skeptic.model_dump(mode="json"),
                    "risk": risk.model_dump(mode="json"),
                    "execution": None if result is None else {"mode": result.mode, "status": result.status, "payload": result.payload},
                    "integration": {"alpaca_cli_profile": "paper", "alpaca_mcp": "https://paper-api.alpaca.markets/mcp"},
                }
                decision_id = self.journal.record_decision(symbol, candidate.strategy, risk.status, payload)
                decision_ids.append(decision_id)
                if risk.status is RiskStatus.REJECTED:
                    self.journal.record_rejection(symbol, risk.reason_codes, payload)
                for alternative in [
                    StrategyType.NO_TRADE,
                    StrategyType.LONG_STRADDLE,
                    StrategyType.BULL_CALL_SPREAD,
                    StrategyType.BEAR_PUT_SPREAD,
                    StrategyType.IRON_CONDOR,
                ]:
                    if alternative != candidate.strategy:
                        self.journal.record_counterfactual(
                            decision_id, alternative, {"status": "pending", "reason": "captured for later mark-to-market"}
                        )
            except Exception as exc:
                LOGGER.exception("Symbol cycle failed for %s", symbol)
                self.journal.record_error("runner", str(exc), {"symbol": symbol})
        return decision_ids

    def run_forever(self, *, demo: bool = False) -> None:
        while True:
            self.run_cycle(demo=demo)
            time.sleep(self.settings.scan_interval_seconds)
