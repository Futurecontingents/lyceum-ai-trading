# Strategy recovery after the invalid Sep-01 test

Status: **DEVELOPMENT RESEARCH ONLY — NO EXECUTABLE EDGE DEMONSTRATED**

Sep-01 is development data for every conclusion in this document. Nothing here is Sep-01 OOS. The prior pre-open option-economics study used historical underlying data ending Aug-28 and Aug-31 option snapshots; the incident reconstruction and agent ablation add Sep-01 only as explicitly labelled diagnostics.

## Best current policy

**NO_TRADE / CASH** is the best defensible policy. Development executable P&L is $0 with zero crossing cost and zero drawdown. This is a control, not a profitable trading edge. No trade-producing system clears cash.

The machine-readable ranking is `artifacts/forward_test/strategy_leaderboard_v2.json`. Its samples are heterogeneous and therefore it is a triage ranking, not a shared-holdout leaderboard.

## Execution-first findings

The most important failure is **SIGNAL TOO SMALL + ENTRY LIQUIDITY + EXIT LIQUIDITY**, with holding-horizon and mapping contributions:

- Historical conditional underlying forecasts implied only $0.08–$0.53 gross per one-contract vertical observation at 15/30/60/90 minutes.
- Zero of 4,878 eligible directional structures had positive expected gross movement minus estimated round-trip quoted crossing.
- At 60 minutes, the broad mean-reversion aggregate earned +$3.23 at midpoint but paid $29.05 at entry and $40.77 at exit, producing -$66.59 mean executable P&L. Delta contributed +$2.30, gamma +$0.05, theta -$0.04, vega +$0.52, and residual +$0.39 per structure. The delta edge was roughly 30 times too small for the round trip.
- Longer holds improved some midpoint economics: mean reversion first became positive at 60 minutes and momentum at 90 minutes. Neither approached executable break-even before trustworthy tape ended.
- The best geometry cell was 60-minute momentum, narrow 22–35 DTE: 45 observations, +$271.05 total midpoint, -$979.90 executable, -$21.78 mean, -$20.00 median, 17.8% positive. Entry crossing was $523.50 and exit crossing $727.45. Its midpoint gross covered only 21.7% of crossing.
- Wider structures generally added legs and crossing faster than exposure. Narrow 22–35 DTE is the least-bad research geometry, not a candidate edge.
- Long volatility cannot be justified by realized-move prediction alone. Expected gamma/theta gross was $5.29–$9.83 per straddle versus $43.48–$67.87 quoted round-trip cost. The predeclared gross filter’s 28 selections lost $234 total (-$8.36 mean) on Aug-31.
- Short condors did not monetize apparent IV premium. Expected negative gamma plus round-trip crossing exceeded intraday theta across tested cells.
- 120-minute and end-of-session comparisons were not promoted because the available Aug-31 tape did not provide trustworthy, adequately populated causal exits. The sparse 90-minute result is diagnostic only.

The correct first target is therefore:

```text
TRADE if and only if
E[structure value change | timestamped state]
- entry crossing
- E[exit crossing | horizon, symbol, DTE, geometry, time]
- conservative slippage margin
> 0
```

NO_TRADE is the default. Direction is a second-stage choice only after a structure clears this economic gate.

## Agent value ablation

`scripts/agent_ablation.py` evaluated 112 Sep-01 judging decision sets; 84 had complete 60-minute underlying outcomes at the analysis cutoff. Exact point-in-time option mapping was not journaled at that cadence, so no subset is credited with executable P&L.

At 60 minutes:

| Signal | Hit rate | Direction/return corr. | Mean signed underlying return | Disagreement/abs-return corr. |
|---|---:|---:|---:|---:|
| Full council | 51.2% | 0.056 | -0.0044% | 0.065 |
| Technical only | 57.1% | 0.061 | -0.0006% | — |
| Options only | see machine artifact | see artifact | see artifact | — |
| Deterministic only | 56.0% | 0.048 | -0.0009% | -0.014 |
| Qwen model agents only | 46.4% | 0.069 | -0.0060% | -0.072 |
| Without News | 50.0% | 0.052 | -0.0032% | 0.054 |
| Without Bull | 47.6% | 0.069 | -0.0099% | 0.107 |
| Without Bear | 58.3% | 0.039 | +0.0014% | 0.054 |
| Momentum | 57.1% | 0.092 | +0.0217% | — |
| Mean reversion | 41.7% | -0.092 | -0.0217% | — |

