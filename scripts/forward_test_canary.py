#!/usr/bin/env python3
"""Read-only live canary for the post-incident forward pipeline."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from lyceum.forward_integrity import init_integrity_schema, validate_feature_vector

if __package__:
    from scripts.forward_test_runner_v2 import live_features_v2, run
    from scripts.quant_research import enumerate_state
    from scripts.shadow_council_producer import produce
else:
    from forward_test_runner_v2 import live_features_v2, run
    from quant_research import enumerate_state
    from shadow_council_producer import produce


def _stage(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"stage": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def canary(shadow_path: Path, manifest_path: Path) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    producer = produce(shadow_path, limit=35)
    stages.append(_stage("COUNCIL", producer["invalid"] == 0, producer))
    with sqlite3.connect(shadow_path) as shadow:
        shadow.row_factory = sqlite3.Row
        init_integrity_schema(shadow)
        batch = shadow.execute(
            "SELECT * FROM capture_batches WHERE status='COMPLETE' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        stages.append(_stage("MARKET", batch is not None, None if batch is None else {"batch_id": batch["id"], "completed_at": batch["completed_at"]}))
        coverage: dict[str, Any] = {}
        option_counts: dict[str, int] = {}
        if batch is not None:
            rows = shadow.execute(
                "SELECT * FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch["id"],)
            ).fetchall()
            for row in rows:
                values, common_reasons, provenance = live_features_v2(shadow, batch, row)
                result = validate_feature_vector(
                    candidate_id="C", required_features=["disagreement", "entropy", "return_5m", "rv_60m"],
                    values=values, provenance=provenance, council_reasons=common_reasons,
                )
                coverage[row["symbol"]] = {
                    "status": result.status, "reasons": result.reasons,
                    "disagreement": values.get("disagreement"), "entropy": values.get("entropy"),
                    "council_run_id": provenance.get("council_run_id"),
                }
                option_counts[row["symbol"]] = len(enumerate_state(shadow, batch, row))
            stages.append(_stage("PERSIST", len(coverage) == 7 and all(item["council_run_id"] for item in coverage.values()), coverage))
            stages.append(_stage("FEATURES", all(item["status"] == "VALID" for item in coverage.values()), coverage))
            stages.append(_stage("OPTIONS", all(count > 0 for count in option_counts.values()), option_counts))
            causal = shadow.execute(
                """SELECT COUNT(*) FROM council_runs
                WHERE batch_id=? AND council_completed_at < market_completed_at""", (batch["id"],)
            ).fetchone()[0]
            stages.append(_stage("CAUSALITY", causal == 0, {"violations": causal}))
            latest_at = datetime.fromisoformat(batch["completed_at"].replace("Z", "+00:00")).astimezone(UTC)
        else:
            latest_at = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="lyceum-forward-canary-") as directory:
        output = Path(directory) / "canary.db"
        leaderboard = Path(directory) / "leaderboard.json"
        runner_result = run(
            shadow_path, output, manifest_path, leaderboard,
            (latest_at - timedelta(minutes=70)).isoformat(),
        )
        with sqlite3.connect(output) as db:
            db.row_factory = sqlite3.Row
            invalid_causality = 0
            for row in db.execute("SELECT horizon,provenance_json FROM forward_outcomes_v2"):
                provenance = json.loads(row["provenance_json"])
                latest = provenance["latest_excursion_minutes"]
                if latest is not None and latest > int(row["horizon"]) + 1e-9:
                    invalid_causality += 1
            outcome_count = db.execute("SELECT COUNT(*) FROM forward_outcomes_v2").fetchone()[0]
        stages.append(_stage("SCORER", invalid_causality == 0 and outcome_count > 0, {**runner_result, "outcomes": outcome_count, "horizon_violations": invalid_causality}))
    passed = all(item["status"] == "PASS" for item in stages)
    return {
        "status": "PASS" if passed else "FAIL", "checked_at": datetime.now(UTC).isoformat(),
        "mode": "READ_ONLY", "orders_submitted": 0, "stages": stages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-01.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = canary(args.shadow, args.manifest)
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    raise SystemExit(0 if payload["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
