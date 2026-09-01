"""Fail-closed contracts and provenance for forward research observations."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from lyceum.consensus import calculate_consensus
from lyceum.models import AgentOpinion, ConsensusMetrics

FEATURE_SCHEMA_VERSION = "forward-features-v2"
COUNCIL_SCHEMA_VERSION = "council-provenance-v1"
EXPECTED_AGENT_COUNT = 5

COUNCIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS council_runs (
 run_id TEXT PRIMARY KEY, batch_id INTEGER NOT NULL, symbol TEXT NOT NULL,
 market_completed_at TEXT NOT NULL, council_started_at TEXT NOT NULL,
 council_completed_at TEXT NOT NULL, feature_schema_version TEXT NOT NULL,
 agent_count INTEGER NOT NULL, opinions_json TEXT NOT NULL,
 consensus_json TEXT NOT NULL, opinions_sha256 TEXT NOT NULL,
 producer_version TEXT NOT NULL, UNIQUE(batch_id,symbol)
);
CREATE INDEX IF NOT EXISTS idx_council_batch_symbol ON council_runs(batch_id,symbol);
CREATE TABLE IF NOT EXISTS forward_integrity_events (
 id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, batch_id INTEGER,
 symbol TEXT, candidate_id TEXT, status TEXT NOT NULL, reasons_json TEXT NOT NULL,
 provenance_json TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class FeatureContractResult:
    status: str
    reasons: tuple[str, ...]
    values: dict[str, float]
    provenance: dict[str, Any]

    @property
    def valid(self) -> bool:
        return self.status == "VALID"


def init_integrity_schema(db: sqlite3.Connection) -> None:
    db.executescript(COUNCIL_SCHEMA)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def persist_council_run(
    db: sqlite3.Connection,
    *,
    batch_id: int,
    symbol: str,
    market_completed_at: str,
    started_at: datetime,
    completed_at: datetime,
    opinions: list[AgentOpinion],
    consensus: ConsensusMetrics,
    producer_version: str,
) -> str:
    if len(opinions) != EXPECTED_AGENT_COUNT:
        raise ValueError(f"expected exactly {EXPECTED_AGENT_COUNT} agent opinions")
    names = [opinion.agent for opinion in opinions]
    if len(set(names)) != EXPECTED_AGENT_COUNT:
        raise ValueError("agent names must be unique")
    if completed_at < started_at:
        raise ValueError("council completion precedes start")
    market_at = datetime.fromisoformat(market_completed_at.replace("Z", "+00:00")).astimezone(UTC)
    if completed_at.astimezone(UTC) < market_at:
        raise ValueError("council completed before market batch")
    recomputed = calculate_consensus(opinions)
    if canonical_json(recomputed.model_dump(mode="json")) != canonical_json(consensus.model_dump(mode="json")):
        raise ValueError("persisted consensus does not match agent opinions")
    payload = [opinion.model_dump(mode="json") for opinion in opinions]
    run_id = str(uuid.uuid4())
    db.execute(
        """INSERT OR REPLACE INTO council_runs(
        run_id,batch_id,symbol,market_completed_at,council_started_at,council_completed_at,
        feature_schema_version,agent_count,opinions_json,consensus_json,opinions_sha256,producer_version
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id, batch_id, symbol, market_completed_at, started_at.astimezone(UTC).isoformat(),
            completed_at.astimezone(UTC).isoformat(), COUNCIL_SCHEMA_VERSION, len(opinions),
            canonical_json(payload), canonical_json(consensus.model_dump(mode="json")),
            sha256_json(payload), producer_version,
        ),
    )
    return run_id


