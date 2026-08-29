"""Schema-constrained model wrappers for language-heavy council roles."""

from __future__ import annotations

import json
import math
import time
from typing import Any

from pydantic import ValidationError

from lyceum.agents.base import BaseMind
from lyceum.models import AgentOpinion, MarketSnapshot, ModelOpinionPayload, ProbabilityDistribution
from lyceum.models.base import ModelProvider

PROMPT_VERSION = "council-probabilities-v1"
SYSTEM_PROMPT = """You are one member of a probabilistic market council. Estimate the next-trading-day outcome from only the supplied evidence. Distinguish observations from inference, cite supplied evidence IDs when available, never invent facts, avoid certainty language, and return one JSON object only. Required keys: probabilities (strong_down, down, flat, up, strong_up), expected_return, confidence, reasoning_summary, evidence. Probabilities must be finite numbers from 0 to 1 and sum to 1."""

ROLE_INSTRUCTIONS = {
    "NewsCatalystAgent": "Assess catalyst and news implications without treating missing news as neutral proof.",
    "BullAdvocateAgent": "Present the strongest evidence-supported upside interpretation; remain calibrated and acknowledge contrary evidence.",
    "BearAdvocateAgent": "Present the strongest evidence-supported downside interpretation; remain calibrated and acknowledge contrary evidence.",
}


def _first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("model response contains no JSON object")


def parse_model_opinion(text: str) -> ModelOpinionPayload:
    payload = _first_json_object(text)
    probabilities = payload.get("probabilities")
    if not isinstance(probabilities, dict):
        raise ValueError("probabilities must be an object")
    keys = ("strong_down", "down", "flat", "up", "strong_up")
    if set(probabilities) != set(keys):
        raise ValueError("probability keys do not match schema")
    values = [probabilities[key] for key in keys]
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
        raise ValueError("probabilities must be numeric")
    numeric = [float(value) for value in values]
    if not all(math.isfinite(value) and value >= 0 for value in numeric):
        raise ValueError("probabilities must be finite and non-negative")
    total = sum(numeric)
    if total <= 0 or abs(total - 1) > 0.02:
        raise ValueError("probability sum is not safely normalizable")
    payload["probabilities"] = ProbabilityDistribution(**dict(zip(keys, (value / total for value in numeric), strict=True)))
    return ModelOpinionPayload.model_validate(payload)


class ModelBackedMind:
    def __init__(self, fallback: BaseMind, provider: ModelProvider, *, retries: int = 1) -> None:
        self.fallback = fallback
        self.provider = provider
        self.retries = retries
        self.name = fallback.name

    def _user_prompt(self, snapshot: MarketSnapshot) -> str:
        context = {
            "role": ROLE_INSTRUCTIONS[self.name],
            "symbol": snapshot.symbol,
            "horizon": "1 trading day",
            "market_timestamp": snapshot.timestamp.isoformat(),
            "market_state": {
                "price": snapshot.price,
                "previous_close": snapshot.previous_close,
                "momentum_1h": snapshot.momentum_1h,
                "momentum_1d": snapshot.momentum_1d,
                "realized_volatility": snapshot.realized_volatility,
                "implied_volatility": snapshot.implied_volatility,
                "option_implied_move_1d": None
                if snapshot.implied_volatility is None
                else snapshot.price * snapshot.implied_volatility / math.sqrt(252),
                "news_sentiment": snapshot.news_sentiment,
                "catalyst_risk": snapshot.catalyst_risk,
            },
            "catalyst_evidence": [item.model_dump(mode="json") for item in snapshot.catalyst_evidence],
        }
        return json.dumps(context, separators=(",", ":"))

    def evaluate(self, snapshot: MarketSnapshot) -> AgentOpinion:
        started = time.perf_counter()
        for _ in range(self.retries + 1):
            try:
                result = self.provider.complete_structured(system_prompt=SYSTEM_PROMPT, user_prompt=self._user_prompt(snapshot))
                parsed = parse_model_opinion(result.content)
                return AgentOpinion(
                    agent=self.name,
                    symbol=snapshot.symbol,
                    timestamp=snapshot.timestamp,
                    horizon="1 trading day",
                    probabilities=parsed.probabilities,
                    expected_return=parsed.expected_return,
                    confidence=parsed.confidence,
                    reasoning_summary=parsed.reasoning_summary,
                    evidence=parsed.evidence,
                    data_freshness=snapshot.timestamp,
                    implementation="model",
                    provider=result.provider,
                    model_name=result.model_name,
                    prompt_version=PROMPT_VERSION,
                    latency_ms=result.latency_ms,
                    fallback_used=False,
                )
            except (ValueError, ValidationError, RuntimeError, TimeoutError):
                continue
        fallback = self.fallback.evaluate(snapshot)
        return fallback.model_copy(
            update={
                "provider": self.provider.name,
                "model_name": self.provider.model_name,
                "prompt_version": PROMPT_VERSION,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "fallback_used": True,
            }
        )
