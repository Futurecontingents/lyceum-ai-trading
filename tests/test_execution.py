from lyceum.config import Settings
from lyceum.execution.paper import PaperExecutor
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
