"""Lyceum command-line entrypoint."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from lyceum.config import load_settings
from lyceum.data import AlpacaCliGateway
from lyceum.experiment import render_markdown, run_experiment
from lyceum.runner import AutonomousRunner


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m lyceum")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the autonomous paper-only loop")
    run.add_argument("--once", action="store_true")
    run.add_argument("--demo", action="store_true", help="safe synthetic vertical slice; never submits")
    sub.add_parser("dashboard", help="launch the Streamlit dashboard")
    experiment = sub.add_parser("experiment", help="run historical disagreement sanity check")
    experiment.add_argument("--output", default="docs/EXPERIMENT_RESULTS.md")
    sub.add_parser("doctor", help="verify Alpaca paper connectivity")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    if args.command == "run":
        runner = AutonomousRunner(settings)
        if args.once:
            print(f"Recorded decisions: {runner.run_cycle(demo=args.demo)}")
        else:
            runner.run_forever(demo=args.demo)
    elif args.command == "dashboard":
        app = Path(__file__).with_name("dashboard") / "app.py"
        raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)]))
    elif args.command == "experiment":
        gateway = AlpacaCliGateway()
        gateway.assert_paper()
        results = run_experiment(gateway.bars("SPY", timeframe="1Hour", days=120, limit=1000))
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_markdown(results), encoding="utf-8")
        print(f"Wrote {output}")
    else:
        AlpacaCliGateway().assert_paper()
        print("Alpaca CLI profile is authenticated to PAPER trading.")


if __name__ == "__main__":
    main()
