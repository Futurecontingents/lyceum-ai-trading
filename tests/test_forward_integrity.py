from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from lyceum.consensus import calculate_consensus
from lyceum.forward_integrity import (
    COUNCIL_SCHEMA_VERSION,
    init_integrity_schema,
    load_verified_council,
    persist_council_run,
    validate_feature_vector,
)
from lyceum.models import AgentOpinion, ProbabilityDistribution
from scripts import forward_test_runner_v2 as runner


def opinion(index: int, timestamp: datetime) -> AgentOpinion:
    up = 0.10 + index * 0.01
    return AgentOpinion(
        agent=f"agent-{index}", symbol="SPY", timestamp=timestamp, horizon="5m",
        probabilities=ProbabilityDistribution(
            strong_down=0.10, down=0.20, flat=0.40 - index * 0.01, up=up, strong_up=0.20
        ),
        expected_return=index * 0.0001, confidence=0.6,
        reasoning_summary="deterministic synthetic opinion", data_freshness=timestamp,
    )


def council_db() -> tuple[sqlite3.Connection, datetime]:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_integrity_schema(db)
    market_at = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    opinions = [opinion(index, market_at) for index in range(5)]
    persist_council_run(
        db, batch_id=1, symbol="SPY", market_completed_at=market_at.isoformat(),
        started_at=market_at, completed_at=market_at + timedelta(seconds=1),
        opinions=opinions, consensus=calculate_consensus(opinions), producer_version="test-v1",
    )
    return db, market_at


def test_missing_council_never_silently_becomes_zero() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_integrity_schema(db)
    consensus, reasons, provenance = load_verified_council(
        db, batch_id=1, symbol="SPY", market_completed_at=datetime.now(UTC).isoformat()
    )
    assert consensus is None
    result = validate_feature_vector(
        candidate_id="C", required_features=["disagreement", "entropy"], values={},
        provenance=provenance, council_reasons=reasons,
    )
    assert result.status == "INVALID_FEATURE_VECTOR"
    assert "MISSING_COUNCIL_RUN" in result.reasons
    assert "MISSING_FEATURE:disagreement" in result.reasons


def test_explicit_verified_zero_is_allowed() -> None:
    db, market_at = council_db()
    _consensus, reasons, provenance = load_verified_council(
        db, batch_id=1, symbol="SPY", market_completed_at=market_at.isoformat()
    )
    result = validate_feature_vector(
        candidate_id="C", required_features=["disagreement", "entropy"],
        values={"disagreement": 0.0, "entropy": 0.0}, provenance=provenance,
        council_reasons=reasons,
    )
    assert result.valid


def test_persisted_consensus_is_recomputed_from_exactly_five_agents() -> None:
    db, market_at = council_db()
    consensus, reasons, provenance = load_verified_council(
        db, batch_id=1, symbol="SPY", market_completed_at=market_at.isoformat()
    )
    assert not reasons
    assert consensus is not None
    assert provenance["council_schema_version"] == COUNCIL_SCHEMA_VERSION
    assert 0 <= consensus["disagreement"] <= 1
    assert 0 <= consensus["entropy"] <= 1


def test_tampered_council_payload_fails_closed() -> None:
    db, market_at = council_db()
    payload = json.loads(db.execute("SELECT consensus_json FROM council_runs").fetchone()[0])
    payload["entropy"] = 0.0
    db.execute("UPDATE council_runs SET consensus_json=?", (json.dumps(payload),))
    _consensus, reasons, _provenance = load_verified_council(
        db, batch_id=1, symbol="SPY", market_completed_at=market_at.isoformat()
    )
    assert "CONSENSUS_MISMATCH_ENTROPY" in reasons


def test_future_market_value_cannot_enter_earlier_council_run() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_integrity_schema(db)
    market_at = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    opinions = [opinion(index, market_at) for index in range(5)]
    with pytest.raises(ValueError, match="before market batch"):
        persist_council_run(
            db, batch_id=1, symbol="SPY", market_completed_at=market_at.isoformat(),
            started_at=market_at - timedelta(seconds=2),
            completed_at=market_at - timedelta(seconds=1), opinions=opinions,
            consensus=calculate_consensus(opinions), producer_version="test-v1",
        )


def test_nonfinite_required_feature_fails_closed() -> None:
    result = validate_feature_vector(
        candidate_id="D", required_features=["return_5m"], values={"return_5m": math.nan},
        provenance={},
    )
    assert result.status == "INVALID_FEATURE_VECTOR"
    assert result.reasons == ("NON_FINITE_FEATURE:return_5m",)


def test_horizon_excursions_cannot_use_later_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    output = sqlite3.connect(":memory:")
    shadow = sqlite3.connect(":memory:")
    output.row_factory = shadow.row_factory = sqlite3.Row
    output.executescript(runner.SCHEMA)
    start = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    batches = []
    for batch_id, minutes in enumerate((0, 5, 15, 30, 60), start=1):
        batches.append({"id": batch_id, "completed_at": (start + timedelta(minutes=minutes)).isoformat()})
    output.execute(
        """INSERT INTO forward_decisions_v2(
        batch_id,decision_available_at,symbol,candidate_id,candidate_name,benchmark,status,
        invalid_reasons_json,signal,strategy,intended_horizon,no_trade_reason,max_loss,entry_mid,
        entry_executable,entry_crossing_cost,legs_json,feature_json,provenance_json,
        feature_schema_version,manifest_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (1, start.isoformat(), "SPY", "X", "synthetic", 0, "VALID", "[]", 1.0,
         "BULL_CALL_SPREAD", 60, None, 100, None, 100, 1, "[]", "{}", "{}", "v2", "hash"),
    )
    executable = {1: 100.0, 2: 101.0, 3: 120.0, 4: 80.0, 5: 110.0}

    def fake_quote(_db: sqlite3.Connection, batch_id: int, _legs: list[object]) -> tuple[float, float, float]:
        return executable[batch_id], executable[batch_id], 1.0

    monkeypatch.setattr(runner, "quote_values", fake_quote)
    runner.score_v2(output, shadow, batches)  # type: ignore[arg-type]
    five = output.execute("SELECT mfe,mae,provenance_json FROM forward_outcomes_v2 WHERE horizon=5").fetchone()
    fifteen = output.execute("SELECT mfe,mae FROM forward_outcomes_v2 WHERE horizon=15").fetchone()
    assert (five["mfe"], five["mae"]) == (1.0, 1.0)
    assert json.loads(five["provenance_json"])["excursion_batch_ids"] == [2]
    assert (fifteen["mfe"], fifteen["mae"]) == (20.0, 1.0)


def test_v2_source_has_no_execution_surface() -> None:
    source = open("scripts/forward_test_runner_v2.py", encoding="utf-8").read().lower()
    for forbidden in ("lyceum.execution", "submit_order", "cancel_order", "subprocess", "alpaca"):
        assert forbidden not in source
