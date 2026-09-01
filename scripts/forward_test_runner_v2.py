#!/usr/bin/env python3
"""Fail-closed, provenance-complete forward evaluator (post-incident v2)."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from lyceum.forward_integrity import (
    FEATURE_SCHEMA_VERSION,
    canonical_json,
    init_integrity_schema,
    load_verified_council,
    record_integrity_event,
    validate_feature_vector,
)

if __package__:
    from scripts.forward_test_runner import evaluate_definition, model_predict, quote_values
    from scripts.quant_research import enumerate_state, iso
else:
    from forward_test_runner import evaluate_definition, model_predict, quote_values
    from quant_research import enumerate_state, iso

NY = ZoneInfo("America/New_York")
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS forward_decisions_v2 (
 id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, decision_available_at TEXT NOT NULL,
 symbol TEXT NOT NULL, candidate_id TEXT NOT NULL, candidate_name TEXT NOT NULL,
 benchmark INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, invalid_reasons_json TEXT NOT NULL,
 signal REAL, strategy TEXT NOT NULL, intended_horizon INTEGER NOT NULL, no_trade_reason TEXT,
 max_loss REAL, entry_mid REAL, entry_executable REAL, entry_crossing_cost REAL,
 legs_json TEXT NOT NULL, feature_json TEXT NOT NULL, provenance_json TEXT NOT NULL,
 feature_schema_version TEXT NOT NULL, manifest_hash TEXT NOT NULL,
 UNIQUE(batch_id,symbol,candidate_id)
);
CREATE TABLE IF NOT EXISTS forward_outcomes_v2 (
 decision_id INTEGER NOT NULL, horizon INTEGER NOT NULL, exit_batch_id INTEGER NOT NULL,
 exit_available_at TEXT NOT NULL, scoring_available_at TEXT NOT NULL,
 midpoint_pnl REAL NOT NULL, market_move_pnl REAL NOT NULL,
 entry_crossing_cost REAL NOT NULL, exit_crossing_cost REAL NOT NULL,
 conservative_pnl REAL NOT NULL, mfe REAL, mae REAL, provenance_json TEXT NOT NULL,
 PRIMARY KEY(decision_id,horizon),
 FOREIGN KEY(decision_id) REFERENCES forward_decisions_v2(id)
);
"""


def _finite(value: Any, name: str) -> float:
    if value is None:
        raise ValueError(f"missing {name}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite {name}")
    return number


