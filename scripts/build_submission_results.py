#!/usr/bin/env python3
"""Build sanitized, layered public submission results from frozen artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_results(
    manifest: dict[str, Any],
    historical: dict[str, Any],
    economics: dict[str, Any],
    leaderboard: dict[str, Any],
    long_history: dict[str, Any],
    option_bridge: dict[str, Any],
    data_manifest: dict[str, Any],
    sep03_manifest: dict[str, Any],
) -> dict[str, Any]:
    vol = historical["volatility_models"][str(historical["best_vol_horizon"])]
    vol_full = vol["walk_forward"]
    vol_without = vol["benchmarks"]["ridge_without_disagreement"]
    diagnostic = next(
        row
        for row in economics["directional_by_signal_horizon"]
        if row["signal"] == "rev5" and row["horizon"] == 60
    )
    n = int(diagnostic["n"])
    entry = float(diagnostic["entry_crossing"])
    exit_ = float(diagnostic["exit_crossing"])
    spy = next(item for item in data_manifest["instruments"] if item["symbol"] == "SPY")
    sp500 = next(item for item in data_manifest["instruments"] if item["symbol"] == "^GSPC")
    a01 = next(item for item in long_history["signals"] if item["experiment_id"] == "A01")
    har = long_history["volatility_campaign"]["models"]["har_ridge"]
    bridge = option_bridge["option_economics"]

    return {
        "schema_version": 1,
        "generated_at": sep03_manifest["frozen_at"],
        "claim_policy": (
            "Historical association, development diagnostics, sealed forward evidence, "
            "and paper execution are separate layers. No profitability claim."
        ),
        "historical": {
            "label": "HISTORICAL",
            "status": "COMPLETED",
            "dataset": historical["dataset"],
            "walk_forward": manifest["walk_forward"],
            "direction": {
                "best_momentum_hit_rate": historical["best_momentum"]["directional_hit_rate"],
                "best_reversal_hit_rate": historical["best_reversal"]["directional_hit_rate"],
                "conclusion": "Directional performance is weak and not an executable edge claim.",
            },
            "volatility": {
                "horizon_minutes": historical["best_vol_horizon"],
                "correlation": vol_full["correlation"],
                "mae": vol_full["mae"],
                "without_disagreement_correlation": vol_without["correlation"],
                "without_disagreement_mae": vol_without["mae"],
                "incremental_correlation_from_disagreement": (
                    vol_full["correlation"] - vol_without["correlation"]
                ),
                "conclusion": "Realized volatility is more predictable; disagreement adds modest information.",
            },
        },
        "long_history": {
            "label": "LONG-HISTORY EVIDENCE",
            "status": "COMPLETED",
            "spy": {
                "sessions": spy["sessions"],
                "calendar_years": spy["calendar_years"],
                "start": spy["start"],
                "end": spy["end"],
            },
            "sp500_proxy": {
                "sessions": sp500["sessions"],
                "calendar_years": sp500["calendar_years"],
                "start": sp500["start"],
                "end": sp500["end"],
                "limitation": "Regime context only; not tradeable option history.",
            },
            "registered_hypotheses": len(long_history["signals"]) + len(long_history["volatility_event_hypotheses"]),
            "a01": {
                "n": a01["full_history_metrics"]["n"],
                "mean_return": a01["full_history_metrics"]["mean_return"],
                "hac_t_stat": a01["full_history_metrics"]["hac_t_stat"],
                "supported": a01["long_history_supported"],
            },
            "har": {
                "n": har["n"],
                "correlation": har["correlation"],
                "mae": har["mae"],
                "oos_r2": har["oos_r2_vs_pre2016_unconditional_mean"],
            },
        },
        "option_execution": {
            "label": "REAL OPTION EXECUTION ECONOMICS",
            "status": "DEVELOPMENT_DIAGNOSTIC",
            "observations": bridge["observations"],
            "directional_structures": bridge["pnl_diagnostics_by_structure"]["directional_vertical"]["n"],
            "median_spot_hurdle_usd": bridge["directional_break_even"]["median_spot_move_dollars"],
            "a01_expected_move_usd": bridge["best_supported_signal_comparison"]["recent_underlying_mean_move_dollars_at_recent_median_spot"],
            "a01_move_to_cost_ratio": bridge["best_supported_signal_comparison"]["magnitude_to_cost_hurdle_ratio"],
            "plausibly_clears": bridge["best_supported_signal_comparison"]["plausibly_clears"],
            "conclusion": "Statistical predictability did not survive the observed quoted-side option hurdle.",
        },
        "development": {
            "label": "DEVELOPMENT DIAGNOSTIC — NOT HOLDOUT",
            "status": "FROZEN_PREMARKET",
            "data_cutoff_exclusive": economics["data_cutoff_exclusive"],
            "sample": "2026-08-31 captured option quotes; one late-session date",
            "diagnostic": {
                "signal": "five-minute reversal",
                "holding_minutes": 60,
                "structure_observations": n,
                "mean_midpoint_pnl_usd": diagnostic["midpoint_pnl"] / n,
                "mean_entry_crossing_cost_usd": entry / n,
                "mean_exit_crossing_cost_usd": exit_ / n,
                "mean_round_trip_crossing_cost_usd": (entry + exit_) / n,
                "mean_conservative_executable_pnl_usd": diagnostic["mean_executable_pnl"],
                "conclusion": "A positive midpoint diagnostic became strongly negative at quoted sides.",
            },
            "limitations": economics["limitations"],
        },
        "sealed_forward": {
            "label": "SEALED FORWARD",
            "status": "INVALID_INCIDENT_PRESERVED",
            "session": manifest["sealed_session"],
            "manifest_status": manifest["status"],
            "candidates": [candidate["id"] for candidate in manifest["candidates"]],
            "signals": None,
            "trades": None,
            "scored_decisions": None,
            "orders": "PROHIBITED",
            "interpretation": (
                "The complete A-E comparison is invalid: C/D lacked required live council features, "
                "and sub-60-minute MFE/MAE contained lookahead. The failed run is not reranked."
            ),
        },
        "forward_after_incident": {
            "sep02": "Pre-open execution-economics diagnostic only; no trade-producing sealed candidate promoted.",
            "sep03": {
                "status": sep03_manifest["status"],
                "mode": sep03_manifest["mode"],
                "frozen_at": sep03_manifest["frozen_at"],
                "order_submission": sep03_manifest["order_submission"],
                "trade_producing_candidates": sum(item["trade_producing"] for item in sep03_manifest["candidates"]),
                "interpretation": "Observation-only future evidence; static preflight passed and live canary remains session-time evidence.",
            },
        },
        "paper_execution": {
            "label": "PAPER EXECUTION",
            "status": "NO_PUBLIC_PERFORMANCE_RESULT_CLAIMED",
            "fresh_account_initial_equity_usd": 100000,
            "submitted_during_submission_validation": 0,
            "interpretation": "Validation submitted no orders; broker credentials and account state remain private.",
        },
        "sources": {
            "manifest": "research/forward_test_2026-09-01.json",
            "historical": "artifacts/forward_test/historical_signal_results.json (machine-local input)",
            "development": "artifacts/nextgen_research/option_economics_preopen_freeze_2026-09-01.json (machine-local input)",
            "leaderboard": "artifacts/forward_test/live_leaderboard.json (machine-local input)",
            "long_history": "artifacts/long_history/signal_leaderboard.json",
            "option_bridge": "artifacts/long_history/option_bridge.json",
            "data_manifest": "artifacts/long_history/data_manifest.json",
            "sep03_manifest": "research/forward_test_2026-09-03.json",
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    hist = result["historical"]
    long = result["long_history"]
    execution = result["option_execution"]
    dev = result["development"]
    diag = dev["diagnostic"]
    forward = result["sealed_forward"]
    paper = result["paper_execution"]
    after = result["forward_after_incident"]
    dataset = hist["dataset"]
    vol = hist["volatility"]
    return f"""# Lyceum Current Results

