# Operations

## Daily 20-minute routine

1. `git pull && source .venv/bin/activate`
2. `python -m lyceum doctor`
3. `python -m lyceum run --once` during market hours
4. `python -m lyceum dashboard`
5. Review the latest decision, skeptic objection, risk reasons, errors, and counterfactuals.
6. `pytest && ruff check .`

Keep `READ_ONLY` until observed decisions and option liquidity look sensible. `SIMULATED` is the next step. Enabling `PAPER_AUTONOMOUS` is deliberate and never enables live money.

## Emergency halt

```bash
touch HALT
```

This rejects new candidates at the deterministic gate. It does not liquidate or modify positions. Inspect account state through the paper dashboard or `alpaca position list` before deciding any further action.

## Logs and memory

Structured decision state is stored in `data/lyceum.db`, which is ignored by Git. The dashboard reads the database directly. API and parsing failures live in the `errors` table. Never add `.env`, database files, OAuth profiles, or terminal dumps containing tokens to Git.
