# Sep-03 preregistration

Status: **RESEARCH SPECIFICATION READY; EXECUTION PREFLIGHT NOT READY; RUNNER NOT ARMED**.

Freeze cutoff: 2026-08-28 for historical fitting; recent option evidence cutoff is strictly before 2026-09-01 market open. No Sep-01 outcome was used to fit a promoted rule. No production or frozen forward-test configuration is changed by this document.

The evidence does not justify another option strategy. Sep-03 is therefore preregistered as a read-only/shadow discrimination test with a fail-closed NO_TRADE control. This is scientifically preferable to forcing an option order.

## Frozen candidates (maximum four)

### CONTROL — cash / NO_TRADE

- Signal/features/model: none.
- Decision: `NO_TRADE` for every observation.
- Option construction/execution/holding/risk: none; zero orders and zero max loss.
- Purpose: executable P&L baseline of $0.

### NEXTGEN_A — overnight drift observation

- Signal: SPY prior regular-session close to next regular-session open, unconditional.
- Target: close-to-open underlying return.
- Parameter/model: none.
- Universe: SPY only.
- Option rule: `NO_TRADE`; observed expected spot move $0.44 is below the $4.44 median vertical hurdle and no overnight NBBO exit sample exists.
- Observation horizon: one overnight interval.
- Risk/execution: read-only; no order.
- Promotion question: does future close-to-open movement remain positive, and can separately collected overnight option quotes ever lower the hurdle without assuming midpoint fills?

### NEXTGEN_B — HAR-ridge volatility observation

- Features: current absolute SPY log return, trailing 5-day RMS, trailing 22-day RMS.
- Model: expanding ridge linear regression with intercept unpenalized and diagonal feature penalty 10; training data ends 2026-08-28.
- Target: square root of sum of next five daily squared log returns.
- Universe: SPY only.
- Option rule: `NO_TRADE` until forecasted dollar value change exceeds contemporaneous quoted-side round-trip cost with a positive buffer; the present dataset establishes no valid fixed buffer, so Sep-03 remains observation-only.
- Holding horizon: five sessions for forecast scoring.
- Risk/execution: read-only; no order.

### NEXTGEN_C — capitulation timing observation

- Signal: prior SPY adjusted close return <= -2.0%.
- Target: next-session open-to-30-minute return and next-five-session return.
- Universe: SPY only; no news/council features.
- Option rule: `NO_TRADE`; recent 30-minute N=14 and historical sealed holdout N=15 are below promotion requirements.
- Holding/scoring: 30 minutes and five sessions, recorded separately.
- Risk/execution: read-only; no order.

## Frozen integrity and reproduction

- Seed: `20260902`.
- Chronological splits: early 1993-01-29–2006-12-29; middle 2007-01-01–2015-12-31; recent 2016-01-01–2022-12-30; sealed holdout 2023-01-01–2026-08-28.
- Research scripts: `scripts/long_history_data.py`, `scripts/long_history_campaign.py`, `scripts/long_history_regimes.py`, `scripts/long_history_bridge.py`.
- Machine manifests: `artifacts/long_history/*.json`.
- Starting HEAD: `62002e3a9607a86286f4a4a433eb872db8b21dc6`.
- Frozen research implementation/result commit: `e05b75d`.

## Fail-closed preflight

The repaired read-only infrastructure preflight was run at 2026-09-02T12:30:09Z and preserved as `artifacts/long_history/sep03_infrastructure_preflight.json`. Paper endpoint, services, SQLite, seven-symbol/five-agent coverage, option quotes, output storage, and read-only runner checks passed. The overall result was **FAIL** because the latest complete batch was 59,599 seconds old during the off-hours check. The preflight also requires the legacy five-candidate Sep-01 manifest and cannot truthfully validate this four-candidate observation-only specification without changing runner behavior. Consequently Sep-03 is **NOT READY**, no runner is armed, and no tuning or orders may occur after market open. The research package itself is reproducible and ready for audit.
