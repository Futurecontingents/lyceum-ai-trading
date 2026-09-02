#!/usr/bin/env python3
"""Run the preregistered long-history signal and volatility campaign."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SEED = 20260902
ROOT = Path("artifacts/long_history")
SPLITS = {
    "early_discovery_train": ("1993-01-29", "2006-12-29"),
    "middle_validation": ("2007-01-01", "2015-12-31"),
    "recent_validation": ("2016-01-01", "2022-12-30"),
    "sealed_historical_holdout": ("2023-01-01", "2026-08-28"),
}
ERAS = {
    "dot_com": ("1993-01-29", "2002-12-31"),
    "pre_gfc": ("2003-01-01", "2006-12-31"),
    "gfc": ("2007-01-01", "2009-12-31"),
    "post_gfc_recovery": ("2010-01-01", "2012-12-31"),
    "low_vol_2010s": ("2013-01-01", "2019-12-31"),
    "covid": ("2020-01-01", "2021-12-31"),
    "inflation_rate_shock_2022": ("2022-01-01", "2022-12-31"),
    "modern_2023_2026": ("2023-01-01", "2026-08-28"),
}
DROP_WINDOWS = {
    "without_dot_com": ERAS["dot_com"],
    "without_gfc": ERAS["gfc"],
    "without_covid": ERAS["covid"],
    "without_2022": ERAS["inflation_rate_shock_2022"],
    "without_recent_2024_2026": ("2024-01-01", "2026-08-28"),
}


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    family: str
    hypothesis: str
    definition: str
    target: str
    horizon: int
    build: Callable[[dict[str, pd.DataFrame]], pd.DataFrame]
    parent: str | None = None
    motivation: str = "economically motivated preregistered hypothesis"


def load(symbol: str) -> pd.DataFrame:
    filename = symbol.replace("^", "index_") + "_yahoo.csv"
    frame = pd.read_csv(ROOT / "normalized" / filename, parse_dates=["date"])
    return frame.set_index("date").sort_index()


def forward_return(frame: pd.DataFrame, horizon: int) -> pd.Series:
    return frame["close"].shift(-horizon) / frame["close"] - 1


def result_frame(pnl: pd.Series, signal: pd.Series | None = None) -> pd.DataFrame:
    out = pd.DataFrame({"pnl": pnl})
    if signal is not None:
        out["signal"] = signal
    return out.replace([np.inf, -np.inf], np.nan).dropna(subset=["pnl"])


def hac_se(values: np.ndarray, lag: int) -> float:
    values = values[np.isfinite(values)]
    n = len(values)
    if n < 2:
        return math.nan
    centered = values - values.mean()
    variance = float(centered @ centered) / n
    for k in range(1, min(lag, n - 1) + 1):
        weight = 1 - k / (lag + 1)
        covariance = float(centered[k:] @ centered[:-k]) / n
        variance += 2 * weight * covariance
    return math.sqrt(max(variance, 0) / n)


def max_drawdown(values: np.ndarray) -> float:
    wealth = np.cumsum(values)
    peak = np.maximum.accumulate(np.r_[0.0, wealth])
    return float(np.min(np.r_[0.0, wealth] - peak))


def block_bootstrap(values: np.ndarray, block: int, rng: np.random.Generator, reps: int = 500) -> tuple[float, float]:
    n = len(values)
    if n < 10:
        return math.nan, math.nan
    means = np.empty(reps)
    blocks = math.ceil(n / block)
    for i in range(reps):
        starts = rng.integers(0, n, blocks)
        sample = np.concatenate([np.take(values, np.arange(start, start + block) % n) for start in starts])[:n]
        means[i] = sample.mean()
    return tuple(float(x) for x in np.quantile(means, [0.025, 0.975]))


def surrogate_p(values: np.ndarray, block: int, rng: np.random.Generator, reps: int = 500) -> float:
    n = len(values)
    observed = abs(float(values.mean()))
    exceed = 0
    for _ in range(reps):
        signs = np.repeat(rng.choice([-1.0, 1.0], math.ceil(n / block)), block)[:n]
        exceed += abs(float(np.mean(values * signs))) >= observed
    return (exceed + 1) / (reps + 1)


def metrics(frame: pd.DataFrame, horizon: int, *, seed_offset: int = 0) -> dict[str, Any]:
    values = frame["pnl"].to_numpy(float)
    n = len(values)
    if not n:
        return {"n": 0}
    lag = max(1, horizon - 1)
    se = hac_se(values, lag)
    mean = float(values.mean())
    standard = float(values.std(ddof=1)) if n > 1 else math.nan
    ac_sum = 0.0
    centered = values - mean
    denom = float(centered @ centered)
    if denom > 0:
        for k in range(1, min(lag, n - 1) + 1):
            ac_sum += max(0.0, float(centered[k:] @ centered[:-k]) / denom)
    effective_n = n / (1 + 2 * ac_sum)
    rng = np.random.default_rng(SEED + seed_offset)
    ci = block_bootstrap(values, max(5, horizon), rng)
    placebo = surrogate_p(values, max(5, horizon), rng)
    best_index = int(np.argmax(values))
    without_best = np.delete(values, best_index)
    years = max((frame.index.max() - frame.index.min()).days / 365.2425, 1 / 252)
    return {
        "n": n,
        "effective_n": float(effective_n),
        "mean_return": mean,
        "median_return": float(np.median(values)),
        "hac_standard_error": se,
        "hac_t_stat": mean / se if se and np.isfinite(se) else math.nan,
        "annualized_sharpe_event_sequence": mean / standard * math.sqrt(n / years) if standard > 0 else math.nan,
        "hit_rate": float(np.mean(values > 0)),
        "expected_magnitude": float(np.mean(np.abs(values))),
        "cumulative_return_arithmetic": float(values.sum()),
        "max_sequential_drawdown": max_drawdown(values),
        "worst_event": float(values.min()),
        "best_event": float(values.max()),
        "mean_without_best_event": float(without_best.mean()) if len(without_best) else math.nan,
        "bootstrap_95_ci_mean": list(ci),
        "block_sign_surrogate_p": placebo,
        "start": frame.index.min().date().isoformat(),
        "end": frame.index.max().date().isoformat(),
    }


def split_metrics(frame: pd.DataFrame, horizon: int, seed_offset: int) -> dict[str, Any]:
    return {
        name: metrics(frame.loc[start:end], horizon, seed_offset=seed_offset + i)
        for i, (name, (start, end)) in enumerate(SPLITS.items())
    }


def bh_adjust(p_values: list[float]) -> list[float]:
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty(len(p))
    running = 1.0
    for rank in range(len(p), 0, -1):
        idx = order[rank - 1]
        running = min(running, p[idx] * len(p) / rank)
        adjusted[idx] = running
    return adjusted.tolist()


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_experiments() -> list[Experiment]:
    def momentum(lb: int, horizon: int) -> Callable[[dict[str, pd.DataFrame]], pd.DataFrame]:
        def builder(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
            f = data["SPY"]
            signal = np.sign(f["close"] / f["close"].shift(lb) - 1)
            return result_frame(signal * forward_return(f, horizon), signal)
        return builder

    def reversal(lb: int, horizon: int) -> Callable[[dict[str, pd.DataFrame]], pd.DataFrame]:
        def builder(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
            f = data["SPY"]
            signal = -np.sign(f["close"] / f["close"].shift(lb) - 1)
            return result_frame(signal * forward_return(f, horizon), signal)
        return builder

    def capitulation(threshold: float) -> Callable[[dict[str, pd.DataFrame]], pd.DataFrame]:
        def builder(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
            f = data["SPY"]
            daily = f["close"].pct_change()
            return result_frame(forward_return(f, 5).where(daily <= threshold))
        return builder

    def gap(direction: float, sigma_threshold: float) -> Callable[[dict[str, pd.DataFrame]], pd.DataFrame]:
        def builder(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
            f = data["SPY"]
            gap_return = f["open"] / f["close"].shift(1) - 1
            sigma = f["close"].pct_change().rolling(22).std().shift(1)
            active = gap_return.abs() >= sigma_threshold * sigma
            pnl = direction * np.sign(gap_return) * (f["close"] / f["open"] - 1)
            return result_frame(pnl.where(active), direction * np.sign(gap_return))
        return builder

    def cross_section(kind: str) -> Callable[[dict[str, pd.DataFrame]], pd.DataFrame]:
        def builder(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
            symbols = ["SPY", "QQQ", "IWM", "DIA"]
            close = pd.concat({s: data[s]["close"] for s in symbols}, axis=1).dropna()
            next_return = close.shift(-1) / close - 1
            if kind == "reversal":
                score = close.pct_change().dropna()
                chosen = score.idxmin(axis=1)
            else:
                score = (close / close.shift(63) - 1).dropna()
                chosen = score.idxmax(axis=1)
            selected = pd.Series([next_return.loc[d, s] for d, s in chosen.items()], index=chosen.index)
            pnl = selected - next_return.mean(axis=1)
            return result_frame(pnl)
        return builder

    experiments = [
        Experiment("A01", "overnight", "Positive close-to-open drift", "Long SPY from prior adjusted close to adjusted open every session", "close-to-open return", 1, lambda d: result_frame(d["SPY"]["open"] / d["SPY"]["close"].shift(1) - 1)),
        Experiment("B01", "intraday", "Positive open-to-close drift", "Long SPY from adjusted open to adjusted close every session", "open-to-close return", 1, lambda d: result_frame(d["SPY"]["close"] / d["SPY"]["open"] - 1)),
        Experiment("C01", "momentum", "21-day momentum continues", "Sign of trailing 21-session SPY return times next 5-session return", "signed 5-session return", 5, momentum(21, 5)),
        Experiment("C02", "momentum", "63-day momentum continues", "Sign of trailing 63-session SPY return times next 21-session return", "signed 21-session return", 21, momentum(63, 21), "C01", "nearby horizon perturbation of C01"),
        Experiment("C03", "momentum", "126-day momentum continues", "Sign of trailing 126-session SPY return times next 21-session return", "signed 21-session return", 21, momentum(126, 21), "C02", "slower trend hypothesis"),
        Experiment("D01", "reversal", "One-day moves reverse", "Opposite sign of prior one-session SPY return times next one-session return", "signed 1-session return", 1, reversal(1, 1)),
        Experiment("D02", "reversal", "Five-day moves reverse", "Opposite sign of prior 5-session SPY return times next 5-session return", "signed 5-session return", 5, reversal(5, 5), "D01", "multi-day reversal perturbation"),
        Experiment("E01", "capitulation", "Large down days rebound", "Long SPY for 5 sessions after adjusted close return <= -2%", "5-session return", 5, capitulation(-0.02)),
        Experiment("E02", "capitulation", "Extreme down days rebound more", "Long SPY for 5 sessions after adjusted close return <= -3%", "5-session return", 5, capitulation(-0.03), "E01", "rarer fixed-threshold perturbation"),
        Experiment("H01", "trend_conditioned_reversal", "Selloffs above trend rebound", "Long SPY 5 sessions after <=-2% day only when prior close is above trailing 200-day MA", "5-session return", 5, lambda d: result_frame(forward_return(d["SPY"], 5).where((d["SPY"]["close"].pct_change() <= -0.02) & (d["SPY"]["close"].shift(1) > d["SPY"]["close"].rolling(200).mean().shift(1))))),
        Experiment("I01", "gap", "Large gaps continue intraday", "For absolute gap >= 1 trailing daily sigma, follow gap sign open-to-close", "signed open-to-close return", 1, gap(1.0, 1.0)),
        Experiment("I02", "gap", "Large gaps reverse intraday", "For absolute gap >= 1 trailing daily sigma, fade gap sign open-to-close", "signed open-to-close return", 1, gap(-1.0, 1.0), "I01", "opposite economically plausible gap hypothesis"),
        Experiment("I03", "gap", "Extreme gaps continue intraday", "For absolute gap >= 1.5 trailing daily sigma, follow gap sign open-to-close", "signed open-to-close return", 1, gap(1.0, 1.5), "I01", "rarer event perturbation"),
        Experiment("J01", "cross_sectional", "Worst broad ETF reverses", "Among SPY/QQQ/IWM/DIA, long prior-session worst performer for one session; score selected return minus contemporaneous equal-weight universe return", "selected ETF next-session return minus equal-weight baseline", 1, cross_section("reversal")),
        Experiment("J02", "cross_sectional", "Strongest broad ETF momentum continues", "Among SPY/QQQ/IWM/DIA, long strongest trailing-63-session performer for one session; score selected return minus contemporaneous equal-weight universe return", "selected ETF next-session return minus equal-weight baseline", 1, cross_section("momentum")),
    ]
    return experiments


def volatility_campaign(data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    f = data["SPY"]
    log_return = np.log(f["close"]).diff()
    variance = log_return.pow(2)
    target = variance.shift(-1).rolling(5).sum().shift(-4).pow(0.5)
    features = pd.DataFrame({
        "rv1": variance.pow(0.5),
        "rv5": variance.rolling(5).mean().pow(0.5),
        "rv22": variance.rolling(22).mean().pow(0.5),
    })
    panel = features.assign(target=target).dropna()
    start_oos = pd.Timestamp("2016-01-01")
    oos = panel.loc[start_oos:"2026-08-28"].copy()
    predictions: dict[str, list[float]] = {"har_ols": [], "har_ridge": [], "rv5_baseline": [], "rv22_baseline": []}
    actual: list[float] = []
    dates: list[pd.Timestamp] = []
    for date, row in oos.iterrows():
        train = panel.loc[: date - pd.Timedelta(days=1)]
        if len(train) < 500:
            continue
        x = train[["rv1", "rv5", "rv22"]].to_numpy()
        y = train["target"].to_numpy()
        mean = x.mean(axis=0)
        scale = x.std(axis=0) + 1e-12
        xs = (x - mean) / scale
        design = np.column_stack([np.ones(len(xs)), xs])
        now = np.r_[1.0, (row[["rv1", "rv5", "rv22"]].to_numpy(float) - mean) / scale]
        ols = np.linalg.lstsq(design, y, rcond=None)[0]
        penalty = np.diag([0.0, 10.0, 10.0, 10.0])
        ridge = np.linalg.solve(design.T @ design + penalty, design.T @ y)
        predictions["har_ols"].append(float(max(0, now @ ols)))
        predictions["har_ridge"].append(float(max(0, now @ ridge)))
        predictions["rv5_baseline"].append(float(math.sqrt(5) * row["rv5"]))
        predictions["rv22_baseline"].append(float(math.sqrt(5) * row["rv22"]))
        actual.append(float(row["target"]))
        dates.append(date)
    y = np.asarray(actual)
    unconditional = float(panel.loc[:"2015-12-31", "target"].mean())
    baseline_sse = float(np.sum((y - unconditional) ** 2))
    results: dict[str, Any] = {}
    for name, raw in predictions.items():
        pred = np.asarray(raw)
        results[name] = {
            "oos_start": dates[0].date().isoformat(), "oos_end": dates[-1].date().isoformat(),
            "n": len(y), "correlation": float(np.corrcoef(pred, y)[0, 1]),
            "mae": float(np.mean(np.abs(pred - y))),
            "oos_r2_vs_pre2016_unconditional_mean": float(1 - np.sum((y - pred) ** 2) / baseline_sse),
            "mean_prediction": float(pred.mean()), "mean_actual": float(y.mean()),
        }
    best = max(results, key=lambda name: results[name]["oos_r2_vs_pre2016_unconditional_mean"])
    return {
        "target": "sqrt(sum of next 5 daily squared log returns)",
        "causal_features": ["current absolute log return", "trailing 5-day RMS return", "trailing 22-day RMS return"],
        "walk_forward": "expanding window, refit using only dates strictly before each prediction",
        "models": results, "best_model": best,
        "simple_baseline_winner": best in {"rv5_baseline", "rv22_baseline"},
    }


def main() -> None:
    data = {symbol: load(symbol) for symbol in ("SPY", "QQQ", "IWM", "DIA", "^GSPC")}
    experiments = build_experiments()
    ledger: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for offset, experiment in enumerate(experiments):
        frame = experiment.build(data).sort_index()
        frames[experiment.experiment_id] = frame
        full = metrics(frame, experiment.horizon, seed_offset=offset * 20)
        splits = split_metrics(frame, experiment.horizon, offset * 20 + 5)
        ledger.append({
            "experiment_id": experiment.experiment_id, "parent_experiment": experiment.parent,
            "family": experiment.family, "hypothesis": experiment.hypothesis,
            "source_research_motivation": experiment.motivation, "exact_signal_definition": experiment.definition,
            "exact_target": experiment.target, "horizon_sessions": experiment.horizon,
            "code": "scripts/long_history_campaign.py", "random_seed": SEED,
            "data_cutoff": "2026-08-28", "splits": SPLITS,
            "full_history_metrics": full, "period_metrics": splits,
            "failure_reason": None, "next_hypothesis": None,
        })
    p_values = [entry["full_history_metrics"]["block_sign_surrogate_p"] for entry in ledger]
    q_values = bh_adjust(p_values)
    for entry, q_value in zip(ledger, q_values, strict=True):
        entry["selection_bias_control"] = {
            "family": "all registered directional/event hypotheses", "benjamini_hochberg_q": q_value,
            "fdr_threshold": 0.10, "passes_fdr": q_value <= 0.10,
        }
        holdout = entry["period_metrics"]["sealed_historical_holdout"]
        reasons = []
        if holdout.get("n", 0) < 30:
            reasons.append("fewer than 30 sealed-holdout decisions")
        if holdout.get("bootstrap_95_ci_mean", [-1])[0] <= 0:
            reasons.append("sealed-holdout block-bootstrap CI includes zero")
        if q_value > 0.10:
            reasons.append("fails 10% BH-FDR selection-bias control")
        if entry["full_history_metrics"]["mean_without_best_event"] <= 0:
            reasons.append("mean nonpositive after removing best event")
        entry["failure_reason"] = "; ".join(reasons) or None
        entry["long_history_supported_pre_drop_one"] = not reasons
    def evidence_rank(entry: dict[str, Any]) -> tuple[bool, bool, bool, float]:
        holdout = entry["period_metrics"]["sealed_historical_holdout"]
        return (
            entry["failure_reason"] is None,
            entry["selection_bias_control"]["passes_fdr"],
            holdout.get("n", 0) >= 30,
            holdout.get("hac_t_stat") or -99.0,
        )

    ranked = sorted(ledger, key=evidence_rank, reverse=True)
    finalists = ranked[:5]
    regime_results: dict[str, Any] = {"era_definitions": ERAS, "drop_windows": DROP_WINDOWS, "signals": {}}
    for offset, entry in enumerate(finalists):
        frame = frames[entry["experiment_id"]]
        horizon = entry["horizon_sessions"]
        all_history = metrics(frame, horizon, seed_offset=1000 + offset * 30)
        by_era = {name: metrics(frame.loc[start:end], horizon, seed_offset=1100 + offset * 30 + i) for i, (name, (start, end)) in enumerate(ERAS.items())}
        drop_one = {}
        for i, (name, (start, end)) in enumerate(DROP_WINDOWS.items()):
            reduced = frame.loc[(frame.index < start) | (frame.index > end)]
            drop_one[name] = metrics(reduced, horizon, seed_offset=1200 + offset * 30 + i)
        perturbation_ids = [x["experiment_id"] for x in ledger if x["family"] == entry["family"] and x["experiment_id"] != entry["experiment_id"]]
        robust = all(result.get("mean_return", -1) > 0 for result in drop_one.values())
        entry["drop_one_era_positive_all"] = robust
        entry["parameter_perturbations"] = perturbation_ids
        if not robust:
            entry["long_history_supported"] = False
            entry["failure_reason"] = "; ".join(filter(None, [entry["failure_reason"], "negative in at least one drop-one-era test"]))
        else:
            entry["long_history_supported"] = entry["long_history_supported_pre_drop_one"]
        regime_results["signals"][entry["experiment_id"]] = {"all_history": all_history, "by_era": by_era, "drop_one_era": drop_one, "parameter_perturbations": perturbation_ids}
    finalist_ids = {x["experiment_id"] for x in finalists}
    for entry in ledger:
        if entry["experiment_id"] not in finalist_ids:
            entry["long_history_supported"] = False
            entry["drop_one_era_positive_all"] = None
    volatility = volatility_campaign(data)
    leaderboard = {
        "generated_by": "scripts/long_history_campaign.py", "random_seed": SEED,
        "data_cutoff": "2026-08-28", "predeclared_splits": SPLITS,
        "ranking_rule": "evidence gates (holdout CI/N, FDR, remove-best), then sealed-holdout HAC t-stat; never used to refit parameters",
        "multiple_testing": "Benjamini-Hochberg FDR across all 15 registered return hypotheses plus block-sign surrogate nulls; q<=0.10",
        "signals": [{key: value for key, value in entry.items() if key not in {"code"}} for entry in ranked],
        "volatility_campaign": volatility,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "experiment_ledger.json").write_text(json.dumps(json_safe(ledger), indent=2, allow_nan=False) + "\n")
    (ROOT / "signal_leaderboard.json").write_text(json.dumps(json_safe(leaderboard), indent=2, allow_nan=False) + "\n")
    (ROOT / "regime_results.json").write_text(json.dumps(json_safe(regime_results), indent=2, allow_nan=False) + "\n")
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / "experiment_ledger.json", ROOT / "signal_leaderboard.json", ROOT / "regime_results.json")}
    print(json.dumps({"experiments": len(ledger), "top_five": [x["experiment_id"] for x in finalists], "best_volatility": volatility["best_model"], "hashes": hashes}, indent=2))


if __name__ == "__main__":
    main()
