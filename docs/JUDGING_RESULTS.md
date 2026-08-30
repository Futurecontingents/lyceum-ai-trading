# Judging results

## Account baseline

- Environment: Alpaca Paper Trading
- Profile: `judging`
- Initial equity: `$100,000.00`
- Initial open positions: `0`
- Initial open orders: `0`
- Status: `ACTIVE`
- First autonomous market session: pending

## Observed examples

The 2026-08-30 closed-market READ_ONLY rehearsal used real Alpaca data and the isolated `data/judging.db` journal:

- Seven symbols completed the full analysis path; all seven risk decisions were `REJECTED`.
- One decision selected `NO_TRADE`; six produced candidates that were rejected before execution.
- Five candidates received `SKEPTIC_VETO`; weekend quote age produced `STALE_QUOTE` where applicable.
- Observed Jensen–Shannon disagreement ranged from `0.0610` to `0.1611` (mean `0.0915`).
- Thirty-five deterministic opinions and 28 pending counterfactuals were journaled.
- Broker orders, fills, and open positions remained zero; equity remained `$100,000.00`.

Demo and development results are excluded. No performance conclusion is drawn from this setup rehearsal.
