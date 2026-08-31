"""SQLite decision journal: the dashboard's single source of truth."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_observations (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_opinions (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, agent TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, action TEXT NOT NULL, risk_status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rejected_trades (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, reason_codes TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, client_order_id TEXT UNIQUE, status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS positions (id INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, symbol TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pnl_snapshots (id INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, equity REAL NOT NULL, buying_power REAL NOT NULL, pnl REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS counterfactuals (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, decision_id INTEGER NOT NULL, action TEXT NOT NULL, outcome REAL, payload TEXT NOT NULL, FOREIGN KEY(decision_id) REFERENCES decisions(id));
CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, component TEXT NOT NULL, message TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opinions_symbol ON agent_opinions(symbol, created_at DESC);
"""


class Journal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def encode(payload: Any) -> str:
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        return json.dumps(payload, default=str, separators=(",", ":"))

    def _insert(self, sql: str, params: tuple[Any, ...]) -> int:
        with self.connection() as connection:
            return int(connection.execute(sql, params).lastrowid)

    def record_observation(self, symbol: str, payload: Any) -> int:
        return self._insert(
            "INSERT INTO market_observations(created_at,symbol,payload) VALUES(?,?,?)", (self.now(), symbol, self.encode(payload))
        )

    def record_opinion(self, symbol: str, agent: str, payload: Any) -> int:
        return self._insert(
            "INSERT INTO agent_opinions(created_at,symbol,agent,payload) VALUES(?,?,?,?)", (self.now(), symbol, agent, self.encode(payload))
        )

    def record_decision(self, symbol: str, action: str, risk_status: str, payload: Any) -> int:
        return self._insert(
            "INSERT INTO decisions(created_at,symbol,action,risk_status,payload) VALUES(?,?,?,?,?)",
            (self.now(), symbol, action, risk_status, self.encode(payload)),
        )

    def record_rejection(self, symbol: str, reasons: list[str], payload: Any) -> int:
        return self._insert(
            "INSERT INTO rejected_trades(created_at,symbol,reason_codes,payload) VALUES(?,?,?,?)",
            (self.now(), symbol, self.encode(reasons), self.encode(payload)),
        )

    def record_order(self, client_order_id: str, status: str, payload: Any) -> int:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO orders(created_at,client_order_id,status,payload) VALUES(?,?,?,?)
                ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status,payload=excluded.payload""",
                (self.now(), client_order_id, status, self.encode(payload)),
            )
            row = connection.execute("SELECT id FROM orders WHERE client_order_id=?", (client_order_id,)).fetchone()
        return int(row[0])

    def record_counterfactual(self, decision_id: int, action: str, payload: Any) -> int:
        return self._insert(
            "INSERT INTO counterfactuals(created_at,decision_id,action,payload) VALUES(?,?,?,?)",
            (self.now(), decision_id, action, self.encode(payload)),
        )

    def record_pnl(self, equity: float, buying_power: float, pnl: float = 0) -> int:
        return self._insert(
            "INSERT INTO pnl_snapshots(captured_at,equity,buying_power,pnl) VALUES(?,?,?,?)", (self.now(), equity, buying_power, pnl)
        )

    def record_error(self, component: str, message: str, payload: Any | None = None) -> int:
        return self._insert(
            "INSERT INTO errors(created_at,component,message,payload) VALUES(?,?,?,?)",
            (self.now(), component, message, self.encode(payload or {})),
        )

    def recent(self, table: str, limit: int = 50) -> list[dict[str, Any]]:
        allowed = {"decisions", "agent_opinions", "pnl_snapshots", "counterfactuals", "errors", "rejected_trades"}
        if table not in allowed:
            raise ValueError("unsupported journal table")
        time_column = "captured_at" if table == "pnl_snapshots" else "created_at"
        with self.connection() as connection:
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY {time_column} DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def has_client_order(self, client_order_id: str) -> bool:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM orders WHERE client_order_id=? AND status NOT IN ('REJECTED','CANCELED','CANCELLED')",
                (client_order_id,),
            ).fetchone()
        return row is not None

    def last_symbol_trade_at(self, symbol: str) -> datetime | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT created_at FROM decisions
                WHERE symbol=? AND action!='NO_TRADE'
                AND json_extract(payload,'$.execution.status') IN ('SUBMITTED','SIMULATED_FILL')
                ORDER BY created_at DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None
