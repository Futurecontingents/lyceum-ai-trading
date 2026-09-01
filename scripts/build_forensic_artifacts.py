#!/usr/bin/env python3
"""Build auditable machine-readable artifacts for the Sep-01 incident response."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path, output: Path) -> None:
    generated = datetime.now(UTC).isoformat()
    manifest_path = root / "research/forward_test_2026-09-01.json"
    manifest = json.loads(manifest_path.read_text())
    candidate_hashes = {
        candidate["id"]: hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for candidate in manifest["candidates"]
    }
    write(
        output / "candidate_hashes_v2.json",
        {"generated_at": generated, "manifest_sha256": sha(manifest_path), "candidate_hashes": candidate_hashes},
    )
    with sqlite3.connect(root / "data/shadow_market.db") as db:
        db.row_factory = sqlite3.Row
        latest = db.execute(
            "SELECT id,completed_at FROM capture_batches WHERE status='COMPLETE' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        rows = db.execute(
            """SELECT u.symbol,c.run_id,c.agent_count,c.feature_schema_version,c.council_completed_at,
            json_extract(c.consensus_json,'$.disagreement') AS disagreement,
            json_extract(c.consensus_json,'$.entropy') AS entropy
            FROM underlying_snapshots u LEFT JOIN council_runs c
            ON c.batch_id=u.batch_id AND c.symbol=u.symbol
            WHERE u.batch_id=? ORDER BY u.symbol""", (latest["id"],)
        ).fetchall()
    coverage = {
        row["symbol"]: {
            "covered": row["run_id"] is not None, "council_run_id": row["run_id"],
            "agent_count": row["agent_count"], "schema": row["feature_schema_version"],
            "council_completed_at": row["council_completed_at"],
            "disagreement": row["disagreement"], "entropy": row["entropy"],
        }
        for row in rows
    }
    write(
        output / "feature_coverage_v2.json",
        {"generated_at": generated, "batch_id": latest["id"], "market_completed_at": latest["completed_at"],
         "required_symbols": 7, "covered_symbols": sum(item["covered"] for item in coverage.values()),
         "coverage": coverage},
    )
    canary_path = output / "live_canary_v2.json"
    preflight_path = output / "integrity_status_v2.json"
    write(
        output / "integrity_summary_v2.json",
        {"generated_at": generated, "incident_status": "SEP01_INVALID",
         "preflight": json.loads(preflight_path.read_text())["status"],
         "live_canary": json.loads(canary_path.read_text())["status"],
         "orders_submitted_during_canary": json.loads(canary_path.read_text())["orders_submitted"],
         "failed_runner_isolated": True, "next_sealed_test_started": False},
    )
    ledger = [
        {"experiment_id": "IR-001", "hypothesis": "Sep-01 zeros came from a failed council persistence transaction",
         "result": "REJECTED", "finding": "producer never ran; zero shadow_results was expected from launch topology"},
        {"experiment_id": "IR-002", "hypothesis": "silent council defaults changed C/D behavior",
         "result": "CONFIRMED", "finding": "post-hoc causal-input reconstruction materially changed trade selection; both remained negative"},
        {"experiment_id": "IR-003", "hypothesis": "sub-60m excursion metrics were horizon bounded",
         "result": "REJECTED", "finding": "one 60m vector was reused for 5/15/30m MFE and MAE"},
        {"experiment_id": "IR-004", "hypothesis": "typed feature contracts reject the original missing-row case",
         "result": "CONFIRMED", "finding": "regression test records INVALID_FEATURE_VECTOR and no evaluation"},
        {"experiment_id": "IR-005", "hypothesis": "v2 survives a real read-only end-to-end canary",
         "result": "CONFIRMED", "finding": "all seven stages passed; zero orders"},
        {"experiment_id": "SR-001", "hypothesis": "gross directional option move clears round-trip crossing",
         "result": "REJECTED", "finding": "0 of 4,878 eligible structures had positive forecast gross-minus-cost"},
        {"experiment_id": "SR-002", "hypothesis": "60m narrow 22-35 DTE geometry restores economics",
         "result": "REJECTED", "finding": "best momentum bucket mean executable P&L -$21.78"},
        {"experiment_id": "SR-003", "hypothesis": "full council adds directional information",
         "result": "REJECTED", "finding": "84 scored 60m states: full hit 51.2%, technical-only 57.1%; neither had option P&L evidence"},
        {"experiment_id": "SR-004", "hypothesis": "disagreement improvement is large enough to monetize",
         "result": "REJECTED", "finding": "forecast gain is below even the cheapest observed round-trip cost"},
    ]
    write(output / "experiment_ledger_v2.json", {"generated_at": generated, "experiments": ledger})
    board = [
        {"rank": 1, "candidate": "CASH_NO_TRADE", "evidence": "development control", "trades": 0,
         "executable_pnl": 0.0, "mean": None, "status": "BEST_CURRENT_POLICY_NO_EDGE"},
        {"rank": 2, "candidate": "A_COST_FILTERED_MOMENTUM", "evidence": "evaluable Sep-01 agreed cutoff",
         "trades": None, "executable_pnl": -421.80, "mean": None, "status": "REJECT"},
        {"rank": 3, "candidate": "D_RECONSTRUCTED_RIDGE", "evidence": "post-hoc development diagnostic",
         "trades": 45, "executable_pnl": -441.80, "mean": -9.8178, "status": "REJECT_NOT_OOS"},
        {"rank": 4, "candidate": "B_COST_FILTERED_REVERSION", "evidence": "evaluable Sep-01 agreed cutoff",
         "trades": None, "executable_pnl": -647.90, "mean": None, "status": "REJECT"},
        {"rank": 5, "candidate": "NARROW_22_35DTE_MOMENTUM_60M", "evidence": "Aug-31 development",
         "trades": 45, "executable_pnl": -979.90, "mean": -21.7756, "status": "REJECT_SINGLE_DAY"},
    ]
    write(
        output / "strategy_leaderboard_v2.json",
        {"generated_at": generated, "ranking_basis": "conservative executable total P&L; heterogeneous development samples",
         "warning": "not a common holdout leaderboard and not evidence of edge", "leaderboard": board},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("artifacts/forward_test"))
    args = parser.parse_args()
    build(args.root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
