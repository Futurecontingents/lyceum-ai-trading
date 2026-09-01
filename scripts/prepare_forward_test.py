#!/usr/bin/env python3
"""Build historical signals and preregister the sealed 2026-09-01 forward test."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from lyceum.agents import market_council
from lyceum.consensus import calculate_consensus
from lyceum.models import MarketSnapshot

SYMBOLS = ("SPY", "QQQ", "AAPL", "NVDA", "AMD", "META", "TSLA")
HORIZONS = (5, 15, 30, 60)
STEPS = {minutes: minutes // 5 for minutes in HORIZONS}
FEATURES = (
    "return_5m", "return_15m", "return_30m", "return_60m", "rv_15m", "rv_60m",
    "range_pct", "volume_ratio", "vwap_deviation",
    "disagreement", "entropy", "minute_sin", "minute_cos",
)
NY = ZoneInfo("America/New_York")
SEED = 20260901


def fetch_symbol(profile: str, symbol: str, start: date, end: date, cache: Path) -> Path:
    path = cache / f"{symbol}-{start}-{end}-iex-raw-5Min.json"
    if path.exists():
        return path
    bars: list[dict[str, Any]] = []
    token = ""
    while True:
        command = [
            "alpaca", "--profile", profile, "data", "bars", "--symbol", symbol,
            "--start", start.isoformat(), "--end", end.isoformat(), "--timeframe", "5Min",
            "--feed", "iex", "--adjustment", "raw", "--sort", "asc", "--limit", "1000",
        ]
        if token:
            command += ["--page-token", token]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        payload = json.loads(result.stdout)
        bars.extend(payload.get("bars", []))
        token = str(payload.get("next_page_token") or "")
        if not token:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bars, separators=(",", ":")) + "\n")
    return path


def load_bars(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        symbol = path.name.split("-", 1)[0]
        frame = pd.DataFrame(json.loads(path.read_text()))
        frame["symbol"] = symbol
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True).rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    local = data["timestamp"].dt.tz_convert(NY)
    data["session"] = local.dt.date
    data["minute"] = local.dt.hour * 60 + local.dt.minute - 570
    data = data[(data["minute"] >= 0) & (data["minute"] < 390)].sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return data


def council_features(row: Any) -> tuple[float, float]:
    snapshot = MarketSnapshot(
        symbol=row.symbol, timestamp=row.timestamp.to_pydatetime(), price=float(row.close), previous_close=float(row.close / (1 + row.return_5m)),
        momentum_1h=float(row.return_60m), momentum_1d=float(row.return_1d), realized_volatility=float(max(row.rv_1d, 0.01)),
    )
    consensus = calculate_consensus([agent.evaluate(snapshot) for agent in market_council()])
    return consensus.disagreement, consensus.entropy


def build_features(bars: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, group in bars.groupby("symbol", sort=False):
        group = group.copy()
        session = group.groupby("session", sort=False)
        for horizon, steps in STEPS.items():
            group[f"return_{horizon}m"] = session["close"].pct_change(steps, fill_method=None)
            group[f"target_return_{horizon}m"] = session["close"].shift(-steps) / group["close"] - 1
        group["return_1d"] = group["close"] / group["close"].shift(78) - 1
        one = session["close"].pct_change(fill_method=None)
        group["rv_15m"] = one.rolling(3, min_periods=3).std() * math.sqrt(3)
        group["rv_60m"] = one.rolling(12, min_periods=8).std() * math.sqrt(12)
        group["rv_1d"] = one.rolling(78, min_periods=40).std() * math.sqrt(78)
        group["rv_5d"] = one.rolling(390, min_periods=195).std() * math.sqrt(78)
        group["range_pct"] = (group["high"] - group["low"]) / group["close"]
        group["volume_ratio"] = group["volume"] / group["volume"].rolling(78, min_periods=20).median()
        typical = (group["high"] + group["low"] + group["close"]) / 3
        rolling_pv = (typical * group["volume"]).rolling(24, min_periods=6).sum()
        rolling_volume = group["volume"].rolling(24, min_periods=6).sum()
        group["vwap_deviation"] = group["close"] / (rolling_pv / rolling_volume) - 1
        group["minute_sin"] = np.sin(2 * np.pi * group["minute"] / 390)
        group["minute_cos"] = np.cos(2 * np.pi * group["minute"] / 390)
        for horizon, steps in STEPS.items():
            future_variance = sum(one.shift(-offset).pow(2) for offset in range(1, steps + 1))
            group[f"target_rv_{horizon}m"] = np.sqrt(future_variance)
        parts.append(group)
    data = pd.concat(parts, ignore_index=True).replace([np.inf, -np.inf], np.nan)
    usable = data.dropna(subset=["return_5m", "return_15m", "return_30m", "return_60m", "return_1d", "rv_1d", "rv_5d"])
    values = [council_features(row) for row in usable.itertuples(index=False)]
    data.loc[usable.index, "disagreement"] = [value[0] for value in values]
    data.loc[usable.index, "entropy"] = [value[1] for value in values]
    return data


def rule_metrics(data: pd.DataFrame, signal: pd.Series, horizon: int) -> dict[str, Any]:
    target = data[f"target_return_{horizon}m"]
    valid = signal.notna() & target.notna() & (signal != 0)
    pnl = np.sign(signal[valid]) * target[valid]
    return {
        "decisions": int(valid.sum()), "directional_hit_rate": float((pnl > 0).mean()),
        "total_signed_return": float(pnl.sum()), "mean_signed_return": float(pnl.mean()),
        "median_signed_return": float(pnl.median()), "worst_signed_return": float(pnl.min()),
    }


def ridge_fit(x: np.ndarray, y: np.ndarray, penalty: float = 10.0) -> dict[str, Any]:
    mu, sigma = x.mean(axis=0), x.std(axis=0)
    sigma[sigma == 0] = 1
    design = np.c_[np.ones(len(x)), (x - mu) / sigma]
    weights = np.linalg.solve(design.T @ design + np.eye(design.shape[1]) * penalty, design.T @ y)
    return {"mean": mu.tolist(), "scale": sigma.tolist(), "weights": weights.tolist(), "penalty": penalty}


def ridge_predict(model: dict[str, Any], x: np.ndarray) -> np.ndarray:
    mean_, scale, weights = (np.asarray(model[key]) for key in ("mean", "scale", "weights"))
    return np.c_[np.ones(len(x)), (x - mean_) / scale] @ weights


def walk_forward_ml(data: pd.DataFrame, target: str, feature_names: tuple[str, ...] = FEATURES) -> tuple[dict[str, Any], dict[str, Any]]:
    eligible = data.dropna(subset=[*feature_names, target]).copy()
    eligible["month"] = pd.to_datetime(eligible["timestamp"], utc=True).dt.strftime("%Y-%m")
    predictions, outcomes = [], []
    for month in sorted(eligible.loc[eligible["timestamp"] >= "2025-01-01", "month"].unique()):
        test = eligible[eligible["month"] == month]
        train = eligible[eligible["timestamp"] < test["timestamp"].min()].copy()
        train = train.groupby("symbol", group_keys=False).apply(lambda x: x.iloc[:-12], include_groups=False)
        if len(train) < 1000 or test.empty:
            continue
        model = ridge_fit(train[list(feature_names)].to_numpy(float), train[target].to_numpy(float))
        predictions.extend(ridge_predict(model, test[list(feature_names)].to_numpy(float)))
        outcomes.extend(test[target].to_numpy(float))
    prediction, outcome = np.asarray(predictions), np.asarray(outcomes)
    correlation = float(np.corrcoef(prediction, outcome)[0, 1]) if len(prediction) > 2 else None
    metrics = {"observations": len(outcome), "correlation": correlation, "mae": float(np.mean(np.abs(prediction - outcome)))}
    final = ridge_fit(eligible[list(feature_names)].to_numpy(float), eligible[target].to_numpy(float))
    return final, metrics


def research(data: pd.DataFrame, cutoff: date) -> dict[str, Any]:
    clean = data[(data["session"] < cutoff) & (data["timestamp"] >= "2024-01-01")].copy()
    oos = clean[clean["timestamp"] >= "2025-01-01"].copy()
    momentum, reversal = [], []
    for lookback in HORIZONS:
        volatility_scale = oos["rv_1d"] * math.sqrt(lookback / 390)
        active = oos[f"return_{lookback}m"].abs() >= 0.5 * volatility_scale
        for holding in HORIZONS:
            raw = oos[f"return_{lookback}m"].where(active, 0)
            momentum.append({"lookback": lookback, "holding": holding, **rule_metrics(oos, raw, holding)})
            reversal.append({"lookback": lookback, "holding": holding, **rule_metrics(oos, -raw, holding)})
    vwap_rules = []
    for threshold in (0.5, 1.0):
        z = oos["vwap_deviation"] / oos["rv_1d"].clip(lower=1e-6)
        for holding in HORIZONS:
            vwap_rules.append({"threshold": threshold, "holding": holding, **rule_metrics(oos, -z.where(z.abs() >= threshold, 0), holding)})
    best_momentum = max(momentum, key=lambda x: x["total_signed_return"])
    best_reversal = max(reversal, key=lambda x: x["total_signed_return"])
    best_baseline = max(vwap_rules, key=lambda x: x["total_signed_return"])
    direction_models = {}
    volatility_models = {}
    for horizon in HORIZONS:
        model, metrics = walk_forward_ml(clean, f"target_return_{horizon}m")
        direction_models[str(horizon)] = {"model": model, "walk_forward": metrics}
        model, metrics = walk_forward_ml(clean, f"target_rv_{horizon}m")
        _, har_metrics = walk_forward_ml(clean, f"target_rv_{horizon}m", ("rv_15m", "rv_60m", "minute_sin", "minute_cos"))
        _, no_disagreement_metrics = walk_forward_ml(
            clean, f"target_rv_{horizon}m", tuple(name for name in FEATURES if name not in {"disagreement", "entropy"})
        )
        volatility_models[str(horizon)] = {
            "model": model, "walk_forward": metrics,
            "benchmarks": {
                "HAR_intraday": har_metrics, "ridge_without_disagreement": no_disagreement_metrics,
                "EWMA_proxy": {"feature": "rv_60m", "note": "reported through HAR benchmark; no IV is backfilled historically"},
                "IV_RV": "UNAVAILABLE_HISTORICALLY_NO_POINT_IN_TIME_IV",
            },
        }
    best_ml_horizon = max(HORIZONS, key=lambda h: direction_models[str(h)]["walk_forward"]["correlation"] or -math.inf)
    best_vol_horizon = max(HORIZONS, key=lambda h: volatility_models[str(h)]["walk_forward"]["correlation"] or -math.inf)
    return {
        "dataset": {
            "start": str(clean["session"].min()), "end": str(clean["session"].max()), "bars": len(clean),
            "sessions": int(clean["session"].nunique()), "symbols": list(SYMBOLS), "timeframe": "5Min IEX raw",
            "contaminated_excluded": "2026-08-31",
        },
        "best_momentum": best_momentum, "best_reversal": best_reversal, "best_baseline": best_baseline,
        "direction_models": direction_models, "volatility_models": volatility_models,
        "best_ml_horizon": best_ml_horizon, "best_vol_horizon": best_vol_horizon,
        "all_rule_results": {"momentum": momentum, "reversal": reversal, "vwap_reversion": vwap_rules},
    }


def candidate_manifest(result: dict[str, Any], generated_at: str, data_hashes: dict[str, str]) -> dict[str, Any]:
    momentum, reversal, baseline = result["best_momentum"], result["best_reversal"], result["best_baseline"]
    ml_horizon, vol_horizon = result["best_ml_horizon"], result["best_vol_horizon"]
    common = {
        "max_loss": 500, "dte": [7, 35], "quote_age_seconds": 180, "minimum_displayed_size": 1,
        "minimum_volume": 1, "maximum_leg_spread_pct": 0.15, "entry_rank": "minimum crossing cost, then worst-leg spread, then max loss",
        "strike_delta_rules": {
            "directional_vertical": "long leg nearest ATM; short leg 0<width<=5 points",
            "long_straddle": "same-strike call and put nearest ATM",
            "iron_condor": "short deltas abs 0.10-0.40; each wing 0<width<=5 points",
        },
        "exit_marks_minutes": [5, 15, 30, 60],
        "exit_condition": "evaluate/close at candidate holding_minutes; retain 5/15/30/60 diagnostic executable marks",
        "crossing_cost_units": "USD per one-contract structure from midpoint to quoted executable entry",
        "orders": "PROHIBITED",
    }
    candidates = [
        {
            "id": "A", "name": "cost_filtered_momentum", "signal": f"sign(return_{momentum['lookback']}m) when abs(return)>0.5*RV_1d*sqrt({momentum['lookback']}/390)",
            "features": [f"return_{momentum['lookback']}m", "rv_1d", "option_crossing_cost"], "model": "deterministic",
            "model_hash": hashlib.sha256(json.dumps(momentum, sort_keys=True).encode()).hexdigest(), "holding_minutes": momentum["holding"],
            "structures": ["BULL_CALL_SPREAD", "BEAR_PUT_SPREAD"], "direction_mapping": "positive->bull call; negative->bear put",
            "maximum_entry_crossing_cost": 2.0, "historical": momentum, **common,
        },
        {
            "id": "B", "name": "cost_filtered_mean_reversion", "signal": f"-sign(return_{reversal['lookback']}m) when abs(return)>0.5*RV_1d*sqrt({reversal['lookback']}/390)",
            "features": [f"return_{reversal['lookback']}m", "rv_1d", "option_crossing_cost"], "model": "deterministic",
            "model_hash": hashlib.sha256(json.dumps(reversal, sort_keys=True).encode()).hexdigest(), "holding_minutes": reversal["holding"],
            "structures": ["BULL_CALL_SPREAD", "BEAR_PUT_SPREAD"], "direction_mapping": "positive reversal->bull call; negative->bear put",
            "maximum_entry_crossing_cost": 2.0, "historical": reversal, **common,
        },
        {
            "id": "C", "name": "lyceum_volatility_disagreement", "signal": "ridge forecast of forward realized move; disagreement is volatility input; compare forecast with ATM IV implied move",
            "features": list(FEATURES), "model": "ridge", "parameters": result["volatility_models"][str(vol_horizon)]["model"],
            "model_hash": hashlib.sha256(json.dumps(result["volatility_models"][str(vol_horizon)]["model"], sort_keys=True).encode()).hexdigest(),
            "holding_minutes": vol_horizon, "structures": ["LONG_STRADDLE", "IRON_CONDOR"],
            "entry_condition": "long straddle if forecast/implied move>=1.10; iron condor if implied/forecast>=1.25; otherwise NO_TRADE",
            "maximum_entry_crossing_cost": 4.0, "historical": result["volatility_models"][str(vol_horizon)]["walk_forward"], **common,
        },
        {
            "id": "D", "name": "direct_economic_ridge", "signal": "ridge forward-return forecast mapped to candidate delta; trade only when predicted gross option move exceeds estimated round-trip crossing by 25%",
            "features": list(FEATURES), "model": "ridge", "parameters": result["direction_models"][str(ml_horizon)]["model"],
            "model_hash": hashlib.sha256(json.dumps(result["direction_models"][str(ml_horizon)]["model"], sort_keys=True).encode()).hexdigest(),
            "holding_minutes": ml_horizon, "structures": ["BULL_CALL_SPREAD", "BEAR_PUT_SPREAD"],
            "entry_condition": "abs(predicted_return)*spot*50 > 1.25*estimated_roundtrip_crossing",
            "maximum_entry_crossing_cost": 4.0, "historical": result["direction_models"][str(ml_horizon)]["walk_forward"], **common,
        },
        {
            "id": "E", "name": "vwap_reversion_baseline", "signal": f"-sign(price/VWAP_120m-1) when abs(VWAP_120m_deviation/RV_1d)>={baseline['threshold']}",
            "features": ["vwap_deviation", "rv_1d", "option_crossing_cost"], "model": "deterministic",
            "model_hash": hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest(), "holding_minutes": baseline["holding"],
            "structures": ["BULL_CALL_SPREAD", "BEAR_PUT_SPREAD"], "direction_mapping": "below VWAP->bull call; above VWAP->bear put",
            "maximum_entry_crossing_cost": 2.0, "historical": baseline, **common,
        },
    ]
    return {
        "schema_version": 1, "status": "FROZEN", "generated_at": generated_at, "sealed_session": "2026-09-01",
        "training_cutoff": "2026-08-30T23:59:59-04:00", "excluded_development_session": "2026-08-31",
        "random_seed": SEED, "dataset": result["dataset"], "data_sha256": data_hashes,
        "walk_forward": "expanding monthly tests from 2025-01; 12 five-minute bars purged per symbol at every boundary",
        "historical_option_quotes": "UNAVAILABLE; no historical option P&L fabricated", "candidates": candidates,
        "forward_test": {
            "source": "shared COMPLETE batches in data/shadow_market.db", "database": "data/forward_test.db",
            "leaderboard": "artifacts/forward_test/live_leaderboard.json", "first_observation_not_before": "2026-09-01T09:30:00-04:00",
            "candidate_modification_during_session": "PROHIBITED", "order_submission": "PROHIBITED",
        },
        "sources": [
            {"url": "https://academic.oup.com/rof/article/27/1/289/6510952", "hypothesis": "full bid/ask crossing can erase option-return signals; rank executable economics"},
            {"url": "https://academic.oup.com/rfs/article/38/6/1783/8010873", "hypothesis": "DTE, moneyness, IV/RV and spread characteristics predict option returns; avoid five-minute-only conclusions"},
            {"url": "https://papers.ssrn.com/abstract=3393464", "hypothesis": "HAR volatility forecasts should include intraday periodicity"},
            {"url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4022147", "hypothesis": "pooled cross-symbol information can improve intraday volatility forecasts"},
            {"url": "https://academic.oup.com/rfs/article/39/3/783/8193725", "hypothesis": "quoted option spreads are a conservative upper-bound cost; keep explicit cost decomposition"},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="judging")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 8, 31))
    parser.add_argument("--cutoff", type=date.fromisoformat, default=date(2026, 8, 31))
    parser.add_argument("--cache", type=Path, default=Path("artifacts/forward_test/historical"))
    parser.add_argument("--results", type=Path, default=Path("artifacts/forward_test/historical_signal_results.json"))
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-01.json"))
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=3) as pool:
        paths = list(pool.map(lambda symbol: fetch_symbol(args.profile, symbol, args.start, args.end, args.cache), SYMBOLS))
    data = build_features(load_bars(paths))
    result = research(data, args.cutoff)
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps(result, indent=2) + "\n")
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    manifest = candidate_manifest(result, datetime.now(UTC).isoformat(), hashes)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"results": str(args.results), "manifest": str(args.manifest), "dataset": result["dataset"]}, indent=2))


if __name__ == "__main__":
    main()
