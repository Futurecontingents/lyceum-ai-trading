"""Read-only live capture and non-executing shadow research."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import product
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from lyceum.agents import market_council
from lyceum.config import Settings
from lyceum.consensus import calculate_consensus
from lyceum.models import (
    ConsensusMetrics,
    CouncilMode,
    ExecutionMode,
    MarketSnapshot,
    OptionContract,
    OptionLeg,
    PortfolioState,
    RiskStatus,
    StrategyType,
    TradeCandidate,
)
from lyceum.risk import evaluate_risk
from lyceum.strategies import review_candidate, select_strategy

UNIVERSE = ("SPY", "QQQ", "AAPL", "NVDA", "AMD", "META", "TSLA")
OCC_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<date>\d{6})(?P<type>[CP])(?P<strike>\d{8})$")
CAPTURE_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS capture_batches (
 id INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, completed_at TEXT, market_open INTEGER NOT NULL,
 status TEXT NOT NULL, duration_seconds REAL, error TEXT
);
CREATE TABLE IF NOT EXISTS underlying_snapshots (
 id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, captured_at TEXT NOT NULL, symbol TEXT NOT NULL,
 trade_price REAL, trade_size REAL, bid REAL, ask REAL, spread REAL, spread_pct REAL,
 minute_volume REAL, daily_volume REAL, return_5m REAL, return_15m REAL, return_30m REAL, return_60m REAL,
 realized_volatility REAL, quote_timestamp TEXT, trade_timestamp TEXT,
 snapshot_json TEXT NOT NULL, bars_json TEXT NOT NULL,
 UNIQUE(batch_id,symbol), FOREIGN KEY(batch_id) REFERENCES capture_batches(id)
);
CREATE TABLE IF NOT EXISTS option_snapshots (
 id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, captured_at TEXT NOT NULL, underlying TEXT NOT NULL,
 contract_symbol TEXT NOT NULL, expiry TEXT NOT NULL, strike REAL NOT NULL, option_type TEXT NOT NULL,
 bid REAL, ask REAL, mid REAL, spread REAL, spread_pct REAL, bid_size REAL, ask_size REAL,
 trade_price REAL, trade_size REAL, volume REAL, open_interest REAL, implied_volatility REAL,
 delta REAL, gamma REAL, theta REAL, vega REAL, quote_timestamp TEXT, quote_age_seconds REAL,
 payload_json TEXT NOT NULL, UNIQUE(batch_id,contract_symbol), FOREIGN KEY(batch_id) REFERENCES capture_batches(id)
);
CREATE TABLE IF NOT EXISTS shadow_results (
 id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, captured_at TEXT NOT NULL, symbol TEXT NOT NULL,
 config_id TEXT NOT NULL, is_production INTEGER NOT NULL, strategy TEXT NOT NULL, max_loss REAL NOT NULL,
 worst_spread_pct REAL, skeptic_veto INTEGER NOT NULL, risk_status TEXT NOT NULL, risk_reasons TEXT NOT NULL,
 signal_quality TEXT NOT NULL, structure_quality TEXT NOT NULL, risk_quality TEXT NOT NULL,
 execution_quality TEXT NOT NULL, entry_mid REAL, forward_5m REAL, forward_15m REAL,
 forward_30m REAL, forward_60m REAL, direction_correct_60m INTEGER, vol_regime_correct_60m INTEGER,
 option_mark_change REAL,
 payload_json TEXT NOT NULL, UNIQUE(batch_id,symbol,config_id)
);
CREATE INDEX IF NOT EXISTS idx_underlying_symbol_time ON underlying_snapshots(symbol,captured_at);
CREATE INDEX IF NOT EXISTS idx_options_contract_time ON option_snapshots(contract_symbol,captured_at);
CREATE INDEX IF NOT EXISTS idx_shadow_config ON shadow_results(config_id,captured_at);
"""


class ShadowSafetyError(RuntimeError):
    """Raised when research code is asked to cross its read-only boundary."""


