from __future__ import annotations

from scripts.forward_test_runner import model_predict


def test_frozen_ridge_prediction_is_deterministic() -> None:
    parameters = {"mean": [1.0, 2.0], "scale": [2.0, 4.0], "weights": [0.5, 1.0, -2.0]}
    assert model_predict(parameters, [3.0, 6.0]) == -0.5


def test_forward_runner_has_no_execution_or_order_imports() -> None:
    source = open("scripts/forward_test_runner.py", encoding="utf-8").read()
    assert "lyceum.execution" not in source
    assert "submit_order" not in source
    assert "cancel_order" not in source
    assert "subprocess" not in source
    assert "alpaca" not in source.lower()