Generated from frozen or append-only machine artifacts at `{result['generated_at']}`.

> {result['claim_policy']}

## LONG-HISTORY — {long['status']}

- SPY: **{long['spy']['sessions']:,}** sessions / **{long['spy']['calendar_years']:.2f} years**, {long['spy']['start']} through {long['spy']['end']}
- S&P 500 proxy: **{long['sp500_proxy']['sessions']:,}** sessions / **{long['sp500_proxy']['calendar_years']:.2f} years** ({long['sp500_proxy']['limitation']})
- Registered hypotheses: **{long['registered_hypotheses']}**
- Close-to-open SPY drift: N={long['a01']['n']:,}, mean {long['a01']['mean_return']:.4%}, HAC t={long['a01']['hac_t_stat']:.2f}, supported={str(long['a01']['supported']).upper()}
- HAR ridge volatility forecast: OOS N={long['har']['n']:,}, correlation {long['har']['correlation']:.3f}, OOS R² {long['har']['oos_r2']:.3f}

Conclusion: Underlying drift and volatility predictability are supported. Neither is automatically executable option alpha.

## HISTORICAL — {hist['status']}

- Dataset: **{dataset['bars']:,}** five-minute bars, **{dataset['sessions']}** sessions, {dataset['start']} through {dataset['end']}
- Symbols: {', '.join(dataset['symbols'])}
- Split: {hist['walk_forward']}
- Best tested momentum directional hit rate: **{hist['direction']['best_momentum_hit_rate']:.2%}**
- Best tested reversal directional hit rate: **{hist['direction']['best_reversal_hit_rate']:.2%}**
- {vol['horizon_minutes']}-minute realized-volatility correlation: **{vol['correlation']:.3f}**
- Same volatility model without disagreement: **{vol['without_disagreement_correlation']:.3f}**
- Incremental correlation from disagreement: **{vol['incremental_correlation_from_disagreement']:+.3f}**

