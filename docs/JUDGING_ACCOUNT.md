# Judging Paper Account

Lyceum uses a dedicated, fresh **$100,000 Alpaca paper account** authenticated as the local CLI profile `judging`. The account was validated as `ACTIVE`, with zero initial positions and orders, before the autonomous paper service was armed. Account identifiers and OAuth credentials are machine-local and are not committed.

## Safety invariants

- Endpoint must equal `https://paper-api.alpaca.markets`.
- Live endpoints and live execution modes are rejected by configuration validation.
- Autonomous paper execution requires both `PAPER_AUTONOMOUS` and `LYCEUM_ENABLE_PAPER_ORDERS=true`.
- A missing/active `HALT` switch, stale data, failed model, skeptic veto, or deterministic risk rejection cannot be bypassed by an LLM.
- Development databases, positions, orders, and account identity are never copied into judging state.

## Local verification

```bash
alpaca profile list
alpaca --profile judging account get
python -m lyceum doctor
python -m lyceum run --once
```

The final command may stop at the market-clock check outside trading hours. For a non-trading validation, keep `LYCEUM_EXECUTION_MODE=READ_ONLY` and `LYCEUM_ENABLE_PAPER_ORDERS=false`.

Before every judged autonomous session, confirm the profile, paper endpoint, account status, account state, `HALT` absence, service health, and current risk configuration. Never paste credentials into documentation, logs, issues, or submission prose.
