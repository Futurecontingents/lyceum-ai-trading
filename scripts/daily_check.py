#!/usr/bin/env python3
"""Factual judging-session report from Alpaca and the isolated SQLite journal."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lyceum.config import load_settings
from lyceum.data import AlpacaCliGateway


def cli_json(profile: str, *args: str) -> Any:
    completed = subprocess.run(
        ["alpaca", "--profile", profile, *args], capture_output=True, text=True, timeout=30, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def rows(connection: sqlite3.Connection, table: str, date: str) -> list[sqlite3.Row]:
    time_column = "captured_at" if table == "pnl_snapshots" else "created_at"
    return connection.execute(
        f"SELECT * FROM {table} WHERE substr({time_column},1,10)=? ORDER BY {time_column}", (date,)
    ).fetchall()


def payload(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["payload"])


def money(value: float | None) -> str:
    return "unavailable" if value is None else f"${value:,.2f}"


def main() -> None:
    settings = load_settings()
    if settings.alpaca_profile != "judging":
        raise SystemExit("Refusing report: LYCEUM_ALPACA_PROFILE must be judging")
    summary = AlpacaCliGateway(settings.alpaca_profile).validate_startup(expected_account_id=settings.expected_account_id)
    account = cli_json(settings.alpaca_profile, "account", "get")
    positions_raw = cli_json(settings.alpaca_profile, "position", "list")
    orders_raw = cli_json(settings.alpaca_profile, "order", "list", "--status", "all")
    positions = positions_raw if isinstance(positions_raw, list) else positions_raw.get("positions", [])
    orders = orders_raw if isinstance(orders_raw, list) else orders_raw.get("orders", [])
    date = datetime.now(UTC).date().isoformat()

    connection = sqlite3.connect(Path(settings.database_path))
    connection.row_factory = sqlite3.Row
    decisions = rows(connection, "decisions", date)
    opinions = rows(connection, "agent_opinions", date)
    pnl = rows(connection, "pnl_snapshots", date)
    errors = rows(connection, "errors", date)
    counterfactuals = rows(connection, "counterfactuals", date)
    connection.close()

    decision_payloads = [payload(row) for row in decisions]
    opinion_payloads = [payload(row) for row in opinions]
    equities = [float(row["equity"]) for row in pnl]
    start_equity = equities[0] if equities else None
    end_equity = equities[-1] if equities else float(summary["equity"])
    peak = equities[0] if equities else end_equity
    max_drawdown = 0.0
    for equity in equities:
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    unrealized = sum(float(item.get("unrealized_pl") or 0) for item in positions)
    last_equity = float(account.get("last_equity") or end_equity)
    total_daily_pnl = end_equity - last_equity
    interpreted_realized = total_daily_pnl - unrealized
    order_statuses = Counter(str(item.get("status", "unknown")).lower() for item in orders)
    skeptic_vetoes = sum("SKEPTIC_VETO" in item["risk"]["reason_codes"] for item in decision_payloads)
    risk_rejections = sum(row["risk_status"] == "REJECTED" for row in decisions)
    model_backed = sum(item.get("implementation") == "model" for item in opinion_payloads)
    fallbacks = sum(bool(item.get("fallback_used")) for item in opinion_payloads)
    disagreements = [float(item["consensus"]["disagreement"]) for item in decision_payloads]

    print(f"# Lyceum judging report — {date}\n")
    print("## Observed facts\n")
    print(f"- Profile: `{summary['profile']}`; endpoint: `{summary['endpoint']}`; status: `{summary['status']}`")
    print(f"- Starting equity observed: {money(start_equity)}")
    print(f"- Ending equity observed: {money(end_equity)}")
    print(f"- Alpaca daily equity change: {money(total_daily_pnl)}")
    print(f"- Open-position unrealized P&L: {money(unrealized)}")
    print(f"- Maximum observed intraday drawdown: {money(max_drawdown)}")
    print(f"- Autonomous preflight cycles: {len(pnl)}")
    print(f"- Decisions: {len(decisions)}; NO_TRADE: {sum(row['action'] == 'NO_TRADE' for row in decisions)}")
    print(f"- Candidate trades: {sum(row['action'] != 'NO_TRADE' for row in decisions)}")
    print(f"- Skeptic vetoes: {skeptic_vetoes}; risk rejections: {risk_rejections}")
    print(f"- Orders observed: {len(orders)}; statuses: {dict(order_statuses)}")
    print(f"- Fills: {order_statuses['filled']}; cancellations: {order_statuses['canceled'] + order_statuses['cancelled']}; rejections: {order_statuses['rejected']}")
    print(f"- Open positions: {len(positions)}")
    print(
        "- Disagreement mean/max: "
        + (f"{sum(disagreements) / len(disagreements):.4f}/{max(disagreements):.4f}" if disagreements else "unavailable")
    )
    print(f"- Model-backed opinions: {model_backed}; deterministic fallbacks: {fallbacks}")
    print(f"- API/model errors journaled: {len(errors)}; counterfactuals captured: {len(counterfactuals)}")
    print("\n## Interpretation\n")
    print(f"- Approximate realized P&L (daily equity change minus current unrealized P&L): {money(interpreted_realized)}")
    print("- This approximation is not a broker tax-lot realization report and is labeled interpretation, not observed fact.")
    print("- No strategy-performance conclusion is made from a single session or from absent trades.")


if __name__ == "__main__":
    main()
