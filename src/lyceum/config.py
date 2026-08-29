"""Validated application configuration with non-negotiable paper safeguards."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

from lyceum.models import CouncilMode, ExecutionMode

PAPER_TRADING_URL = "https://paper-api.alpaca.markets"
UNIVERSE = ("SPY", "QQQ", "AAPL", "NVDA", "AMD", "META", "TSLA")


class ConfigurationError(RuntimeError):
    """Raised when Lyceum cannot prove it is configured for paper trading."""


class Settings(BaseModel):
    """Runtime settings. There is intentionally no live-trading field."""

    api_key: str = ""
    secret_key: str = ""
    paper: bool = True
    trading_base_url: str = PAPER_TRADING_URL
    data_feed: str = "iex"
    alpaca_profile: str = Field(default="paper", min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    expect_fresh_account: bool = False
    execution_mode: ExecutionMode = ExecutionMode.READ_ONLY
    enable_paper_orders: bool = False
    database_path: Path = Path("data/lyceum.db")
    emergency_halt_file: Path = Path("HALT")
    scan_interval_seconds: int = Field(default=900, ge=30)
    universe: tuple[str, ...] = UNIVERSE
    max_loss_per_trade: float = Field(default=500.0, gt=0)
    max_daily_realized_loss: float = Field(default=1_500.0, gt=0)
    max_portfolio_heat: float = Field(default=3_000.0, gt=0)
    max_simultaneous_positions: int = Field(default=4, ge=1)
    max_symbol_concentration: float = Field(default=0.02, gt=0, le=1)
    max_bid_ask_spread_pct: float = Field(default=0.18, gt=0, le=1)
    max_quote_age_seconds: int = Field(default=180, ge=1)
    min_quote_size: int = Field(default=1, ge=0)
    cooldown_minutes: int = Field(default=30, ge=0)
    council_mode: CouncilMode = CouncilMode.DETERMINISTIC
    model_provider: Literal["deterministic", "openai_compatible"] = "deterministic"
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = ""
    model_timeout_seconds: float = Field(default=12, gt=0, le=60)
    model_retries: int = Field(default=1, ge=0, le=2)

    @field_validator("trading_base_url")
    @classmethod
    def paper_url_only(cls, value: str) -> str:
        if value.rstrip("/") != PAPER_TRADING_URL:
            raise ValueError("Lyceum only permits https://paper-api.alpaca.markets")
        return PAPER_TRADING_URL

    @model_validator(mode="after")
    def validate_safety(self) -> Settings:
        if not self.paper:
            raise ValueError("Lyceum has no live mode; ALPACA_PAPER must remain true")
        if self.execution_mode is ExecutionMode.PAPER_AUTONOMOUS and not self.enable_paper_orders:
            raise ValueError("PAPER_AUTONOMOUS requires LYCEUM_ENABLE_PAPER_ORDERS=true")
        return self

    def assert_paper(self) -> None:
        """Re-check the invariant at trust boundaries."""
        if not self.paper or self.trading_base_url != PAPER_TRADING_URL:
            raise ConfigurationError("paper-only invariant failed")


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    """Load environment values without logging or exposing credentials."""
    if env_file is not None:
        load_dotenv(dotenv_path=env_file, override=False)
    try:
        return Settings(
            api_key=os.getenv("ALPACA_API_KEY", "").strip(),
            secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
            paper=_truthy(os.getenv("ALPACA_PAPER", "true")),
            trading_base_url=os.getenv("ALPACA_TRADING_BASE_URL", PAPER_TRADING_URL),
            data_feed=os.getenv("ALPACA_DATA_FEED", "iex").lower(),
            alpaca_profile=os.getenv("LYCEUM_ALPACA_PROFILE", "paper").strip(),
            expect_fresh_account=_truthy(os.getenv("LYCEUM_EXPECT_FRESH_ACCOUNT", "false")),
            execution_mode=ExecutionMode(os.getenv("LYCEUM_EXECUTION_MODE", "READ_ONLY")),
            enable_paper_orders=_truthy(os.getenv("LYCEUM_ENABLE_PAPER_ORDERS", "false")),
            database_path=Path(os.getenv("LYCEUM_DATABASE_PATH", "data/lyceum.db")),
            emergency_halt_file=Path(os.getenv("LYCEUM_HALT_FILE", "HALT")),
            scan_interval_seconds=int(os.getenv("LYCEUM_SCAN_INTERVAL_SECONDS", "900")),
            council_mode=CouncilMode(os.getenv("LYCEUM_COUNCIL_MODE", "DETERMINISTIC").upper()),
            model_provider=os.getenv("LYCEUM_MODEL_PROVIDER", "deterministic").lower(),
            model_base_url=os.getenv("LYCEUM_MODEL_BASE_URL", "").strip(),
            model_api_key=os.getenv("LYCEUM_MODEL_API_KEY", "").strip(),
            model_name=os.getenv("LYCEUM_MODEL_NAME", "").strip(),
            model_timeout_seconds=float(os.getenv("LYCEUM_MODEL_TIMEOUT_SECONDS", "12")),
            model_retries=int(os.getenv("LYCEUM_MODEL_RETRIES", "1")),
        )
    except (ValueError, TypeError) as exc:
        raise ConfigurationError(str(exc)) from exc
