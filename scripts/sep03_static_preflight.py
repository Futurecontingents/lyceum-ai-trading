#!/usr/bin/env python3
"""Static pre-market readiness gate; deliberately ignores quote freshness."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PAPER_ENDPOINT = "https://paper-api.alpaca.markets"


def check(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"check": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=30, check=False)


def run(manifest_path: Path, shadow_path: Path, profile: str) -> dict[str, Any]:
    from sep03_forward_scorer import score_latest

    manifest = json.loads(manifest_path.read_text())
    checks: list[dict[str, Any]] = []
    frozen_at = datetime.fromisoformat(manifest["frozen_at"].replace("Z", "+00:00")).astimezone(UTC)
    market_open = datetime.fromisoformat(manifest["first_observation_not_before"]).astimezone(UTC)
    commit = manifest["frozen_git_commit"]
    commit_exists = git("cat-file", "-e", f"{commit}^{{commit}}").returncode == 0
    commit_ancestor = git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0
    checks.append(check("frozen_git_commit", commit_exists and commit_ancestor and frozen_at < market_open, {"commit": commit, "frozen_at": frozen_at.isoformat(), "market_open": market_open.isoformat()}))
    computed_candidates = {item["id"]: canonical_hash(item) for item in manifest["candidates"]}
    checks.append(check("candidate_hashes", computed_candidates == manifest["candidate_hashes"], computed_candidates))
    computed_models = {item["path"]: file_hash(Path(item["path"])) for item in manifest.get("models", [])}
    checks.append(check("model_hashes", computed_models == manifest.get("model_hashes", {}), computed_models or "NO_MODEL_CANDIDATES"))
    data_manifest = json.loads(Path(manifest["data_manifest_path"]).read_text())
    cutoff_ok = data_manifest["cutoff"] == manifest["data_cutoff"] and manifest["data_cutoff"] < frozen_at.date().isoformat()
    checks.append(check("data_cutoff", cutoff_ok, {"manifest": manifest["data_cutoff"], "source": data_manifest["cutoff"]}))
    try:
        with sqlite3.connect(shadow_path) as db:
            quick = db.execute("PRAGMA quick_check").fetchone()[0]
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"capture_batches", "underlying_snapshots", "option_snapshots", "council_runs"}
        checks.append(check("database_schema", quick == "ok" and required <= tables, {"quick_check": quick, "missing": sorted(required - tables)}))
    except sqlite3.Error as exc:
        checks.append(check("database_schema", False, f"{type(exc).__name__}: {exc}"))
    doctor = subprocess.run(["alpaca", "--profile", profile, "doctor"], capture_output=True, text=True, timeout=30, check=False)
    doctor_text = doctor.stdout + doctor.stderr
    paper = doctor.returncode == 0 and PAPER_ENDPOINT in doctor_text and "api.alpaca.markets" not in doctor_text.replace(PAPER_ENDPOINT, "")
    checks.append(check("paper_only_enforcement", paper, "paper endpoint verified" if paper else "paper endpoint not proven"))
    runner = Path(manifest["runner_path"])
    source = runner.read_text().lower()
    forbidden = [word for word in ("submit_order", "cancel_order", "lyceum.execution", "tradingclient", "requests.post") if word in source]
    runner_ok = file_hash(runner) == manifest["runner_sha256"] and not forbidden and manifest["mode"] == "READ_ONLY_SHADOW"
    checks.append(check("runner_configuration", runner_ok, {"sha256": file_hash(runner), "forbidden": forbidden, "mode": manifest["mode"]}))
    normalized = Path("artifacts/long_history/normalized/SPY_yahoo.csv")
    last_date = normalized.read_text().splitlines()[-1].split(",", 1)[0]
    checks.append(check("no_future_data", last_date <= manifest["data_cutoff"], {"last_data_date": last_date, "cutoff": manifest["data_cutoff"]}))
    trade_candidates = [item["id"] for item in manifest["candidates"] if item["trade_producing"]]
    scoring_ok = len(trade_candidates) <= 3 and all(item["frozen_decision_reason"] for item in manifest["candidates"])
    checks.append(check("scoring_logic", scoring_ok, {"trade_producing_candidates": trade_candidates, "maximum": 3}))
    paths = manifest["persistence_paths"]
    path_ok = all(not Path(path).is_absolute() and ".." not in Path(path).parts for path in paths.values())
    checks.append(check("persistence_paths", path_ok, paths))
    try:
        with tempfile.TemporaryDirectory(prefix="lyceum-sep03-static-") as directory:
            probe = score_latest(shadow_path, Path(directory) / "probe.db", manifest_path)
        checks.append(check("scorer_static_probe", probe["database_quick_check"] == "ok" and probe["orders_submitted"] == 0, probe))
    except (RuntimeError, sqlite3.Error, OSError, ValueError) as exc:
        checks.append(check("scorer_static_probe", False, f"{type(exc).__name__}: {exc}"))
    return {
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "preflight_type": "STATIC_PRE_MARKET", "checked_at": datetime.now(UTC).isoformat(),
        "quote_freshness_checked": False, "orders_submitted": 0, "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-03.json"))
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--profile", default="judging")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run(args.manifest, args.shadow, args.profile)
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    raise SystemExit(0 if payload["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
