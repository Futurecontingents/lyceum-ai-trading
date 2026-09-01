#!/usr/bin/env python3
"""Development-only Sep-01 agent ablation against later underlying returns."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from lyceum.consensus import calculate_consensus
from lyceum.models import AgentOpinion

HORIZONS = (5, 15, 30, 60)


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3:
        return None
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def run(journal_path: Path, shadow_path: Path, output: Path) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    with sqlite3.connect(journal_path) as journal, sqlite3.connect(shadow_path) as shadow:
        journal.row_factory = shadow.row_factory = sqlite3.Row
        decisions = journal.execute(
            "SELECT * FROM decisions WHERE created_at>='2026-09-01T00:00:00+00:00' ORDER BY created_at"
        ).fetchall()
        for decision in decisions:
            payload = json.loads(decision["payload"])
            opinions = [AgentOpinion.model_validate(item) for item in payload["opinions"]]
            if len(opinions) != 5:
                continue
            market = payload["market"]
            entry_at = instant(decision["created_at"])
            entry_price = float(market["price"])
            future_returns: dict[int, float] = {}
            for horizon in HORIZONS:
                future = shadow.execute(
                    """SELECT u.trade_price,b.completed_at FROM underlying_snapshots u
                    JOIN capture_batches b ON b.id=u.batch_id
                    WHERE u.symbol=? AND b.status='COMPLETE' AND b.completed_at>=?
                    ORDER BY b.completed_at LIMIT 1""",
                    (decision["symbol"], (entry_at + timedelta(minutes=horizon)).isoformat()),
                ).fetchone()
                if future is not None:
                    future_returns[horizon] = float(future["trade_price"]) / entry_price - 1
            groups: dict[str, list[AgentOpinion]] = {
                "technical_only": [item for item in opinions if item.agent == "TechnicalQuantAgent"],
                "options_only": [item for item in opinions if item.agent == "OptionsMarketAgent"],
                "deterministic_only": [item for item in opinions if item.implementation == "deterministic"],
                "qwen_model_only": [item for item in opinions if item.implementation == "model"],
                "full_council": opinions,
                "without_news": [item for item in opinions if item.agent != "NewsCatalystAgent"],
                "without_bull": [item for item in opinions if item.agent != "BullAdvocateAgent"],
                "without_bear": [item for item in opinions if item.agent != "BearAdvocateAgent"],
            }
            signals = {
                name: {
                    "direction": calculate_consensus(group).expected_direction,
                    "disagreement": calculate_consensus(group).disagreement,
                }
                for name, group in groups.items() if group
            }
            momentum = float(market.get("momentum_1h") or 0)
            signals["momentum"] = {"direction": math.copysign(1, momentum) if momentum else 0.0, "disagreement": 0.0}
            signals["mean_reversion"] = {"direction": -math.copysign(1, momentum) if momentum else 0.0, "disagreement": 0.0}
            observations.append(
                {"created_at": decision["created_at"], "symbol": decision["symbol"],
                 "signals": signals, "future_returns": future_returns}
            )
    metrics: dict[str, dict[str, Any]] = {}
    names = sorted({name for item in observations for name in item["signals"]})
    for name in names:
        by_horizon: dict[str, Any] = {}
        for horizon in HORIZONS:
            pairs = [
                (float(item["signals"][name]["direction"]), float(item["future_returns"][horizon]),
                 float(item["signals"][name]["disagreement"]))
                for item in observations if name in item["signals"] and horizon in item["future_returns"]
            ]
            directions = [item[0] for item in pairs]
            returns = [item[1] for item in pairs]
            disagreements = [item[2] for item in pairs]
            active = [(direction, future) for direction, future, _ in pairs if direction != 0]
            by_horizon[str(horizon)] = {
                "n": len(pairs),
                "directional_hit_rate": sum(direction * future > 0 for direction, future in active) / len(active) if active else None,
                "direction_return_correlation": pearson(directions, returns),
                "mean_signed_underlying_return": mean(direction * future for direction, future in active) if active else None,
                "disagreement_abs_return_correlation": pearson(disagreements, [abs(value) for value in returns]),
                "executable_option_pnl": None,
                "pnl_limitation": "exact point-in-time option mapping was not journaled at judging-decision cadence",
            }
        metrics[name] = by_horizon
    payload = {
        "status": "DEVELOPMENT_ONLY_NOT_OOS", "data_start": "2026-09-01T00:00:00Z",
        "generated_at": datetime.now(UTC).isoformat(), "decision_sets": len(observations),
        "horizons_minutes": HORIZONS, "metrics": metrics,
        "conclusion": "No agent subset may be credited with executable edge; council economics remain unproven.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, default=Path("data/judging.db"))
    parser.add_argument("--shadow", type=Path, default=Path("data/shadow_market.db"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/forward_test/agent_ablation_sep01_development.json"))
    args = parser.parse_args()
    payload = run(args.journal, args.shadow, args.output)
    print(json.dumps({"status": payload["status"], "decision_sets": payload["decision_sets"]}))


if __name__ == "__main__":
    main()
