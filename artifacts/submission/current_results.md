# Lyceum Current Results

Generated from frozen or append-only machine artifacts at `2026-09-02T12:46:30Z`.

> Historical association, development diagnostics, sealed forward evidence, and paper execution are separate layers. No profitability claim.

## LONG-HISTORY — COMPLETED

- SPY: **8,453** sessions / **33.58 years**, 1993-01-29 through 2026-08-28
- S&P 500 proxy: **14,286** sessions / **56.65 years** (Regime context only; not tradeable option history.)
- Registered hypotheses: **19**
- Close-to-open SPY drift: N=8,452, mean 0.0403%, HAC t=5.82, supported=TRUE
- HAR ridge volatility forecast: OOS N=2,674, correlation 0.676, OOS R² 0.464

Conclusion: Underlying drift and volatility predictability are supported. Neither is automatically executable option alpha.

## HISTORICAL — COMPLETED

- Dataset: **361,439** five-minute bars, **666** sessions, 2024-01-02 through 2026-08-28
- Symbols: SPY, QQQ, AAPL, NVDA, AMD, META, TSLA
- Split: expanding monthly tests from 2025-01; 12 five-minute bars purged per symbol at every boundary
- Best tested momentum directional hit rate: **49.42%**
- Best tested reversal directional hit rate: **50.47%**
- 60-minute realized-volatility correlation: **0.780**
- Same volatility model without disagreement: **0.774**
- Incremental correlation from disagreement: **+0.006**

Conclusion: Directional performance is weak and not an executable edge claim. Realized volatility is more predictable; disagreement adds modest information.

## DEVELOPMENT — FROZEN_PREMARKET

This is an execution-economics diagnostic from one captured late-session option date, **not** an untouched holdout.

- Signal/hold: five-minute reversal, 60 minutes
- Structure observations: 460
- Mean midpoint P&L: **$+3.23**
- Mean entry crossing cost: **$29.05**
- Mean exit crossing cost: **$40.77**
- Mean round-trip crossing cost: **$69.82**
- Mean conservative executable P&L: **$-66.59**

Conclusion: A positive midpoint diagnostic became strongly negative at quoted sides. The sample is too narrow for a production claim.

## OPTION EXECUTION — DEVELOPMENT_DIAGNOSTIC

- Point-in-time option structures: **9,627**
- Directional structures: **4,878**
- Median delta-adjusted spot hurdle: **$4.44**
- A01 expected recent SPY move: **$0.44**
- Expected move / cost hurdle: **0.098**
- Economically clears: **FALSE**

Conclusion: Statistical predictability did not survive the observed quoted-side option hurdle.

## SEALED FORWARD — INVALID_INCIDENT_PRESERVED

- Session: 2026-09-01
- Candidates: A, B, C, D, E
- Order submission: PROHIBITED

The complete A-E comparison is invalid: C/D lacked required live council features, and sub-60-minute MFE/MAE contained lookahead. The failed run is not reranked.

The original artifacts are preserved. Infrastructure repairs do not repair the failed experiment, and no clean sealed rerun has completed.

## FORWARD EVIDENCE AFTER THE INCIDENT

- Sep-02: Pre-open execution-economics diagnostic only; no trade-producing sealed candidate promoted.
- Sep-03: **FROZEN / READ_ONLY_SHADOW**, frozen 2026-09-02T12:46:30Z; trade-producing candidates: 0; orders: PROHIBITED.

Observation-only future evidence; static preflight passed and live canary remains session-time evidence. One or two sessions remain anecdotal evidence, not statistical proof.

## PAPER EXECUTION — NO_PUBLIC_PERFORMANCE_RESULT_CLAIMED

- Fresh judging baseline: **$100,000**
- Orders submitted during submission validation: **0**
- No public paper P&L or profitability claim is made.

## Reproduce

```bash
python scripts/build_submission_results.py
```

Machine-local source artifacts are preserved for audit; deliberately sanitized long-history summaries and frozen public manifests are tracked. This generated summary contains no credentials or account identifiers.
