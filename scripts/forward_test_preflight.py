#!/usr/bin/env python3
"""Fail-closed readiness gate for any post-incident sealed forward test."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lyceum.forward_integrity import (
    EXPECTED_AGENT_COUNT,
    FEATURE_SCHEMA_VERSION,
    init_integrity_schema,
    load_verified_council,
)

PAPER_ENDPOINT = "https://paper-api.alpaca.markets"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"check": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def _doctor(profile: str) -> tuple[bool, str]:
    completed = subprocess.run(
        ["alpaca", "--profile", profile, "doctor"], capture_output=True, text=True,
        timeout=30, check=False,
    )
    text = f"{completed.stdout}\n{completed.stderr}"
    passed = completed.returncode == 0 and PAPER_ENDPOINT in text and "api.alpaca.markets" not in text.replace(PAPER_ENDPOINT, "")
    return passed, "paper endpoint verified" if passed else "paper endpoint not proven"


def _process_loaded(label: str) -> bool:
    completed = subprocess.run(
        ["launchctl", "print", f"gui/{__import__('os').getuid()}/{label}"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return completed.returncode == 0


def run_preflight(
    *, shadow_path: Path, output_path: Path, manifest_path: Path, runner_path: Path,
    profile: str, expected_manifest_hash: str | None, expected_runner_hash: str | None,
    require_producer: bool, max_batch_age_seconds: int,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    manifest_hash = _sha(manifest_path)
    runner_hash = _sha(runner_path)
    manifest = json.loads(manifest_path.read_text())
    checks.append(_check("manifest_frozen", manifest.get("status") == "FROZEN" and len(manifest.get("candidates", [])) == 5, manifest_hash))
    checks.append(_check("manifest_hash", expected_manifest_hash in (None, manifest_hash), manifest_hash))
    checks.append(_check("runner_hash", expected_runner_hash in (None, runner_hash), runner_hash))
    candidate_hashes = {
        item["id"]: hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for item in manifest["candidates"]
    }
    checks.append(_check("candidate_hashes", len(candidate_hashes) == 5, candidate_hashes))
    try:
        with sqlite3.connect(shadow_path) as db:
            db.row_factory = sqlite3.Row
            init_integrity_schema(db)
            quick = db.execute("PRAGMA quick_check").fetchone()[0]
            checks.append(_check("shadow_sqlite_quick_check", quick == "ok", quick))
            batch = db.execute(
                "SELECT * FROM capture_batches WHERE status='COMPLETE' ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
            if batch is None:
                checks.append(_check("latest_complete_batch", False, "none"))
            else:
                age = (datetime.now(UTC) - datetime.fromisoformat(batch["completed_at"].replace("Z", "+00:00")).astimezone(UTC)).total_seconds()
                checks.append(_check("latest_complete_batch", age <= max_batch_age_seconds, {"id": batch["id"], "age_seconds": age}))
                symbols = db.execute(
                    "SELECT symbol FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch["id"],)
                ).fetchall()
                council_failures: dict[str, list[str]] = {}
                for symbol_row in symbols:
                    _consensus, reasons, _provenance = load_verified_council(
                        db, batch_id=int(batch["id"]), symbol=symbol_row["symbol"],
                        market_completed_at=batch["completed_at"],
                    )
                    if reasons:
                        council_failures[symbol_row["symbol"]] = reasons
                checks.append(_check("five_agent_council_coverage", len(symbols) == 7 and not council_failures, council_failures or f"{len(symbols)} symbols"))
                quotes = db.execute(
                    """SELECT COUNT(*) AS total,
                    SUM(CASE WHEN bid>0 AND ask>bid AND bid_size>=1 AND ask_size>=1
                        AND quote_timestamp IS NOT NULL THEN 1 ELSE 0 END) AS valid
                    FROM option_snapshots WHERE batch_id=?""", (batch["id"],)
                ).fetchone()
                total, valid = int(quotes["total"] or 0), int(quotes["valid"] or 0)
                checks.append(_check("option_quote_availability", total > 0 and valid > 0, {"total": total, "valid": valid}))
            db.execute("SAVEPOINT preflight_write")
            db.execute("CREATE TABLE IF NOT EXISTS preflight_write_probe(value INTEGER)")
            db.execute("INSERT INTO preflight_write_probe VALUES(1)")
            db.execute("ROLLBACK TO preflight_write")
            db.execute("RELEASE preflight_write")
            checks.append(_check("shadow_database_writable", True, "transaction rolled back"))
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        checks.append(_check("shadow_database", False, f"{type(exc).__name__}: {exc}"))
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(output_path) as output:
            output.execute("CREATE TABLE IF NOT EXISTS preflight_probe(value INTEGER)")
            output.execute("BEGIN")
            output.execute("INSERT INTO preflight_probe VALUES(1)")
            output.rollback()
            quick = output.execute("PRAGMA quick_check").fetchone()[0]
        checks.append(_check("outcome_storage", quick == "ok", quick))
    except (sqlite3.DatabaseError, OSError) as exc:
        checks.append(_check("outcome_storage", False, f"{type(exc).__name__}: {exc}"))
    doctor_ok, doctor_detail = _doctor(profile)
    checks.append(_check("paper_endpoint", doctor_ok, doctor_detail))
    checks.append(_check("raw_collector_loaded", _process_loaded("com.lyceum.shadow-collector"), "launch agent"))
    producer_loaded = _process_loaded("com.lyceum.shadow-council")
    checks.append(_check("council_producer_loaded", producer_loaded or not require_producer, "launch agent"))
    source = runner_path.read_text().lower()
    forbidden = [name for name in ("submit_order", "cancel_order", "lyceum.execution", "alpaca") if name in source]
    checks.append(_check("read_only_runner", not forbidden, forbidden or "no execution surface"))
    checks.append(_check("feature_schema", FEATURE_SCHEMA_VERSION == "forward-features-v2", FEATURE_SCHEMA_VERSION))
    checks.append(_check("agent_count_invariant", EXPECTED_AGENT_COUNT == 5, EXPECTED_AGENT_COUNT))
    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    return {
        "status": status, "checked_at": datetime.now(UTC).isoformat(), "profile": profile,
        "paper_only": doctor_ok, "manifest_hash": manifest_hash, "runner_hash": runner_hash,
        "candidate_hashes": candidate_hashes, "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--database", type=Path, default=Path("data/forward_test_v2.db"))
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-01.json"))
    parser.add_argument("--runner", type=Path, default=Path("scripts/forward_test_runner_v2.py"))
    parser.add_argument("--profile", default="judging")
    parser.add_argument("--expected-manifest-hash")
    parser.add_argument("--expected-runner-hash")
    parser.add_argument("--require-producer", action="store_true")
    parser.add_argument("--max-batch-age-seconds", type=int, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_preflight(
        shadow_path=args.shadow, output_path=args.database, manifest_path=args.manifest,
        runner_path=args.runner, profile=args.profile,
        expected_manifest_hash=args.expected_manifest_hash,
        expected_runner_hash=args.expected_runner_hash,
        require_producer=args.require_producer, max_batch_age_seconds=args.max_batch_age_seconds,
    )
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    raise SystemExit(0 if payload["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