def load_verified_council(
    db: sqlite3.Connection, *, batch_id: int, symbol: str, market_completed_at: str
) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
    row = db.execute(
        "SELECT * FROM council_runs WHERE batch_id=? AND symbol=?", (batch_id, symbol)
    ).fetchone()
    provenance: dict[str, Any] = {
        "batch_id": batch_id,
        "symbol": symbol,
        "market_completed_at": market_completed_at,
        "council_run_id": None,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }
    if row is None:
        return None, ["MISSING_COUNCIL_RUN"], provenance
    record = dict(row)
    provenance.update(
        {
            "council_run_id": record["run_id"],
            "council_completed_at": record["council_completed_at"],
            "council_schema_version": record["feature_schema_version"],
            "opinions_sha256": record["opinions_sha256"],
            "producer_version": record["producer_version"],
        }
    )
    reasons: list[str] = []
    if int(record["agent_count"]) != EXPECTED_AGENT_COUNT:
        reasons.append("WRONG_AGENT_COUNT")
    if record["feature_schema_version"] != COUNCIL_SCHEMA_VERSION:
        reasons.append("WRONG_COUNCIL_SCHEMA")
    try:
        opinions_payload = json.loads(record["opinions_json"])
        if sha256_json(opinions_payload) != record["opinions_sha256"]:
            reasons.append("OPINION_HASH_MISMATCH")
        opinions = [AgentOpinion.model_validate(item) for item in opinions_payload]
        if len({item.agent for item in opinions}) != EXPECTED_AGENT_COUNT:
            reasons.append("DUPLICATE_OR_MISSING_AGENT")
        recomputed = calculate_consensus(opinions).model_dump(mode="json")
        stored = json.loads(record["consensus_json"])
        for name in ("entropy", "disagreement", "expected_direction"):
            if not math.isclose(float(recomputed[name]), float(stored[name]), abs_tol=1e-12):
                reasons.append(f"CONSENSUS_MISMATCH_{name.upper()}")
    except (ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
        reasons.append(f"MALFORMED_COUNCIL_PAYLOAD:{type(exc).__name__}")
        stored = None
    market_at = datetime.fromisoformat(market_completed_at.replace("Z", "+00:00")).astimezone(UTC)
    completed_at = datetime.fromisoformat(record["council_completed_at"].replace("Z", "+00:00")).astimezone(UTC)
    if completed_at < market_at:
        reasons.append("CAUSALITY_COUNCIL_BEFORE_MARKET")
    return stored, reasons, provenance


def validate_feature_vector(
    *,
    candidate_id: str,
    required_features: list[str],
    values: Mapping[str, Any],
    provenance: Mapping[str, Any],
    council_reasons: list[str] | None = None,
) -> FeatureContractResult:
    reasons = list(council_reasons or [])
    checked: dict[str, float] = {}
    for feature in required_features:
        if feature not in values:
            reasons.append(f"MISSING_FEATURE:{feature}")
            continue
        raw = values[feature]
        if raw is None:
            reasons.append(f"NULL_FEATURE:{feature}")
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            reasons.append(f"NON_NUMERIC_FEATURE:{feature}")
            continue
        if not math.isfinite(value):
            reasons.append(f"NON_FINITE_FEATURE:{feature}")
            continue
        checked[feature] = value
    if any(name in required_features for name in ("disagreement", "entropy")) and not provenance.get("council_run_id"):
        reasons.append("UNPROVEN_COUNCIL_FEATURE")
    return FeatureContractResult(
        status="VALID" if not reasons else "INVALID_FEATURE_VECTOR",
        reasons=tuple(sorted(set(reasons))),
        values=checked,
        provenance=dict(provenance),
    )


def record_integrity_event(
    db: sqlite3.Connection,
    *,
    batch_id: int,
    symbol: str,
    candidate_id: str,
    result: FeatureContractResult,
) -> None:
    db.execute(
        """INSERT INTO forward_integrity_events(
        recorded_at,batch_id,symbol,candidate_id,status,reasons_json,provenance_json
        ) VALUES(?,?,?,?,?,?,?)""",
        (
            datetime.now(UTC).isoformat(), batch_id, symbol, candidate_id, result.status,
            canonical_json(result.reasons), canonical_json(result.provenance),
        ),
    )
