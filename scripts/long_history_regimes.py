#!/usr/bin/env python3
"""Add causal rolling regimes and volatility-transition hypotheses to the campaign."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from long_history_campaign import ROOT, SEED, bh_adjust, build_experiments, json_safe, load, metrics, split_metrics


def causal_regimes(spy: pd.DataFrame) -> pd.DataFrame:
    returns = np.log(spy["close"]).diff()
    rv22 = returns.rolling(22).std() * np.sqrt(252)
    past_median_vol = rv22.expanding(252).median().shift(1)
    drawdown = spy["close"] / spy["close"].rolling(252).max() - 1
    regimes = pd.DataFrame(index=spy.index)
    regimes["trend"] = np.where(spy["close"] > spy["close"].rolling(200).mean(), "above_200dma", "below_200dma")
    regimes["realized_volatility"] = np.where(rv22 > past_median_vol, "above_past_expanding_median", "below_past_expanding_median")
    regimes["drawdown"] = np.select([drawdown <= -0.20, drawdown <= -0.10], ["drawdown_ge_20pct", "drawdown_10_to_20pct"], default="drawdown_lt_10pct")
    vix = pd.read_csv(ROOT / "raw/cboe_vix.csv", parse_dates=["DATE"]).set_index("DATE")["CLOSE"].reindex(spy.index).ffill()
    regimes["vix"] = pd.cut(vix, [-np.inf, 20, 30, np.inf], labels=["vix_below_20", "vix_20_to_30", "vix_above_30"]).astype(str)
    rates = pd.read_csv(ROOT / "raw/fred_dgs10.csv", parse_dates=["observation_date"]).set_index("observation_date")["DGS10"]
    rates = pd.to_numeric(rates, errors="coerce").reindex(spy.index).ffill()
    change = rates - rates.shift(63)
    regimes["rates"] = np.select([change >= 0.50, change <= -0.50], ["rising_ge_50bp_63d", "falling_ge_50bp_63d"], default="stable_within_50bp_63d")
    return regimes


def conditional_metrics(frame: pd.DataFrame, regimes: pd.DataFrame, horizon: int, seed: int) -> dict[str, Any]:
    output: dict[str, Any] = {}
    aligned = regimes.reindex(frame.index)
    for column in regimes.columns:
        output[column] = {}
        for offset, label in enumerate(sorted(aligned[column].dropna().unique())):
            selected = frame.loc[aligned[column] == label]
            output[column][str(label)] = metrics(selected, horizon, seed_offset=seed + offset)
    return output


def volatility_events(spy: pd.DataFrame) -> list[dict[str, Any]]:
    log_return = np.log(spy["close"]).diff()
    variance = log_return.pow(2)
    rv5 = variance.rolling(5).mean().pow(0.5)
    rv22 = variance.rolling(22).mean().pow(0.5)
    target = variance.shift(-1).rolling(5).sum().shift(-4).pow(0.5)
    causal_baseline = target.expanding(252).mean().shift(5)
    excess = target - causal_baseline
    vix = pd.read_csv(ROOT / "raw/cboe_vix.csv", parse_dates=["DATE"]).set_index("DATE")["CLOSE"].reindex(spy.index).ffill()
    definitions = [
        ("G01", "volatility_shock", "RV shock continuation", "Trailing 5-day RMS / trailing 22-day RMS >= 1.5", (rv5 / rv22) >= 1.5),
        ("G02", "volatility_shock", "Extreme RV shock continuation", "Trailing 5-day RMS / trailing 22-day RMS >= 2.0", (rv5 / rv22) >= 2.0),
        ("K01", "volatility_transition", "VIX jump forecasts movement", "CBOE VIX one-session increase >=20%", vix.pct_change() >= 0.20),
        ("K02", "volatility_transition", "High VIX forecasts movement", "CBOE VIX close >30", vix > 30),
    ]
    entries = []
    for offset, (identifier, family, hypothesis, definition, active) in enumerate(definitions):
        frame = pd.DataFrame({"pnl": excess.where(active)}).dropna()
        entries.append({
            "experiment_id": identifier, "parent_experiment": None, "family": family,
            "hypothesis": hypothesis, "source_research_motivation": "causal volatility-state forecast hypothesis",
            "exact_signal_definition": definition,
            "exact_target": "next 5-session realized magnitude minus expanding historical mean known with a 5-session publication lag",
            "horizon_sessions": 5, "code": "scripts/long_history_regimes.py", "random_seed": SEED,
            "data_cutoff": "2026-08-28", "full_history_metrics": metrics(frame, 5, seed_offset=2000 + offset * 10),
            "period_metrics": split_metrics(frame, 5, 2010 + offset * 10),
        })
    q_values = bh_adjust([x["full_history_metrics"].get("block_sign_surrogate_p", 1.0) for x in entries])
    for entry, q_value in zip(entries, q_values, strict=True):
        entry["selection_bias_control"] = {"family": "four registered volatility-state hypotheses", "benjamini_hochberg_q": q_value, "fdr_threshold": 0.10, "passes_fdr": q_value <= 0.10}
        holdout = entry["period_metrics"]["sealed_historical_holdout"]
        reasons = []
        if holdout.get("n", 0) < 30:
            reasons.append("fewer than 30 sealed-holdout events")
        ci = holdout.get("bootstrap_95_ci_mean", [None, None])
        if ci[0] is None or ci[0] <= 0:
            reasons.append("sealed-holdout block-bootstrap CI includes zero")
        if q_value > 0.10:
            reasons.append("fails volatility-family BH-FDR")
        entry["failure_reason"] = "; ".join(reasons) or None
        entry["long_history_supported"] = not reasons
    return entries


def main() -> None:
    spy = load("SPY")
    data = {symbol: load(symbol) for symbol in ("SPY", "QQQ", "IWM", "DIA", "^GSPC")}
    regimes = causal_regimes(spy)
    experiments = {experiment.experiment_id: experiment for experiment in build_experiments()}
    regime_path = ROOT / "regime_results.json"
    regime_payload = json.loads(regime_path.read_text())
    regime_payload["causal_rolling_regime_definitions"] = {
        "trend": "current adjusted close versus trailing 200-session mean",
        "realized_volatility": "trailing 22-session realized vol versus expanding past median shifted one session",
        "drawdown": "current close versus trailing 252-session maximum, fixed 10%/20% bands",
        "vix": "current official CBOE VIX close, fixed <20 / 20-30 / >30 bands",
        "rates": "current FRED DGS10 minus 63-session lag, fixed +/-50 bp bands",
    }
    regime_payload["causal_rolling_regime_counts"] = {column: regimes[column].value_counts().to_dict() for column in regimes.columns}
    regime_payload["causal_rolling_signal_results"] = {}
    for offset, identifier in enumerate(("A01", "C03", "D02", "H01", "E01")):
        experiment = experiments[identifier]
        frame = experiment.build(data).sort_index()
        regime_payload["causal_rolling_signal_results"][identifier] = conditional_metrics(frame, regimes, experiment.horizon, 3000 + offset * 30)
    events = volatility_events(spy)
    regime_payload["volatility_event_hypotheses"] = events
    regime_path.write_text(json.dumps(json_safe(regime_payload), indent=2, allow_nan=False) + "\n")
    ledger_path = ROOT / "experiment_ledger.json"
    ledger = [x for x in json.loads(ledger_path.read_text()) if x["experiment_id"] not in {"G01", "G02", "K01", "K02"}]
    ledger.extend(events)
    ledger_path.write_text(json.dumps(json_safe(ledger), indent=2, allow_nan=False) + "\n")
    leaderboard_path = ROOT / "signal_leaderboard.json"
    leaderboard = json.loads(leaderboard_path.read_text())
    leaderboard["volatility_event_hypotheses"] = events
    leaderboard_path.write_text(json.dumps(json_safe(leaderboard), indent=2, allow_nan=False) + "\n")
    print(json.dumps({"rolling_regime_rows": len(regimes), "volatility_events": [{"id": x["experiment_id"], "supported": x["long_history_supported"]} for x in events]}, indent=2))


if __name__ == "__main__":
    main()
