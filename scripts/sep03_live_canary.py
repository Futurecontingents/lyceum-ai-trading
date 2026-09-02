#!/usr/bin/env python3
"""Live-market canary for fresh causal inputs and read-only scorer health."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lyceum.forward_integrity import load_verified_council

if __package__:
    from scripts.sep03_forward_scorer import score_latest
else:
    from sep03_forward_scorer import score_latest


def stage(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"stage": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def run(manifest_path: Path, shadow_path: Path, max_age_seconds: int) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    stages: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    with sqlite3.connect(shadow_path) as db:
        db.row_factory = sqlite3.Row
        batch = db.execute("SELECT * FROM capture_batches WHERE status='COMPLETE' ORDER BY completed_at DESC LIMIT 1").fetchone()
        if batch is None:
            stages.append(stage("fresh_underlying_quotes", False, "no complete batch"))
            stages.append(stage("fresh_option_quotes", False, "no complete batch"))
            stages.append(stage("five_agent_rows_where_required", False, "no complete batch"))
            stages.append(stage("causal_timestamps", False, "no complete batch"))
            stages.append(stage("option_snapshot", False, "no complete batch"))
        else:
            batch_age = (now - parse_time(batch["completed_at"])).total_seconds()
            underlyings = db.execute("SELECT * FROM underlying_snapshots WHERE batch_id=?", (batch["id"],)).fetchall()
            underlying_ages = [(now - parse_time(row["quote_timestamp"])).total_seconds() for row in underlyings if row["quote_timestamp"]]
            underlying_ok = len(underlyings) >= 1 and underlying_ages and max(underlying_ages) <= max_age_seconds and batch_age <= max_age_seconds
            stages.append(stage("fresh_underlying_quotes", bool(underlying_ok), {"batch_id": batch["id"], "batch_age_seconds": batch_age, "rows": len(underlyings), "max_quote_age_seconds": max(underlying_ages, default=None)}))
            options = db.execute("SELECT * FROM option_snapshots WHERE batch_id=?", (batch["id"],)).fetchall()
            option_ages = [(now - parse_time(row["quote_timestamp"])).total_seconds() for row in options if row["quote_timestamp"]]
            valid_options = [row for row in options if row["bid"] and row["ask"] and row["ask"] > row["bid"]]
            option_ok = valid_options and option_ages and max(option_ages) <= max_age_seconds
            stages.append(stage("fresh_option_quotes", bool(option_ok), {"rows": len(options), "valid": len(valid_options), "max_quote_age_seconds": max(option_ages, default=None)}))
            requires_council = any(item.get("requires_five_agent_council", False) for item in manifest["candidates"])
            council_failures = {}
            if requires_council:
                for row in underlyings:
                    _consensus, reasons, _provenance = load_verified_council(db, batch_id=batch["id"], symbol=row["symbol"], market_completed_at=batch["completed_at"])
                    if reasons:
                        council_failures[row["symbol"]] = reasons
            stages.append(stage("five_agent_rows_where_required", not requires_council or not council_failures, "NOT_REQUIRED_BY_FROZEN_CANDIDATES" if not requires_council else council_failures or "complete"))
            causal_violations = sum(
                parse_time(row["quote_timestamp"]) > parse_time(batch["completed_at"]) for row in [*underlyings, *options] if row["quote_timestamp"]
            )
            stages.append(stage("causal_timestamps", causal_violations == 0, {"future_quote_timestamp_violations": causal_violations}))
            stages.append(stage("option_snapshot", len(valid_options) > 0, {"valid_option_snapshots": len(valid_options)}))
    try:
        with tempfile.TemporaryDirectory(prefix="lyceum-sep03-canary-") as directory:
            result = score_latest(shadow_path, Path(directory) / "canary.db", manifest_path)
        stages.append(stage("scorer_health", result["orders_submitted"] == 0 and result["database_quick_check"] == "ok", result))
    except (RuntimeError, sqlite3.Error, OSError, ValueError) as exc:
        stages.append(stage("scorer_health", False, f"{type(exc).__name__}: {exc}"))
    return {
        "status": "PASS" if all(item["status"] == "PASS" for item in stages) else "FAIL",
        "preflight_type": "LIVE_MARKET_CANARY", "checked_at": now.isoformat(),
        "max_age_seconds": max_age_seconds, "orders_submitted": 0, "stages": stages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-03.json"))
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--max-age-seconds", type=int, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run(args.manifest, args.shadow, args.max_age_seconds)
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    raise SystemExit(0 if payload["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
