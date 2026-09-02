#!/usr/bin/env python3
"""Bridge long-history signals to recent 5-minute and observed option economics."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path("artifacts/long_history")
CUTOFF = pd.Timestamp("2026-08-28", tz="UTC")
HORIZONS = (5, 15, 30, 60, 90, 120)


def finite(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite(item) for item in value]
    if isinstance(value, (np.bool_, np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def simple_metrics(values: pd.Series) -> dict[str, Any]:
    values = values.replace([np.inf, -np.inf], np.nan).dropna()
    n = len(values)
    if not n:
        return {"n": 0, "mean_return": None}
    standard_error = float(values.std(ddof=1) / math.sqrt(n)) if n > 1 else math.nan
    mean = float(values.mean())
    return {
        "n": n, "mean_return": mean, "median_return": float(values.median()),
        "standard_error": standard_error, "t_stat": mean / standard_error if standard_error else math.nan,
        "hit_rate": float((values > 0).mean()), "mean_absolute_return": float(values.abs().mean()),
        "worst_return": float(values.min()),
    }


def load_sessions(symbol: str = "SPY") -> pd.DataFrame:
    path = Path(f"artifacts/forward_test/historical/{symbol}-2024-01-01-2026-08-31-iex-raw-5Min.json")
    bars = pd.DataFrame(json.loads(path.read_text()))
    bars["timestamp"] = pd.to_datetime(bars["t"], utc=True)
    bars = bars[bars["timestamp"] <= CUTOFF + pd.Timedelta(days=1)]
    local = bars["timestamp"].dt.tz_convert(ZoneInfo("America/New_York"))
    bars["date"] = pd.to_datetime(local.dt.date)
    bars["time"] = local.dt.time
    regular = ((local.dt.hour > 9) | ((local.dt.hour == 9) & (local.dt.minute >= 30))) & (local.dt.hour < 16)
    bars = bars[regular].sort_values("timestamp")
    records = []
    for date, group in bars.groupby("date"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        if len(group) < 70:
            continue
        row: dict[str, Any] = {"date": date, "open": float(group.iloc[0]["o"]), "close": float(group.iloc[-1]["c"]), "bars": len(group)}
        for minutes in HORIZONS:
            row[f"close_{minutes}m"] = float(group.iloc[minutes // 5 - 1]["c"])
        records.append(row)
    return pd.DataFrame(records).set_index("date").sort_index()


def intraday_bridge() -> dict[str, Any]:
    sessions = load_sessions()
    adjusted = pd.read_csv(ROOT / "normalized/SPY_yahoo.csv", parse_dates=["date"]).set_index("date")
    features = pd.DataFrame(index=adjusted.index)
    features["C03"] = np.sign(adjusted["close"] / adjusted["close"].shift(126) - 1)
    features["D02"] = -np.sign(adjusted["close"] / adjusted["close"].shift(5) - 1)
    daily_return = adjusted["close"].pct_change()
    features["E01"] = (daily_return <= -0.02).astype(float)
    features["H01"] = ((daily_return <= -0.02) & (adjusted["close"].shift(1) > adjusted["close"].rolling(200).mean().shift(1))).astype(float)
    features = features.shift(1).reindex(sessions.index)
    targets = {f"{minutes}m": sessions[f"close_{minutes}m"] / sessions["open"] - 1 for minutes in HORIZONS}
    targets["close"] = sessions["close"] / sessions["open"] - 1
    targets["overnight"] = sessions["open"].shift(-1) / sessions["close"] - 1
    results: dict[str, Any] = {
        "dataset": {"start": sessions.index.min().date().isoformat(), "end": sessions.index.max().date().isoformat(), "sessions": len(sessions), "source": "Alpaca IEX raw 5-minute bars", "cutoff": "2026-08-28"},
        "signals": {}, "time_of_day_unconditional": {name: simple_metrics(values) for name, values in targets.items()},
    }
    overnight = sessions["open"] / sessions["close"].shift(1) - 1
    results["signals"]["A01"] = {
        "timing": "prior regular-session close to next regular-session open",
        "horizons": {"overnight": simple_metrics(overnight)},
        "exact_timing_match": True,
    }
    for signal in ("C03", "D02", "E01", "H01"):
        active = features[signal].replace(0, np.nan)
        results["signals"][signal] = {
            "timing": "signal fixed at prior close; executable target starts next regular-session open",
            "horizons": {name: simple_metrics(active * value) for name, value in targets.items()},
            "exact_timing_match": False,
        }
    return results


def group_summary(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    output = []
    for keys, group in frame.groupby(columns, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        record = dict(zip(columns, keys, strict=True))
        record.update({
            "n": len(group), "median_roundtrip_crossing_dollars": float(group["roundtrip_crossing"].median()),
            "mean_roundtrip_crossing_dollars": float(group["roundtrip_crossing"].mean()),
            "median_break_even_spot_move_dollars": float(group["break_even_spot_move"].median()),
            "p75_break_even_spot_move_dollars": float(group["break_even_spot_move"].quantile(0.75)),
        })
        output.append(record)
    return output


def option_bridge(intraday: dict[str, Any]) -> dict[str, Any]:
    source = Path("artifacts/nextgen_research/option_economics_preopen_freeze_2026-09-01.json")
    payload = json.loads(source.read_text())
    observations = pd.DataFrame(payload["observations"])
    observations["roundtrip_crossing"] = observations["entry_crossing"] + observations["exit_crossing"]
    observations["entry_at"] = pd.to_datetime(observations["entry_at"], utc=True)
    local_hour = observations["entry_at"].dt.tz_convert(ZoneInfo("America/New_York")).dt.hour + observations["entry_at"].dt.minute / 60
    observations["time_of_day"] = pd.cut(local_hour, [9.49, 10.5, 14.0, 16.01], labels=["open_hour", "midday", "afternoon"])
    observations["spread_bucket"] = pd.cut(observations["roundtrip_crossing"], [-np.inf, 20, 50, np.inf], labels=["le_20", "20_to_50", "gt_50"])
    directional = observations[(observations["name"] == "directional_vertical") & (observations["delta_shares"].abs() >= 2)].copy()
    directional["break_even_spot_move"] = directional["roundtrip_crossing"] / directional["delta_shares"].abs()
    a01_recent = intraday["signals"]["A01"]["horizons"]["overnight"]
    recent_spy = pd.read_csv(ROOT / "normalized/SPY_yahoo.csv")["close"].tail(252).median()
    expected_spot_move = abs(a01_recent["mean_return"]) * recent_spy
    median_hurdle = float(directional["break_even_spot_move"].median())
    diagnostics = {}
    for name, group in observations.groupby("name"):
        diagnostics[name] = {
            "n": len(group), "mean_midpoint_diagnostic_pnl": float(group["midpoint_pnl"].mean()),
            "mean_conservative_quoted_side_pnl": float(group["executable_pnl"].mean()),
            "median_roundtrip_crossing_dollars": float(group["roundtrip_crossing"].median()),
        }
    council = json.loads(Path("artifacts/forward_test/agent_ablation_sep01_development.json").read_text())
    return {
        "source": str(source), "source_cutoff_exclusive": payload["data_cutoff_exclusive"],
        "coverage": payload["coverage"], "observations": len(observations),
        "definitions": {
            "midpoint_diagnostic": "exit midpoint minus entry midpoint; diagnostic only",
            "conservative_quoted_side_executable": "exit executable quoted side minus entry executable quoted side",
            "empirical_paper_execution": "actual Alpaca PAPER fills, isolated from quote-based metrics; paper simulator is not evidence of live fill quality",
        },
        "pnl_diagnostics_by_structure": diagnostics,
        "directional_break_even": {
            "filter": "directional vertical observations with absolute net delta >= 2 shares",
            "overall_n": len(directional), "median_spot_move_dollars": median_hurdle,
            "by_structure_dte_geometry": group_summary(directional, ["name", "dte_band", "geometry"]),
            "by_symbol": group_summary(directional, ["symbol"]),
            "by_time_of_day": group_summary(directional, ["time_of_day"]),
            "by_spread_bucket": group_summary(directional, ["spread_bucket"]),
        },
        "best_supported_signal_comparison": {
            "signal": "A01 overnight SPY drift", "recent_underlying_mean_return": a01_recent["mean_return"],
            "recent_underlying_mean_move_dollars_at_recent_median_spot": expected_spot_move,
            "observed_vertical_median_break_even_spot_move_dollars": median_hurdle,
            "magnitude_to_cost_hurdle_ratio": expected_spot_move / median_hurdle,
            "plausibly_clears": expected_spot_move >= median_hurdle,
            "important_mismatch": "option observations are intraday, not close-to-open; no actual overnight option NBBO exits were captured",
        },
        "empirical_paper_execution": {
            "n": 1, "instrument": "SPY 2026-09-04 763 call", "paper_only": True,
            "entry": "buy limit 3.20 filled 3.17", "exit": "ask 3.21 unfilled and canceled; marketable limit 3.12 filled 3.16",
            "net_pnl_dollars_before_fees": -1.0,
            "interpretation": "single simulator trial; excluded from inference and not evidence of live midpoint improvement",
        },
        "council_incremental": {
            "status": council["status"], "decision_sets": council["decision_sets"],
            "conclusion": "INCONCLUSIVE",
            "reason": "development-only 112-decision ablation; not an untouched OOS test conditional on the long-history HAR/ridge baseline; executable option mapping absent",
        },
        "limitations": [
            "No fabricated historical option quotes, IV, Greeks, spreads, or fills.",
            "Option hurdle comes from 9,627 actual recent option observations over a single partial session, so regime and overnight coverage are absent.",
            "Quoted-side executable P&L is conservative and distinct from midpoint diagnostics and one PAPER fill trial.",
        ],
    }


def main() -> None:
    intraday = intraday_bridge()
    bridge = option_bridge(intraday)
    output = {"intraday_bridge": intraday, "option_economics": bridge}
    (ROOT / "option_bridge.json").write_text(json.dumps(finite(output), indent=2, allow_nan=False) + "\n")
    print(json.dumps({"intraday_sessions": intraday["dataset"]["sessions"], "option_observations": bridge["observations"], "signal_cost_ratio": bridge["best_supported_signal_comparison"]["magnitude_to_cost_hurdle_ratio"]}, indent=2))


if __name__ == "__main__":
    main()
