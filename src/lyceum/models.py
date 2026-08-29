"""Typed contracts shared by all Lyceum layers."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ExecutionMode(StrEnum):
    READ_ONLY = "READ_ONLY"
    SIMULATED = "SIMULATED"
    PAPER_AUTONOMOUS = "PAPER_AUTONOMOUS"


class StrategyType(StrEnum):
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"
    BEAR_PUT_SPREAD = "BEAR_PUT_SPREAD"
    LONG_STRADDLE = "LONG_STRADDLE"
    IRON_CONDOR = "IRON_CONDOR"
    NO_TRADE = "NO_TRADE"


class RiskStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProbabilityDistribution(BaseModel):
    strong_down: float = Field(ge=0, le=1)
    down: float = Field(ge=0, le=1)
    flat: float = Field(ge=0, le=1)
    up: float = Field(ge=0, le=1)
    strong_up: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def normalized(self) -> ProbabilityDistribution:
        values = self.vector()
        if not all(math.isfinite(value) for value in values):
            raise ValueError("probabilities must be finite")
        if not math.isclose(sum(values), 1.0, abs_tol=1e-6):
            raise ValueError("probabilities must sum to 1")
        return self

    def vector(self) -> tuple[float, float, float, float, float]:
        return (self.strong_down, self.down, self.flat, self.up, self.strong_up)


class AgentOpinion(BaseModel):
    agent: str
    symbol: str
    timestamp: datetime
    horizon: str
    probabilities: ProbabilityDistribution
    expected_return: float
    confidence: float = Field(ge=0, le=1)
    reasoning_summary: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(default_factory=list)
    data_freshness: datetime

    @field_validator("expected_return")
    @classmethod
    def finite_return(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("expected_return must be finite")
        return value


class MarketSnapshot(BaseModel):
    symbol: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    price: float = Field(gt=0)
    previous_close: float = Field(gt=0)
    momentum_1h: float = 0.0
    momentum_1d: float = 0.0
    realized_volatility: float = Field(default=0.2, ge=0)
    implied_volatility: float | None = Field(default=None, ge=0)
    news_sentiment: float = Field(default=0, ge=-1, le=1)
    catalyst_risk: float = Field(default=0, ge=0, le=1)


class ConsensusMetrics(BaseModel):
    distribution: ProbabilityDistribution
    entropy: float = Field(ge=0, le=1)
    pairwise_js_divergence: dict[str, float]
    disagreement: float = Field(ge=0, le=1)
    directional_conviction: float = Field(ge=0, le=1)
    expected_direction: float = Field(ge=-1, le=1)


class OptionContract(BaseModel):
    symbol: str
    underlying: str
    expiration: str
    strike: float = Field(gt=0)
    option_type: Literal["call", "put"]
    bid: float = Field(ge=0)
    ask: float = Field(ge=0)
    bid_size: int = Field(default=0, ge=0)
    ask_size: int = Field(default=0, ge=0)
    implied_volatility: float | None = Field(default=None, ge=0)
    delta: float | None = None
    quote_timestamp: datetime

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float:
        return (self.ask - self.bid) / self.midpoint if self.midpoint > 0 else math.inf


class OptionLeg(BaseModel):
    contract: OptionContract
    side: Literal["buy", "sell"]
    ratio: int = Field(default=1, ge=1)


class TradeCandidate(BaseModel):
    symbol: str
    strategy: StrategyType
    legs: list[OptionLeg] = Field(default_factory=list)
    expiry: str | None = None
    expected_move: float | None = None
    estimated_debit: float = Field(default=0, ge=0)
    max_loss: float = Field(default=0, ge=0)
    rationale: str
    client_order_id: str | None = None


class SkepticReview(BaseModel):
    strongest_argument_against: str
    hidden_assumption: str
    liquidity_concern: str
    iv_concern: str
    event_concern: str
    veto_confidence: float = Field(ge=0, le=1)


class PortfolioState(BaseModel):
    equity: float = Field(gt=0)
    buying_power: float = Field(ge=0)
    daily_realized_pnl: float = 0
    open_positions: int = Field(default=0, ge=0)
    open_risk: float = Field(default=0, ge=0)
    symbol_exposure: dict[str, float] = Field(default_factory=dict)


class RiskDecision(BaseModel):
    status: RiskStatus
    reason_codes: list[str]
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
