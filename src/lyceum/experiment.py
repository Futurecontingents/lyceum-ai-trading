"""Pragmatic disagreement-vs-future-volatility experiment."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev

from lyceum.agents import market_council
from lyceum.consensus import calculate_consensus
from lyceum.models import MarketSnapshot


def _pearson(left: list[float], right: list[float]) -> float:
    if len(left) < 2:
        return math.nan
    lx, rx = mean(left), mean(right)
    numerator = sum((a - lx) * (b - rx) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum((a - lx) ** 2 for a in left) * sum((b - rx) ** 2 for b in right))
    return numerator / denominator if denominator else math.nan


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        rank = (index + end + 2) / 2
        for position in order[index : end + 1]:
            ranks[position] = rank
        index = end + 1
    return ranks


@dataclass(frozen=True)
class HorizonResult:
    horizon: str
    n: int
    pearson_abs_return: float
    spearman_abs_return: float
    pearson_realized_volatility: float
    spearman_realized_volatility: float
    buckets: dict[str, dict[str, float]]


def run_experiment(bars: list[dict], horizon_steps: dict[str, int] | None = None) -> list[HorizonResult]:
    horizon_steps = horizon_steps or {"1h": 1, "4h": 4, "1 trading day": 7}
    closes = [float(item["c"]) for item in bars]
    observations: list[tuple[int, float]] = []
    for index in range(8, len(closes)):
        recent = [closes[i] / closes[i - 1] - 1 for i in range(index - 6, index + 1)]
        snapshot = MarketSnapshot(
            symbol="SPY",
            price=closes[index],
            previous_close=closes[index - 1],
            momentum_1h=recent[-1],
            momentum_1d=closes[index] / closes[index - 7] - 1,
            realized_volatility=max(0.01, pstdev(recent) * math.sqrt(252 * 6.5)),
        )
        opinions = [mind.evaluate(snapshot) for mind in market_council()]
        observations.append((index, calculate_consensus(opinions).disagreement))
    results: list[HorizonResult] = []
    for label, steps in horizon_steps.items():
        disagreements, abs_returns, realized_vols = [], [], []
        for index, disagreement in observations:
            if index + steps >= len(closes):
                continue
            forward = [closes[i] / closes[i - 1] - 1 for i in range(index + 1, index + steps + 1)]
            disagreements.append(disagreement)
            abs_returns.append(abs(closes[index + steps] / closes[index] - 1))
            realized_vols.append(math.sqrt(sum(value * value for value in forward)))
        sorted_values = sorted(disagreements)
        cuts = [sorted_values[int((len(sorted_values) - 1) * q)] for q in (0.25, 0.5, 0.75)] if sorted_values else [0, 0, 0]
        bucket_data: dict[str, list[tuple[float, float]]] = {"low": [], "mid-low": [], "mid-high": [], "high": []}
        for d, absolute, volatility in zip(disagreements, abs_returns, realized_vols, strict=True):
            bucket = "low" if d <= cuts[0] else "mid-low" if d <= cuts[1] else "mid-high" if d <= cuts[2] else "high"
            bucket_data[bucket].append((absolute, volatility))
        buckets = {
            name: {
                "n": len(values),
                "mean_abs_return": mean(v[0] for v in values) if values else math.nan,
                "mean_realized_volatility": mean(v[1] for v in values) if values else math.nan,
            }
            for name, values in bucket_data.items()
        }
        results.append(
            HorizonResult(
                label,
                len(disagreements),
                _pearson(disagreements, abs_returns),
                _pearson(_ranks(disagreements), _ranks(abs_returns)),
                _pearson(disagreements, realized_vols),
                _pearson(_ranks(disagreements), _ranks(realized_vols)),
                buckets,
            )
        )
    return results


def render_markdown(results: list[HorizonResult]) -> str:
    lines = [
        "# Historical Experiment",
        "",
        "This is a pragmatic historical sanity check, not evidence of profitability. Signals use only information available before each forward window.",
        "",
        "| Horizon | n | Pearson vs |return| | Spearman vs |return| | Pearson vs realized vol | Spearman vs realized vol |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r.horizon} | {r.n} | {r.pearson_abs_return:.3f} | {r.spearman_abs_return:.3f} | {r.pearson_realized_volatility:.3f} | {r.spearman_realized_volatility:.3f} |"
        )
    lines += ["", "## Disagreement buckets", ""]
    for r in results:
        lines += [
            f"### {r.horizon}",
            "",
            "| Bucket | n | Mean subsequent |return| | Mean subsequent realized volatility |",
            "|---|---:|---:|---:|",
        ]
        for name, values in r.buckets.items():
            lines.append(f"| {name} | {int(values['n'])} | {values['mean_abs_return']:.4%} | {values['mean_realized_volatility']:.4%} |")
        lines.append("")
    lines += [
        "## Interpretation",
        "",
        "A positive correlation would support further investigation; a weak or unstable result means disagreement remains an experimental dashboard signal. Lyceum then falls back to a documented combination of market regime, momentum, implied volatility, and consensus. No result here is fabricated or presented as a trading edge.",
    ]
    return "\n".join(lines) + "\n"
