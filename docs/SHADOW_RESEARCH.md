# Shadow market capture and research

Lyceum's shadow layer records the live market seen by the judging profile and evaluates alternate configurations without importing or calling the execution layer. It cannot place, cancel, or inspect orders or positions. The production service, strategy thresholds, risk gate, and account state are not modified.

## Capture scope

During market hours, each batch records SPY, QQQ, AAPL, NVDA, AMD, META, and TSLA:

- latest underlying trade and quote, sizes, spread, minute/day volume, raw 1-minute bars, 5/15/30/60-minute returns, and annualized realized volatility;
- every option strike returned by Alpaca between 7 and 35 DTE, with pagination;
- option bid/ask/mid, sizes, spread, latest trade, daily volume, IV when supplied, Greeks when supplied, quote timestamp/age, and the raw response.

Alpaca's option-chain snapshot does not supply trustworthy open interest, so `open_interest` remains null. Captures are append-only batches in the ignored machine-local `data/shadow_market.db` SQLite database (WAL mode). A failed batch remains recorded with `ERROR`; it is never treated as research input.

```bash
.venv/bin/python scripts/market_snapshot_collector.py --profile judging
```

The allowlisted CLI adapter accepts only `clock`, `data snapshot`, `data bars`, and `data option chain`. Trading, account, position, and other data commands fail closed before a subprocess starts.

## Shadow evaluation

```bash
.venv/bin/python scripts/shadow_research.py --latest-batches 12
```

Each snapshot is evaluated against the exact production selector plus 32 deterministic threshold combinations spanning direction, disagreement, DTE, spread, and maximum-loss bounds. The production selector is only a comparison row. Research uses READ_ONLY settings and the deterministic council so broad sweeps neither call a local LLM nor inherit the autonomous execution mode.

Every result stores signal, structure, skeptic, risk, and execution-quality stages separately. Once later captures exist, outcomes are filled using the first observation at or after 5, 15, 30, and 60 minutes. Long straddles are classified as high-volatility predictions and iron condors as low-volatility predictions; the 60-minute absolute move is compared with the snapshot's annualized realized-volatility baseline. Directional structures are left unscored for volatility regime. The option result is calculated only when all original legs exist in the 5-minute outcome batch; it is the signed structure midpoint change per contract. Missing or partial future option data remains null.

This is research evidence, not a strategy auto-tuner. No shadow setting is promoted to production automatically.

## Operations and containment

The local launch agent `com.lyceum.shadow-collector` uses a four-minute launch interval. Including a typical 30-second collection run, observed snapshots remain inside the requested five-minute cadence. It is deliberately a separate short-lived process. Typical memory is below 100 MB plus short CLI subprocesses; full-chain network/CPU work occurs sequentially, not in parallel. Stop it without affecting judging:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.lyceum.shadow-collector.plist
```

Inspect collector state independently:

```bash
launchctl print gui/$(id -u)/com.lyceum.shadow-collector
sqlite3 data/shadow_market.db 'select id,captured_at,status,duration_seconds,error from capture_batches order by id desc limit 10;'
```

The database, WAL files, launch-agent logs, credentials, and account-specific state are machine-local and must not be committed.
