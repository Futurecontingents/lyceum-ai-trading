from lyceum.config import Settings
from lyceum.memory import Journal
from lyceum.runner import AutonomousRunner


def test_demo_cycle_persists_full_vertical_slice(tmp_path):
    settings = Settings(database_path=tmp_path / "demo.db", emergency_halt_file=tmp_path / "HALT")
    journal = Journal(settings.database_path)
    ids = AutonomousRunner(settings, journal=journal).run_cycle(demo=True)
    assert len(ids) == 1
    assert len(journal.recent("agent_opinions")) == 5
    assert len(journal.recent("counterfactuals")) == 4
