"""Read-only connectivity diagnostics for Alpaca paper trading."""

from __future__ import annotations

from lyceum.alpaca_client import stock_data_client, trading_client
from lyceum.config import load_settings
from lyceum.market_data import latest_spy_quote


def run() -> dict[str, object]:
    settings = load_settings()
    trading = trading_client(settings)
    account = trading.get_account()
    clock = trading.get_clock()
    quote = latest_spy_quote(stock_data_client(settings), settings.data_feed)

    return {
        "environment": "paper",
        "endpoint": settings.trading_base_url,
        "account_status": str(account.status),
        "equity": str(account.equity),
        "buying_power": str(account.buying_power),
        "market_is_open": clock.is_open,
        "next_open": clock.next_open.isoformat(),
        "next_close": clock.next_close.isoformat(),
        "spy_bid": str(quote.bid_price),
        "spy_ask": str(quote.ask_price),
    }


def main() -> None:
    result = run()
    print("Alpaca read-only connectivity check")
    for key, value in result.items():
        print(f"{key}: {value}")
    print("No orders were submitted.")


if __name__ == "__main__":
    main()
