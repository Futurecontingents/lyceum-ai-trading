# Signal-to-option bridge

## Layer 1 → Layer 2: exact timing

The recent Alpaca IEX sample contains 659 complete SPY regular sessions from 2024-01-02 through 2026-08-28. A01's exact close-to-next-open timing remains positive: N=658, mean **0.0638%**, median 0.0948%, t=2.57, hit rate 61.9%.

Daily signals do not automatically transfer intraday. C03 is negative at 15/30/60/90/120 minutes and close when entered at the next open. D02's best recent bridge is 30 minutes at 0.0189% (t=1.82), far below the option hurdle. E01's apparent 30-minute rebound is 0.2458%, but has only 14 events; H01's 120-minute result has only 8. These are not promoted.

## Layer 2 → Layer 3: actual observed option economics

The option dataset contains **9,627 actual point-in-time observations** from a single partial session (2026-08-31), across seven symbols and defined-risk verticals, straddles, and condors. It is recent real quote evidence, not fabricated historical chains.

| Structure | N | Mean midpoint diagnostic P&L | Mean quoted-side executable P&L | Median round-trip crossing |
|---|---:|---:|---:|---:|
| Directional vertical | 4,878 | -$0.92 | -$62.26 | $28.00 |
| Long straddle | 1,071 | +$5.06 | -$62.44 | $39.00 |
| Iron condor | 3,678 | -$1.61 | -$82.57 | $30.00 |

These definitions are deliberately separate:

1. **MIDPOINT DIAGNOSTIC:** exit midpoint minus entry midpoint.
2. **CONSERVATIVE QUOTED-SIDE EXECUTABLE:** exit executable quoted side minus entry executable quoted side.
3. **EMPIRICAL PAPER EXECUTION:** one isolated simulator trial: SPY 2026-09-04 763 call bought 3.17 and sold 3.16, -$1 before fees. The ask exit did not fill and was canceled. One PAPER fill is not live execution evidence and is excluded from inference.

## Minimum required edge

For 4,628 directional-vertical observations with absolute net delta of at least two shares, estimated spot break-even is `(entry crossing + exit crossing) / |net delta shares|`. Median required SPY-equivalent movement is **$4.44**. Breakdowns by DTE/geometry, symbol, spread bucket, and time of day are in `option_bridge.json`.

A01's recent mean move is approximately **$0.44** at the recent median SPY price. Its magnitude/cost ratio is **0.098**: about one-tenth of the observed median hurdle. This is also an optimistic comparison because the option sample has no overnight exit observations. Therefore:

> A01 is long-history supported but not option-tradeable. The correct option decision is NO_TRADE unless future point-in-time quotes establish a materially lower overnight hurdle.

The rare E01 30-minute estimate implies a larger spot move but remains underpowered and still generally below the observed $4.44 median hurdle. Sparse event trading remains a research direction, not a promoted strategy.

## Council increment

The available council ablation has 112 development-only decision sets. It is not an untouched OOS test conditional on HAR/ridge and lacks exact executable option mapping. Disagreement correlations rise at some horizons, but the council's incremental contribution is **INCONCLUSIVE**, not positive evidence.

Machine artifact: `artifacts/long_history/option_bridge.json`.
