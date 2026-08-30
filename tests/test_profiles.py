import pytest

from lyceum.config import Settings, load_settings
from lyceum.data.alpaca_cli import AlpacaCliError, AlpacaCliGateway
from lyceum.execution.paper import PaperExecutor
from lyceum.models import OptionLeg, StrategyType, TradeCandidate
from tests.helpers import contract


class SummaryGateway(AlpacaCliGateway):
    def __init__(
        self,
        *,
        positions: int = 0,
        orders: int = 0,
        equity: float = 100_000,
        status: str = "ACTIVE",
        account_id: str = "different-account",
    ) -> None:
        super().__init__(profile="judging")
        self.positions = positions
        self.orders = orders
        self.equity = equity
        self.status = status
        self.account_id = account_id

    def profile_summary(self):
        return {
            "profile": self.profile,
            "endpoint": "https://paper-api.alpaca.markets",
            "account_id": self.account_id,
            "status": self.status,
            "equity": self.equity,
            "buying_power": 400_000.0,
            "open_positions": self.positions,
            "open_orders": self.orders,
        }


def test_account_profile_selection(monkeypatch, tmp_path):
    monkeypatch.setenv("LYCEUM_ALPACA_PROFILE", "judging")
    settings = load_settings(tmp_path / "missing")
    assert settings.alpaca_profile == "judging"
    assert AlpacaCliGateway(settings.alpaca_profile).profile == "judging"


def test_executor_command_uses_selected_profile():
    settings = Settings(alpaca_profile="judging")
    item = TradeCandidate(
        symbol="SPY",
        strategy=StrategyType.BULL_CALL_SPREAD,
        legs=[OptionLeg(contract=contract(), side="buy"), OptionLeg(contract=contract("SPYTESTC2"), side="sell")],
        estimated_debit=300,
        max_loss=300,
        rationale="profile test",
        client_order_id="lyceum-profile-test",
    )
    assert PaperExecutor(settings, SummaryGateway()).command(item, dry_run=True)[:3] == ["alpaca", "--profile", "judging"]


def test_fresh_account_validation_passes_only_when_empty():
    assert SummaryGateway().validate_startup(expect_fresh=True)["profile"] == "judging"
    with pytest.raises(AlpacaCliError, match="FRESH ACCOUNT CHECK FAILED"):
        SummaryGateway(positions=1).validate_startup(expect_fresh=True)
    with pytest.raises(AlpacaCliError, match="FRESH ACCOUNT CHECK FAILED"):
        SummaryGateway(orders=1).validate_startup(expect_fresh=True)
    with pytest.raises(AlpacaCliError, match="FRESH ACCOUNT CHECK FAILED"):
        SummaryGateway(equity=99_999).validate_startup(expect_fresh=True)


def test_startup_requires_active_and_pinned_account():
    with pytest.raises(AlpacaCliError, match="ACCOUNT STATUS CHECK FAILED"):
        SummaryGateway(status="ACCOUNT_UPDATED").validate_startup()
    with pytest.raises(AlpacaCliError, match="ACCOUNT ID CHECK FAILED"):
        SummaryGateway(account_id="wrong").validate_startup(expected_account_id="judging-api-account-id")
    assert (
        SummaryGateway(account_id="judging-api-account-id").validate_startup(expected_account_id="judging-api-account-id")["status"]
        == "ACTIVE"
    )


def test_profile_name_is_safely_bounded():
    with pytest.raises(ValueError):
        Settings(alpaca_profile="judging; order submit")