def live_features_v2(
    db: sqlite3.Connection, batch: sqlite3.Row, row: sqlite3.Row
) -> tuple[dict[str, float], list[str], dict[str, Any]]:
    reasons: list[str] = []
    try:
        bars = json.loads(row["bars_json"])
        if len(bars) < 61:
            reasons.append("INSUFFICIENT_BARS")
        closes = np.asarray([_finite(item.get("c"), "bar_close") for item in bars], dtype=float)
        volumes = np.asarray([_finite(item.get("v"), "bar_volume") for item in bars], dtype=float)
        returns = closes[1:] / closes[:-1] - 1
        recent = bars[-1]
        typical = np.asarray(
            [(_finite(item.get("h"), "bar_high") + _finite(item.get("l"), "bar_low") + _finite(item.get("c"), "bar_close")) / 3 for item in bars[-120:]]
        )
        recent_volume = volumes[-len(typical):]
        volume_total = float(np.sum(recent_volume))
        if volume_total <= 0:
            raise ValueError("non-positive volume total")
        vwap = float(np.sum(typical * recent_volume) / volume_total)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, IndexError) as exc:
        return {}, [*reasons, f"MALFORMED_MARKET_FEATURES:{type(exc).__name__}"], {
            "batch_id": int(batch["id"]), "symbol": row["symbol"], "market_completed_at": batch["completed_at"]
        }

    consensus, council_reasons, provenance = load_verified_council(
        db, batch_id=int(batch["id"]), symbol=row["symbol"], market_completed_at=batch["completed_at"]
    )
    reasons.extend(council_reasons)
    options = db.execute(
        """SELECT implied_volatility,strike,quote_timestamp FROM option_snapshots
        WHERE batch_id=? AND underlying=? AND implied_volatility IS NOT NULL""",
        (batch["id"], row["symbol"]),
    ).fetchall()
    spot = _finite(row["trade_price"], "trade_price")
    atm = sorted(options, key=lambda option: abs(float(option["strike"]) - spot))[:30]
    if not atm:
        reasons.append("MISSING_ATM_IV")
        atm_iv = math.nan
    else:
        atm_iv = median(_finite(option["implied_volatility"], "implied_volatility") for option in atm)
    local = iso(batch["completed_at"]).astimezone(NY)
    minute = local.hour * 60 + local.minute - 570
    values = {
        "return_5m": row["return_5m"], "return_15m": row["return_15m"],
        "return_30m": row["return_30m"], "return_60m": row["return_60m"],
        "rv_15m": float(math.sqrt(np.sum(np.square(returns[-15:])))),
        "rv_60m": float(math.sqrt(np.sum(np.square(returns[-60:])))),
        "rv_1d": None if row["realized_volatility"] is None else float(row["realized_volatility"]) / math.sqrt(252),
        "range_pct": (_finite(recent.get("h"), "recent_high") - _finite(recent.get("l"), "recent_low")) / _finite(recent.get("c"), "recent_close"),
        "volume_ratio": float(volumes[-1] / max(np.median(volumes[-60:]), 1)),
        "vwap_deviation": spot / vwap - 1,
        "minute_sin": math.sin(2 * math.pi * minute / 390),
        "minute_cos": math.cos(2 * math.pi * minute / 390), "atm_iv": atm_iv, "spot": spot,
    }
    if consensus is not None:
        values.update(
            disagreement=consensus.get("disagreement"), entropy=consensus.get("entropy"),
            jsd=consensus.get("disagreement"), consensus_direction=consensus.get("expected_direction"),
        )
    completed_at = iso(batch["completed_at"])
    for name in ("quote_timestamp", "trade_timestamp"):
        timestamp = row[name]
        if not timestamp:
            reasons.append(f"MISSING_UNDERLYING_{name.upper()}")
        elif iso(timestamp) > completed_at:
            reasons.append(f"CAUSALITY_FUTURE_UNDERLYING_{name.upper()}")
    for option in atm:
        if not option["quote_timestamp"]:
            reasons.append("MISSING_OPTION_QUOTE_TIMESTAMP")
        else:
            quote_at = iso(option["quote_timestamp"])
            age = (completed_at - quote_at).total_seconds()
            if age < 0:
                reasons.append("CAUSALITY_FUTURE_OPTION_QUOTE")
            elif age > 180:
                reasons.append("STALE_OPTION_QUOTE")
    provenance.update(
        {
            "underlying_snapshot_id": int(row["id"]),
            "underlying_quote_timestamp": row["quote_timestamp"],
            "underlying_trade_timestamp": row["trade_timestamp"],
            "option_observation_count": len(options),
            "atm_option_quote_timestamps": [option["quote_timestamp"] for option in atm],
        }
    )
    return values, reasons, provenance


def _leg_provenance(
    shadow: sqlite3.Connection, batch_id: int, candidate: Any | None
) -> list[dict[str, Any]]:
    if candidate is None:
        return []
    records: list[dict[str, Any]] = []
    for contract, sign in candidate.legs:
        row = shadow.execute(
            """SELECT id,contract_symbol,quote_timestamp,captured_at,bid,ask,bid_size,ask_size
            FROM option_snapshots WHERE batch_id=? AND contract_symbol=?""", (batch_id, contract)
        ).fetchone()
        if row is None:
            records.append({"contract_symbol": contract, "sign": sign, "missing": True})
        else:
            records.append(
                {"option_snapshot_id": int(row["id"]), "contract_symbol": row["contract_symbol"],
                 "sign": sign, "quote_timestamp": row["quote_timestamp"],
                 "captured_at": row["captured_at"], "bid": row["bid"], "ask": row["ask"],
                 "bid_size": row["bid_size"], "ask_size": row["ask_size"]}
            )
    return records


