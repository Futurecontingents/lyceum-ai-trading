# Lyceum final research report

**Research cutoff:** 2026-08-28 for fitted historical evidence. Later sessions are separated as forward, execution, or post-hoc evidence.

**Canonical conclusion:** No profitable executable option edge has been demonstrated. Lyceum rejects unsupported trades rather than manufacturing P&L.

## Executive conclusion

Lyceum tested whether probabilistic disagreement among five market agents can become cost-aware option decisions. The campaign spans 33.58 years / 8,453 SPY sessions, 56.65 years / 14,286 sessions of S&P 500 proxy history, 361,439 five-minute observations / 666 recent sessions, 19 registered long-history hypotheses, 9,627 recent point-in-time option-structure observations, and isolated Alpaca paper execution.

The evidence supports two forecasting statements: close-to-open SPY drift persists across decades, and a simple HAR-style realized-volatility model has meaningful out-of-sample predictability. It does **not** support a profitable option strategy. Ordinary expected moves are too small relative to entry and exit crossing costs, rare large-move states are underpowered or unstable, and the full LLM council has not demonstrated directional or executable value-add.

This distinction is the project’s central result: statistical predictability is not automatically executable option alpha.

## Evidence inventory

| Layer | Scope | Valid use |
|---|---|---|
| Long-history ETF | SPY 1993-01-29–2026-08-28; 8,453 sessions; 33.58 years | Underlying return and regime inference |
| Long S&P 500 proxy | 1970-01-02–2026-08-28; 14,286 sessions; 56.65 years | Regime context only; not tradeable option history |
| Recent intraday | 361,439 five-minute observations; 666 sessions; seven symbols | Causal intraday signal and volatility tests |
| Recent options | 9,627 point-in-time structures from one partial 2026-08-31 session | Execution-economics diagnostic, not a historical option backtest |
| Alpaca paper | One isolated buy/sell simulator trial and journaled paper service state | Plumbing/fill evidence only; no performance inference |
| Forward tests | Sep-01 failed sealed test; Sep-03 frozen read-only observer | Reported separately below |

The SPY independent-source reconciliation remains strict **FAIL** because of one vendor discrepancy: on 2026-04-20 Yahoo reports a raw close of $708.71997 while Nasdaq returns $710.14. The Nasdaq row duplicates the prior close in every OHLC field with no volume; Yahoo and independent contemporaneous sources support $708.72. No value was overwritten to force a pass.

## Methodology

The long-history campaign registered 19 hypotheses before ranking. It used fixed chronological discovery, validation, recent-validation, and sealed-holdout windows; expanding estimation; Newey–West/HAC uncertainty; moving-block bootstrap intervals; block-sign surrogate nulls; Benjamini–Hochberg correction; outcome-independent regime definitions; removal of the single best event; and drop-one-era checks. The option bridge separated midpoint diagnostics from quoted-side executable P&L and measured entry and exit crossing independently.

The repaired V2 validation path is fail closed: required features must be finite, present, causal, schema-valid, and linked to their producer. Council-dependent states require five agent opinions and recomputable consensus. Invalid observations are persisted with reasons but excluded from scoring. MFE/MAE windows are horizon bounded.

## Findings by evidentiary status

### SUPPORTED

1. **Close-to-open SPY drift is statistically supported across decades.** A01 (prior adjusted close to next adjusted open) has N=8,452, mean 0.0403%, HAC t=5.82, BH q=0.0150, and sealed-holdout mean 0.0494%. It is positive in seven of eight outcome-independent eras and remains positive after every mandated drop-one-era test. This supports an underlying effect, not an option trade.
2. **HAR-style volatility forecasting has meaningful out-of-sample predictability.** HAR ridge has OOS N=2,674, correlation 0.6758, MAE 0.007226, and OOS R² 0.4641 versus the pre-2016 unconditional mean. It improves MAE and R² over trailing-5- and trailing-22-day realized-volatility baselines. Ridge and OLS are nearly identical, so added complexity is not justified.
3. **Execution cost is a first-class target.** For 4,628 directional-vertical observations with sufficient delta, the median observed delta-adjusted spot hurdle is $4.44. A01 implies about $0.44 at the recent SPY price—a ratio of 0.098. At 60 minutes, mean reversion earned +$3.23 at midpoint but paid $29.05 entering and $40.77 exiting, producing -$66.59 mean quoted-side P&L.

### INCONCLUSIVE

1. **Full LLM council value-add.** On 84 complete Sep-01 development decision sets, the full council’s 60-minute directional hit rate was 51.2% versus 57.1% for technical-only and 57.1% for simple momentum. These are small, overlapping, post-incident development samples without exact option mapping. Historical disagreement improved a 60-minute volatility correlation only from 0.7740 to 0.7800 and MAE from 0.00142741 to 0.00140322—economically smaller than observed option costs.
2. **Rare capitulation states.** Prior SPY days below -5% and -3% show large signed move/cost ratios, but effective N and recent confirmation fail. The adequately populated <=-2% state has N=337, conservative effective N=67.4, expected signed movement $1.68, and a $1.75 symbol-specific hurdle: ratio 0.96, below the frozen 1.25 buffer.
3. **Volatility monetization.** HAR forecasts realized volatility, but long straddles and short condors did not clear quoted round trips. More point-in-time option history and fill-quality evidence would be required.

