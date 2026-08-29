import json
from datetime import UTC, datetime

import pytest

from lyceum.agents.minds import BearAdvocateAgent, market_council
from lyceum.agents.model_backed import ModelBackedMind, parse_model_opinion
from lyceum.config import Settings
from lyceum.memory import Journal
from lyceum.models import CouncilMode, MarketSnapshot, PortfolioState, RiskStatus
from lyceum.models.base import CompletionResult
from lyceum.models.factory import create_model_provider
from lyceum.risk import evaluate_risk
from tests.test_risk import candidate, skeptic


class FakeProvider:
    name = "openai_compatible"
    model_name = "test/model"

    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = 0

    def complete_structured(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
        self.calls += 1
        if self.error:
            raise self.error
        assert "probabilistic market council" in system_prompt
        assert '"symbol":"SPY"' in user_prompt
        return CompletionResult(self.content or "{}", self.name, self.model_name, 12.5)


def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="SPY",
        timestamp=datetime.now(UTC),
        price=500,
        previous_close=498,
        momentum_1h=0.002,
        momentum_1d=0.01,
        realized_volatility=0.2,
        implied_volatility=0.22,
    )


def valid_response() -> str:
    return json.dumps(
        {
            "probabilities": {"strong_down": 0.1, "down": 0.15, "flat": 0.25, "up": 0.3, "strong_up": 0.2},
            "expected_return": 0.004,
            "confidence": 0.64,
            "reasoning_summary": "Upside momentum is constructive but volatility limits conviction.",
            "evidence": ["market_state.momentum_1d"],
        }
    )


def test_model_provider_disabled_by_default():
    assert create_model_provider(Settings()) is None
    assert all(item.__class__.__name__ != "ModelBackedMind" for item in market_council(Settings()))


def test_hybrid_without_complete_provider_configuration_degrades_to_deterministic():
    settings = Settings(council_mode=CouncilMode.HYBRID, model_provider="openai_compatible")
    opinions = [mind.evaluate(snapshot()) for mind in market_council(settings)]
    assert len(opinions) == 5
    assert all(item.implementation == "deterministic" and not item.fallback_used for item in opinions)


def test_malformed_model_output_falls_back_deterministically():
    provider = FakeProvider("not-json")
    opinion = ModelBackedMind(BearAdvocateAgent(), provider, retries=1).evaluate(snapshot())
    assert opinion.implementation == "deterministic"
    assert opinion.fallback_used is True
    assert opinion.provider == "openai_compatible"
    assert provider.calls == 2


def test_timeout_falls_back_without_stopping_loop():
    opinion = ModelBackedMind(BearAdvocateAgent(), FakeProvider(error=TimeoutError()), retries=0).evaluate(snapshot())
    assert opinion.fallback_used is True
    assert opinion.probabilities.model_dump()


def test_probability_validation_rejects_unsafe_sum_and_normalizes_small_drift():
    bad = valid_response().replace('"strong_up": 0.2', '"strong_up": 0.8')
    with pytest.raises(ValueError, match="safely normalizable"):
        parse_model_opinion(bad)
    near = valid_response().replace('"strong_up": 0.2', '"strong_up": 0.201')
    assert sum(parse_model_opinion(near).probabilities.vector()) == pytest.approx(1.0)


def test_hybrid_composition_and_model_metadata_persistence(tmp_path):
    provider = FakeProvider(valid_response())
    settings = Settings(council_mode=CouncilMode.HYBRID, model_provider="openai_compatible")
    opinions = [mind.evaluate(snapshot()) for mind in market_council(settings, provider=provider)]
    assert [item.implementation for item in opinions] == ["deterministic", "deterministic", "model", "model", "model"]
    journal = Journal(tmp_path / "trace.db")
    journal.record_opinion("SPY", opinions[2].agent, opinions[2])
    payload = json.loads(journal.recent("agent_opinions")[0]["payload"])
    assert payload["provider"] == "openai_compatible"
    assert payload["model_name"] == "test/model"
    assert payload["prompt_version"] == "council-probabilities-v1"
    assert payload["fallback_used"] is False


def test_model_opinion_cannot_bypass_deterministic_risk(tmp_path):
    opinion = ModelBackedMind(BearAdvocateAgent(), FakeProvider(valid_response())).evaluate(snapshot())
    assert opinion.implementation == "model"
    decision = evaluate_risk(
        candidate(max_loss=700),
        PortfolioState(equity=100_000, buying_power=400_000),
        skeptic(),
        Settings(emergency_halt_file=tmp_path / "HALT"),
    )
    assert decision.status is RiskStatus.REJECTED
    assert "MAX_LOSS_PER_TRADE" in decision.reason_codes
