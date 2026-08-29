from datetime import UTC, datetime, timedelta

from lyceum.models import OptionContract


def contract(symbol="SPYTESTC", option_type="call", strike=500.0, bid=4.9, ask=5.1, age=0):
    return OptionContract(
        symbol=symbol,
        underlying="SPY",
        expiration=(datetime.now(UTC).date() + timedelta(days=14)).isoformat(),
        strike=strike,
        option_type=option_type,
        bid=bid,
        ask=ask,
        bid_size=10,
        ask_size=10,
        implied_volatility=0.22,
        quote_timestamp=datetime.now(UTC) - timedelta(seconds=age),
    )
