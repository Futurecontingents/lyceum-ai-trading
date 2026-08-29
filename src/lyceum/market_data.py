"""Read-only stock market-data helpers."""

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest


def latest_spy_quote(client: StockHistoricalDataClient, feed: str = "iex"):
    """Fetch SPY's latest quote without submitting any order."""
    data_feed = DataFeed.IEX if feed.lower() == "iex" else DataFeed.SIP
    request = StockLatestQuoteRequest(symbol_or_symbols="SPY", feed=data_feed)
    return client.get_stock_latest_quote(request)["SPY"]
