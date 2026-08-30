from lyceum.data.alpaca_cli import AlpacaCliGateway


class BarsGateway(AlpacaCliGateway):
    def bars(self, symbol: str, **_kwargs):
        assert symbol == "SPY"
        return [
            {"c": 100, "t": "2026-08-28T18:00:00Z"},
            {"c": 101, "t": "2026-08-28T19:00:00Z"},
            {"c": 102, "t": "2026-08-28T20:00:00Z"},
        ]


def test_market_snapshot_calculates_adjacent_returns_without_strict_zip_failure():
    snapshot = BarsGateway("judging").market_snapshot("SPY")
    assert snapshot.price == 102
    assert snapshot.previous_close == 101
    assert snapshot.momentum_1h == 102 / 101 - 1


class ChainGateway(AlpacaCliGateway):
    def __init__(self):
        super().__init__("judging")
        self.requested_types = []

    def _json(self, *args: str):
        option_type = args[args.index("--type") + 1]
        self.requested_types.append(option_type)
        letter = "C" if option_type == "call" else "P"
        return {
            "snapshots": {
                f"SPY260918{letter}00500000": {
                    "latestQuote": {
                        "bp": 4.9,
                        "ap": 5.1,
                        "bs": 10,
                        "as": 10,
                        "t": "2026-08-28T20:00:00Z",
                    },
                    "impliedVolatility": 0.22,
                    "greeks": {"delta": 0.5 if option_type == "call" else -0.5},
                }
            }
        }


def test_option_chain_fetches_calls_and_puts_separately_to_avoid_one_sided_limit():
    gateway = ChainGateway()
    contracts = gateway.option_chain("SPY", 500)
    assert gateway.requested_types == ["call", "put"]
    assert {item.option_type for item in contracts} == {"call", "put"}
