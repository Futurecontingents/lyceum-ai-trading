#!/usr/bin/env python3
"""Screen only causal rare states large enough to approach observed option hurdles."""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd
from long_history_bridge import load_sessions
from long_history_campaign import ERAS, ROOT, hac_se, load

SEED = 20260902
OUTPUT = ROOT / "high_magnitude_states.json"


def bootstrap_ci(values: np.ndarray, *, block: int = 5, reps: int = 1000) -> list[float | None]:
    values = values[np.isfinite(values)]
    if len(values) < 10:
        return [None, None]
    rng = np.random.default_rng(SEED + len(values))
    means = []
    for _ in range(reps):
        starts = rng.integers(0, len(values), math.ceil(len(values) / block))
        sample = np.concatenate([np.take(values, np.arange(start, start + block) % len(values)) for start in starts])[: len(values)]
        means.append(float(sample.mean()))
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def summarize(
    *, identifier: str, family: str, definition: str, target: str,
    frame: pd.DataFrame, hurdle: float, reference_spot: float, source: str,
    recent_start: str = "2024-01-01",
) -> dict[str, Any]:
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["absolute_return", "signed_return"])
    absolute = frame["absolute_return"].to_numpy(float) * reference_spot
    signed = frame["signed_return"].to_numpy(float)
    n = len(frame)
    signed_se = hac_se(signed, 4) if n else math.nan
    recent = frame.loc[recent_start:]
    era_rows = {}
    stable_positive = 0
    eligible_eras = 0
    for name, (start, end) in ERAS.items():
        values = frame.loc[start:end]
        if len(values) >= 5:
            eligible_eras += 1
            stable_positive += float(values["signed_return"].mean()) > 0
        era_rows[name] = {
            "n": len(values),
            "mean_absolute_move_dollars": float(values["absolute_return"].mean() * reference_spot) if len(values) else None,
            "mean_signed_return": float(values["signed_return"].mean()) if len(values) else None,
        }
    expected = float(np.mean(absolute)) if n else None
    absolute_ci = bootstrap_ci(absolute)
    signed_ci = bootstrap_ci(signed)
    effective_n = n / 5 if n else 0.0
    signed_dollars = float(np.mean(signed) * reference_spot) if n else None
    ratio = max(0.0, signed_dollars) / hurdle if signed_dollars is not None else None
    recent_signed = float(recent["signed_return"].mean()) if len(recent) else None
    recent_confirmed = len(recent) >= 10 and recent_signed is not None and recent_signed > 0
    plausible = (
        n >= 30 and effective_n >= 20 and ratio is not None and ratio >= 1.25
        and absolute_ci[0] is not None and absolute_ci[0] / hurdle >= 0.5
        and signed_ci[0] is not None and signed_ci[0] > 0
        and eligible_eras >= 3 and stable_positive / eligible_eras >= 0.6
        and recent_confirmed
    )
    return {
        "state_id": identifier, "family": family, "exact_causal_definition": definition,
        "exact_target": target, "source": source, "n": n, "effective_n_conservative_n_over_5": effective_n,
        "current_reference_spot_dollars": reference_spot,
        "conditional_expected_absolute_move_dollars": expected,
        "absolute_move_block_bootstrap_95_ci_dollars": absolute_ci,
        "conditional_signed_edge": float(np.mean(signed)) if n else None,
        "conditional_signed_edge_dollars_at_reference_spot": signed_dollars,
        "signed_edge_hac_standard_error": signed_se if math.isfinite(signed_se) else None,
        "signed_edge_block_bootstrap_95_ci": signed_ci,
        "hit_rate": float(np.mean(signed > 0)) if n else None,
        "actual_option_cost_hurdle_dollars": hurdle,
        "expected_move_to_cost_hurdle_ratio": ratio,
        "regime_stability": {
            "eligible_eras": eligible_eras, "positive_signed_edge_eras": stable_positive,
            "positive_fraction": stable_positive / eligible_eras if eligible_eras else None, "by_era": era_rows,
        },
        "recent_intraday_confirmation": {
            "start": recent_start, "n": len(recent),
            "mean_absolute_move_dollars": float(recent["absolute_return"].mean() * reference_spot) if len(recent) else None,
            "mean_signed_return": recent_signed, "confirmed": recent_confirmed,
        },
        "option_plausible_and_statistically_promotable": plausible,
        "failure_reason": None if plausible else "fails one or more preregistered magnitude, signed-CI, effective-N, regime, or recent-confirmation gates",
    }


