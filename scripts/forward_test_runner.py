#!/usr/bin/env python3
"""Evaluate the five preregistered systems on sealed shared shadow batches."""

from __future__ import annotations

import argparse
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

if __package__:
    from scripts.quant_research import Candidate, enumerate_state, iso
else:
    from quant_research import Candidate, enumerate_state, iso

NY = ZoneInfo("America/New_York")
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS forward_decisions (
 id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, decision_available_at TEXT NOT NULL,
 symbol TEXT NOT NULL, candidate_id TEXT NOT NULL, candidate_name TEXT NOT NULL,
 benchmark INTEGER NOT NULL DEFAULT 0, signal REAL, strategy TEXT NOT NULL,
 intended_horizon INTEGER NOT NULL, no_trade_reason TEXT, max_loss REAL,
 entry_mid REAL, entry_executable REAL, entry_crossing_cost REAL,
 legs_json TEXT NOT NULL, feature_json TEXT NOT NULL, manifest_hash TEXT NOT NULL,
 UNIQUE(batch_id,symbol,candidate_id)
);
CREATE TABLE IF NOT EXISTS forward_outcomes (
 decision_id INTEGER NOT NULL, horizon INTEGER NOT NULL, exit_batch_id INTEGER NOT NULL,
 exit_available_at TEXT NOT NULL, midpoint_pnl REAL NOT NULL, market_move_pnl REAL NOT NULL,
 entry_crossing_cost REAL NOT NULL, exit_crossing_cost REAL NOT NULL,
 conservative_pnl REAL NOT NULL, mfe REAL, mae REAL,
 PRIMARY KEY(decision_id,horizon), FOREIGN KEY(decision_id) REFERENCES forward_decisions(id)
);
"""


def model_predict(parameters: dict[str, Any], values: list[float]) -> float:
    vector = np.asarray(values, dtype=float)
    center, scale, weights = (np.asarray(parameters[key], dtype=float) for key in ("mean", "scale", "weights"))
    return float(np.r_[1.0, (vector - center) / scale] @ weights)


def live_features(db: sqlite3.Connection, batch: sqlite3.Row, row: sqlite3.Row) -> dict[str, float]:
    bars = json.loads(row["bars_json"])
    closes = np.asarray([float(item["c"]) for item in bars], dtype=float)
    volumes = np.asarray([float(item["v"]) for item in bars], dtype=float)
    returns = closes[1:] / closes[:-1] - 1
    recent = bars[-1]
    typical = np.asarray([(float(item["h"]) + float(item["l"]) + float(item["c"])) / 3 for item in bars[-120:]])
    recent_volume = volumes[-len(typical):]
    vwap = float(np.sum(typical * recent_volume) / max(np.sum(recent_volume), 1))
    payload_row = db.execute(
        "SELECT payload_json FROM shadow_results WHERE batch_id=? AND symbol=? AND config_id='production'",
        (batch["id"], row["symbol"]),
    ).fetchone()
    consensus = json.loads(payload_row[0])["consensus"] if payload_row else {}
    options = db.execute(
        "SELECT implied_volatility,strike,option_type,bid,ask FROM option_snapshots WHERE batch_id=? AND underlying=? AND implied_volatility IS NOT NULL",
        (batch["id"], row["symbol"]),
    ).fetchall()
    spot = float(row["trade_price"])
    atm = sorted(options, key=lambda option: abs(float(option["strike"]) - spot))[:30]
    atm_iv = median(float(option["implied_volatility"]) for option in atm) if atm else 0.0
    local = iso(batch["completed_at"]).astimezone(NY)
    minute = local.hour * 60 + local.minute - 570
    return {
        "return_5m": float(row["return_5m"] or 0), "return_15m": float(row["return_15m"] or 0),
        "return_30m": float(row["return_30m"] or 0), "return_60m": float(row["return_60m"] or 0),
        "rv_15m": float(math.sqrt(np.sum(np.square(returns[-15:])))),
        "rv_60m": float(math.sqrt(np.sum(np.square(returns[-60:])))),
        "rv_1d": float(row["realized_volatility"] or 0.2) / math.sqrt(252),
        "range_pct": (float(recent["h"]) - float(recent["l"])) / float(recent["c"]),
        "volume_ratio": float(volumes[-1] / max(np.median(volumes[-60:]), 1)),
        "vwap_deviation": spot / vwap - 1, "disagreement": float(consensus.get("disagreement", 0)),
        "entropy": float(consensus.get("entropy", 0)), "minute_sin": math.sin(2 * math.pi * minute / 390),
        "minute_cos": math.cos(2 * math.pi * minute / 390), "atm_iv": atm_iv, "spot": spot,
        "consensus_direction": float(consensus.get("expected_direction", 0)),
    }


def structure(records: list[Candidate], name: str, maximum_crossing: float) -> Candidate | None:
    pool = [item for item in records if item.structure == name and item.rank == "min_crossing" and item.crossing_cost <= maximum_crossing]
    return min(pool, key=lambda item: (item.crossing_cost, item.worst_spread_pct, item.max_loss), default=None)


def evaluate_definition(definition: dict[str, Any], features: dict[str, float], records: list[Candidate]) -> tuple[float, Candidate | None, str]:
    candidate_id = definition["id"]
    crossing = float(definition["maximum_entry_crossing_cost"])
    direction = 0.0
    if candidate_id in {"A", "B"}:
        lookback = int(definition["historical"]["lookback"])
        raw = features[f"return_{lookback}m"]
        threshold = 0.5 * features["rv_1d"] * math.sqrt(lookback / 390)
        direction = math.copysign(1.0, raw) if abs(raw) >= threshold else 0.0
        if candidate_id == "B":
            direction *= -1
    elif candidate_id == "C":
        vector = [features[name] for name in definition["features"]]
        forecast = max(0.0, model_predict(definition["parameters"], vector))
        implied_move = features["atm_iv"] * math.sqrt(definition["holding_minutes"] / (252 * 390))
        if implied_move > 0 and forecast / implied_move >= 1.10:
            selected = structure(records, "LONG_STRADDLE", crossing)
            return forecast, selected, "NO_LIQUID_LONG_STRADDLE" if selected is None else ""
        if forecast > 0 and implied_move / forecast >= 1.25:
            selected = structure(records, "IRON_CONDOR", crossing)
            return -forecast, selected, "NO_LIQUID_IRON_CONDOR" if selected is None else ""
        return forecast, None, "VOLATILITY_EDGE_BELOW_THRESHOLD"
    elif candidate_id == "D":
        vector = [features[name] for name in definition["features"]]
        prediction = model_predict(definition["parameters"], vector)
        direction = math.copysign(1.0, prediction) if prediction else 0.0
    elif candidate_id == "E":
        zscore = features["vwap_deviation"] / max(features["rv_1d"], 1e-9)
        direction = -math.copysign(1.0, zscore) if abs(zscore) >= float(definition["historical"]["threshold"]) else 0.0
    if not direction:
        return 0.0, None, "SIGNAL_BELOW_THRESHOLD"
    selected = structure(records, "BULL_CALL_SPREAD" if direction > 0 else "BEAR_PUT_SPREAD", crossing)
    if selected is None:
        return direction, None, "NO_LIQUID_DIRECTIONAL_STRUCTURE"
    if candidate_id == "D":
        gross_proxy = abs(prediction) * features["spot"] * 50
        if gross_proxy <= 1.25 * selected.crossing_cost * 2:
            return prediction, None, "PREDICTED_EDGE_DOES_NOT_CLEAR_COST"
        return prediction, selected, ""
    return direction, selected, ""


def entry_midpoint(shadow: sqlite3.Connection, candidate: Candidate) -> float:
    total = 0.0
    for contract, sign in candidate.legs:
        row = shadow.execute(
            "SELECT mid FROM option_snapshots WHERE batch_id=? AND contract_symbol=?", (candidate.batch_id, contract)
        ).fetchone()
        total += sign * float(row["mid"]) * 100
    return total


def insert_decision(output: sqlite3.Connection, batch: sqlite3.Row, symbol: str, definition: dict[str, Any], signal: float, candidate: Candidate | None, reason: str, features: dict[str, float], manifest_hash: str, benchmark: bool = False) -> None:
    output.execute(
        """INSERT OR IGNORE INTO forward_decisions(
        batch_id,decision_available_at,symbol,candidate_id,candidate_name,benchmark,signal,strategy,
        intended_horizon,no_trade_reason,max_loss,entry_mid,entry_executable,entry_crossing_cost,
        legs_json,feature_json,manifest_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            batch["id"], batch["completed_at"], symbol, definition["id"], definition["name"], benchmark,
            signal, candidate.structure if candidate else "NO_TRADE", definition["holding_minutes"], reason or None,
            candidate.max_loss if candidate else None, None, candidate.entry_value if candidate else None,
            candidate.crossing_cost if candidate else None, json.dumps(candidate.legs if candidate else []),
            json.dumps(features, separators=(",", ":")), manifest_hash,
        ),
    )