Conclusion: {hist['direction']['conclusion']} {vol['conclusion']}

## DEVELOPMENT — {dev['status']}

This is an execution-economics diagnostic from one captured late-session option date, **not** an untouched holdout.

- Signal/hold: {diag['signal']}, {diag['holding_minutes']} minutes
- Structure observations: {diag['structure_observations']:,}
- Mean midpoint P&L: **${diag['mean_midpoint_pnl_usd']:+.2f}**
- Mean entry crossing cost: **${diag['mean_entry_crossing_cost_usd']:.2f}**
- Mean exit crossing cost: **${diag['mean_exit_crossing_cost_usd']:.2f}**
- Mean round-trip crossing cost: **${diag['mean_round_trip_crossing_cost_usd']:.2f}**
- Mean conservative executable P&L: **${diag['mean_conservative_executable_pnl_usd']:+.2f}**

Conclusion: {diag['conclusion']} The sample is too narrow for a production claim.

## OPTION EXECUTION — {execution['status']}

- Point-in-time option structures: **{execution['observations']:,}**
- Directional structures: **{execution['directional_structures']:,}**
- Median delta-adjusted spot hurdle: **${execution['median_spot_hurdle_usd']:.2f}**
- A01 expected recent SPY move: **${execution['a01_expected_move_usd']:.2f}**
- Expected move / cost hurdle: **{execution['a01_move_to_cost_ratio']:.3f}**
- Economically clears: **{str(execution['plausibly_clears']).upper()}**

Conclusion: {execution['conclusion']}

## SEALED FORWARD — {forward['status']}

- Session: {forward['session']}
- Candidates: {', '.join(forward['candidates'])}
- Order submission: {forward['orders']}

{forward['interpretation']}

The original artifacts are preserved. Infrastructure repairs do not repair the failed experiment, and no clean sealed rerun has completed.

## FORWARD EVIDENCE AFTER THE INCIDENT

- Sep-02: {after['sep02']}
- Sep-03: **{after['sep03']['status']} / {after['sep03']['mode']}**, frozen {after['sep03']['frozen_at']}; trade-producing candidates: {after['sep03']['trade_producing_candidates']}; orders: {after['sep03']['order_submission']}.

{after['sep03']['interpretation']} One or two sessions remain anecdotal evidence, not statistical proof.

## PAPER EXECUTION — {paper['status']}

- Fresh judging baseline: **${paper['fresh_account_initial_equity_usd']:,}**
- Orders submitted during submission validation: **{paper['submitted_during_submission_validation']}**
- No public paper P&L or profitability claim is made.

## Reproduce

```bash
python scripts/build_submission_results.py
```

Machine-local source artifacts are preserved for audit; deliberately sanitized long-history summaries and frozen public manifests are tracked. This generated summary contains no credentials or account identifiers.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("research/forward_test_2026-09-01.json"))
    parser.add_argument("--historical", type=Path, default=Path("artifacts/forward_test/historical_signal_results.json"))
    parser.add_argument("--economics", type=Path, default=Path("artifacts/nextgen_research/option_economics_preopen_freeze_2026-09-01.json"))
    parser.add_argument("--leaderboard", type=Path, default=Path("artifacts/forward_test/live_leaderboard.json"))
    parser.add_argument("--long-history", type=Path, default=Path("artifacts/long_history/signal_leaderboard.json"))
    parser.add_argument("--option-bridge", type=Path, default=Path("artifacts/long_history/option_bridge.json"))
    parser.add_argument("--data-manifest", type=Path, default=Path("artifacts/long_history/data_manifest.json"))
    parser.add_argument("--sep03-manifest", type=Path, default=Path("research/forward_test_2026-09-03.json"))
    parser.add_argument("--json-output", type=Path, default=Path("artifacts/submission/current_results.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("artifacts/submission/current_results.md"))
    args = parser.parse_args()

    result = build_results(
        load_json(args.manifest),
        load_json(args.historical),
        load_json(args.economics),
        load_json(args.leaderboard),
        load_json(args.long_history),
        load_json(args.option_bridge),
        load_json(args.data_manifest),
        load_json(args.sep03_manifest),
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")


if __name__ == "__main__":
    main()
