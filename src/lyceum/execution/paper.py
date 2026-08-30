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


class ExecutionUncertain(RuntimeError):
    """Submission may have reached Alpaca and must be reconciled before retrying."""


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
        if self.settings.emergency_halt_file.exists():
            raise ExecutionBlocked("emergency HALT appeared after risk evaluation")
        self.gateway.validate_startup(expected_account_id=self.settings.expected_account_id)
        if not bool(self.gateway.clock().get("is_open")):
            raise ExecutionBlocked("Alpaca market clock is closed at the execution boundary")
        try:
            completed = subprocess.run(self.command(candidate, dry_run=False), capture_output=True, text=True, timeout=30, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ExecutionUncertain("paper order submission timed out; broker state is uncertain") from exc
        if completed.returncode != 0:
            raise ExecutionBlocked(completed.stderr.strip() or "paper order rejected")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ExecutionUncertain("paper order returned malformed acknowledgement; broker state is uncertain") from exc
        return ExecutionResult(ExecutionMode.PAPER_AUTONOMOUS, "SUBMITTED", payload)

    @staticmethod
    def request_payload(candidate: TradeCandidate) -> dict[str, Any]:
        net_price = sum(leg.contract.ask if leg.side == "buy" else -leg.contract.bid for leg in candidate.legs)
        rounded_price = round(net_price, 2)
        if rounded_price == 0:
            rounded_price = -0.01 if net_price < 0 else 0.01
        return {
            "order_class": "mleg",
            "qty": "1",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": rounded_price,
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
            self.settings.alpaca_profile,
            "order",
            "submit",
            "--order-class",
            "mleg",
            "--qty",
            str(payload["qty"]),
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
