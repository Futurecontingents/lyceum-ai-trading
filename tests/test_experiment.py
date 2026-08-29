import math

from lyceum.experiment import render_markdown, run_experiment


def test_historical_experiment_reports_all_horizons():
    results = run_experiment([{"c": 100 + index * 0.2 + math.sin(index / 3)} for index in range(80)])
    assert [item.horizon for item in results] == ["1h", "4h", "1 trading day"]
    assert all(item.n > 50 for item in results)
    assert "Pearson" in render_markdown(results)
