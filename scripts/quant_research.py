#!/usr/bin/env python3
"""Run a reproducible, read-only, cost-aware option research tournament."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any

import numpy as np

SEED = 20260901
SUPPORTED = ("BULL_CALL_SPREAD", "BEAR_PUT_SPREAD", "IRON_CONDOR", "LONG_STRADDLE")
FEATURES = (
    "return_5m",
    "return_15m",
    "return_30m",
    "return_60m",
    "realized_volatility",
    "volume_surprise",
    "underlying_spread_pct",
    "atm_iv",
    "iv_rv_ratio",
    "put_call_skew",
    "term_slope",
    "chain_spread",
    "consensus_direction",
    "disagreement",
    "entropy",
    "minutes_from_open",
)


@dataclass(frozen=True)
class Split:
    train: tuple[int, ...]
    validation: tuple[int, ...]
    holdout: tuple[int, ...]
    purged: tuple[int, ...]
    embargoed: tuple[int, ...]


@dataclass(frozen=True)
class Candidate:
    batch_id: int
    symbol: str
    completed_at: str
    structure: str
    expiry: str
    dte: int
    max_loss: float
    entry_value: float
    crossing_cost: float
    worst_spread_pct: float
    min_volume: float
    rank: str
    legs: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class System:
    experiment_id: str
    parent: str | None
    track: str
    name: str
    hypothesis: str
    motivation: str
    signal: str
    target: str
    feature_set: tuple[str, ...]
    model: str
    parameter: float
    horizon: int = 5


def iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def quote_ok(row: sqlite3.Row, available: datetime, max_spread: float = 0.15) -> bool:
    if not row["quote_timestamp"] or not (float(row["bid"] or 0) > 0 and float(row["ask"] or 0) > float(row["bid"] or 0)):
        return False
    mid = (float(row["bid"]) + float(row["ask"])) / 2
    age = (available - iso(row["quote_timestamp"])).total_seconds()
    return (
        0 <= age <= 180
        and min(float(row["bid_size"] or 0), float(row["ask_size"] or 0)) >= 1
        and float(row["volume"] or 0) >= 1
        and (float(row["ask"]) - float(row["bid"])) / mid <= max_spread
    )


def chronological_split(batch_ids: list[int]) -> Split:
    if len(batch_ids) < 24:
        raise ValueError("the initial leakage-safe split requires 24 complete batches")
    return Split(tuple(batch_ids[:11]), tuple(batch_ids[13:16]), tuple(batch_ids[18:22]), tuple(batch_ids[11:13]), tuple(batch_ids[16:18]))


def _leg_metrics(legs: list[tuple[sqlite3.Row, int]]) -> tuple[float, float, float, float]:
    entry = sum(sign * float(row["ask"] if sign > 0 else row["bid"]) * 100 for row, sign in legs)
    crossing = sum((float(row["ask"]) - float(row["bid"])) * 50 for row, _ in legs)
    worst = max((float(row["ask"]) - float(row["bid"])) / float(row["mid"]) for row, _ in legs)
    volume = min(float(row["volume"] or 0) for row, _ in legs)
    return entry, crossing, worst, volume


def _candidate(batch: sqlite3.Row, symbol: str, structure: str, expiry: str, max_loss: float, legs: list[tuple[sqlite3.Row, int]], rank: str) -> Candidate:
    entry, crossing, worst, volume = _leg_metrics(legs)
    return Candidate(
        int(batch["id"]), symbol, str(batch["completed_at"]), structure, expiry,
        (datetime.fromisoformat(expiry).date() - iso(batch["completed_at"]).date()).days,
        round(max_loss, 8), round(entry, 8), round(crossing, 8), worst, volume, rank,
        tuple((str(row["contract_symbol"]), sign) for row, sign in legs),
    )


def enumerate_state(db: sqlite3.Connection, batch: sqlite3.Row, underlying: sqlite3.Row) -> list[Candidate]:
    available = iso(batch["completed_at"])
    symbol, spot = str(underlying["symbol"]), float(underlying["trade_price"])
    rows = db.execute("SELECT * FROM option_snapshots WHERE batch_id=? AND underlying=?", (batch["id"], symbol)).fetchall()
    valid = [row for row in rows if quote_ok(row, available)]
    by_expiry: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in valid:
        dte = (datetime.fromisoformat(row["expiry"]).date() - available.date()).days
        if 7 <= dte <= 35 and 0.85 <= float(row["strike"]) / spot <= 1.15:
            by_expiry[str(row["expiry"])].append(row)
    generated: list[Candidate] = []
    for expiry, chain in by_expiry.items():
        calls = sorted((r for r in chain if r["option_type"] == "call"), key=lambda r: float(r["strike"]))
        puts = sorted((r for r in chain if r["option_type"] == "put"), key=lambda r: float(r["strike"]))
        atm_calls = sorted(calls, key=lambda r: (abs(float(r["strike"]) - spot), float(r["spread_pct"] or 99)))[:8]
        atm_puts = sorted(puts, key=lambda r: (abs(float(r["strike"]) - spot), float(r["spread_pct"] or 99)))[:8]
        for long in atm_calls:
            shorts = [r for r in calls if 0 < float(r["strike"]) - float(long["strike"]) <= 5]
            for short in sorted(shorts, key=lambda r: (float(r["spread_pct"] or 99), -float(r["volume"] or 0)))[:8]:
                legs = [(long, 1), (short, -1)]
                entry, crossing, _, _ = _leg_metrics(legs)
                if 0 < entry <= 500:
                    generated.append(_candidate(batch, symbol, "BULL_CALL_SPREAD", expiry, entry, legs, "raw"))
        for long in atm_puts:
            shorts = [r for r in puts if 0 < float(long["strike"]) - float(r["strike"]) <= 5]
            for short in sorted(shorts, key=lambda r: (float(r["spread_pct"] or 99), -float(r["volume"] or 0)))[:8]:
                legs = [(long, 1), (short, -1)]
                entry, crossing, _, _ = _leg_metrics(legs)
                if 0 < entry <= 500:
                    generated.append(_candidate(batch, symbol, "BEAR_PUT_SPREAD", expiry, entry, legs, "raw"))
        puts_by_strike = {float(r["strike"]): r for r in puts}
        for call in atm_calls:
            put = puts_by_strike.get(float(call["strike"]))
            if put:
                legs = [(call, 1), (put, 1)]
                entry, _, _, _ = _leg_metrics(legs)
                if 0 < entry <= 500:
                    generated.append(_candidate(batch, symbol, "LONG_STRADDLE", expiry, entry, legs, "raw"))
        short_puts = sorted(
            (r for r in puts if r["delta"] is not None and 0.10 <= abs(float(r["delta"])) <= 0.40 and float(r["strike"]) < spot),
            key=lambda r: (float(r["spread_pct"] or 99), abs(abs(float(r["delta"])) - 0.25)),
        )[:10]
        short_calls = sorted(
            (r for r in calls if r["delta"] is not None and 0.10 <= abs(float(r["delta"])) <= 0.40 and float(r["strike"]) > spot),
            key=lambda r: (float(r["spread_pct"] or 99), abs(abs(float(r["delta"])) - 0.25)),
        )[:10]
        put_sides: list[tuple[sqlite3.Row, sqlite3.Row]] = []
        call_sides: list[tuple[sqlite3.Row, sqlite3.Row]] = []
        for short in short_puts:
            wings = [r for r in puts if 0 < float(short["strike"]) - float(r["strike"]) <= 5]
            put_sides.extend((short, wing) for wing in sorted(wings, key=lambda r: float(r["spread_pct"] or 99))[:3])
        for short in short_calls:
            wings = [r for r in calls if 0 < float(r["strike"]) - float(short["strike"]) <= 5]
            call_sides.extend((short, wing) for wing in sorted(wings, key=lambda r: float(r["spread_pct"] or 99))[:3])
        for short_put, long_put in put_sides[:18]:
            for short_call, long_call in call_sides[:18]:
                legs = [(long_put, 1), (short_put, -1), (short_call, -1), (long_call, 1)]
                entry, _, _, _ = _leg_metrics(legs)
                width = max(float(short_put["strike"]) - float(long_put["strike"]), float(long_call["strike"]) - float(short_call["strike"]))
                max_loss = width * 100 + entry
                if entry < 0 and 0 < max_loss <= 500 and -entry < width * 100:
                    generated.append(_candidate(batch, symbol, "IRON_CONDOR", expiry, max_loss, legs, "raw"))
    selected: list[Candidate] = []
    for structure in SUPPORTED:
        pool = [item for item in generated if item.structure == structure]
        rankings: dict[str, Callable[[Candidate], tuple[float, ...]]] = {
            "min_crossing": lambda x: (x.crossing_cost, x.worst_spread_pct, x.max_loss),
            "max_liquidity": lambda x: (-x.min_volume, x.worst_spread_pct, x.crossing_cost),
            "risk_adjusted": lambda x: (
                -(max(0.0, -x.entry_value) / x.max_loss) if x.structure == "IRON_CONDOR" else x.entry_value / max(x.max_loss, 1),
                x.crossing_cost,
            ),
        }
        for rank, key in rankings.items():
            if pool:
                selected.append(Candidate(**{**asdict(min(pool, key=key)), "rank": rank}))
    unique = {(item.structure, item.rank, item.legs): item for item in selected}
    return list(unique.values())


def state_features(db: sqlite3.Connection, batch: sqlite3.Row, row: sqlite3.Row) -> dict[str, float]:
    options = db.execute("SELECT * FROM option_snapshots WHERE batch_id=? AND underlying=?", (batch["id"], row["symbol"])).fetchall()
    spot = float(row["trade_price"])
    atm = sorted((o for o in options if o["implied_volatility"]), key=lambda o: abs(float(o["strike"]) - spot))[:30]
    calls = [float(o["implied_volatility"]) for o in atm if o["option_type"] == "call"]
    puts = [float(o["implied_volatility"]) for o in atm if o["option_type"] == "put"]
    near = [o for o in options if o["implied_volatility"] and abs(float(o["strike"]) / spot - 1) <= 0.03]
    expiries: dict[str, list[float]] = defaultdict(list)
    for option in near:
        expiries[str(option["expiry"])].append(float(option["implied_volatility"]))
    terms = sorted((key, mean(values)) for key, values in expiries.items())
    atm_iv = median([float(o["implied_volatility"]) for o in atm]) if atm else float(row["realized_volatility"] or 0)
    rv = max(float(row["realized_volatility"] or 0), 1e-6)
    payload_row = db.execute("SELECT payload_json FROM shadow_results WHERE batch_id=? AND symbol=? AND config_id='production'", (batch["id"], row["symbol"])).fetchone()
    consensus = json.loads(payload_row[0])["consensus"] if payload_row else {}
    captured = iso(batch["completed_at"])
    open_at = captured.replace(hour=13, minute=30, second=0, microsecond=0)
    return {
        "return_5m": float(row["return_5m"] or 0), "return_15m": float(row["return_15m"] or 0),
        "return_30m": float(row["return_30m"] or 0), "return_60m": float(row["return_60m"] or 0),
        "realized_volatility": rv, "volume_surprise": float(row["minute_volume"] or 0) / max(float(row["daily_volume"] or 1), 1),
        "underlying_spread_pct": float(row["spread_pct"] or 0), "atm_iv": atm_iv, "iv_rv_ratio": atm_iv / rv,
        "put_call_skew": (median(puts) - median(calls)) if puts and calls else 0,
        "term_slope": terms[-1][1] - terms[0][1] if len(terms) > 1 else 0,
        "chain_spread": median([float(o["spread_pct"]) for o in atm if o["spread_pct"] is not None]) if atm else 1,
        "consensus_direction": float(consensus.get("expected_direction", 0)), "disagreement": float(consensus.get("disagreement", 0)),
        "entropy": float(consensus.get("entropy", 0)), "minutes_from_open": (captured - open_at).total_seconds() / 60,
    }


def outcome(db: sqlite3.Connection, candidate: Candidate, future_batch: sqlite3.Row, extra_slippage: float = 0.0) -> float | None:
    available = iso(future_batch["completed_at"])
    value, extra = 0.0, 0.0
    for contract, sign in candidate.legs:
        row = db.execute("SELECT * FROM option_snapshots WHERE batch_id=? AND contract_symbol=?", (future_batch["id"], contract)).fetchone()
        if row is None or not quote_ok(row, available, max_spread=1.0):
            return None
        value += sign * float(row["bid"] if sign > 0 else row["ask"]) * 100
        extra += (float(row["ask"]) - float(row["bid"])) * 100 * extra_slippage
    extra += candidate.crossing_cost * 2 * extra_slippage
    return value - candidate.entry_value - extra


def future_batch(batches: list[sqlite3.Row], candidate: Candidate, minutes: int) -> sqlite3.Row | None:
    cutoff = iso(candidate.completed_at) + timedelta(minutes=minutes)
    return next((batch for batch in batches if iso(batch["completed_at"]) >= cutoff), None)


def load_dataset(db: sqlite3.Connection, cutoff: str | None = None) -> tuple[list[sqlite3.Row], dict[tuple[int, str], dict[str, float]], list[dict[str, Any]]]:
    batches = db.execute(
        "SELECT * FROM capture_batches WHERE status='COMPLETE' AND (? IS NULL OR completed_at<=?) ORDER BY completed_at",
        (cutoff, cutoff),
    ).fetchall()
    features: dict[tuple[int, str], dict[str, float]] = {}
    records: list[dict[str, Any]] = []
    for batch in batches:
        for underlying in db.execute("SELECT * FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch["id"],)).fetchall():
            key = (int(batch["id"]), str(underlying["symbol"]))
            features[key] = state_features(db, batch, underlying)
            for candidate in enumerate_state(db, batch, underlying):
                record = {"candidate": candidate}
                for horizon in (5, 15, 30, 60):
                    future = future_batch(batches, candidate, horizon)
                    record[f"pnl_{horizon}"] = outcome(db, candidate, future) if future else None
                    record[f"stress_{horizon}"] = outcome(db, candidate, future, 0.25) if future else None
                    record[f"adverse_{horizon}"] = outcome(db, candidate, future, 0.50) if future else None
                records.append(record)
    return batches, features, records


def pick(records: list[dict[str, Any]], batch: int, symbol: str, structure: str, rank: str = "min_crossing") -> dict[str, Any] | None:
    pool = [r for r in records if r["candidate"].batch_id == batch and r["candidate"].symbol == symbol and r["candidate"].structure == structure]
    return next((r for r in pool if r["candidate"].rank == rank), pool[0] if pool else None)


def rule_decisions(system: System, batch_ids: tuple[int, ...], features: dict[tuple[int, str], dict[str, float]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = []
    for batch in batch_ids:
        for symbol in sorted(s for b, s in features if b == batch):
            f = features[(batch, symbol)]
            structure = None
            if system.track == "execution_min_cost":
                pool = [
                    r for r in records
                    if r["candidate"].batch_id == batch and r["candidate"].symbol == symbol
                    and r["candidate"].rank == "min_crossing" and r[f"pnl_{system.horizon}"] is not None
                    and r["candidate"].crossing_cost <= system.parameter
                ]
                if pool:
                    decisions.append(min(pool, key=lambda r: (r["candidate"].crossing_cost, r["candidate"].worst_spread_pct)))
                continue
            if system.track == "direction_momentum" and abs(f["return_15m"]) >= system.parameter:
                structure = "BULL_CALL_SPREAD" if f["return_15m"] > 0 else "BEAR_PUT_SPREAD"
            elif system.track == "direction_reversal" and abs(f["return_15m"]) >= system.parameter:
                structure = "BEAR_PUT_SPREAD" if f["return_15m"] > 0 else "BULL_CALL_SPREAD"
            elif system.track == "council" and abs(f["consensus_direction"]) >= system.parameter:
                structure = "BULL_CALL_SPREAD" if f["consensus_direction"] > 0 else "BEAR_PUT_SPREAD"
            elif system.track == "short_vol" and f["iv_rv_ratio"] >= system.parameter:
                structure = "IRON_CONDOR"
            elif system.track == "long_vol" and f["iv_rv_ratio"] <= system.parameter:
                structure = "LONG_STRADDLE"
            elif system.track == "index_momentum" and symbol in {"SPY", "QQQ"} and abs(f["return_15m"]) >= system.parameter:
                structure = "BULL_CALL_SPREAD" if f["return_15m"] > 0 else "BEAR_PUT_SPREAD"
            elif system.track == "cost_filtered_momentum":
                structure = "BULL_CALL_SPREAD" if f["return_15m"] > 0 else "BEAR_PUT_SPREAD"
            if structure:
                chosen = pick(records, batch, symbol, structure)
                cost_ok = chosen is not None and (
                    system.track != "cost_filtered_momentum" or chosen["candidate"].crossing_cost <= system.parameter
                )
                if chosen and cost_ok and chosen[f"pnl_{system.horizon}"] is not None:
                    decisions.append(chosen)
    return decisions


def matrix(rows: list[dict[str, Any]], features: dict[tuple[int, str], dict[str, float]]) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for row in rows:
        c = row["candidate"]
        f = features[(c.batch_id, c.symbol)]
        structure = [float(c.structure == item) for item in SUPPORTED]
        x.append([f[name] for name in FEATURES] + structure + [c.max_loss / 500, c.crossing_cost / 100, c.dte / 35])
        y.append(float(row["pnl_5"]))
    return np.asarray(x), np.asarray(y)


def ml_decisions(kind: str, train_ids: tuple[int, ...], validation_ids: tuple[int, ...], target_ids: tuple[int, ...], features: dict[tuple[int, str], dict[str, float]], records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float, dict[str, dict[str, Any]]]:
    train = [r for r in records if r["candidate"].batch_id in train_ids and r["pnl_5"] is not None]
    validation = [r for r in records if r["candidate"].batch_id in validation_ids and r["pnl_5"] is not None]
    target = [r for r in records if r["candidate"].batch_id in target_ids and r["pnl_5"] is not None]
    x_train, y_train = matrix(train, features)
    x_val, _ = matrix(validation, features)
    x_target, _ = matrix(target, features)
    mu, sigma = x_train.mean(axis=0), x_train.std(axis=0)
    sigma[sigma == 0] = 1
    def design(z: np.ndarray) -> np.ndarray:
        standardized = (z - mu) / sigma
        if kind == "nonlinear_ridge":
            core = standardized[:, : len(FEATURES)]
            standardized = np.c_[standardized, core**2, core[:, :8] * core[:, 8:16]]
        return np.c_[np.ones(len(standardized)), standardized]

    if kind in {"ridge", "nonlinear_ridge"}:
        x = design(x_train)
        weights = np.linalg.solve(x.T @ x + np.eye(x.shape[1]) * 10.0, x.T @ y_train)

        def predict(z: np.ndarray) -> np.ndarray:
            return design(z) @ weights
    else:
        raise ValueError(f"unsupported model: {kind}")
    val_predictions = predict(x_val)
    thresholds = [0.0, 5.0, 10.0, 20.0, 40.0]
    def selected(rows: list[dict[str, Any]], predictions: np.ndarray, threshold: float) -> list[dict[str, Any]]:
        choices: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}
        for prediction, row in zip(predictions, rows, strict=True):
            c = row["candidate"]
            key = (c.batch_id, c.symbol)
            if prediction >= threshold and (key not in choices or prediction > choices[key][0]):
                choices[key] = (float(prediction), row)
        return [item[1] for item in choices.values()]
    threshold = max(thresholds, key=lambda t: sum(float(r["pnl_5"]) for r in selected(validation, val_predictions, t)))
    target_predictions = predict(x_target)
    sensitivity = {
        f"threshold_{value:g}": metrics(selected(target, target_predictions, value))
        for value in sorted({max(-20.0, threshold + offset) for offset in (-10, -5, 0, 5, 10)})
    }
    return selected(target, target_predictions, threshold), threshold, sensitivity


def metrics(rows: list[dict[str, Any]], horizon: int = 5) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda r: (r["candidate"].completed_at, r["candidate"].symbol))
    values = [float(r[f"pnl_{horizon}"]) for r in ordered if r[f"pnl_{horizon}"] is not None]
    stress = [float(r[f"stress_{horizon}"]) for r in ordered if r[f"stress_{horizon}"] is not None]
    adverse = [float(r[f"adverse_{horizon}"]) for r in ordered if r[f"adverse_{horizon}"] is not None]
    curve, peak, drawdown = 0.0, 0.0, 0.0
    for value in values:
        curve += value
        peak = max(peak, curve)
        drawdown = max(drawdown, peak - curve)
    per_symbol = {}
    for symbol in sorted({r["candidate"].symbol for r in ordered}):
        subset = [float(r[f"pnl_{horizon}"]) for r in ordered if r["candidate"].symbol == symbol and r[f"pnl_{horizon}"] is not None]
        per_symbol[symbol] = {"n": len(subset), "total": sum(subset), "mean": mean(subset) if subset else None}
    best_trade = max(values, default=0)
    best_symbol = max(per_symbol, key=lambda s: per_symbol[s]["total"], default=None)
    excursions = [
        [float(row[f"pnl_{h}"]) for h in (5, 15, 30, 60) if row.get(f"pnl_{h}") is not None]
        for row in ordered
    ]
    mfe = [max(values) for values in excursions if values]
    mae = [min(values) for values in excursions if values]
    return {
        "decisions": len(values), "feasible_trades": len(values), "total_pnl": sum(values), "mean_pnl": mean(values) if values else None,
        "median_pnl": median(values) if values else None, "positive_rate": sum(v > 0 for v in values) / len(values) if values else None,
        "max_drawdown": drawdown, "worst_trade": min(values, default=None), "best_trade": max(values, default=None),
        "crossing_cost": sum(r["candidate"].crossing_cost * 2 for r in ordered),
        "return_per_max_risk": sum(values) / sum(r["candidate"].max_loss for r in ordered) if ordered else None,
        "stress_total": sum(stress), "adverse_total": sum(adverse), "remove_best_trade_total": sum(values) - best_trade,
        "best_symbol": best_symbol, "remove_best_symbol_total": sum(v["total"] for s, v in per_symbol.items() if s != best_symbol),
        "mean_mfe": mean(mfe) if mfe else None, "mean_mae": mean(mae) if mae else None, "per_symbol": per_symbol,
    }


def run(db_path: Path, output_root: Path, cutoff: str | None = None) -> Path:
    np.random.seed(SEED)
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed")
        batches, features, records = load_dataset(db, cutoff)
    batch_ids = [int(b["id"]) for b in batches]
    split = chronological_split(batch_ids)
    systems: list[System] = []
    specs = [
        ("direction_momentum", "Momentum", [0.0, 0.0005, 0.001, 0.002]),
        ("direction_reversal", "Mean reversal", [0.0, 0.0005, 0.001, 0.002]),
        ("council", "Council direction", [0.0, 0.02, 0.05, 0.10]),
        ("short_vol", "IV/RV short volatility", [1.0, 1.25, 1.5, 2.0]),
        ("long_vol", "RV expansion long volatility", [1.0, 1.25, 1.5, 2.0]),
        ("index_momentum", "Index-only momentum", [0.0, 0.0005, 0.001, 0.002]),
        ("cost_filtered_momentum", "Crossing-filtered momentum", [1.0, 2.0, 3.0, 5.0]),
        ("execution_min_cost", "Minimum-cost structure", [1.0, 2.0, 3.0, 5.0]),
    ]
    motivation = {
        "direction_momentum": "intraday time-series momentum literature",
        "direction_reversal": "diagnosed momentum failure and short-horizon reversal baseline",
        "council": "existing Lyceum production hypothesis",
        "short_vol": "variance-risk-premium and IV/RV literature",
        "long_vol": "volatility expansion and direct straddle-P&L target",
        "index_momentum": "single-name quote instability diagnosed in the first tournament",
        "cost_filtered_momentum": "transaction costs destroyed the raw directional branches",
        "execution_min_cost": "execution-first redesign after signal-correct trades still lost to option costs",
    }
    ledger = []
    finalists: list[dict[str, Any]] = []
    for track, label, parameters in specs:
        variants = []
        for index, parameter in enumerate(parameters, 1):
            system = System(
                f"{track}-{index:02d}", f"{track}-{index - 1:02d}" if index > 1 else None, track, f"{label} p={parameter:g}",
                f"A causal {label.lower()} signal can exceed full quoted crossing costs after liquidity-first construction.",
                motivation[track], f"{track} entry rule with threshold {parameter:g}", "five-minute conservative executable structure P&L",
                FEATURES if track in {"short_vol", "long_vol", "execution_min_cost"} else ("return_15m", "consensus_direction", "realized_volatility"),
                "deterministic rule", parameter,
            )
            systems.append(system)
            val_rows = rule_decisions(system, split.validation, features, records)
            val_metrics = metrics(val_rows)
            variants.append((val_metrics["total_pnl"], system, val_metrics))
            ledger.append({
                "experiment_id": system.experiment_id, "parent_experiment": system.parent, "hypothesis": system.hypothesis,
                "source_research_motivation": system.motivation, "code_config_version": "WORKTREE", "train_period": list(split.train),
                "validation_period": list(split.validation), "holdout_period": list(split.holdout), "metrics": {"validation": val_metrics},
                "failure_reason": None if val_metrics["total_pnl"] > 0 else "transaction costs or signal mapping produced non-positive validation P&L",
                "next_hypothesis": "add liquidity/cost-aware threshold or redirect to direct-P&L model",
            })
        _, best, validation_metrics = max(variants, key=lambda item: item[0])
        holdout_rows = rule_decisions(best, split.holdout, features, records)
        finalists.append({"system": asdict(best), "selected_on_validation": validation_metrics, "holdout": metrics(holdout_rows), "rows": holdout_rows})
    for kind in ("ridge", "nonlinear_ridge"):
        decisions, threshold, sensitivity = ml_decisions(kind, split.train, split.validation, split.holdout, features, records)
        system = System(
            f"ml-{kind}", "short_vol-04", "ml", f"Direct P&L {kind}",
            "A regularized cost-aware model can choose the structure whose executable P&L exceeds crossing cost.",
            "direct option-P&L labeling and limited-tabular-data guidance", f"highest predicted P&L above validation threshold ${threshold:g}",
            "five-minute conservative executable structure P&L", FEATURES, kind, threshold,
        )
        result = metrics(decisions)
        finalists.append({
            "system": asdict(system), "selected_on_validation": {"selection_threshold": threshold},
            "holdout": result, "rows": decisions, "parameter_sensitivity": sensitivity,
        })
        ledger.append({
            "experiment_id": system.experiment_id, "parent_experiment": system.parent, "hypothesis": system.hypothesis,
            "source_research_motivation": system.motivation, "code_config_version": "WORKTREE", "train_period": list(split.train),
            "validation_period": list(split.validation), "holdout_period": list(split.holdout), "metrics": {"holdout": result},
            "failure_reason": None if result["total_pnl"] > 0 else "direct predictions did not clear executable costs on holdout",
            "next_hypothesis": "collect independent sessions before increasing model complexity",
        })
    finalists.sort(key=lambda item: (item["holdout"]["decisions"] > 0, item["holdout"]["total_pnl"]), reverse=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = output_root / timestamp
    out.mkdir(parents=True, exist_ok=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True).stdout.splitlines()
    for entry in ledger:
        entry["code_config_version"] = head
    cutoff = max(str(b["completed_at"]) for b in batches)
    manifest = {
        "run_id": timestamp, "seed": SEED, "database": str(db_path), "database_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "data_cutoff": cutoff, "git_head": head, "working_tree": status, "script": "scripts/quant_research.py",
        "command": f".venv/bin/python scripts/quant_research.py --database {db_path} --output-root {output_root} --data-cutoff {cutoff}",
        "split": asdict(split), "purge_embargo": "2 complete batches on each side for a five-minute target",
        "feature_set": FEATURES, "candidate_records": len(records), "supported_structures": SUPPORTED,
    }
    serializable = []
    for item in finalists:
        clean = {key: value for key, value in item.items() if key != "rows"}
        clean["horizon_breakdown"] = {str(h): metrics(item["rows"], h) for h in (5, 15, 30, 60)}
        clean["training_examples"] = sum(1 for r in records if r["candidate"].batch_id in split.train and r["pnl_5"] is not None) if item["system"]["track"] == "ml" else len(split.train) * 7
        clean["windows"] = {
            "train": [batches[0]["completed_at"], batches[10]["completed_at"]],
            "validation": [batches[13]["completed_at"], batches[15]["completed_at"]],
            "holdout": [batches[18]["completed_at"], batches[21]["completed_at"]],
        }
        clean["structure_breakdown"] = dict(
            (name, sum(r["candidate"].structure == name for r in item["rows"])) for name in SUPPORTED
        )
        clean["dte_range"] = [
            min((r["candidate"].dte for r in item["rows"]), default=None),
            max((r["candidate"].dte for r in item["rows"]), default=None),
        ]
        if "parameter_sensitivity" not in clean:
            clean["parameter_sensitivity"] = {
                f"parameter_{candidate.parameter:g}": metrics(
                    rule_decisions(candidate, split.holdout, features, records)
                )
                for candidate in systems if candidate.track == item["system"]["track"]
            }
        m = clean["holdout"]
        clean["robustness"] = {
            "untouched_holdout": True,
            "transaction_cost_stress_pass": m["stress_total"] > 0,
            "single_best_trade_removal_pass": m["remove_best_trade_total"] > 0,
            "best_symbol_removal_pass": m["remove_best_symbol_total"] > 0,
            "symbol_breadth_pass": sum(v["total"] > 0 for v in m["per_symbol"].values()) >= 2,
            "baseline_cash_advantage": m["total_pnl"],
        }
        baseline_track = (
            "direction_momentum" if item["system"]["track"] in {"direction_reversal", "council", "index_momentum", "cost_filtered_momentum"}
            else "short_vol" if item["system"]["track"] == "long_vol"
            else "execution_min_cost" if item["system"]["track"] == "ml"
            else None
        )
        baseline_item = next((x for x in finalists if x["system"]["track"] == baseline_track), None)
        clean["baseline_comparison"] = {
            "cash_total": 0.0,
            "relevant_baseline": baseline_item["system"]["name"] if baseline_item else "cash",
            "relevant_baseline_total": baseline_item["holdout"]["total_pnl"] if baseline_item else 0.0,
            "incremental_total": m["total_pnl"] - (baseline_item["holdout"]["total_pnl"] if baseline_item else 0.0),
        }
        clean["entry_filter"] = "7-35 DTE; max loss <=$500; entry quote age <=180s; bid>0; ask>bid; displayed sizes >=1; volume >=1; each leg spread <=15%; liquidity-first rank"
        clean["exit_horizon_minutes"] = item["system"]["horizon"]
        clean["classification"] = (
            "FORWARD-TEST READY" if m["total_pnl"] > 0 and all(
                value for key, value in clean["robustness"].items() if key.endswith("_pass")
            ) else "PROMISING BUT NEEDS MORE DATA — OVERFIT / FRAGILE" if m["total_pnl"] > 0 else "REJECTED"
        )
        serializable.append(clean)
    sources = [
        {
            "topic": "intraday momentum", "url": "https://profiles.wustl.edu/en/publications/market-intraday-momentum/",
            "conclusion": "The documented first-half-hour to last-half-hour effect is time-of-day and regime specific; the present two-hour sample cannot validate it.",
        },
        {
            "topic": "variance risk premium", "url": "https://ideas.repec.org/p/wpa/wuwpfi/0409015.html",
            "conclusion": "IV versus realized variance motivates short-volatility tests, but an intraday defined-risk implementation must first clear option execution costs.",
        },
        {
            "topic": "HAR realized volatility", "url": "https://people.unipi.it/fulvio_corsi/wp-content/uploads/sites/473/2018/08/FulvioCorsi_Tesi_2005.pdf",
            "conclusion": "Multi-horizon realized-volatility components are useful, but daily and weekly HAR components are unavailable in a one-session capture.",
        },
        {
            "topic": "option transaction costs", "url": "https://academic.oup.com/rof/article/27/1/289/6510952",
            "conclusion": "Bid/ask adjustments can consume option strategy profits; full ask-to-bid P&L is the primary metric here.",
        },
        {
            "topic": "option liquidity and effective spreads", "url": "https://academic.oup.com/rfs/article-abstract/33/11/4973/5732665",
            "conclusion": "Price improvement may reduce realized costs, but quoted crossing remains the conservative evidence standard without execution records.",
        },
        {
            "topic": "Alpaca option snapshots", "url": "https://docs.alpaca.markets/us/v1.4.2/reference/optionsnapshots",
            "conclusion": "Snapshots provide latest quotes and Greeks; they do not provide order-book execution evidence.",
        },
    ]
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "experiment_ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
    (out / "ranked_candidates.json").write_text(json.dumps(serializable, indent=2) + "\n")
    (out / "research_log.json").write_text(json.dumps(sources, indent=2) + "\n")
    report = ["# Lyceum quant research tournament", "", f"Run `{timestamp}`; data cutoff `{cutoff}`; seed `{SEED}`.", "", "## Ranked holdout candidates", ""]
    for rank, item in enumerate(serializable[:5], 1):
        s, m = item["system"], item["holdout"]
        report += [
            f"### {rank}. {s['name']}", "",
            f"- Track: {s['track']}", f"- Signal: {s['signal']}", f"- Target: {s['target']}", f"- Model: {s['model']}",
            f"- Holdout decisions: {m['decisions']}", f"- Total / mean / median P&L: ${m['total_pnl']:.2f} / ${m['mean_pnl'] or 0:.2f} / ${m['median_pnl'] or 0:.2f}",
            f"- Positive rate: {(m['positive_rate'] or 0):.1%}", f"- Stress / adverse total: ${m['stress_total']:.2f} / ${m['adverse_total']:.2f}",
            f"- Remove best trade / best symbol: ${m['remove_best_trade_total']:.2f} / ${m['remove_best_symbol_total']:.2f}", "",
        ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/quant-research"))
    parser.add_argument("--data-cutoff")
    args = parser.parse_args()
    print(run(args.database, args.output_root, args.data_cutoff))


if __name__ == "__main__":
    main()
