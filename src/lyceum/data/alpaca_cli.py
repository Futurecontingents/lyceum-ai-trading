"""Read-only Alpaca CLI gateway using the authenticated paper OAuth profile."""

from __future__ import annotations

import json
import math
import re
import subprocess
from datetime import UTC, datetime, timedelta
from statistics import pstdev
from typing import Any

from lyceum.config import PAPER_TRADING_URL
from lyceum.models import MarketSnapshot, OptionContract, PortfolioState

OCC_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<date>\d{6})(?P<type>[CP])(?P<strike>\d{8})$")


class AlpacaCliError(RuntimeError):
    pass


class AlpacaCliGateway:
    """Executes only explicitly constructed CLI argument arrays—never a shell."""

    def __init__(self, profile: str = "paper", timeout: int = 30) -> None:
        self.profile = profile
        self.timeout = timeout

    def _json(self, *args: str) -> Any:
        completed = subprocess.run(
            ["alpaca", "--profile", self.profile, *args], capture_output=True, text=True, timeout=self.timeout, check=False
        )
        if completed.returncode != 0:
            raise AlpacaCliError(completed.stderr.strip() or completed.stdout.strip())
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AlpacaCliError("Alpaca CLI returned malformed JSON") from exc

    def assert_paper(self) -> None:
        completed = subprocess.run(
            ["alpaca", "--profile", self.profile, "doctor"], capture_output=True, text=True, timeout=self.timeout, check=False
        )
        if completed.returncode != 0 or f"Trading:  {PAPER_TRADING_URL}" not in completed.stdout:
            raise AlpacaCliError(f"profile {self.profile!r} did not resolve to the paper endpoint")

    @staticmethod
    def _collection_count(payload: Any) -> int:
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for key in ("positions", "orders"):
                if isinstance(payload.get(key), list):
                    return len(payload[key])
        raise AlpacaCliError("Alpaca CLI returned an unexpected collection")

    def profile_summary(self) -> dict[str, Any]:
        self.assert_paper()
        account = self._json("account", "get")
        positions = self._collection_count(self._json("position", "list"))
        orders = self._collection_count(self._json("order", "list", "--status", "open"))
        return {
            "profile": self.profile,
            "endpoint": PAPER_TRADING_URL,
            "account_id": str(account["id"]),
            "status": str(account["status"]),
            "equity": float(account["equity"]),
            "buying_power": float(account["buying_power"]),
            "open_positions": positions,
            "open_orders": orders,
        }

    def validate_startup(self, *, expect_fresh: bool = False) -> dict[str, Any]:
        summary = self.profile_summary()
        if expect_fresh and (summary["open_positions"] or summary["open_orders"]):
            raise AlpacaCliError("FRESH ACCOUNT CHECK FAILED: expected zero open positions and zero open orders")
        return summary

    def account(self) -> PortfolioState:
        data = self.profile_summary()
        return PortfolioState(
            equity=data["equity"],
            buying_power=data["buying_power"],
            daily_realized_pnl=0.0,
            open_positions=data["open_positions"],
            open_orders=data["open_orders"],
            open_risk=0.0,
        )

    def clock(self) -> dict[str, Any]:
        return self._json("clock")

    def bars(self, symbol: str, *, timeframe: str = "1Hour", days: int = 45, limit: int = 1000) -> list[dict[str, Any]]:
        start = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
        data = self._json(
            "data", "bars", "--symbol", symbol, "--start", start, "--timeframe", timeframe, "--feed", "iex", "--limit", str(limit)
        )
        return list(data.get("bars", []))

    def market_snapshot(self, symbol: str) -> MarketSnapshot:
        bars = self.bars(symbol, days=8, limit=80)
        if len(bars) < 3:
            raise AlpacaCliError(f"insufficient bars for {symbol}")
        closes = [float(bar["c"]) for bar in bars]
        returns = [b / a - 1 for a, b in zip(closes, closes[1:], strict=True) if a > 0]
        realized = pstdev(returns[-20:]) * math.sqrt(252 * 6.5) if len(returns) > 1 else 0.2
        return MarketSnapshot(
            symbol=symbol,
            timestamp=datetime.fromisoformat(str(bars[-1]["t"]).replace("Z", "+00:00")),
            price=closes[-1],
            previous_close=closes[-2],
            momentum_1h=returns[-1],
            momentum_1d=closes[-1] / closes[max(0, len(closes) - 7)] - 1,
            realized_volatility=max(0.01, realized),
        )

    def option_chain(self, symbol: str, price: float, *, days_min: int = 7, days_max: int = 35, limit: int = 100) -> list[OptionContract]:
        today = datetime.now(UTC).date()
        data = self._json(
            "data",
            "option",
            "chain",
            "--underlying-symbol",
            symbol,
            "--expiration-date-gte",
            (today + timedelta(days=days_min)).isoformat(),
            "--expiration-date-lte",
            (today + timedelta(days=days_max)).isoformat(),
            "--strike-price-gte",
            f"{price * 0.9:.2f}",
            "--strike-price-lte",
            f"{price * 1.1:.2f}",
            "--limit",
            str(limit),
        )
        contracts: list[OptionContract] = []
        for option_symbol, snapshot in data.get("snapshots", {}).items():
            match = OCC_RE.match(option_symbol)
            quote = snapshot.get("latestQuote") or {}
            if not match or not quote.get("t"):
                continue
            contracts.append(
                OptionContract(
                    symbol=option_symbol,
                    underlying=symbol,
                    expiration=datetime.strptime(match.group("date"), "%y%m%d").date().isoformat(),
                    strike=int(match.group("strike")) / 1000,
                    option_type="call" if match.group("type") == "C" else "put",
                    bid=float(quote.get("bp") or 0),
                    ask=float(quote.get("ap") or 0),
                    bid_size=int(quote.get("bs") or 0),
                    ask_size=int(quote.get("as") or 0),
                    implied_volatility=snapshot.get("impliedVolatility"),
                    delta=(snapshot.get("greeks") or {}).get("delta"),
                    quote_timestamp=datetime.fromisoformat(str(quote["t"]).replace("Z", "+00:00")),
                )
            )
        return contracts
