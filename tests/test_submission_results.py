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

    result = build_results(manifest, historical, economics, leaderboard)

    assert result["sealed_forward"]["status"] == "IN_PROGRESS"
    assert result["development"]["diagnostic"]["mean_round_trip_crossing_cost_usd"] == 25
    incremental = result["historical"]["volatility"]["incremental_correlation_from_disagreement"]
    assert incremental == pytest.approx(0.01)
    markdown = render_markdown(result)
    assert "HISTORICAL" in markdown
    assert "DEVELOPMENT" in markdown
    assert "SEALED FORWARD" in markdown
    assert "PAPER EXECUTION" in markdown