def quote_values(shadow: sqlite3.Connection, batch_id: int, legs: list[list[Any]]) -> tuple[float, float, float] | None:
    midpoint = executable = crossing = 0.0
    for contract, sign in legs:
        row = shadow.execute(
            "SELECT bid,ask,mid,bid_size,ask_size FROM option_snapshots WHERE batch_id=? AND contract_symbol=?",
            (batch_id, contract),
        ).fetchone()
        if row is None or not (float(row["bid"] or 0) > 0 and float(row["ask"] or 0) > float(row["bid"] or 0)) or min(float(row["bid_size"] or 0), float(row["ask_size"] or 0)) < 1:
            return None
        midpoint += sign * float(row["mid"]) * 100
        executable += sign * float(row["bid"] if sign > 0 else row["ask"]) * 100
        crossing += (float(row["ask"]) - float(row["bid"])) * 50
    return midpoint, executable, crossing


def score(output: sqlite3.Connection, shadow: sqlite3.Connection, batches: list[sqlite3.Row]) -> None:
    by_id = {int(batch["id"]): batch for batch in batches}
    for decision in output.execute("SELECT * FROM forward_decisions WHERE strategy!='NO_TRADE'").fetchall():
        entry_batch = by_id.get(int(decision["batch_id"]))
        if entry_batch is None:
            continue
        entry_at = iso(entry_batch["completed_at"])
        legs = json.loads(decision["legs_json"])
        entry = quote_values(shadow, int(entry_batch["id"]), legs)
        if entry is None:
            continue
        output.execute("UPDATE forward_decisions SET entry_mid=? WHERE id=?", (entry[0], decision["id"]))
        excursions: list[float] = []
        for batch in batches:
            elapsed = (iso(batch["completed_at"]) - entry_at).total_seconds() / 60
            if not 0 < elapsed <= 60:
                continue
            values = quote_values(shadow, int(batch["id"]), legs)
            if values:
                excursions.append(values[1] - float(decision["entry_executable"]))
        targets: list[tuple[int, sqlite3.Row]] = []
        for horizon in (5, 15, 30, 60):
            future = next((batch for batch in batches if iso(batch["completed_at"]) >= entry_at + timedelta(minutes=horizon)), None)
            if future is None:
                continue
            targets.append((horizon, future))
        session_date = entry_at.astimezone(NY).date()
        now_ny = datetime.now(UTC).astimezone(NY)
        session_closed = session_date < now_ny.date() or (session_date == now_ny.date() and now_ny.hour >= 16)
        if session_closed:
            end_of_session = [
                batch for batch in batches
                if iso(batch["completed_at"]).astimezone(NY).date() == session_date and iso(batch["completed_at"]) > entry_at
            ]
            if end_of_session:
                targets.append((0, end_of_session[-1]))
        for horizon, future in targets:
            values = quote_values(shadow, int(future["id"]), legs)
            if values is None:
                continue
            midpoint_pnl = values[0] - entry[0]
            conservative = values[1] - float(decision["entry_executable"])
            output.execute(
                """INSERT OR REPLACE INTO forward_outcomes(decision_id,horizon,exit_batch_id,exit_available_at,
                midpoint_pnl,market_move_pnl,entry_crossing_cost,exit_crossing_cost,conservative_pnl,mfe,mae)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    decision["id"], horizon, future["id"], future["completed_at"], midpoint_pnl, midpoint_pnl,
                    float(decision["entry_crossing_cost"]), values[2], conservative,
                    max(excursions) if excursions else None, min(excursions) if excursions else None,
                ),
            )


def leaderboard(output: sqlite3.Connection, manifest: dict[str, Any], path: Path) -> None:
    board = []
    definitions = manifest["candidates"] + [
        {"id": "MOMENTUM", "name": "simple_momentum"}, {"id": "REVERSION", "name": "simple_mean_reversion"},
        {"id": "CASH", "name": "cash"},
    ]
    for definition in definitions:
        decisions = output.execute("SELECT * FROM forward_decisions WHERE candidate_id=?", (definition["id"],)).fetchall()
        intended = []
        for decision in decisions:
            row = output.execute(
                "SELECT * FROM forward_outcomes WHERE decision_id=? AND horizon=?", (decision["id"], decision["intended_horizon"])
            ).fetchone()
            if row:
                intended.append((decision, row))
        values = [float(row["conservative_pnl"]) for _, row in intended]
        mfe_values = [float(row["mfe"]) for _, row in intended if row["mfe"] is not None]
        mae_values = [float(row["mae"]) for _, row in intended if row["mae"] is not None]
        per_symbol = defaultdict(float)
        per_strategy = defaultdict(float)
        for decision, row in intended:
            per_symbol[decision["symbol"]] += float(row["conservative_pnl"])
            per_strategy[decision["strategy"]] += float(row["conservative_pnl"])
        board.append({
            "candidate_id": definition["id"], "name": definition["name"], "signals": sum(d["signal"] not in (None, 0) for d in decisions),
            "trades": sum(d["strategy"] != "NO_TRADE" for d in decisions), "scored_trades": len(values),
            "positive_trades": sum(value > 0 for value in values), "total_conservative_pnl": sum(values),
            "mean": mean(values) if values else None, "median": median(values) if values else None,
            "mfe": mean(mfe_values) if mfe_values else None, "mae": mean(mae_values) if mae_values else None,
            "worst_trade": min(values, default=None),
            "crossing_cost": sum(float(d["entry_crossing_cost"] or 0) + float(r["exit_crossing_cost"]) for d, r in intended),
            "pnl_per_max_risk": sum(values) / sum(float(d["max_loss"] or 0) for d, _ in intended) if intended else None,
            "per_symbol": dict(per_symbol), "per_strategy": dict(per_strategy),
            "horizon_breakdown": {
                ("EOD" if horizon == 0 else str(horizon)): {
                    "scored": len(rows := output.execute(
                        """SELECT o.conservative_pnl,o.midpoint_pnl,o.entry_crossing_cost,o.exit_crossing_cost
                        FROM forward_outcomes o JOIN forward_decisions d ON d.id=o.decision_id
                        WHERE d.candidate_id=? AND o.horizon=?""", (definition["id"], horizon)
                    ).fetchall()),
                    "conservative_pnl": sum(float(row["conservative_pnl"]) for row in rows),
                    "midpoint_pnl": sum(float(row["midpoint_pnl"]) for row in rows),
                    "entry_crossing_cost": sum(float(row["entry_crossing_cost"]) for row in rows),
                    "exit_crossing_cost": sum(float(row["exit_crossing_cost"]) for row in rows),
                }
                for horizon in (5, 15, 30, 60, 0)
            },
        })
    payload = {"updated_at": datetime.now(UTC).isoformat(), "sealed_session": manifest["sealed_session"], "leaderboard": board}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def run(shadow_path: Path, output_path: Path, manifest_path: Path, leaderboard_path: Path, start: str | None = None) -> dict[str, int]:
    manifest_text = manifest_path.read_text()
    manifest = json.loads(manifest_text)
    if manifest["status"] != "FROZEN" or len(manifest["candidates"]) != 5:
        raise RuntimeError("forward test requires exactly five frozen candidates")
    manifest_hash = __import__("hashlib").sha256(manifest_text.encode()).hexdigest()
    with sqlite3.connect(shadow_path) as shadow, sqlite3.connect(output_path) as output:
        shadow.row_factory = output.row_factory = sqlite3.Row
        output.executescript(SCHEMA)
        session_start = start or manifest["forward_test"]["first_observation_not_before"]
        batches = shadow.execute(
            "SELECT * FROM capture_batches WHERE status='COMPLETE' AND completed_at>=? ORDER BY completed_at",
            (datetime.fromisoformat(session_start).astimezone(UTC).isoformat(),),
        ).fetchall()
        created = 0
        for batch in batches:
            underlyings = shadow.execute("SELECT * FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch["id"],)).fetchall()
            for row in underlyings:
                features = live_features(shadow, batch, row)
                candidates = enumerate_state(shadow, batch, row)
                for definition in manifest["candidates"]:
                    before = output.total_changes
                    signal, candidate, reason = evaluate_definition(definition, features, candidates)
                    insert_decision(output, batch, row["symbol"], definition, signal, candidate, reason, features, manifest_hash)
                    created += output.total_changes - before
                for benchmark_id, source_id in (("MOMENTUM", "A"), ("REVERSION", "B")):
                    source = next(item for item in manifest["candidates"] if item["id"] == source_id)
                    benchmark = {**source, "id": benchmark_id, "name": f"simple_{source['name'].replace('cost_filtered_', '')}", "maximum_entry_crossing_cost": 4.0}
                    signal, candidate, reason = evaluate_definition({**benchmark, "id": source_id}, features, candidates)
                    insert_decision(output, batch, row["symbol"], benchmark, signal, candidate, reason, features, manifest_hash, True)
                cash = {"id": "CASH", "name": "cash", "holding_minutes": 5}
                insert_decision(output, batch, row["symbol"], cash, 0, None, "CASH_CONTROL", features, manifest_hash, True)
        score(output, shadow, batches)
        output.commit()
        leaderboard(output, manifest, leaderboard_path)
        return {"complete_batches": len(batches), "new_decisions": created}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--database", type=Path, default=Path("data/forward_test.db"))
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-01.json"))
    parser.add_argument("--leaderboard", type=Path, default=Path("artifacts/forward_test/live_leaderboard.json"))
    parser.add_argument("--start", help="explicit development-only cutoff; sealed session uses the manifest default")
    args = parser.parse_args()
    print(json.dumps(run(args.shadow, args.database, args.manifest, args.leaderboard, args.start)))


if __name__ == "__main__":
    main()
