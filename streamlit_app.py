"""Credential-free public entry point for the Lyceum dashboard."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

# The public demo is deliberately isolated from any operator configuration.
os.environ.update(
    {
        "ALPACA_API_KEY": "",
        "ALPACA_SECRET_KEY": "",
        "ALPACA_PAPER": "true",
        "ALPACA_TRADING_BASE_URL": "https://paper-api.alpaca.markets",
        "LYCEUM_EXECUTION_MODE": "READ_ONLY",
        "LYCEUM_ENABLE_PAPER_ORDERS": "false",
        "LYCEUM_COUNCIL_MODE": "DETERMINISTIC",
        "LYCEUM_MODEL_PROVIDER": "deterministic",
        "LYCEUM_DATABASE_PATH": "/tmp/lyceum_public_demo.db",
        "LYCEUM_HALT_FILE": "/tmp/lyceum_public_demo_halt",
    }
)

from lyceum.config import load_settings  # noqa: E402
from lyceum.memory import Journal  # noqa: E402
from lyceum.runner import AutonomousRunner  # noqa: E402

settings = load_settings(env_file=None)
journal = Journal(settings.database_path)
if not journal.recent("decisions", 1):
    AutonomousRunner(settings, journal=journal).run_cycle(demo=True)

runpy.run_module("lyceum.dashboard.app", run_name="__main__")
