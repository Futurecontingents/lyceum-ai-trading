#!/usr/bin/env python3
"""Read-only Sep-03 observation scorer; it has no broker execution surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sep03_decisions (
 id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, symbol TEXT NOT NULL,
 candidate_id TEXT NOT NULL, observed_at TEXT NOT NULL, decision TEXT NOT NULL,
 reason TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, candidate_sha256 TEXT NOT NULL,
 market_completed_at TEXT NOT NULL, payload_json TEXT NOT NULL,
 UNIQUE(batch_id, symbol, candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_sep03_batch ON sep03_decisions(batch_id, symbol);
"""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def score_latest(shadow_path: Path, output_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest_text = manifest_path.read_text()
    manifest = json.loads(manifest_text)
    if manifest.get("status") != "FROZEN" or manifest.get("mode") != "READ_ONLY_SHADOW":
        raise RuntimeError("Sep-03 manifest must be frozen read-only shadow mode")
    manifest_hash = hashlib.sha256(manifest_text.encode()).hexdigest()
    with sqlite3.connect(shadow_path) as shadow, sqlite3.connect(output_path) as output:
        shadow.row_factory = sqlite3.Row
        output.executescript(SCHEMA)
        batch = shadow.execute(
            "SELECT * FROM capture_batches WHERE status='COMPLETE' ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        if batch is None:
            raise RuntimeError("no complete shadow batch")
        rows = shadow.execute(
            "SELECT * FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch["id"],)
        ).fetchall()
        created = 0
        for candidate in manifest["candidates"]:
            symbols = set(candidate.get("universe", []))
            for row in rows:
                if symbols and row["symbol"] not in symbols:
                    continue
                candidate_hash = sha256_json(candidate)
                decision = "NO_TRADE"
                reason = candidate["frozen_decision_reason"]
                payload = {
                    "trade_producing": candidate["trade_producing"],
                    "signal_definition": candidate["signal_definition"],
                    "target": candidate["target"],
                    "trade_price": row["trade_price"],
                    "quote_timestamp": row["quote_timestamp"],
                    "orders_submitted": 0,
                }
                output.execute(
                    """INSERT OR IGNORE INTO sep03_decisions(
                    batch_id,symbol,candidate_id,observed_at,decision,reason,manifest_sha256,
                    candidate_sha256,market_completed_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        batch["id"], row["symbol"], candidate["id"], datetime.now(UTC).isoformat(),
                        decision, reason, manifest_hash, candidate_hash, batch["completed_at"], canonical(payload),
                    ),
                )
                created += output.execute("SELECT changes()").fetchone()[0]
        output.commit()
        quick = output.execute("PRAGMA quick_check").fetchone()[0]
    return {"batch_id": batch["id"], "decisions_created": created, "database_quick_check": quick, "orders_submitted": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--database", type=Path, default=Path("data/sep03_forward_test.db"))
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-03.json"))
    args = parser.parse_args()
    print(json.dumps(score_latest(args.shadow, args.database, args.manifest), sort_keys=True))


if __name__ == "__main__":
    main()