def _insert_decision(
    output: sqlite3.Connection, *, batch: sqlite3.Row, symbol: str, definition: dict[str, Any],
    result: Any, manifest_hash: str, signal: float | None = None, candidate: Any = None,
    reason: str = "", benchmark: bool = False,
) -> None:
    output.execute(
        """INSERT OR IGNORE INTO forward_decisions_v2(
        batch_id,decision_available_at,symbol,candidate_id,candidate_name,benchmark,status,
        invalid_reasons_json,signal,strategy,intended_horizon,no_trade_reason,max_loss,entry_mid,
        entry_executable,entry_crossing_cost,legs_json,feature_json,provenance_json,
        feature_schema_version,manifest_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            batch["id"], batch["completed_at"], symbol, definition["id"], definition["name"], benchmark,
            result.status, canonical_json(result.reasons), signal,
            candidate.structure if candidate else "NO_TRADE", int(definition["holding_minutes"]),
            reason or None, candidate.max_loss if candidate else None, None,
            candidate.entry_value if candidate else None, candidate.crossing_cost if candidate else None,
            canonical_json(candidate.legs if candidate else []), canonical_json(result.values),
            canonical_json(result.provenance), FEATURE_SCHEMA_VERSION, manifest_hash,
        ),
    )


def score_v2(output: sqlite3.Connection, shadow: sqlite3.Connection, batches: list[sqlite3.Row]) -> None:
    by_id = {int(batch["id"]): batch for batch in batches}
    decisions = output.execute(
        "SELECT * FROM forward_decisions_v2 WHERE status='VALID' AND strategy!='NO_TRADE'"
    ).fetchall()
    for decision in decisions:
        entry_batch = by_id.get(int(decision["batch_id"]))
        if entry_batch is None:
            continue
        entry_at = iso(entry_batch["completed_at"])
        legs = json.loads(decision["legs_json"])
        entry = quote_values(shadow, int(entry_batch["id"]), legs)
        if entry is None:
            continue
        output.execute("UPDATE forward_decisions_v2 SET entry_mid=? WHERE id=?", (entry[0], decision["id"]))
        for horizon in (5, 15, 30, 60):
            future = next(
                (batch for batch in batches if iso(batch["completed_at"]) >= entry_at + timedelta(minutes=horizon)), None
            )
            if future is None:
                continue
            values = quote_values(shadow, int(future["id"]), legs)
            if values is None:
                continue
            excursions: list[float] = []
            excursion_batches: list[int] = []
            for excursion_batch in batches:
                elapsed = (iso(excursion_batch["completed_at"]) - entry_at).total_seconds() / 60
                if not 0 < elapsed <= horizon:
                    continue
                excursion = quote_values(shadow, int(excursion_batch["id"]), legs)
                if excursion is not None:
                    excursions.append(excursion[1] - float(decision["entry_executable"]))
                    excursion_batches.append(int(excursion_batch["id"]))
            midpoint_pnl = values[0] - entry[0]
            conservative = values[1] - float(decision["entry_executable"])
            scoring_at = datetime.now(UTC).isoformat()
            provenance = {
                "entry_batch_id": int(entry_batch["id"]), "entry_available_at": entry_batch["completed_at"],
                "exit_batch_id": int(future["id"]), "exit_available_at": future["completed_at"],
                "horizon_minutes": horizon, "excursion_batch_ids": excursion_batches,
                "entry_option_snapshots": _leg_provenance(shadow, int(entry_batch["id"]), type("CandidateRef", (), {"legs": legs})()),
                "exit_option_snapshots": _leg_provenance(shadow, int(future["id"]), type("CandidateRef", (), {"legs": legs})()),
                "latest_excursion_minutes": max(
                    ((iso(by_id[item]["completed_at"]) - entry_at).total_seconds() / 60 for item in excursion_batches),
                    default=None,
                ),
            }
            output.execute(
                """INSERT OR REPLACE INTO forward_outcomes_v2(
                decision_id,horizon,exit_batch_id,exit_available_at,scoring_available_at,midpoint_pnl,
                market_move_pnl,entry_crossing_cost,exit_crossing_cost,conservative_pnl,mfe,mae,provenance_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    decision["id"], horizon, future["id"], future["completed_at"], scoring_at,
                    midpoint_pnl, midpoint_pnl, float(decision["entry_crossing_cost"]), values[2],
                    conservative, max(excursions) if excursions else None,
                    min(excursions) if excursions else None, canonical_json(provenance),
                ),
            )


