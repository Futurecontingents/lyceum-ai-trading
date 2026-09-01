#!/usr/bin/env python3
"""Quarantined Sep-02 research: decompose Aug-31 executable option economics.

This diagnostic intentionally reads only COMPLETE shadow batches dated 2026-08-31.
It has no broker imports and cannot inspect or affect the sealed Sep-01 forward test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any

CUTOFF = datetime(2026, 9, 1, tzinfo=UTC)
HORIZONS = (15, 30, 60, 90)
DTE_BANDS = ((7, 13, "7-13"), (14, 21, "14-21"), (22, 35, "22-35"))


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True)
class Leg:
    symbol: str
    sign: int


@dataclass(frozen=True)
class Structure:
    name: str
    dte_band: str
    geometry: str
    legs: tuple[Leg, ...]
    width: float | None


def valid_quote(row: sqlite3.Row, available_at: datetime) -> bool:
    bid, ask = float(row["bid"] or 0), float(row["ask"] or 0)
    if not row["quote_timestamp"] or not (0 < bid < ask):
        return False
    age = (available_at - instant(row["quote_timestamp"])).total_seconds()
    return 0 <= age <= 180 and min(float(row["bid_size"] or 0), float(row["ask_size"] or 0)) >= 1


def midpoint(row: sqlite3.Row) -> float:
    return (float(row["bid"]) + float(row["ask"])) / 2


def dte_band(expiry: str) -> str | None:
    days = (date.fromisoformat(expiry) - date(2026, 8, 31)).days
    return next((label for low, high, label in DTE_BANDS if low <= days <= high), None)


def structure_quotes(
    structure: Structure, entry_chain: dict[str, sqlite3.Row], exit_chain: dict[str, sqlite3.Row]
) -> dict[str, float] | None:
    entry_mid = entry_exec = exit_mid = exit_exec = 0.0
    delta = gamma = theta = vega = 0.0
    vega_pnl = 0.0
    entry_ivs: list[float] = []
    for leg in structure.legs:
        start, end = entry_chain.get(leg.symbol), exit_chain.get(leg.symbol)
        if start is None or end is None:
            return None
        sign = leg.sign
        entry_mid += sign * midpoint(start) * 100
        entry_exec += sign * float(start["ask"] if sign > 0 else start["bid"]) * 100
        exit_mid += sign * midpoint(end) * 100
        exit_exec += sign * float(end["bid"] if sign > 0 else end["ask"]) * 100
        delta += sign * float(start["delta"] or 0) * 100
        gamma += sign * float(start["gamma"] or 0) * 100
        theta += sign * float(start["theta"] or 0) * 100
        vega += sign * float(start["vega"] or 0) * 100
        if start["implied_volatility"] is not None and end["implied_volatility"] is not None:
            entry_ivs.append(float(start["implied_volatility"]))
            # Alpaca vega is option-price change per one IV percentage point.
            iv_points = (float(end["implied_volatility"]) - float(start["implied_volatility"])) * 100
            vega_pnl += sign * float(start["vega"] or 0) * iv_points * 100
    return {
        "entry_mid": entry_mid,
        "entry_exec": entry_exec,
        "exit_mid": exit_mid,
        "exit_exec": exit_exec,
        "entry_crossing": entry_exec - entry_mid,
        "exit_crossing": exit_mid - exit_exec,
        "midpoint_pnl": exit_mid - entry_mid,
        "executable_pnl": exit_exec - entry_exec,
        "delta_shares": delta,
        "gamma_shares_per_dollar": gamma,
        "theta_per_day": theta,
        "vega_per_point": vega,
        "vega_pnl": vega_pnl,
        "entry_iv": median(entry_ivs) if entry_ivs else 0.0,
    }


def calibrate_underlying(history_dir: Path) -> dict[tuple[str, str, int], dict[str, float]]:
    """Estimate signal-conditioned return moments using data strictly before Aug-31."""
    samples: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for path in sorted(history_dir.glob("*-5Min.json")):
        symbol = path.name.split("-", 1)[0]
        bars = [bar for bar in json.loads(path.read_text()) if instant(bar["t"]) < datetime(2026, 8, 31, tzinfo=UTC)]
        sessions: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for bar in bars:
            sessions[instant(bar["t"]).date()].append(bar)
        for session in sessions.values():
            closes = [float(bar["c"]) for bar in session]
            one_bar_returns = [0.0] + [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
            for index in range(12, len(closes)):
                rv_day = math.sqrt(sum(value * value for value in one_bar_returns[max(1, index - 77):index + 1]))
                raw = {"mom60": closes[index] / closes[index - 12] - 1, "rev5": -(closes[index] / closes[index - 1] - 1)}
                for signal, value in raw.items():
                    lookback = 60 if signal == "mom60" else 5
                    threshold = 0.5 * rv_day * math.sqrt(lookback / 390)
                    if abs(value) < threshold:
                        continue
                    direction = math.copysign(1, value)
                    for horizon in HORIZONS:
                        future = index + horizon // 5
                        if future >= len(closes):
                            continue
                        samples[(symbol, signal, horizon)].append(direction * (closes[future] / closes[index] - 1))
                for horizon in HORIZONS:
                    future = index + horizon // 5
                    if future < len(closes):
                        samples[(symbol, "unconditional", horizon)].append(closes[future] / closes[index] - 1)
    return {
        key: {
            "n": len(values), "mean_signed_return": mean(values), "median_signed_return": median(values),
            "mean_abs_return": mean(abs(value) for value in values),
            "mean_squared_return": mean(value * value for value in values),
        }
        for key, values in samples.items() if values
    }


def directional_structures(rows: list[sqlite3.Row], spot: float, direction: int) -> list[Structure]:
    by_expiry: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        band = dte_band(str(row["expiry"]))
        if band and 0.92 <= float(row["strike"]) / spot <= 1.08:
            by_expiry[str(row["expiry"])].append(row)
    found: list[Structure] = []
    option_type = "call" if direction > 0 else "put"
    for expiry, chain in by_expiry.items():
        typed = [row for row in chain if row["option_type"] == option_type]
        if not typed:
            continue
        target = 0.50 if direction > 0 else -0.50
        long = min(typed, key=lambda row: abs(float(row["delta"] or 0) - target))
        long_strike = float(long["strike"])
        shorts = [
            row for row in typed
            if (float(row["strike"]) - long_strike) * direction > 0
            and abs(float(row["strike"]) - long_strike) <= 5.0
        ]
        for geometry, predicate in (
            ("narrow", lambda width: width <= 2.5),
            ("wide", lambda width: 2.5 < width <= 5.0),
        ):
            pool = [row for row in shorts if predicate(abs(float(row["strike"]) - long_strike))]
            if not pool:
                continue
            short = min(pool, key=lambda row: (float(row["ask"]) - float(row["bid"]), abs(float(row["delta"] or 0))))
            width = abs(float(short["strike"]) - long_strike)
            found.append(Structure(
                "directional_vertical", str(dte_band(expiry)), geometry,
                (Leg(str(long["contract_symbol"]), 1), Leg(str(short["contract_symbol"]), -1)), width,
            ))
    return found


def straddles(rows: list[sqlite3.Row], spot: float) -> list[Structure]:
    grouped: dict[tuple[str, float], dict[str, sqlite3.Row]] = defaultdict(dict)
    for row in rows:
        if dte_band(str(row["expiry"])) and abs(float(row["strike"]) / spot - 1) <= 0.03:
            grouped[(str(row["expiry"]), float(row["strike"]))][str(row["option_type"])] = row
    by_band: dict[str, list[tuple[float, Structure]]] = defaultdict(list)
    for (expiry, strike), pair in grouped.items():
        if "call" not in pair or "put" not in pair:
            continue
        cost = sum(float(pair[k]["ask"]) - float(pair[k]["bid"]) for k in ("call", "put"))
        structure = Structure(
            "long_straddle", str(dte_band(expiry)), "atm",
            (Leg(str(pair["call"]["contract_symbol"]), 1), Leg(str(pair["put"]["contract_symbol"]), 1)), None,
        )
        by_band[structure.dte_band].append((abs(strike - spot) + cost, structure))
    return [min(pool, key=lambda item: item[0])[1] for pool in by_band.values()]


def condors(rows: list[sqlite3.Row], spot: float) -> list[Structure]:
    by_expiry: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if dte_band(str(row["expiry"])) and 0.90 <= float(row["strike"]) / spot <= 1.10:
            by_expiry[str(row["expiry"])].append(row)
    found: list[Structure] = []
    for expiry, chain in by_expiry.items():
        puts = [row for row in chain if row["option_type"] == "put" and float(row["strike"]) < spot]
        calls = [row for row in chain if row["option_type"] == "call" and float(row["strike"]) > spot]
        if not puts or not calls:
            continue
        short_put = min(puts, key=lambda row: abs(abs(float(row["delta"] or 0)) - 0.25))
        short_call = min(calls, key=lambda row: abs(abs(float(row["delta"] or 0)) - 0.25))
        for geometry, low, high in (("narrow", 0.0, 2.5), ("wide", 2.5, 5.0)):
            put_wings = [row for row in puts if low < float(short_put["strike"]) - float(row["strike"]) <= high]
            call_wings = [row for row in calls if low < float(row["strike"]) - float(short_call["strike"]) <= high]
            if not put_wings or not call_wings:
                continue
            long_put = min(put_wings, key=lambda row: float(row["ask"]) - float(row["bid"]))
            long_call = min(call_wings, key=lambda row: float(row["ask"]) - float(row["bid"]))
            width = max(
                float(short_put["strike"]) - float(long_put["strike"]),
                float(long_call["strike"]) - float(short_call["strike"]),
            )
            found.append(Structure(
                "iron_condor", str(dte_band(expiry)), geometry,
                (Leg(str(long_put["contract_symbol"]), 1), Leg(str(short_put["contract_symbol"]), -1),
                 Leg(str(short_call["contract_symbol"]), -1), Leg(str(long_call["contract_symbol"]), 1)), width,
            ))
    return found


def summarized(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    result = []
    for group, values in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0])):
        pnl = [float(value["executable_pnl"]) for value in values]
        item = {key: value for key, value in zip(keys, group, strict=True)}
        item.update({
            "n": len(values), "midpoint_pnl": sum(float(v["midpoint_pnl"]) for v in values),
            "executable_pnl": sum(pnl), "mean_executable_pnl": mean(pnl),
            "median_executable_pnl": median(pnl), "positive_rate": sum(value > 0 for value in pnl) / len(pnl),
            "delta_pnl": sum(float(v["delta_pnl"]) for v in values),
            "gamma_pnl": sum(float(v["gamma_pnl"]) for v in values),
            "theta_pnl": sum(float(v["theta_pnl"]) for v in values),
            "vega_pnl": sum(float(v["vega_pnl"]) for v in values),
            "greek_residual": sum(float(v["greek_residual"]) for v in values),
            "entry_crossing": sum(float(v["entry_crossing"]) for v in values),
            "exit_crossing": sum(float(v["exit_crossing"]) for v in values),
            "gross_to_roundtrip_cost": (
                sum(float(v["midpoint_pnl"]) for v in values)
                / max(sum(float(v["entry_crossing"] + v["exit_crossing"]) for v in values), 1e-9)
            ),
        })
        result.append(item)
    return result


def run(database: Path, output: Path, history_dir: Path) -> dict[str, Any]:
    calibration = calibrate_underlying(history_dir)
    extract_hash = hashlib.sha256()
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        batches = db.execute(
            "SELECT * FROM capture_batches WHERE status='COMPLETE' AND completed_at>=? AND completed_at<? ORDER BY completed_at",
            ("2026-08-31T00:00:00+00:00", CUTOFF.isoformat()),
        ).fetchall()
        if not batches or any(instant(row["completed_at"]) >= CUTOFF for row in batches):
            raise RuntimeError("Aug-31 quarantine invariant failed")
        underlying: dict[tuple[int, str], sqlite3.Row] = {}
        chains: dict[tuple[int, str], dict[str, sqlite3.Row]] = {}
        for batch in batches:
            extract_hash.update(str(batch["completed_at"]).encode())
            for row in db.execute("SELECT * FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch["id"],)):
                key = (int(batch["id"]), str(row["symbol"]))
                underlying[key] = row
                extract_hash.update(str(row["snapshot_json"]).encode())
                available = instant(batch["completed_at"])
                options = db.execute(
                    "SELECT * FROM option_snapshots WHERE batch_id=? AND underlying=? AND delta IS NOT NULL ORDER BY contract_symbol",
                    key,
                ).fetchall()
                for option in options:
                    extract_hash.update(str(option["payload_json"]).encode())
                chains[key] = {str(option["contract_symbol"]): option for option in options if valid_quote(option, available)}

        batch_times = [(row, instant(row["completed_at"])) for row in batches]
        observations: list[dict[str, Any]] = []
        for entry_batch, entry_at in batch_times:
            batch_id = int(entry_batch["id"])
            for symbol in sorted(symbol for candidate_batch, symbol in underlying if candidate_batch == batch_id):
                start_underlying = underlying[(batch_id, symbol)]
                spot = float(start_underlying["trade_price"])
                rv_day = max(float(start_underlying["realized_volatility"] or 0.2) / math.sqrt(252), 1e-9)
                raw_signals = {
                    "mom60": float(start_underlying["return_60m"] or 0),
                    "rev5": -float(start_underlying["return_5m"] or 0),
                }
                signals = {
                    name: (math.copysign(1, raw) if abs(raw) >= 0.5 * rv_day * math.sqrt((60 if name == "mom60" else 5) / 390) else 0)
                    for name, raw in raw_signals.items()
                }
                entry_chain = chains[(batch_id, symbol)]
                for horizon in HORIZONS:
                    exit_item = next(((row, at) for row, at in batch_times if at >= entry_at + timedelta(minutes=horizon)), None)
                    if exit_item is None:
                        continue
                    exit_batch, exit_at = exit_item
                    exit_key = (int(exit_batch["id"]), symbol)
                    if exit_key not in underlying:
                        continue
                    end_spot = float(underlying[exit_key]["trade_price"])
                    elapsed_minutes = (exit_at - entry_at).total_seconds() / 60
                    exit_chain = chains[exit_key]
                    requested: list[tuple[str, int, Structure]] = []
                    for signal_name, direction in signals.items():
                        if direction:
                            requested.extend((signal_name, int(direction), item) for item in directional_structures(list(entry_chain.values()), spot, int(direction)))
                    requested.extend(("vol_long", 0, item) for item in straddles(list(entry_chain.values()), spot))
                    requested.extend(("vol_short", 0, item) for item in condors(list(entry_chain.values()), spot))
                    for signal_name, direction, structure in requested:
                        values = structure_quotes(structure, entry_chain, exit_chain)
                        if values is None:
                            continue
                        move = end_spot - spot
                        delta_pnl = values["delta_shares"] * move
                        gamma_pnl = 0.5 * values["gamma_shares_per_dollar"] * move * move
                        theta_pnl = values["theta_per_day"] * elapsed_minutes / 1440
                        greek_total = delta_pnl + gamma_pnl + theta_pnl + values["vega_pnl"]
                        observations.append({
                            "entry_batch": batch_id, "entry_at": entry_at.isoformat(), "exit_at": exit_at.isoformat(),
                            "symbol": symbol, "signal": signal_name, "direction": direction, "horizon": horizon,
                            **asdict(structure), **values, "spot_move": move, "elapsed_minutes": elapsed_minutes,
                            "entry_spot": spot,
                            "delta_pnl": delta_pnl, "gamma_pnl": gamma_pnl, "theta_pnl": theta_pnl,
                            "greek_residual": values["midpoint_pnl"] - greek_total,
                        })

    directional = [row for row in observations if row["name"] == "directional_vertical"]
    volatility = [row for row in observations if row["name"] != "directional_vertical"]
    trade_filter = []
    for row in directional:
        moments = calibration[(str(row["symbol"]), str(row["signal"]), int(row["horizon"]))]
        spot = float(row["entry_spot"])
        expected_move = float(row["direction"]) * moments["mean_signed_return"]
        expected_dollar_move = float(row["direction"]) * moments["mean_signed_return"] * spot
        expected_delta = float(row["delta_shares"]) * expected_dollar_move
        expected_gamma = 0.5 * float(row["gamma_shares_per_dollar"]) * spot * spot * moments["mean_squared_return"]
        gross = expected_delta + expected_gamma
        cost = 2 * float(row["entry_crossing"])
        trade_filter.append({
            **row, "expected_underlying_move": expected_move, "expected_gross_move": gross,
            "estimated_roundtrip_cost": cost, "expected_net": gross - cost, "trade": gross > cost,
            "calibration_n": int(moments["n"]),
        })
    volatility_expected = []
    for row in volatility:
        moments = calibration[(str(row["symbol"]), "unconditional", int(row["horizon"]))]
        spot = float(row["entry_spot"])
        expected_gamma = 0.5 * float(row["gamma_shares_per_dollar"]) * spot * spot * moments["mean_squared_return"]
        expected_theta = float(row["theta_per_day"]) * float(row["elapsed_minutes"]) / 1440
        cost = 2 * float(row["entry_crossing"])
        implied_move = float(row["entry_iv"]) * math.sqrt(int(row["horizon"]) / (252 * 390))
        volatility_expected.append({
            **row, "forecast_abs_move_pct": moments["mean_abs_return"], "implied_move_pct": implied_move,
            "iv_move_premium_pct": implied_move - moments["mean_abs_return"],
            "expected_gamma_theta_gross": expected_gamma + expected_theta,
            "estimated_roundtrip_cost": cost,
            "expected_net_before_vega": expected_gamma + expected_theta - cost,
            "clears_cost": expected_gamma + expected_theta > cost,
            "calibration_n": int(moments["n"]),
        })
    result = {
        "research_track": "sep02_next_generation_option_economics",
        "generated_at": datetime.now(UTC).isoformat(),
        "data_cutoff_exclusive": CUTOFF.isoformat(),
        "source_database": str(database),
        "source_extract_sha256": extract_hash.hexdigest(),
        "complete_batches": len(batches),
        "coverage": {"start": batches[0]["completed_at"], "end": batches[-1]["completed_at"], "symbols": sorted({key[1] for key in underlying})},
        "limitations": [
            "One late-session date cannot establish statistical significance or generalize across regimes.",
            "Quoted-side execution is conservative; effective fills may improve, but improvement is not assumed.",
            "Greek attribution is a first-order/second-order local approximation; residual includes higher-order Greeks, changing Greeks, quote noise, and model error.",
            "Theta is prorated over calendar minutes and vega uses entry vega; both are estimates.",
            "90-minute results are sparse because the capture spans only about 103 minutes.",
        ],
        "directional_by_signal_horizon": summarized(directional, ("signal", "horizon")),
        "directional_by_horizon_dte_geometry": summarized(directional, ("signal", "horizon", "dte_band", "geometry")),
        "volatility_by_structure_horizon_dte_geometry": summarized(volatility, ("name", "signal", "horizon", "dte_band", "geometry")),
        "trade_no_trade": {
            "all": summarized(trade_filter, ("signal", "horizon")),
            "selected": summarized([row for row in trade_filter if row["trade"]], ("signal", "horizon")),
            "rejected": summarized([row for row in trade_filter if not row["trade"]], ("signal", "horizon")),
        },
        "expected_economics": {
            "directional": [{key: row[key] for key in (
                "signal", "horizon", "symbol", "dte_band", "geometry", "expected_gross_move",
                "estimated_roundtrip_cost", "expected_net", "trade", "calibration_n",
            )} for row in trade_filter],
            "volatility": [{key: row[key] for key in (
                "name", "horizon", "symbol", "dte_band", "geometry", "forecast_abs_move_pct",
                "implied_move_pct", "iv_move_premium_pct", "expected_gamma_theta_gross",
                "estimated_roundtrip_cost", "expected_net_before_vega", "clears_cost", "calibration_n",
                "midpoint_pnl", "executable_pnl",
            )} for row in volatility_expected],
        },
        "historical_calibration": {"|".join(map(str, key)): value for key, value in calibration.items()},
        "observations": observations,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/nextgen_research/option_economics_2026-08-31.json"))
    parser.add_argument("--history-dir", type=Path, default=Path("artifacts/forward_test/historical"))
    args = parser.parse_args()
    result = run(args.database, args.output, args.history_dir)
    print(json.dumps({"complete_batches": result["complete_batches"], "observations": len(result["observations"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
