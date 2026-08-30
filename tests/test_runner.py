import pytest

from lyceum.config import Settings
from lyceum.memory import Journal
from lyceum.models import ExecutionMode
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
