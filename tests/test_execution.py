import subprocess

import pytest

from lyceum.config import Settings
from lyceum.execution.paper import ExecutionBlocked, ExecutionUncertain, PaperExecutor
from lyceum.models import OptionLeg, RiskDecision, RiskStatus, StrategyType, TradeCandidate
from tests.helpers import contract


class NeverCalledGateway:
    def assert_paper(self):
        raise AssertionError("READ_ONLY must not reach submission preflight")


def test_read_only_returns_preview_without_submission():
    candidate = TradeCandidate(
        symbol="SPY",
        strategy=StrategyType.BULL_CALL_SPREAD,
        legs=[OptionLeg(contract=contract(), side="buy"), OptionLeg(contract=contract("SPYTESTC2", strike=505), side="sell")],
        estimated_debit=300,
        max_loss=300,
        rationale="test",
        client_order_id="lyceum-test",
    )
    result = PaperExecutor(Settings(), NeverCalledGateway()).execute(
        candidate, RiskDecision(status=RiskStatus.APPROVED, reason_codes=["ALL_CHECKS_PASSED"])
    )
    assert result.status == "PREVIEW_ONLY"
    assert result.payload["order_class"] == "mleg"
    assert result.payload["qty"] == "1"
    assert "--qty" in PaperExecutor(Settings(), NeverCalledGateway()).command(candidate, dry_run=True)


def test_credit_order_uses_negative_net_limit_price():
    candidate = TradeCandidate(
        symbol="SPY",
        strategy=StrategyType.IRON_CONDOR,
        legs=[
            OptionLeg(contract=contract("SPYP1", "put", 490, bid=0.9, ask=1.0), side="buy"),
            OptionLeg(contract=contract("SPYP2", "put", 495, bid=2.0, ask=2.1), side="sell"),
            OptionLeg(contract=contract("SPYC1", "call", 505, bid=2.0, ask=2.1), side="sell"),
            OptionLeg(contract=contract("SPYC2", "call", 510, bid=0.9, ask=1.0), side="buy"),
        ],
        max_loss=300,
        rationale="credit test",
        client_order_id="lyceum-credit-test",
    )
    assert PaperExecutor.request_payload(candidate)["limit_price"] == -2.0


class AutonomousGateway:
    def validate_startup(self, **_kwargs):
        return {"status": "ACTIVE"}

    def clock(self):
        return {"is_open": self.is_open}

    def __init__(self, is_open: bool):
        self.is_open = is_open


def autonomous_settings(tmp_path):
    return Settings(
        execution_mode="PAPER_AUTONOMOUS",
        enable_paper_orders=True,
        expected_account_id="judging-api-account-id",
        emergency_halt_file=tmp_path / "HALT",
    )


def test_execution_rechecks_market_clock_immediately_before_submit(tmp_path, monkeypatch):
    item = TradeCandidate(
        symbol="SPY",
        strategy=StrategyType.BULL_CALL_SPREAD,
        legs=[OptionLeg(contract=contract(), side="buy"), OptionLeg(contract=contract("SPYTESTC2", strike=505), side="sell")],
        max_loss=300,
        rationale="test",
        client_order_id="lyceum-test",
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: pytest.fail("submission must not run while closed"))
    with pytest.raises(ExecutionBlocked, match="clock is closed"):
        PaperExecutor(autonomous_settings(tmp_path), AutonomousGateway(False)).execute(
            item, RiskDecision(status=RiskStatus.APPROVED, reason_codes=["ALL_CHECKS_PASSED"])
        )


def test_submission_timeout_is_classified_as_uncertain(tmp_path, monkeypatch):
    item = TradeCandidate(
        symbol="SPY",
        strategy=StrategyType.BULL_CALL_SPREAD,
        legs=[OptionLeg(contract=contract(), side="buy"), OptionLeg(contract=contract("SPYTESTC2", strike=505), side="sell")],
        max_loss=300,
        rationale="test",
        client_order_id="lyceum-test",
    )

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("alpaca", 30)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ExecutionUncertain, match="state is uncertain"):
        PaperExecutor(autonomous_settings(tmp_path), AutonomousGateway(True)).execute(
            item, RiskDecision(status=RiskStatus.APPROVED, reason_codes=["ALL_CHECKS_PASSED"])
        )