These are small, overlapping, development-only samples. The full council did not beat technical-only or momentum on the displayed directional measures. Removing Bear improved hit rate but reduced correlation; removing Bull improved disagreement/absolute-return correlation while worsening signed economics. Those unstable trade-offs are not a selection basis. News, Bull, and Bear have no demonstrated incremental executable value.

Earlier historical walk-forward volatility modelling found disagreement improved 60-minute correlation only from 0.773998 to 0.779987 and MAE from 0.00142741 to 0.00140322. The MAE improvement corresponds to about $0.019 on a $767 underlying, or an intentionally generous $1.86 at 100-delta-share exposure—below even the cheapest observed option round trip.

The local Qwen replay produced only five scored states and no option P&L, so its high correlations are not evidence. A frontier Codex challenger was not run: this environment does not provide a timestamp-isolated, programmatically callable copy of the current reasoning model for batch evaluation without adding a runtime/API dependency, and present-day model knowledge would contaminate the historical information boundary.

## Ranked development candidates

1. **CASH_NO_TRADE** — $0, no trades. Best current policy; no edge claim.
2. **A cost-filtered momentum** — -$421.80 intended 60-minute executable P&L at the agreed evaluable Sep-01 cutoff. Reject.
3. **D post-hoc reconstructed ridge** — 45 scored five-minute trades, -$441.80 total, -$9.82 mean. Reject; reconstruction is not OOS.
4. **B cost-filtered reversion** — -$647.90 intended 30-minute executable P&L at the agreed evaluable Sep-01 cutoff. Reject.
5. **Narrow 22–35 DTE momentum, 60m** — 45 Aug-31 development observations, -$979.90 total, -$21.78 mean. Reject; one partial session.

Comparisons by total P&L are confounded by unequal trade counts and windows. Every trading candidate is negative on mean executable P&L as well. Cash wins both economically and under transaction-cost stress.

## Robustness assessment

- Chronology: historical calibration ends before Aug-31; Sep-01 is development only. There is no untouched option holdout remaining.
- Purge/embargo: historical underlying walk-forward splits were chronological; the option tape has only two captured dates and cannot support an honest independent split after Sep-01 was inspected.
- Cost stress: candidates already fail at quoted-side execution. Lower assumed effective spreads would be sensitivity analysis, not acceptance evidence.
- Parameter perturbation: 15/30/60/90-minute, three DTE bands, and narrow/wide geometry were compared using economically motivated cells; negative economics persist.
- Best trade and best symbol removal: no aggregate candidate qualifies for finalist robustness testing because none is positive before those removals. Removing favorable observations cannot repair a negative aggregate.
- Symbol/time decomposition: results are heterogeneous and exit liquidity dominates; no stable symbol or time bucket is promoted.
- Overlap: overlapping decisions materially reduce effective N. Reported raw counts are not treated as independent samples.
- Baselines: cash beats all; simple momentum was not improved by the full council on the Sep-01 development ablation.

## Next sealed generation

Infrastructure is ready for another *read-only* sealed experiment: typed contracts, five-opinion provenance, horizon-specific scoring, continuous producer, preflight, and live canary all pass. Strategy readiness does not follow.

- **CONTROL RERUN:** C/D may be rerun unchanged except for plumbing repair, in a separately hashed manifest, to test implementation fidelity. It must not be presented as a continuation or repair of Sep-01.
- **NEXT-GEN:** no trade-producing candidate is ready to seal. The first candidate should be a sparse two-stage `TRADE/NO_TRADE` policy with a horizon-specific exit-liquidity model and narrow 22–35 DTE structures only as an initial research restriction.

No new sealed test has been started. A clean future market date, committed code hash, frozen data cutoff, candidate hashes, and passing preflight are still required. After that future session opens, parameters must remain unchanged.

## Reproduction

```bash
.venv/bin/python scripts/nextgen_option_economics.py \
  --output artifacts/nextgen_research/option_economics_preopen_freeze_2026-09-01.json
.venv/bin/python scripts/agent_ablation.py
.venv/bin/python scripts/build_forensic_artifacts.py
```

Primary evidence:

- `research/sep02_option_economics_preopen_2026-09-01.md`
- `artifacts/nextgen_research/option_economics_preopen_freeze_2026-09-01.json`
- `artifacts/forward_test/agent_ablation_sep01_development.json`
- `artifacts/forward_test/experiment_ledger_v2.json`
- `artifacts/forward_test/strategy_leaderboard_v2.json`
