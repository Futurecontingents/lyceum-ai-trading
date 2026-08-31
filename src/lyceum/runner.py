"""Resilient orchestration loop for the complete Lyceum vertical slice."""

from __future__ import annotations

import hashlib
import logging
import signal
import threading
from datetime import UTC, datetime, timedelta

from lyceum.agents import market_council
from lyceum.config import Settings
from lyceum.consensus import calculate_consensus
from lyceum.data import AlpacaCliGateway
from lyceum.execution.paper import ExecutionBlocked, ExecutionUncertain, PaperExecutor
from lyceum.memory import Journal
from lyceum.models import ExecutionMode, MarketSnapshot, OptionContract, PortfolioState, RiskStatus, StrategyType
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
        self.settings, self.gateway = settings, gateway or AlpacaCliGateway(settings.alpaca_profile)
        self.journal = journal or Journal(settings.database_path)
        self.executor = PaperExecutor(settings, self.gateway)
        self.last_market_open = False

    def run_cycle(self, *, demo: bool = False, analyze_when_closed: bool = False) -> list[int]:
        if analyze_when_closed and self.settings.execution_mode is not ExecutionMode.READ_ONLY:
            raise RuntimeError("closed-market analysis is permitted only in READ_ONLY mode")
        if demo:
            portfolio, symbols = PortfolioState(equity=100_000, buying_power=400_000), ("SPY",)
            self.last_market_open = False
        else:
            summary = self.gateway.validate_startup(
                expect_fresh=self.settings.expect_fresh_account,
                expected_account_id=self.settings.expected_account_id,
            )
            portfolio = PortfolioState(
                equity=summary["equity"],
                buying_power=summary["buying_power"],
                open_positions=summary["open_positions"],
                open_orders=summary["open_orders"],
            )
            self.journal.record_pnl(portfolio.equity, portfolio.buying_power)
            clock = self.gateway.clock()
            self.last_market_open = bool(clock.get("is_open"))
            LOGGER.info(
                "Preflight profile=%s account_id=%s endpoint=%s status=%s equity=%.2f buying_power=%.2f positions=%d open_orders=%d market_open=%s mode=%s halt=%s",
                summary["profile"],
                summary["account_id"],
                summary["endpoint"],
                summary["status"],
                summary["equity"],
                summary["buying_power"],
                summary["open_positions"],
                summary["open_orders"],
                self.last_market_open,
                self.settings.execution_mode,
                self.settings.emergency_halt_file.exists(),
            )
            if not self.last_market_open and not analyze_when_closed:
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
                chain_ivs = [item.implied_volatility for item in contracts if item.implied_volatility is not None]
                if chain_ivs:
                    snapshot = snapshot.model_copy(update={"implied_volatility": sum(chain_ivs) / len(chain_ivs)})
                self.journal.record_observation(symbol, snapshot)
                opinions = [mind.evaluate(snapshot) for mind in market_council(self.settings)]
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
                    last_symbol_trade_at=self.journal.last_symbol_trade_at(symbol),
                )
                result = None
                if risk.status is RiskStatus.APPROVED:
                    if self.settings.execution_mode is ExecutionMode.PAPER_AUTONOMOUS and candidate.strategy is not StrategyType.NO_TRADE:
                        self.journal.record_order(candidate.client_order_id, "SUBMISSION_INTENT", self.executor.request_payload(candidate))
                    try:
                        result = self.executor.execute(candidate, risk)
                    except ExecutionUncertain as exc:
                        self.journal.record_order(candidate.client_order_id, "UNKNOWN", {"error": str(exc)})
                        self.settings.emergency_halt_file.touch(exist_ok=True)
                        self.journal.record_error("execution", str(exc), {"symbol": symbol, "halt_created": True})
                        raise
                    except ExecutionBlocked as exc:
                        if self.settings.execution_mode is ExecutionMode.PAPER_AUTONOMOUS and candidate.strategy is not StrategyType.NO_TRADE:
                            self.journal.record_order(candidate.client_order_id, "REJECTED", {"error": str(exc)})
                        raise
                if result is not None and result.status == "SUBMITTED":
                    self.journal.record_order(candidate.client_order_id, result.status, result.payload)
                payload = {
                    "market": snapshot.model_dump(mode="json"),
                    "opinions": [item.model_dump(mode="json") for item in opinions],
                    "consensus": consensus.model_dump(mode="json"),
                    "candidate": candidate.model_dump(mode="json"),
                    "skeptic": skeptic.model_dump(mode="json"),
                    "risk": risk.model_dump(mode="json"),
                    "execution": None if result is None else {"mode": result.mode, "status": result.status, "payload": result.payload},
                    "run_context": {
                        "demo": demo,
                        "configured_council_mode": self.settings.council_mode,
                        "actual_council_mode": "HYBRID" if any(item.implementation == "model" for item in opinions) else "DETERMINISTIC",
                        "execution_mode": self.settings.execution_mode,
                    },
                    "integration": {
                        "alpaca_cli_profile": self.settings.alpaca_profile,
                        "alpaca_mcp": "https://paper-api.alpaca.markets/mcp",
                    },
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
            except ExecutionUncertain:
                LOGGER.exception("Uncertain execution state for %s; HALT created and cycle aborted", symbol)
                raise
            except Exception as exc:
                LOGGER.exception("Symbol cycle failed for %s", symbol)
                self.journal.record_error("runner", str(exc), {"symbol": symbol})
        return decision_ids

    def run_forever(self, *, demo: bool = False) -> None:
        stopping = threading.Event()

        def request_stop(signum: int, _frame: object) -> None:
            LOGGER.info("Received signal %s; shutting down safely", signum)
            stopping.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        failures = 0
        while not stopping.is_set():
            try:
                self.run_cycle(demo=demo)
                failures = 0
                delay = self.settings.scan_interval_seconds if self.last_market_open else self.settings.market_closed_poll_seconds
            except Exception as exc:
                failures += 1
                delay = min(self.settings.market_closed_poll_seconds, 2 ** min(failures, 8))
                self.journal.record_error("service", str(exc), {"consecutive_failures": failures, "retry_seconds": delay})
                LOGGER.exception("Cycle failed; retrying safely in %s seconds", delay)
                if failures >= 5:
                    self.settings.emergency_halt_file.touch(exist_ok=True)
                    LOGGER.error("Repeated failures created HALT; order submission remains disabled")
            stopping.wait(delay)
        LOGGER.info("Lyceum service stopped cleanly")
