#!/usr/bin/env python3
"""Fetch, preserve, normalize, and reconcile long-history market data."""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import certifi
import pandas as pd

CUTOFF = "2026-08-28"
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "^GSPC")
YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?period1=0&period2=1788048000&interval=1d&events=div%2Csplits&includeAdjustedClose=true"
NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass=etf&fromdate=2024-01-01&todate=2026-08-28&limit=5000"
CBOE_VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
FRED_DGS10_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        return
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; LyceumResearch/1.0)",
            "Accept": "application/json,text/csv,text/plain,*/*",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    payload = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                payload = response.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(2 ** attempt)
    if payload is None:  # pragma: no cover - defensive guard
        raise RuntimeError(f"No payload returned for {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def yahoo_frame(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = json.loads(path.read_text())
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(timestamps, unit="s", utc=True).date,
            "open_raw": quote["open"], "high_raw": quote["high"], "low_raw": quote["low"],
            "close_raw": quote["close"], "volume": quote["volume"], "close": adjusted,
        }
    ).dropna(subset=["close_raw", "close"])
    factor = frame["close"] / frame["close_raw"]
    for field in ("open", "high", "low"):
        frame[field] = frame[f"{field}_raw"] * factor
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[frame["date"] <= pd.Timestamp(CUTOFF)].sort_values("date").drop_duplicates("date")
    meta = result["meta"]
    return frame, {
        "timezone": meta.get("exchangeTimezoneName"), "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName"), "first_trade_timestamp": meta.get("firstTradeDate"),
    }


def nasdaq_frame(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    rows = payload["data"]["tradesTable"]["rows"]
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    for field in ("close", "open", "high", "low"):
        column = "close" if field == "close" else field
        frame[field] = pd.to_numeric(frame[column].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False))
    return frame.sort_values("date")


def missing_weekdays(frame: pd.DataFrame) -> int:
    expected = pd.bdate_range(frame["date"].min(), frame["date"].max())
    return len(expected.difference(pd.DatetimeIndex(frame["date"])))


