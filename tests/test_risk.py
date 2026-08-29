from datetime import UTC, datetime

from lyceum.config import Settings
from lyceum.models import OptionLeg, PortfolioState, RiskStatus, SkepticReview, StrategyType, TradeCandidate
from lyceum.risk import evaluate_risk
from tests.helpers import contract


def candidate(max_loss=300):
    return TradeCandidate(
        symbol="SPY",
        strategy=StrategyType.BULL_CALL_SPREAD,
        legs=[OptionLeg(contract=contract(), side="buy"), OptionLeg(contract=contract("SPYTESTC2", strike=505), side="sell")],
        expiry="2026-09-18",
        estimated_debit=300,
        max_loss=max_loss,
        rationale="test",
    )


def skeptic(veto=0.1):
    return SkepticReview(
        strongest_argument_against="x",
        hidden_assumption="x",
        liquidity_concern="x",
        iv_concern="x",
        event_concern="x",
        veto_confidence=veto,
    )


def portfolio():
    return PortfolioState(equity=100_000, buying_power=400_000)


def test_valid_defined_risk_candidate_approved(tmp_path):
    assert evaluate_risk(candidate(), portfolio(), skeptic(), Settings(emergency_halt_file=tmp_path / "HALT")).status is RiskStatus.APPROVED


def test_max_loss_rejected(tmp_path):
    decision = evaluate_risk(candidate(700), portfolio(), skeptic(), Settings(emergency_halt_file=tmp_path / "HALT"))
    assert "MAX_LOSS_PER_TRADE" in decision.reason_codes


def test_stale_quote_and_skeptic_rejected(tmp_path):
    item = candidate()
    item.legs[0].contract.quote_timestamp = datetime(2020, 1, 1, tzinfo=UTC)
    decision = evaluate_risk(item, portfolio(), skeptic(0.9), Settings(emergency_halt_file=tmp_path / "HALT"))
    assert {"STALE_QUOTE", "SKEPTIC_VETO"} <= set(decision.reason_codes)


def test_emergency_halt_rejected(tmp_path):
    halt = tmp_path / "HALT"
    halt.touch()
    assert "EMERGENCY_HALT" in evaluate_risk(candidate(), portfolio(), skeptic(), Settings(emergency_halt_file=halt)).reason_codes


def test_duplicate_and_cooldown_rejected(tmp_path):
    decision = evaluate_risk(
        candidate(),
        portfolio(),
        skeptic(),
        Settings(emergency_halt_file=tmp_path / "HALT"),
        duplicate=True,
        last_symbol_trade_at=datetime.now(UTC),
    )
    assert {"DUPLICATE_ORDER", "COOLDOWN"} <= set(decision.reason_codes)