def leaderboard_v2(output: sqlite3.Connection, manifest: dict[str, Any], path: Path) -> dict[str, Any]:
    board = []
    definitions = manifest["candidates"] + [
        {"id": "MOMENTUM", "name": "simple_momentum"},
        {"id": "REVERSION", "name": "simple_mean_reversion"}, {"id": "CASH", "name": "cash"},
    ]
    for definition in definitions:
        decisions = output.execute(
            "SELECT * FROM forward_decisions_v2 WHERE candidate_id=?", (definition["id"],)
        ).fetchall()
        valid = [row for row in decisions if row["status"] == "VALID"]
        invalid = [row for row in decisions if row["status"] != "VALID"]
        intended = []
        for decision in valid:
            row = output.execute(
                "SELECT * FROM forward_outcomes_v2 WHERE decision_id=? AND horizon=?",
                (decision["id"], decision["intended_horizon"]),
            ).fetchone()
            if row:
                intended.append((decision, row))
        pnl = [float(row["conservative_pnl"]) for _, row in intended]
        per_symbol: defaultdict[str, float] = defaultdict(float)
        for decision, row in intended:
            per_symbol[decision["symbol"]] += float(row["conservative_pnl"])
        board.append(
            {
                "candidate_id": definition["id"], "name": definition["name"],
                "observations": len(decisions), "valid_observations": len(valid),
                "invalid_feature_vectors": len(invalid),
                "trades": sum(item["strategy"] != "NO_TRADE" for item in valid),
                "scored_trades": len(pnl), "total_conservative_pnl": sum(pnl),
                "mean": mean(pnl) if pnl else None, "median": median(pnl) if pnl else None,
                "positive_trade_rate": sum(value > 0 for value in pnl) / len(pnl) if pnl else None,
                "worst_trade": min(pnl, default=None),
                "crossing_cost": sum(
                    float(d["entry_crossing_cost"] or 0) + float(o["exit_crossing_cost"]) for d, o in intended
                ),
                "per_symbol": dict(per_symbol),
            }
        )
    payload = {
        "updated_at": datetime.now(UTC).isoformat(), "schema_version": FEATURE_SCHEMA_VERSION,
        "status": "POST_INCIDENT_V2_NOT_COMPARABLE_TO_SEP01", "leaderboard": board,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def run(
    shadow_path: Path, output_path: Path, manifest_path: Path, leaderboard_path: Path,
    start: str | None = None,
) -> dict[str, int]:
    manifest_text = manifest_path.read_text()
    manifest = json.loads(manifest_text)
    if manifest["status"] != "FROZEN" or len(manifest["candidates"]) != 5:
        raise RuntimeError("forward test requires exactly five frozen candidates")
    manifest_hash = hashlib.sha256(manifest_text.encode()).hexdigest()
    with sqlite3.connect(shadow_path) as shadow, sqlite3.connect(output_path) as output:
        shadow.row_factory = output.row_factory = sqlite3.Row
        init_integrity_schema(shadow)
        output.executescript(SCHEMA)
        session_start = start or manifest["forward_test"]["first_observation_not_before"]
        batches = shadow.execute(
            "SELECT * FROM capture_batches WHERE status='COMPLETE' AND completed_at>=? ORDER BY completed_at",
            (datetime.fromisoformat(session_start).astimezone(UTC).isoformat(),),
        ).fetchall()
        created = invalid_count = 0
        for batch in batches:
            underlyings = shadow.execute(
                "SELECT * FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch["id"],)
            ).fetchall()
            for row in underlyings:
                all_values, common_reasons, provenance = live_features_v2(shadow, batch, row)
                candidates = enumerate_state(shadow, batch, row)
                definitions = list(manifest["candidates"])
                for benchmark_id, source_id in (("MOMENTUM", "A"), ("REVERSION", "B")):
                    source = next(item for item in manifest["candidates"] if item["id"] == source_id)
                    definitions.append(
                        {**source, "id": benchmark_id,
                         "name": f"simple_{source['name'].replace('cost_filtered_', '')}",
                         "maximum_entry_crossing_cost": 4.0}
                    )
                definitions.append({"id": "CASH", "name": "cash", "holding_minutes": 5, "features": []})
                for definition in definitions:
                    required = list(definition.get("features", []))
                    # option_crossing_cost is candidate-derived and validated after construction.
                    required = [name for name in required if name != "option_crossing_cost"]
                    if definition["id"] == "C":
                        vector = [all_values.get(name) for name in definition["features"]]
                        if all(value is not None and math.isfinite(float(value)) for value in vector):
                            all_values["volatility_forecast"] = max(
                                0.0, model_predict(definition["parameters"], [float(value) for value in vector])
                            )
                        required.extend(["jsd", "atm_iv", "volatility_forecast"])
                    elif definition["id"] == "D":
                        required.extend(["jsd", "atm_iv"])
                    council_reason_prefixes = (
                        "MISSING_COUNCIL", "WRONG_AGENT", "WRONG_COUNCIL", "OPINION_",
                        "DUPLICATE_", "CONSENSUS_", "MALFORMED_COUNCIL", "CAUSALITY_COUNCIL",
                    )
                    relevant_reasons = common_reasons if any(
                        name in required for name in ("disagreement", "entropy", "jsd")
                    ) else [reason for reason in common_reasons if not reason.startswith(council_reason_prefixes)]
                    result = validate_feature_vector(
                        candidate_id=definition["id"], required_features=required, values=all_values,
                        provenance=provenance,
                        council_reasons=relevant_reasons,
                    )
                    signal = None
                    selected = None
                    reason = ""
                    if result.valid and definition["id"] != "CASH":
                        evaluation_definition = definition
                        if definition["id"] in {"MOMENTUM", "REVERSION"}:
                            evaluation_definition = {**definition, "id": "A" if definition["id"] == "MOMENTUM" else "B"}
                        signal, selected, reason = evaluate_definition(evaluation_definition, all_values, candidates)
                    elif definition["id"] == "CASH":
                        signal, reason = 0.0, "CASH_CONTROL"
                    else:
                        reason = "INVALID_FEATURE_VECTOR"
                        invalid_count += 1
                    result.provenance.update(
                        {
                            "observation_id": f"{batch['id']}:{row['symbol']}:{definition['id']}",
                            "candidate_version": manifest.get("version", manifest.get("created_at", "frozen-v1")),
                            "candidate_hash": hashlib.sha256(
                                canonical_json(definition).encode()
                            ).hexdigest(),
                            "decision_timestamp": datetime.now(UTC).isoformat(),
                            "entry_option_snapshots": _leg_provenance(shadow, int(batch["id"]), selected),
                        }
                    )
                    _insert_decision(
                        output, batch=batch, symbol=row["symbol"], definition=definition, result=result,
                        manifest_hash=manifest_hash, signal=signal, candidate=selected, reason=reason,
                        benchmark=definition["id"] in {"MOMENTUM", "REVERSION", "CASH"},
                    )
                    record_integrity_event(
                        shadow, batch_id=int(batch["id"]), symbol=row["symbol"],
                        candidate_id=definition["id"], result=result,
                    )
                    created += 1
        score_v2(output, shadow, batches)
        output.commit()
        shadow.commit()
        leaderboard_v2(output, manifest, leaderboard_path)
        return {"complete_batches": len(batches), "decisions_considered": created, "invalid_feature_vectors": invalid_count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--database", type=Path, default=Path("data/forward_test_v2.db"))
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-01.json"))
    parser.add_argument("--leaderboard", type=Path, default=Path("artifacts/forward_test/leaderboard_v2.json"))
    parser.add_argument("--start")
    args = parser.parse_args()
    print(json.dumps(run(args.shadow, args.database, args.manifest, args.leaderboard, args.start), sort_keys=True))


if __name__ == "__main__":
    main()
