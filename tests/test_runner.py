import json
from datetime import UTC, datetime

import pytest

from lyceum.config import Settings
from lyceum.memory import Journal
from lyceum.models import ExecutionMode, MarketSnapshot, OptionContract
from lyceum.runner import AutonomousRunner


def test_demo_cycle_persists_full_vertical_slice(tmp_path):
    settings = Settings(database_path=tmp_path / "demo.db", emergency_halt_file=tmp_path / "HALT")
    journal = Journal(settings.database_path)
    ids = AutonomousRunner(settings, journal=journal).run_cycle(demo=True)
    assert len(ids) == 1
    assert len(journal.recent("agent_opinions")) == 5
    assert len(journal.recent("counterfactuals")) == 4


def test_closed_market_analysis_cannot_run_in_autonomous_mode(tmp_path):
    settings = Settings(
        execution_mode=ExecutionMode.PAPER_AUTONOMOUS,
        enable_paper_orders=True,
        expected_account_id="judging-api-account-id",
        database_path=tmp_path / "judging.db",
    )
    with pytest.raises(RuntimeError, match="READ_ONLY"):
        AutonomousRunner(settings).run_cycle(demo=True, analyze_when_closed=True)


class OptionIvGateway:
    def validate_startup(self, **_kwargs):
        return {
            "profile": "judging",
            "account_id": "test",
            "endpoint": "https://paper-api.alpaca.markets",
            "status": "ACTIVE",
            "equity": 100_000,
            "buying_power": 400_000,
            "open_positions": 0,
            "open_orders": 0,
        }

    def clock(self):
        return {"is_open": True}

    def market_snapshot(self, symbol):
        return MarketSnapshot(symbol=symbol, price=100, previous_close=99, realized_volatility=0.2)

    def option_chain(self, symbol, _price):
        return [
            OptionContract(
                symbol="SPY260918C00100000",
                underlying=symbol,
                expiration="2026-09-18",
                strike=100,
                option_type="call",
                bid=1,
                ask=1.1,
                bid_size=10,
                ask_size=10,
                implied_volatility=0.5,
                quote_timestamp=datetime.now(UTC),
            )
        ]


def test_runner_supplies_chain_iv_to_options_agent(tmp_path):
    settings = Settings(universe=("SPY",), database_path=tmp_path / "trace.db", emergency_halt_file=tmp_path / "HALT")
    journal = Journal(settings.database_path)
    AutonomousRunner(settings, gateway=OptionIvGateway(), journal=journal).run_cycle()
    opinion = next(row for row in journal.recent("agent_opinions") if row["agent"] == "OptionsMarketAgent")
    assert "IV=50.0%" in json.loads(opinion["payload"])["evidence"]
