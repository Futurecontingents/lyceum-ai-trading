import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from lyceum.shadow import MarketCollector, ReadOnlyAlpaca, ShadowHarness, ShadowSafetyError, ShadowStore, shadow_configs


def test_read_only_gateway_rejects_every_non_capture_surface(monkeypatch):
    monkeypatch.setattr("lyceum.shadow.subprocess.run", lambda *_args, **_kwargs: pytest.fail("rejected command reached subprocess"))
    client = ReadOnlyAlpaca()
    for command in (("order", "submit"), ("account",), ("positions",), ("data", "option", "trades"), ("data", "news")):
        with pytest.raises(ShadowSafetyError):
            client.json(*command)


def test_read_only_gateway_builds_judging_market_data_command(monkeypatch):
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("lyceum.shadow.subprocess.run", fake_run)
    ReadOnlyAlpaca("judging").json("data", "snapshot", "--symbol", "SPY")
    assert commands == [["alpaca", "--profile", "judging", "data", "snapshot", "--symbol", "SPY"]]


class FakeMarketData:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.calls = []

    def json(self, *args):
        self.calls.append(args)
        if args == ("clock",):
            return {"is_open": True}
        if args[:2] == ("data", "snapshot"):
            symbol = args[args.index("--symbol") + 1]
            return {
                "symbol": symbol,
                "latestQuote": {"bp": 99.9, "ap": 100.1, "bs": 10, "as": 12, "t": self.now.isoformat()},
                "latestTrade": {"p": 100, "s": 5, "t": self.now.isoformat()},
                "minuteBar": {"v": 1000},
                "dailyBar": {"v": 100_000},
            }
        if args[:2] == ("data", "bars"):
            return {
                "bars": [
                    {"t": (self.now - timedelta(minutes=61 - index)).isoformat(), "c": 99 + index / 100, "v": 1000}
                    for index in range(62)
                ]
            }
        if args[:3] == ("data", "option", "chain"):
            symbol = args[args.index("--underlying-symbol") + 1]
            expiry = (self.now + timedelta(days=14)).strftime("%y%m%d")
            snapshots = {}
            for kind in ("C", "P"):
                for strike in (95, 100, 105):
                    contract = f"{symbol}{expiry}{kind}{strike * 1000:08d}"
                    snapshots[contract] = {
                        "latestQuote": {"bp": 1.0, "ap": 1.1, "bs": 10, "as": 10, "t": self.now.isoformat()},
                        "latestTrade": {"p": 1.05, "s": 2, "t": self.now.isoformat()},
                        "dailyBar": {"v": 25},
                        "impliedVolatility": 0.25,
                        "greeks": {"delta": 0.5 if kind == "C" else -0.5, "gamma": 0.03, "theta": -0.1, "vega": 0.2},
                    }
            return {"snapshots": snapshots}
        raise AssertionError(args)


def test_collector_is_append_only_and_harness_never_creates_orders(tmp_path, monkeypatch):
    now = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr("lyceum.shadow.UNIVERSE", ("SPY",))
    store = ShadowStore(tmp_path / "shadow.db")
    collector = MarketCollector(store, FakeMarketData(now))

    first = collector.collect_once()
    second = collector.collect_once()
    assert first["option_contracts"] == second["option_contracts"] == 6

    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM capture_batches").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM underlying_snapshots").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM option_snapshots").fetchone()[0] == 12
        assert db.execute("SELECT volume FROM option_snapshots LIMIT 1").fetchone()[0] == 25
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "orders" not in tables

    result = ShadowHarness(store).run(latest_batches=1)
    assert result["decisions_evaluated"] == 33
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM shadow_results").fetchone()[0] == 33
        assert "orders" not in {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_shadow_grid_has_32_distinct_bounded_configs():
    configs = shadow_configs()
    assert len(configs) == len({config.config_id for config in configs}) == 32
    assert {config.max_loss for config in configs} == {500, 2000}
    assert {config.dte_target for config in configs} == {10, 28}


def test_option_mark_change_requires_complete_future_leg_set(tmp_path):
    store = ShadowStore(tmp_path / "shadow.db")
    payload = {
        "candidate": {
            "legs": [
                {
                    "side": "buy",
                    "ratio": 1,
                    "contract": {"symbol": "SPYTEST", "bid": 1.0, "ask": 1.2},
                }
            ]
        }
    }
    with store.connect() as db:
        assert ShadowHarness._option_mark_change(db, payload, None) is None
        assert ShadowHarness._option_mark_change(db, payload, 999) is None


def test_shadow_payload_is_json_serializable(tmp_path):
    store = ShadowStore(tmp_path / "shadow.db")
    assert json.dumps(ShadowHarness(store).summary())
