#!/usr/bin/env python3
"""Persist exactly one causal five-agent council run per captured symbol."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from lyceum.agents import market_council
from lyceum.config import Settings
from lyceum.consensus import calculate_consensus
from lyceum.forward_integrity import init_integrity_schema, persist_council_run
from lyceum.models import CouncilMode, ExecutionMode
from lyceum.shadow import ShadowStore, _snapshot

PRODUCER_VERSION = "shadow-council-producer-v1"


def produce(database: Path, *, limit: int = 20) -> dict[str, int]:
    store = ShadowStore(database)
    settings = Settings(council_mode=CouncilMode.DETERMINISTIC, execution_mode=ExecutionMode.READ_ONLY)
    council = market_council(settings)
    created = invalid = 0
    with store.connect() as db:
        init_integrity_schema(db)
        rows = db.execute(
            """SELECT b.id AS batch_id,b.completed_at,u.* FROM capture_batches b
            JOIN underlying_snapshots u ON u.batch_id=b.id
            LEFT JOIN council_runs c ON c.batch_id=b.id AND c.symbol=u.symbol
            WHERE b.status='COMPLETE' AND b.completed_at IS NOT NULL AND c.run_id IS NULL
            ORDER BY b.completed_at DESC,u.symbol LIMIT ?""",
            (limit,),
        ).fetchall()
        for row in reversed(rows):
            started = datetime.now(UTC)
            try:
                snapshot = _snapshot(row)
                opinions = [agent.evaluate(snapshot) for agent in council]
                consensus = calculate_consensus(opinions)
                persist_council_run(
                    db,
                    batch_id=int(row["batch_id"]),
                    symbol=row["symbol"],
                    market_completed_at=row["completed_at"],
                    started_at=started,
                    completed_at=datetime.now(UTC),
                    opinions=opinions,
                    consensus=consensus,
                    producer_version=PRODUCER_VERSION,
                )
                created += 1
            except (ValueError, TypeError, sqlite3.DatabaseError):
                invalid += 1
        db.commit()
    return {"observations_considered": len(rows), "council_runs_created": created, "invalid": invalid}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(produce(args.database, limit=args.limit), sort_keys=True))


if __name__ == "__main__":
    main()