def build(output: Path, *, force: bool = False) -> dict[str, Any]:
    raw = output / "raw"
    normalized = output / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(UTC).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": 1, "fetched_at": fetched_at, "cutoff": CUTOFF,
        "provider_splicing": "PROHIBITED", "instruments": [], "reconciliation": {},
        "unavailable_sources": [
            {"provider": "Stooq", "status": "BLOCKED_ANTI_BOT_CHALLENGE", "used": False}
        ],
    }
    for symbol in SYMBOLS:
        encoded = urllib.parse.quote(symbol, safe="")
        url = YAHOO_URL.format(symbol=encoded)
        path = raw / f"yahoo_{symbol.replace('^', 'index_')}.json"
        fetch(url, path, force=force)
        frame, metadata = yahoo_frame(path)
        normalized_path = normalized / f"{symbol.replace('^', 'index_')}_yahoo.csv"
        frame.to_csv(normalized_path, index=False, date_format="%Y-%m-%d")
        sessions = len(frame)
        span_years = (frame["date"].max() - frame["date"].min()).days / 365.2425
        manifest["instruments"].append(
            {
                "symbol": symbol, "proxy": "S&P 500 index" if symbol == "^GSPC" else symbol,
                "provider": "Yahoo Finance chart API", "source_url": url,
                "raw_path": str(path), "normalized_path": str(normalized_path),
                "raw_sha256": sha256(path), "normalized_sha256": sha256(normalized_path),
                "start": frame["date"].min().date().isoformat(),
                "end": frame["date"].max().date().isoformat(), "sessions": sessions,
                "calendar_years": span_years, "frequency": "daily",
                "adjustment": "Yahoo adjusted close; OHLC multiplied by same daily adjclose/raw-close factor",
                "corporate_actions": "Yahoo events embedded; normalized returns use adjusted OHLC",
                "timezone": metadata.get("timezone"), "missing_weekdays_including_exchange_holidays": missing_weekdays(frame),
                "coverage_quality": "PRIMARY_RESEARCH" if symbol != "^GSPC" else "LONG_PROXY_CLOSE_HISTORY",
                "limitations": "Free vendor feed; no point-in-time revisions or delisting panel; index is not directly tradeable" if symbol == "^GSPC" else "Free vendor feed; adjusted fields are vendor-derived",
            }
        )
    for symbol in ("SPY", "QQQ"):
        url = NASDAQ_URL.format(symbol=symbol)
        path = raw / f"nasdaq_{symbol}_2024_2026.json"
        fetch(url, path, force=force)
        nasdaq = nasdaq_frame(path)
        yahoo = pd.read_csv(normalized / f"{symbol}_yahoo.csv", parse_dates=["date"])
        merged = yahoo.merge(nasdaq[["date", "close"]], on="date", suffixes=("_yahoo", "_nasdaq"))
        differences = (merged["close_raw"] - merged["close_nasdaq"]).abs()
        anomalies = merged.loc[differences > 0.01, ["date", "close_raw", "close_nasdaq"]]
        strict_pass = int((differences > 0.01).sum()) == 0
        manifest["reconciliation"][symbol] = {
            "primary": "Yahoo raw close", "independent": "Nasdaq official public historical API raw close",
            "source_url": url, "raw_path": str(path), "raw_sha256": sha256(path),
            "overlap_sessions": len(merged), "max_absolute_close_difference": float(differences.max()),
            "median_absolute_close_difference": float(differences.median()),
            "sessions_with_difference_gt_0_01": int((differences > 0.01).sum()),
            "anomalies": [],
            "status": "PASS" if strict_pass else "FAIL",
        }
        for row in anomalies.itertuples():
            nasdaq_row = nasdaq.loc[nasdaq["date"] == row.date].iloc[0]
            prior_yahoo = yahoo.loc[yahoo["date"] < row.date].iloc[-1]
            placeholder = (
                str(nasdaq_row["volume"]) == "N/A"
                and len({float(nasdaq_row[field]) for field in ("open", "high", "low", "close")}) == 1
                and abs(float(nasdaq_row["close"]) - float(prior_yahoo["close_raw"])) <= 0.0001
            )
            manifest["reconciliation"][symbol]["anomalies"].append(
                {
                    "date": row.date.date().isoformat(),
                    "field": "raw_close",
                    "yahoo_raw_close": float(row.close_raw),
                    "nasdaq_close": float(row.close_nasdaq),
                    "absolute_difference": abs(float(row.close_raw) - float(row.close_nasdaq)),
                    "nasdaq_ohlc": {field: float(nasdaq_row[field]) for field in ("open", "high", "low", "close")},
                    "nasdaq_volume_raw": str(nasdaq_row["volume"]),
                    "prior_session_yahoo_raw_close": float(prior_yahoo["close_raw"]),
                    "classification": "NASDAQ_PLACEHOLDER_DUPLICATING_PRIOR_CLOSE" if placeholder else "UNEXPLAINED_PROVIDER_DISAGREEMENT",
                    "evidence_modified": False,
                }
            )
    manifest["independent_reconciliation_status"] = (
        "PASS" if all(item["status"] == "PASS" for item in manifest["reconciliation"].values()) else "FAIL"
    )
    auxiliary = (("cboe_vix.csv", CBOE_VIX_URL, "CBOE VIX"), ("fred_dgs10.csv", FRED_DGS10_URL, "FRED DGS10"))
    for filename, url, provider in auxiliary:
        path = raw / filename
        fetch(url, path, force=force)
        manifest.setdefault("auxiliary", []).append(
            {"provider": provider, "source_url": url, "raw_path": str(path), "raw_sha256": sha256(path)}
        )
    manifest_path = output / "data_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/long_history"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = build(args.output, force=args.force)
    print(json.dumps({"instruments": len(manifest["instruments"]), "reconciliation": manifest["reconciliation"]}, indent=2))


if __name__ == "__main__":
    main()
