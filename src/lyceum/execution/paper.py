"""Execution boundary with no live mode and immediate paper re-verification."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from lyceum.config import Settings
from lyceum.data.alpaca_cli import AlpacaCliGateway
from lyceum.models import ExecutionMode, RiskDecision, RiskStatus, StrategyType, TradeCandidate


class ExecutionBlocked(RuntimeError):
    pass


@dataclass(slots=True)
class ExecutionResult:
    mode: ExecutionMode
    status: str
    payload: dict[str, Any]


class PaperExecutor:
    def __init__(self, settings: Settings, gateway: AlpacaCliGateway) -> None:
        self.settings, self.gateway = settings, gateway

    def execute(self, candidate: TradeCandidate, risk: RiskDecision) -> ExecutionResult:
        if candidate.strategy is StrategyType.NO_TRADE:
            return ExecutionResult(self.settings.execution_mode, "NO_TRADE", {})
        if risk.status is not RiskStatus.APPROVED:
            raise ExecutionBlocked("deterministic risk gate rejected candidate")
        if self.settings.execution_mode is ExecutionMode.READ_ONLY:
            return ExecutionResult(ExecutionMode.READ_ONLY, "PREVIEW_ONLY", self.request_payload(candidate))
        if self.settings.execution_mode is ExecutionMode.SIMULATED:
            return ExecutionResult(ExecutionMode.SIMULATED, "SIMULATED_FILL", self.request_payload(candidate))
        if not self.settings.enable_paper_orders:
            raise ExecutionBlocked("explicit paper-order flag is disabled")
        self.gateway.assert_paper()
        completed = subprocess.run(self.command(candidate, dry_run=False), capture_output=True, text=True, timeout=30, check=False)
        if completed.returncode != 0:
            raise ExecutionBlocked(completed.stderr.strip() or "paper order rejected")
        return ExecutionResult(ExecutionMode.PAPER_AUTONOMOUS, "SUBMITTED", json.loads(completed.stdout))

    @staticmethod
    def request_payload(candidate: TradeCandidate) -> dict[str, Any]:
        return {
            "order_class": "mleg",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": round(max(0.01, candidate.estimated_debit / 100), 2),
            "client_order_id": candidate.client_order_id,
            "legs": [
                {
                    "symbol": leg.contract.symbol,
                    "ratio_qty": str(leg.ratio),
                    "side": leg.side,
                    "position_intent": "buy_to_open" if leg.side == "buy" else "sell_to_open",
                }
                for leg in candidate.legs
            ],
        }

    def command(self, candidate: TradeCandidate, *, dry_run: bool) -> list[str]:
        payload = self.request_payload(candidate)
        command = [
            "alpaca",
            "--profile",
            "paper",
            "order",
            "submit",
            "--order-class",
            "mleg",
            "--type",
            "limit",
            "--time-in-force",
            "day",
            "--limit-price",
            str(payload["limit_price"]),
            "--client-order-id",
            str(payload["client_order_id"]),
            "--legs",
            json.dumps(payload["legs"], separators=(",", ":")),
        ]
        if dry_run:
            command.append("--dry-run")
        return command