class ReadOnlyAlpaca:
    """A deliberately tiny allowlisted Alpaca CLI surface with no trading verbs."""

    def __init__(self, profile: str = "judging", timeout: int = 45) -> None:
        self.profile = profile
        self.timeout = timeout

    def json(self, *args: str) -> dict[str, Any]:
        if not args or args[0] not in {"clock", "data"}:
            raise ShadowSafetyError("shadow collector permits only clock and market-data commands")
        if args[0] == "data":
            direct_data_call = len(args) >= 2 and args[1] in {"snapshot", "bars"}
            option_chain_call = len(args) >= 3 and args[1:3] == ("option", "chain")
            if not (direct_data_call or option_chain_call):
                raise ShadowSafetyError("market-data command is not allowlisted")
        if any(token in {"order", "submit", "cancel", "position", "account"} for token in args):
            raise ShadowSafetyError("trading/account command rejected by shadow boundary")
        completed = subprocess.run(
            ["alpaca", "--profile", self.profile, *args],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected Alpaca payload")
        return payload


def _iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC) if value else None


def _returns(bars: list[dict[str, Any]], minutes: int) -> float | None:
    if len(bars) <= minutes or float(bars[-minutes - 1]["c"]) <= 0:
        return None
    return float(bars[-1]["c"]) / float(bars[-minutes - 1]["c"]) - 1


class ShadowStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(CAPTURE_SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(shadow_results)")}
            if "vol_regime_correct_60m" not in columns:
                db.execute("ALTER TABLE shadow_results ADD COLUMN vol_regime_correct_60m INTEGER")

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db


class MarketCollector:
    def __init__(self, store: ShadowStore, client: ReadOnlyAlpaca, *, feed: str = "iex") -> None:
        self.store = store
        self.client = client
        self.feed = feed

    def _bars(self, symbol: str, captured_at: datetime) -> list[dict[str, Any]]:
        payload = self.client.json(
            "data",
            "bars",
            "--symbol",
            symbol,
            "--start",
            (captured_at - timedelta(hours=2)).isoformat(),
            "--end",
            captured_at.isoformat(),
            "--timeframe",
            "1Min",
            "--feed",
            self.feed,
            "--adjustment",
            "raw",
            "--sort",
            "asc",
            "--limit",
            "120",
        )
        return list(payload.get("bars", []))

    def _chain(self, symbol: str, captured_at: datetime) -> dict[str, dict[str, Any]]:
        snapshots: dict[str, dict[str, Any]] = {}
        page_token = ""
        while True:
            args = [
                "data",
                "option",
                "chain",
                "--underlying-symbol",
                symbol,
                "--expiration-date-gte",
                (captured_at.date() + timedelta(days=7)).isoformat(),
                "--expiration-date-lte",
                (captured_at.date() + timedelta(days=35)).isoformat(),
                "--limit",
                "1000",
            ]
            if page_token:
                args.extend(("--page-token", page_token))
            payload = self.client.json(*args)
            snapshots.update(payload.get("snapshots", {}))
            page_token = str(payload.get("next_page_token") or "")
            if not page_token:
                return snapshots

    def collect_once(self) -> dict[str, Any]:
        started = time.perf_counter()
        captured_at = datetime.now(UTC)
        market_open = bool(self.client.json("clock").get("is_open"))
        with self.store.connect() as db:
            batch_id = db.execute(
                "INSERT INTO capture_batches(captured_at,market_open,status) VALUES(?,?,?)",
                (captured_at.isoformat(), market_open, "RUNNING" if market_open else "MARKET_CLOSED"),
            ).lastrowid
            db.commit()
        if not market_open:
            duration = time.perf_counter() - started
            with self.store.connect() as db:
                db.execute(
                    "UPDATE capture_batches SET completed_at=?,duration_seconds=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), duration, batch_id),
                )
                db.commit()
            return {"batch_id": batch_id, "market_open": False, "symbols": 0, "option_contracts": 0}
        option_count = 0
        try:
            with self.store.connect() as db:
                for symbol in UNIVERSE:
                    snapshot = self.client.json("data", "snapshot", "--symbol", symbol, "--feed", self.feed)
                    bars = self._bars(symbol, captured_at)
                    quote, trade = snapshot.get("latestQuote") or {}, snapshot.get("latestTrade") or {}
                    bid, ask = float(quote.get("bp") or 0), float(quote.get("ap") or 0)
                    mid = (bid + ask) / 2
                    returns = [float(b["c"]) / float(a["c"]) - 1 for a, b in zip(bars, bars[1:], strict=False) if float(a["c"]) > 0]
                    realized = pstdev(returns[-60:]) * math.sqrt(252 * 390) if len(returns) > 1 else None
                    db.execute(
                        """INSERT INTO underlying_snapshots(
                        batch_id,captured_at,symbol,trade_price,trade_size,bid,ask,spread,spread_pct,
                        minute_volume,daily_volume,return_5m,return_15m,return_30m,return_60m,
                        realized_volatility,quote_timestamp,trade_timestamp,snapshot_json,bars_json
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            batch_id,
                            captured_at.isoformat(),
                            symbol,
                            trade.get("p"),
                            trade.get("s"),
                            bid,
                            ask,
                            ask - bid,
                            (ask - bid) / mid if mid > 0 else None,
                            (snapshot.get("minuteBar") or {}).get("v"),
                            (snapshot.get("dailyBar") or {}).get("v"),
                            _returns(bars, 5),
                            _returns(bars, 15),
                            _returns(bars, 30),
                            _returns(bars, 60),
                            realized,
                            quote.get("t"),
                            trade.get("t"),
                            json.dumps(snapshot, separators=(",", ":")),
                            json.dumps(bars, separators=(",", ":")),
                        ),
                    )
                    for contract_symbol, payload in self._chain(symbol, captured_at).items():
                        match = OCC_RE.match(contract_symbol)
                        quote, trade = payload.get("latestQuote") or {}, payload.get("latestTrade") or {}
                        if not match:
                            continue
                        bid, ask = float(quote.get("bp") or 0), float(quote.get("ap") or 0)
                        mid = (bid + ask) / 2
                        quote_at = _iso(quote.get("t"))
                        greeks = payload.get("greeks") or {}
                        daily = payload.get("dailyBar") or {}
                        db.execute(
                            """INSERT INTO option_snapshots(
                            batch_id,captured_at,underlying,contract_symbol,expiry,strike,option_type,
                            bid,ask,mid,spread,spread_pct,bid_size,ask_size,trade_price,trade_size,volume,
                            open_interest,implied_volatility,delta,gamma,theta,vega,quote_timestamp,quote_age_seconds,payload_json
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                batch_id,
                                captured_at.isoformat(),
                                symbol,
                                contract_symbol,
                                datetime.strptime(match.group("date"), "%y%m%d").date().isoformat(),
                                int(match.group("strike")) / 1000,
                                "call" if match.group("type") == "C" else "put",
                                bid,
                                ask,
                                mid,
                                ask - bid,
                                (ask - bid) / mid if mid > 0 else None,
                                quote.get("bs"),
                                quote.get("as"),
                                trade.get("p"),
                                trade.get("s"),
                                daily.get("v"),
                                None,
                                payload.get("impliedVolatility"),
                                greeks.get("delta"),
                                greeks.get("gamma"),
                                greeks.get("theta"),
                                greeks.get("vega"),
                                quote.get("t"),
                                (captured_at - quote_at).total_seconds() if quote_at else None,
                                json.dumps(payload, separators=(",", ":")),
                            ),
                        )
                        option_count += 1
                duration = time.perf_counter() - started
                db.execute(
                    "UPDATE capture_batches SET completed_at=?,status='COMPLETE',duration_seconds=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), duration, batch_id),
                )
                db.commit()
            return {
                "batch_id": batch_id,
                "market_open": True,
                "symbols": len(UNIVERSE),
                "option_contracts": option_count,
                "duration_seconds": duration,
            }
        except Exception as exc:
            with self.store.connect() as db:
                db.execute(
                    "UPDATE capture_batches SET completed_at=?,status='ERROR',duration_seconds=?,error=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), time.perf_counter() - started, str(exc)[:500], batch_id),
                )
                db.commit()
            raise


@dataclass(frozen=True)
class ShadowConfig:
    config_id: str
    min_direction: float
    long_vol_disagreement: float
    dte_target: int
    max_spread_pct: float
    max_loss: float


def shadow_configs() -> list[ShadowConfig]:
    return [
        ShadowConfig(f"shadow-{index:02d}", direction, disagreement, dte, spread, loss)
        for index, (direction, disagreement, dte, spread, loss) in enumerate(
            product((0.08, 0.12), (0.12, 0.18), (10, 28), (0.18, 0.50), (500.0, 2000.0)), start=1
        )
    ]


def _nearest(contracts: list[OptionContract], option_type: str, target: float, expiry: str) -> OptionContract | None:
    pool = [x for x in contracts if x.option_type == option_type and x.expiration == expiry and x.bid > 0 and x.ask > x.bid]
    return min(pool, key=lambda item: abs(item.strike - target), default=None)


def shadow_select(snapshot: MarketSnapshot, consensus: ConsensusMetrics, contracts: list[OptionContract], config: ShadowConfig) -> TradeCandidate:
    contracts = [item for item in contracts if 7 <= (date.fromisoformat(item.expiration) - snapshot.timestamp.date()).days <= 35]
    if not contracts:
        return TradeCandidate(symbol=snapshot.symbol, strategy=StrategyType.NO_TRADE, rationale="No usable option chain in shadow DTE range")
    target_expiry = snapshot.timestamp.date() + timedelta(days=config.dte_target)
    expiry = min({item.expiration for item in contracts}, key=lambda value: abs((date.fromisoformat(value) - target_expiry).days))
    ivs = [item.implied_volatility for item in contracts if item.implied_volatility]
    iv = mean(ivs) if ivs else snapshot.realized_volatility
    expected_move = snapshot.price * iv * math.sqrt(14 / 365)
    direction = consensus.expected_direction
    if consensus.disagreement > config.long_vol_disagreement and consensus.entropy > 0.72 and iv <= snapshot.realized_volatility * 1.35:
        strategy, targets = StrategyType.LONG_STRADDLE, (("call", snapshot.price, "buy"), ("put", snapshot.price, "buy"))
    elif direction > config.min_direction and consensus.directional_conviction > config.min_direction:
        strategy, targets = StrategyType.BULL_CALL_SPREAD, (("call", snapshot.price, "buy"), ("call", snapshot.price + expected_move, "sell"))
    elif direction < -config.min_direction and consensus.directional_conviction > config.min_direction:
        strategy, targets = StrategyType.BEAR_PUT_SPREAD, (("put", snapshot.price, "buy"), ("put", snapshot.price - expected_move, "sell"))
    elif consensus.entropy < 0.82 and iv > snapshot.realized_volatility * 1.1:
        strategy, targets = StrategyType.IRON_CONDOR, (
            ("put", snapshot.price - 1.4 * expected_move, "buy"),
            ("put", snapshot.price - expected_move, "sell"),
            ("call", snapshot.price + expected_move, "sell"),
            ("call", snapshot.price + 1.4 * expected_move, "buy"),
        )
    else:
        return TradeCandidate(symbol=snapshot.symbol, strategy=StrategyType.NO_TRADE, expiry=expiry, rationale="Shadow signal thresholds not met")
    chosen: list[OptionLeg] = []
    for option_type, target, side in targets:
        contract = _nearest(contracts, option_type, target, expiry)
        if contract is None or any(leg.contract.symbol == contract.symbol for leg in chosen):
            return TradeCandidate(symbol=snapshot.symbol, strategy=StrategyType.NO_TRADE, expiry=expiry, rationale="Incomplete shadow legs")
        chosen.append(OptionLeg(contract=contract, side=side))
    net_debit = sum((leg.contract.ask if leg.side == "buy" else -leg.contract.bid) * 100 for leg in chosen)
    if strategy is StrategyType.IRON_CONDOR:
        widths = [
            max(x.contract.strike for x in chosen if x.contract.option_type == kind)
            - min(x.contract.strike for x in chosen if x.contract.option_type == kind)
            for kind in ("put", "call")
        ]
        max_loss = max(0.0, max(widths) * 100 + net_debit)
    else:
        max_loss = max(0.0, net_debit)
    return TradeCandidate(
        symbol=snapshot.symbol,
        strategy=strategy,
        legs=chosen,
        expiry=expiry,
        expected_move=expected_move,
        estimated_debit=max(0.0, net_debit),
        max_loss=max_loss,
        rationale=f"shadow direction={direction:+.2f} disagreement={consensus.disagreement:.2f} entropy={consensus.entropy:.2f}",
    )


def _snapshot(row: sqlite3.Row) -> MarketSnapshot:
    bars = json.loads(row["bars_json"])
    closes = [float(item["c"]) for item in bars]
    return MarketSnapshot(
        symbol=row["symbol"],
        timestamp=datetime.fromisoformat(row["captured_at"]),
        price=float(row["trade_price"] or (row["bid"] + row["ask"]) / 2),
        previous_close=closes[-2] if len(closes) > 1 else float(row["trade_price"] or (row["bid"] + row["ask"]) / 2),
        momentum_1h=float(row["return_60m"] or 0),
        momentum_1d=float(row["return_60m"] or 0),
        realized_volatility=float(row["realized_volatility"] or 0.2),
    )


def _contracts(rows: list[sqlite3.Row]) -> list[OptionContract]:
    return [
        OptionContract(
            symbol=row["contract_symbol"],
            underlying=row["underlying"],
            expiration=row["expiry"],
            strike=row["strike"],
            option_type=row["option_type"],
            bid=row["bid"] or 0,
            ask=row["ask"] or 0,
            bid_size=int(row["bid_size"] or 0),
            ask_size=int(row["ask_size"] or 0),
            implied_volatility=row["implied_volatility"],
            delta=row["delta"],
            quote_timestamp=_iso(row["quote_timestamp"]) or datetime.fromisoformat(row["captured_at"]),
        )
        for row in rows
    ]


class ShadowHarness:
    def __init__(self, store: ShadowStore) -> None:
        self.store = store

    def run(self, *, latest_batches: int = 1) -> dict[str, Any]:
        configs = shadow_configs()
        decisions = 0
        base_settings = Settings(council_mode=CouncilMode.DETERMINISTIC, execution_mode=ExecutionMode.READ_ONLY)
        with self.store.connect() as db:
            batch_ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM capture_batches WHERE status='COMPLETE' ORDER BY captured_at DESC LIMIT ?", (latest_batches,)
                )
            ]
            for batch_id in reversed(batch_ids):
                underlyings = db.execute("SELECT * FROM underlying_snapshots WHERE batch_id=? ORDER BY symbol", (batch_id,)).fetchall()
                for underlying in underlyings:
                    snapshot = _snapshot(underlying)
                    option_rows = db.execute(
                        "SELECT * FROM option_snapshots WHERE batch_id=? AND underlying=?", (batch_id, snapshot.symbol)
                    ).fetchall()
                    contracts = _contracts(option_rows)
                    ivs = [item.implied_volatility for item in contracts if item.implied_volatility is not None]
                    if ivs:
                        snapshot = snapshot.model_copy(update={"implied_volatility": mean(ivs)})
                    opinions = [mind.evaluate(snapshot) for mind in market_council(base_settings)]
                    consensus = calculate_consensus(opinions)
                    candidates = [("production", True, select_strategy(snapshot, consensus, contracts), None)]
                    candidates.extend((config.config_id, False, shadow_select(snapshot, consensus, contracts, config), config) for config in configs)
                    for config_id, production, candidate, config in candidates:
                        skeptic = review_candidate(candidate, snapshot)
                        risk_settings = base_settings.model_copy(
                            update={
                                "max_loss_per_trade": base_settings.max_loss_per_trade if production else config.max_loss,
                                "max_bid_ask_spread_pct": base_settings.max_bid_ask_spread_pct if production else config.max_spread_pct,
                                "emergency_halt_file": self.store.path.parent / "SHADOW_HALT_DISABLED",
                            }
                        )
                        risk = evaluate_risk(candidate, PortfolioState(equity=100_000, buying_power=400_000), skeptic, risk_settings, now=snapshot.timestamp)
                        worst_spread = max((leg.contract.spread_pct for leg in candidate.legs), default=None)
                        entry_mid = sum((leg.contract.midpoint if leg.side == "buy" else -leg.contract.midpoint) * 100 for leg in candidate.legs)
                        payload = {
                            "configuration": (
                                {
                                    "config_id": "production",
                                    "max_loss": base_settings.max_loss_per_trade,
                                    "max_spread_pct": base_settings.max_bid_ask_spread_pct,
                                }
                                if production
                                else asdict(config)
                            ),
                            "consensus": consensus.model_dump(mode="json"),
                            "candidate": candidate.model_dump(mode="json"),
                            "skeptic": skeptic.model_dump(mode="json"),
                            "risk": risk.model_dump(mode="json"),
                        }
                        db.execute(
                            """INSERT OR REPLACE INTO shadow_results(
                            batch_id,captured_at,symbol,config_id,is_production,strategy,max_loss,worst_spread_pct,
                            skeptic_veto,risk_status,risk_reasons,signal_quality,structure_quality,risk_quality,
                            execution_quality,entry_mid,payload_json
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                batch_id,
                                snapshot.timestamp.isoformat(),
                                snapshot.symbol,
                                config_id,
                                production,
                                candidate.strategy,
                                candidate.max_loss,
                                worst_spread,
                                skeptic.veto_confidence >= 0.8,
                                risk.status,
                                json.dumps(risk.reason_codes),
                                "NO_SIGNAL" if candidate.strategy is StrategyType.NO_TRADE else "CANDIDATE",
                                "NO_STRUCTURE" if not candidate.legs else "STRUCTURED",
                                "ADMISSIBLE" if risk.status is RiskStatus.APPROVED else "REJECTED",
                                "LIQUID" if worst_spread is not None and worst_spread <= risk_settings.max_bid_ask_spread_pct else "UNEXECUTABLE",
                                entry_mid if candidate.legs else None,
                                json.dumps(payload, separators=(",", ":")),
                            ),
                        )
                        decisions += 1
            db.commit()
        self.score_outcomes()
        return self.summary(decisions)

    def score_outcomes(self) -> None:
        with self.store.connect() as db:
            rows = db.execute("SELECT id,symbol,captured_at,payload_json FROM shadow_results").fetchall()
            for row in rows:
                at = datetime.fromisoformat(row["captured_at"])
                values: dict[int, float | None] = {}
                future_batch_ids: dict[int, int | None] = {}
                for minutes in (5, 15, 30, 60):
                    future = db.execute(
                        "SELECT batch_id,trade_price FROM underlying_snapshots WHERE symbol=? AND captured_at>=? ORDER BY captured_at LIMIT 1",
                        (row["symbol"], (at + timedelta(minutes=minutes)).isoformat()),
                    ).fetchone()
                    current = db.execute(
                        "SELECT trade_price FROM underlying_snapshots WHERE symbol=? AND captured_at=?",
                        (row["symbol"], row["captured_at"]),
                    ).fetchone()
                    future_batch_ids[minutes] = int(future["batch_id"]) if future else None
                    values[minutes] = float(future["trade_price"]) / float(current[0]) - 1 if future and current and current[0] else None
                payload = json.loads(row["payload_json"])
                expected_direction = payload["consensus"]["expected_direction"]
                correct = None if values[60] is None else int(expected_direction * values[60] > 0)
                strategy = payload["candidate"]["strategy"]
                predicted_regime = "HIGH" if strategy == StrategyType.LONG_STRADDLE else "LOW" if strategy == StrategyType.IRON_CONDOR else None
                realized_volatility = db.execute(
                    "SELECT realized_volatility FROM underlying_snapshots WHERE symbol=? AND captured_at=?",
                    (row["symbol"], row["captured_at"]),
                ).fetchone()
                baseline_move = float(realized_volatility[0] or 0) * math.sqrt(60 / (252 * 390)) if realized_volatility else None
                regime_correct = (
                    None
                    if values[60] is None or predicted_regime is None or baseline_move is None
                    else int((abs(values[60]) > baseline_move) == (predicted_regime == "HIGH"))
                )
                option_mark_change = self._option_mark_change(db, payload, future_batch_ids[60])
                db.execute(
                    """UPDATE shadow_results SET forward_5m=?,forward_15m=?,forward_30m=?,forward_60m=?,
                    direction_correct_60m=?,vol_regime_correct_60m=?,option_mark_change=? WHERE id=?""",
                    (values[5], values[15], values[30], values[60], correct, regime_correct, option_mark_change, row["id"]),
                )
            db.commit()

    @staticmethod
    def _option_mark_change(db: sqlite3.Connection, payload: dict[str, Any], future_batch_id: int | None) -> float | None:
        """Return the 60-minute structure midpoint change, only with a complete leg set."""
        legs = payload["candidate"]["legs"]
        if not legs or future_batch_id is None:
            return None
        current_mark = 0.0
        future_mark = 0.0
        for leg in legs:
            contract = leg["contract"]
            sign = 1 if leg["side"] == "buy" else -1
            ratio = int(leg.get("ratio", 1))
            current_mark += sign * ratio * (float(contract["bid"]) + float(contract["ask"])) * 50
            future = db.execute(
                "SELECT mid FROM option_snapshots WHERE batch_id=? AND contract_symbol=?",
                (future_batch_id, contract["symbol"]),
            ).fetchone()
            if not future or future["mid"] is None:
                return None
            future_mark += sign * ratio * float(future["mid"]) * 100
        return future_mark - current_mark

    def summary(self, decisions: int = 0) -> dict[str, Any]:
        with self.store.connect() as db:
            batches = db.execute("SELECT count(*) FROM capture_batches WHERE status='COMPLETE'").fetchone()[0]
            snapshots = db.execute("SELECT count(*) FROM underlying_snapshots").fetchone()[0]
            contracts = db.execute("SELECT count(*) FROM option_snapshots").fetchone()[0]
            rows = db.execute(
                """SELECT config_id,is_production,count(*) decisions,
                sum(strategy!='NO_TRADE') candidates,sum(risk_status='APPROVED') approved,
                group_concat(DISTINCT CASE WHEN strategy!='NO_TRADE' THEN symbol END) candidate_symbols,
                avg(worst_spread_pct) avg_spread,avg(NULLIF(max_loss,0)) avg_max_loss,
                avg(skeptic_veto) skeptic_veto_rate,avg(strategy='NO_TRADE') no_trade_rate,
                avg(direction_correct_60m) direction_hit_rate,
                avg(vol_regime_correct_60m) vol_regime_hit_rate,
                avg(abs(forward_60m)) avg_abs_return_60m,avg(option_mark_change) avg_option_mark_change_60m
                FROM shadow_results GROUP BY config_id,is_production ORDER BY is_production DESC,config_id"""
            ).fetchall()
        return {
            "complete_batches": batches,
            "underlying_snapshots": snapshots,
            "option_contracts": contracts,
            "decisions_evaluated": decisions,
            "configs": [dict(row) for row in rows],
        }
