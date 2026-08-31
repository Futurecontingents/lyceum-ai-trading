from __future__ import annotations

from scripts.quant_research import chronological_split, metrics


def test_chronological_split_has_purge_embargo_and_untouched_holdout() -> None:
    split = chronological_split(list(range(1, 25)))
    assert split.train == tuple(range(1, 12))
    assert split.purged == (12, 13)
    assert split.validation == (14, 15, 16)
    assert split.embargoed == (17, 18)
    assert split.holdout == (19, 20, 21, 22)
    assert not (set(split.train) | set(split.validation)) & set(split.holdout)


def test_metrics_uses_sequential_peak_to_trough_drawdown() -> None:
    class C:
        def __init__(self, symbol: str, completed_at: str) -> None:
            self.symbol = symbol
            self.completed_at = completed_at
            self.crossing_cost = 1.0
            self.max_loss = 100.0

    rows = [
        {"candidate": C("SPY", "2026-01-01T00:00:00+00:00"), "pnl_5": 10.0, "stress_5": 8.0, "adverse_5": 6.0},
        {"candidate": C("QQQ", "2026-01-01T00:01:00+00:00"), "pnl_5": -15.0, "stress_5": -17.0, "adverse_5": -19.0},
        {"candidate": C("SPY", "2026-01-01T00:02:00+00:00"), "pnl_5": 3.0, "stress_5": 1.0, "adverse_5": -1.0},
    ]
    result = metrics(rows)
    assert result["total_pnl"] == -2.0
    assert result["max_drawdown"] == 15.0
    assert result["remove_best_trade_total"] == -12.0
