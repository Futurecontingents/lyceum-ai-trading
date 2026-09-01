# Lyceum Current Results

Generated from frozen or append-only machine artifacts at `2026-09-01T18:01:47.821732+00:00`.

> Historical association, development diagnostics, sealed forward evidence, and paper execution are separate layers. No profitability claim.

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

## SEALED FORWARD — INVALID_INCIDENT_PRESERVED

- Session: 2026-09-01
- Candidates: A, B, C, D, E
- Order submission: PROHIBITED

The complete A-E comparison is invalid: C/D lacked required live council features, and sub-60-minute MFE/MAE contained lookahead. The failed run is not reranked.

The original artifacts are preserved. Infrastructure repairs do not repair the failed experiment, and no clean sealed rerun has completed.

## PAPER EXECUTION — NO_PUBLIC_PERFORMANCE_RESULT_CLAIMED

- Fresh judging baseline: **$100,000**
- Orders submitted during submission validation: **0**
- No public paper P&L or profitability claim is made.

## Reproduce

```bash
python scripts/build_submission_results.py
```

The three source result files under ignored `artifacts/` are machine-local and preserved for audit. The frozen public manifest is tracked. This generated, sanitized summary contains no credentials or account identifiers.
