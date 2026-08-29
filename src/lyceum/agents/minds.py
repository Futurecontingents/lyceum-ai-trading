"""The five independent members of Lyceum's market council."""

from __future__ import annotations

import math

from lyceum.agents.base import BaseMind
from lyceum.models import MarketSnapshot


class TechnicalQuantAgent(BaseMind):
    name = "TechnicalQuantAgent"

    def score(self, s: MarketSnapshot):
        raw = math.tanh(18 * (0.65 * s.momentum_1h + 0.35 * s.momentum_1d))
        return (
            raw,
            min(0.9, 0.35 + abs(raw) * 0.5),
            "Momentum across 1h and 1d horizons",
            [f"1h={s.momentum_1h:.2%}", f"1d={s.momentum_1d:.2%}"],
        )


class OptionsMarketAgent(BaseMind):
    name = "OptionsMarketAgent"

    def score(self, s: MarketSnapshot):
        iv = s.implied_volatility if s.implied_volatility is not None else s.realized_volatility
        vol_gap = iv - s.realized_volatility
        direction = math.tanh(10 * s.momentum_1h) * max(0.25, 1 - abs(vol_gap))
        return (
            direction,
            min(0.85, 0.4 + abs(vol_gap)),
            "Options volatility relative to realized movement",
            [f"IV={iv:.1%}", f"realized={s.realized_volatility:.1%}"],
        )


class NewsCatalystAgent(BaseMind):
    name = "NewsCatalystAgent"

    def score(self, s: MarketSnapshot):
        return (
            s.news_sentiment,
            0.3 + 0.6 * abs(s.news_sentiment),
            "Recent catalyst sentiment with explicit event-risk penalty",
            [f"sentiment={s.news_sentiment:+.2f}", f"catalyst_risk={s.catalyst_risk:.2f}"],
        )


class BullAdvocateAgent(BaseMind):
    name = "BullAdvocateAgent"

    def score(self, s: MarketSnapshot):
        return (
            min(1.0, 0.25 + 8 * max(s.momentum_1d, 0)),
            min(0.8, 0.35 + 8 * max(s.momentum_1d, 0)),
            "Strongest evidence-supported bullish case",
            [f"upside momentum={max(s.momentum_1d, 0):.2%}"],
        )


class BearAdvocateAgent(BaseMind):
    name = "BearAdvocateAgent"

    def score(self, s: MarketSnapshot):
        downside = max(-s.momentum_1d, 0)
        return (
            max(-1.0, -0.25 - 8 * downside),
            min(0.8, 0.35 + 8 * downside),
            "Strongest evidence-supported bearish case",
            [f"downside momentum={downside:.2%}"],
        )


def market_council() -> tuple[BaseMind, ...]:
    return (TechnicalQuantAgent(), OptionsMarketAgent(), NewsCatalystAgent(), BullAdvocateAgent(), BearAdvocateAgent())
