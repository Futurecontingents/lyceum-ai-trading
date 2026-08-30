# Judging operations

Lyceum is installed as a user `launchd` service named `com.lyceum.judging`. It stays dormant while Alpaca's authoritative clock is closed and checks again every five minutes. During an open session it runs the normal 15-minute cycle. The service is wrapped in `caffeinate -s`, so the Mac remains awake while connected to AC power; the display may sleep and the session may remain locked.

All commands below run from the repository root.

## Routine commands

```bash
# STATUS
launchctl print gui/$(id -u)/com.lyceum.judging

# RECENT LOGS
tail -n 100 logs/judging-service.log logs/judging-service.err.log

# TODAY'S DECISIONS
sqlite3 data/judging.db "select created_at,symbol,action,risk_status from decisions where date(created_at)=date('now') order by created_at desc;"

# ORDERS / POSITIONS
alpaca --profile judging order list --status all
alpaca --profile judging position list

# EMERGENCY HALT (blocks new orders; does not liquidate)
touch HALT

# RESUME AFTER HALT (only after reviewing account, orders, logs, and errors)
rm HALT

# DISABLE AUTONOMOUS SERVICE
launchctl bootout gui/$(id -u) "$HOME/Library/LaunchAgents/com.lyceum.judging.plist"

# START MANUALLY
scripts/start_judging_session.sh --manual

# RUN DAILY REPORT
source .venv/bin/activate && python scripts/daily_check.py
```

To re-enable after a deliberate `bootout`:

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.lyceum.judging.plist"
launchctl enable gui/$(id -u)/com.lyceum.judging
launchctl kickstart -k gui/$(id -u)/com.lyceum.judging
```

## Safety behavior

- `.env` is machine-local, ignored by Git, and pins the `judging` CLI profile plus its API account UUID.
- `PAPER_AUTONOMOUS` requires both the explicit enable flag and pinned account ID.
- Every cycle verifies `ACTIVE`, the exact account UUID, and `https://paper-api.alpaca.markets`.
- The execution boundary rechecks account identity, `HALT`, and Alpaca's clock immediately before submission.
- `SUBMISSION_INTENT` is durable before the CLI call. A timeout or malformed acknowledgement becomes `UNKNOWN`, creates `HALT`, and is never blindly retried.
- Closed-market READ_ONLY rehearsal is a separate explicit command and cannot run in autonomous mode.
- The dashboard uses `data/judging.db` and labels it `JUDGING`; demo and development journals remain separate.

## Power and shutdown

Keep the Mac connected to its charger with the lid open. Locking the Mac and allowing the display to sleep are safe. Closing a MacBook lid normally suspends it even when `caffeinate` is active. `SIGTERM` and `SIGINT` cause a clean stop after the current bounded operation.