### REJECTED

1. **A proven profitable executable option edge.** None has been demonstrated.
2. **Ordinary short-horizon directional signals as option trades.** Zero of 4,878 eligible directional structures had positive expected gross movement after estimated quoted crossing.
3. **Midpoint P&L as executable performance.** Midpoints are diagnostic marks, not attainable fill claims.
4. **Full-council directional superiority.** It did not beat the relevant technical-only or simple momentum development baselines.
5. **Gap continuation, ETF-selection alpha, and ordinary intraday drift.** These failed holdout, baseline, or robustness gates.
6. **Interpreting disagreement as an option edge by itself.** Its measured forecast increment is too small relative to observed costs.

## Option execution economics

| Structure | Observations | Mean midpoint diagnostic | Mean quoted-side executable | Median round trip |
|---|---:|---:|---:|---:|
| Directional vertical | 4,878 | -$0.92 | -$62.26 | $28.00 |
| Long straddle | 1,071 | +$5.06 | -$62.44 | $39.00 |
| Iron condor | 3,678 | -$1.61 | -$82.57 | $30.00 |

Longer holds improved some midpoint results, but not enough to clear costs before trustworthy tape ended. Narrow 22–35 DTE verticals were less bad than wider structures, yet remained negative. Delta was the useful gross channel; gamma, theta, and vega were secondary over the tested horizons. Exit liquidity was often more expensive than entry liquidity, so a fixed entry-spread filter cannot establish executability.

The correct first-stage target is therefore:

```text
TRADE only if
E[structure value change | timestamped state]
- entry crossing
- E[exit crossing | horizon, symbol, DTE, geometry, time]
- conservative slippage margin
> 0
```

Direction is a second-stage decision. Otherwise the result is `NO_TRADE`.

## Sep-01 forward-test failure

Candidates A–E were frozen before the 2026-09-01 session, but the complete experiment is invalid. The deployed launch topology ran the raw market/option collector without the council producer. The runner then converted the missing council row to an empty mapping and silently imputed disagreement, entropy, and expected direction as zero. Candidate C and D therefore never received their frozen live feature vectors. Separately, one 60-minute excursion vector was reused for every 5/15/30/60-minute outcome, contaminating sub-60-minute MFE/MAE with future information.

The immutable incident snapshot contains 3,192 decisions across 57 batches, seven symbols, and eight evaluated systems. No order was submitted, cancelled, or modified during diagnosis or repair. The original experiment is preserved and never reranked.

The [Sep-01 reconstruction](sep01_reconstruction.md) is explicitly **POST-HOC ONLY**. It recomputed missing council outputs from surviving timestamped inputs after the session and is useful for debugging, not forward evidence. Its trade-producing aggregates remained negative at quoted sides; cash/`NO_TRADE` remained best.

## Forward evidence after the incident

- **Sep-02:** the option-economics analysis was frozen before the session and excluded Sep-01 outcomes, but it was a development diagnostic, not a completed sealed forward test. It promoted no trade-producing candidate.
- **Sep-03:** the specification was frozen at 2026-09-02T12:46:30Z with an Aug-28 data cutoff. It contains only a cash control and a non-trading SPY capitulation observer. Order submission and parameter changes are prohibited. Static preflight passed; the live-market canary and outcomes remain future evidence.

One or two sessions are anecdotal forward evidence, not statistical proof. When sufficient horizons mature, the public appendix must report N, signals, trades, `NO_TRADE`, midpoint diagnostic P&L, quoted-side executable P&L, paper fills, account equity, and integrity status without changing the frozen definitions.

## Final backend boundary

The canonical backend is the repaired V2 evidence and safety path:

```text
market data → five probabilistic agents → consensus / entropy / JSD
→ quantitative signals → option construction → execution-cost evaluation
→ skeptic → deterministic risk gate → Alpaca PAPER execution
→ provenance / journal / counterfactual scoring
```

The source boundary and SHA-256 hashes are frozen in [`final_backend_manifest.json`](final_backend_manifest.json). This freeze does not alter the Sep-01 or Sep-03 manifests, candidates, models, thresholds, option rules, runner behavior, or production configuration.

## Final conclusion

Lyceum’s strongest contribution is methodological integrity. It can represent AI beliefs probabilistically, test them against long history, translate them into options, detect when implementation invalidates an experiment, and reject proposals whose economics do not survive real execution costs. It does not claim that rejecting bad trades is itself alpha.

**AI proposes. Math validates. Alpaca executes.**

## Reproduce and audit

- [Data audit](long_history_data_audit.md)
- [Long-history signal campaign](long_history_signal_campaign.md)
- [Regime robustness](regime_robustness.md)
- [Signal-to-option bridge](signal_to_option_bridge.md)
- [Execution-economics freeze](sep02_option_economics_preopen_2026-09-01.md)
- [Sep-01 incident](incidents/SEP01_FORWARD_TEST_FAILURE.md)
- [Sep-03 preregistration](sep03_preregistration.md)
- [Research archive](archive/README.md)

Random seed where applicable: `20260902`. Historical data cutoff: `2026-08-28`. The source commands and artifact hashes are recorded in the linked reports.
