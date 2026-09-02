import pytest

from scripts.build_submission_results import build_results, render_markdown


def test_submission_results_keep_evidence_layers_separate() -> None:
    manifest = {
        "generated_at": "2026-09-01T00:00:00+00:00",
        "sealed_session": "2026-09-01",
        "status": "FROZEN",
        "walk_forward": "chronological with purge",
        "candidates": [{"id": letter} for letter in "ABCDE"],
    }
    historical = {
        "best_vol_horizon": 60,
        "best_momentum": {"directional_hit_rate": 0.49},
        "best_reversal": {"directional_hit_rate": 0.505},
        "dataset": {"bars": 10, "sessions": 2, "start": "a", "end": "b", "symbols": ["SPY"]},
        "volatility_models": {
            "60": {
                "walk_forward": {"correlation": 0.78, "mae": 0.0014},
                "benchmarks": {"ridge_without_disagreement": {"correlation": 0.77, "mae": 0.0015}},
            }
        },
    }
    economics = {
        "data_cutoff_exclusive": "2026-09-01T00:00:00-04:00",
        "limitations": ["one day"],
        "directional_by_signal_horizon": [
            {
                "signal": "rev5",
                "horizon": 60,
                "n": 2,
                "midpoint_pnl": 10,
                "entry_crossing": 20,
                "exit_crossing": 30,
                "mean_executable_pnl": -20,
            }
        ],
    }
    leaderboard = {"updated_at": "2026-09-01T12:00:00+00:00", "leaderboard": []}
    long_history = {
        "signals": [
            {
                "experiment_id": "A01",
                "full_history_metrics": {"n": 8_452, "mean_return": 0.0004, "hac_t_stat": 5.82},
                "long_history_supported": True,
            }
        ],
        "volatility_event_hypotheses": [],
        "volatility_campaign": {
            "models": {
                "har_ridge": {"n": 2_674, "correlation": 0.676, "mae": 0.0072, "oos_r2_vs_pre2016_unconditional_mean": 0.464}
            }
        },
    }
    option_bridge = {
        "option_economics": {
            "observations": 9_627,
            "pnl_diagnostics_by_structure": {"directional_vertical": {"n": 4_878}},
            "directional_break_even": {"median_spot_move_dollars": 4.44},
            "best_supported_signal_comparison": {
                "recent_underlying_mean_move_dollars_at_recent_median_spot": 0.44,
                "magnitude_to_cost_hurdle_ratio": 0.098,
                "plausibly_clears": False,
            },
        }
    }
    data_manifest = {
        "instruments": [
            {"symbol": "SPY", "sessions": 8_453, "calendar_years": 33.58, "start": "1993-01-29", "end": "2026-08-28"},
            {"symbol": "^GSPC", "sessions": 14_286, "calendar_years": 56.65, "start": "1970-01-02", "end": "2026-08-28"},
        ]
    }
    sep03_manifest = {
        "frozen_at": "2026-09-02T12:46:30Z",
        "status": "FROZEN",
        "mode": "READ_ONLY_SHADOW",
        "order_submission": "PROHIBITED",
        "candidates": [{"trade_producing": False}],
    }

    result = build_results(
        manifest,
        historical,
        economics,
        leaderboard,
        long_history,
        option_bridge,
        data_manifest,
        sep03_manifest,
    )

    assert result["sealed_forward"]["status"] == "INVALID_INCIDENT_PRESERVED"
    assert result["sealed_forward"]["scored_decisions"] is None
    assert result["development"]["diagnostic"]["mean_round_trip_crossing_cost_usd"] == 25
    incremental = result["historical"]["volatility"]["incremental_correlation_from_disagreement"]
    assert incremental == pytest.approx(0.01)
    assert result["long_history"]["a01"]["supported"] is True
    assert result["option_execution"]["plausibly_clears"] is False
    markdown = render_markdown(result)
    assert "HISTORICAL" in markdown
    assert "DEVELOPMENT" in markdown
    assert "SEALED FORWARD" in markdown
    assert "PAPER EXECUTION" in markdown