def daily_states(spy_hurdle: float) -> list[dict[str, Any]]:
    spy = load("SPY")
    reference_spot = float(spy["close"].tail(252).median())
    prior_close = spy["close"].shift(1)
    gap = spy["open"] / prior_close - 1
    open_close = spy["close"] / spy["open"] - 1
    daily = spy["close"].pct_change()
    log_return = np.log(spy["close"]).diff()
    rv_ratio = log_return.pow(2).rolling(5).mean().pow(0.5) / log_return.pow(2).rolling(22).mean().pow(0.5)
    states = []
    for threshold in (0.015, 0.02, 0.03):
        active = gap.abs() >= threshold
        frame = pd.DataFrame({
            "absolute_return": open_close.abs().where(active),
            "signed_return": (np.sign(gap) * open_close).where(active),
        })
        states.append(summarize(
            identifier=f"GAP_CONT_{threshold:.3f}", family="extreme_overnight_gap",
            definition=f"At regular-session open, absolute SPY gap from prior adjusted close >= {threshold:.1%}; follow gap direction to close",
            target="same-session open-to-close continuation return and dollar movement", frame=frame,
            hurdle=spy_hurdle, reference_spot=reference_spot, source="SPY daily adjusted OHLC",
        ))
    for threshold in (-0.02, -0.03, -0.05):
        active = daily.shift(1) <= threshold
        frame = pd.DataFrame({
            "absolute_return": open_close.abs().where(active),
            "signed_return": open_close.where(active),
        })
        states.append(summarize(
            identifier=f"CAPITULATION_{abs(threshold):.2f}", family="capitulation",
            definition=f"Prior adjusted SPY close return <= {threshold:.0%}; enter long at next regular-session open and exit close",
            target="next-session open-to-close long return and dollar movement", frame=frame,
            hurdle=spy_hurdle, reference_spot=reference_spot, source="SPY daily adjusted OHLC",
        ))
    for threshold in (1.5, 1.75):
        active = rv_ratio.shift(1) >= threshold
        frame = pd.DataFrame({
            "absolute_return": open_close.abs().where(active),
            "signed_return": (np.sign(daily.shift(1)) * open_close).where(active),
        })
        states.append(summarize(
            identifier=f"RV_SHOCK_CONT_{threshold:.2f}", family="volatility_shock",
            definition=f"Prior trailing-5-day RMS / trailing-22-day RMS >= {threshold:.2f}; follow prior daily direction next open-to-close",
            target="next-session open-to-close continuation return and dollar movement", frame=frame,
            hurdle=spy_hurdle, reference_spot=reference_spot, source="SPY daily adjusted OHLC",
        ))
    return states


def intraday_states(hurdles: dict[str, float]) -> list[dict[str, Any]]:
    states = []
    for symbol in ("SPY", "QQQ", "AAPL", "NVDA", "AMD", "META", "TSLA"):
        sessions = load_sessions(symbol)
        reference_spot = float(sessions["close"].tail(252).median())
        first_hour = sessions["close_60m"] / sessions["open"] - 1
        after_hour = sessions["close"] / sessions["close_60m"] - 1
        hurdle = hurdles[symbol]
        for threshold in (0.01, 0.02):
            active = first_hour.abs() >= threshold
            for mode, sign in (("CONT", 1.0), ("REV", -1.0)):
                frame = pd.DataFrame({
                    "absolute_return": after_hour.abs().where(active),
                    "signed_return": (sign * np.sign(first_hour) * after_hour).where(active),
                })
                states.append(summarize(
                    identifier=f"{symbol}_FIRST_HOUR_{mode}_{threshold:.2f}", family="extreme_first_hour",
                    definition=f"At 10:30 ET, absolute {symbol} open-to-60m move >= {threshold:.0%}; {'follow' if mode == 'CONT' else 'fade'} direction to close",
                    target="10:30 ET-to-close signed return and dollar movement", frame=frame,
                    hurdle=hurdle, reference_spot=reference_spot,
                    source=f"Alpaca IEX raw 5-minute {symbol} bars", recent_start="2024-01-01",
                ))
    return states


def main() -> None:
    bridge = json.loads((ROOT / "option_bridge.json").read_text())
    hurdle_rows = bridge["option_economics"]["directional_break_even"]["by_symbol"]
    hurdles = {row["symbol"]: row["median_break_even_spot_move_dollars"] for row in hurdle_rows}
    states = daily_states(hurdles["SPY"]) + intraday_states(hurdles)
    ranked = sorted(states, key=lambda item: item["expected_move_to_cost_hurdle_ratio"] or -1, reverse=True)
    promoted = [item for item in ranked if item["option_plausible_and_statistically_promotable"]][:3]
    payload = {
        "generated_by": "scripts/high_magnitude_state_screen.py", "data_cutoff": "2026-08-28",
        "selection_rule": "rank positive expected signed return at current reference spot / symbol-specific observed median delta-adjusted directional-vertical hurdle; absolute movement is reported separately; promotion also requires signed CI, effective N, regime stability, and recent confirmation",
        "states_tested": len(states), "trade_producing_candidates": promoted,
        "ranked_states": ranked,
        "untestable_state_families": [{
            "family": "major catalyst/news",
            "reason": "no long-history point-in-time causal news/event dataset; council/news outputs cannot be retrofitted",
        }],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"states_tested": len(states), "best": ranked[0]["state_id"], "best_ratio": ranked[0]["expected_move_to_cost_hurdle_ratio"], "promoted": [x["state_id"] for x in promoted]}, indent=2))


if __name__ == "__main__":
    main()
