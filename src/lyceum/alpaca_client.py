"""Factories for read-only Alpaca SDK clients."""

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from lyceum.config import Settings


def trading_client(settings: Settings) -> TradingClient:
    """Return a client pinned to Alpaca paper trading."""
    settings.validate_safety()
    return TradingClient(settings.api_key, settings.secret_key, paper=True)


def stock_data_client(settings: Settings) -> StockHistoricalDataClient:
    """Return an authenticated stock market-data client."""
    settings.validate_safety()
    return StockHistoricalDataClient(settings.api_key, settings.secret_key)
