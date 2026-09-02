# Archived Sep-01 sealed forward test — pre-incident interim audit

> This report predates discovery of the complete experiment-integrity failure. It is preserved for provenance and superseded by the [incident report](../incidents/SEP01_FORWARD_TEST_FAILURE.md). Do not use its leaderboard as forward evidence.

**Audit cutoff:** 2026-09-01 17:14:53 UTC / 13:14:53 ET

**Production broker snapshot:** 2026-09-01 17:18 UTC

**Mode:** observation and audit only; no candidate, manifest, runner, production, strategy, or risk setting was changed.

## 1. Test integrity — FAIL

The price/outcome ledger is causal and internally consistent, but the cross-candidate sealed test is **not valid as preregistered** because Candidates C and D did not receive two required live features.

| Check | Result | Evidence |
|---|---:|---|
| A–E definitions and hashes unchanged | PASS | Manifest SHA-256 `1658477538d34a241c0522f26e37187294e70df4f08c7e0c8fe30c2a1c7f1750`; all 2,688 stored decisions carry it; manifest and runner are unchanged from preregistration commit `a72b874` |
| No post-open parameter change | PASS | Frozen files were committed at 13:36 Dubai, before the 17:30 Dubai open, and have no later diff |
| Runner completeness | PASS | 48 complete batches × 7 symbols × 8 systems = 2,688 expected and actual decisions |
| Causal bars/features | PASS, except missing-feature substitution below | 29,941 inspected bars; zero bar timestamps after batch completion |
| Required horizon elapsed before scoring | PASS | Zero horizon violations; every outcome uses the first complete batch at/after its target |
| Duplicate observations/outcomes | PASS | Zero duplicate underlying, option, decision, or outcome keys |
| Executable P&L identity | PASS | For every scored outcome: midpoint − entry crossing − exit crossing = conservative P&L; zero violations |
| Entry quotes existed and were causal | PASS | 1,076/1,076 legs present; maximum age 44.788s; zero future/stale quotes |
| Exit quotes existed at/after horizon | PASS | 3,532/3,532 scored legs present; maximum age 46.823s; zero future/stale quotes |
| Missing quotes silently substituted | PASS for option prices | Zero matured-but-unscorable outcomes and no substituted option quote |
| Shadow test submitted orders | PASS | Zero; the forward runner has no execution path |
| Candidate C/D council features | **FAIL** | There are **zero Sep-01 `shadow_results` rows**. `live_features()` silently supplied `disagreement=0` and `entropy=0` for all 336 states. C and D require both features. |
| Horizon-specific MFE/MAE | **FAIL / EXCLUDED** | The runner attaches the full available 60-minute excursion to 5m, 15m, and 30m rows. Those MFE/MAE fields are not used below. |

Consequences:

- Candidate C did **not** test whether Lyceum disagreement predicts volatility; disagreement and entropy had zero variance.
- Candidate D did **not** receive its preregistered live feature vector, so its output is not a valid test of the frozen D model.
- A, B, and E do not consume disagreement/entropy, but a fair A–E ranking is still withheld because the requested sealed tournament is compromised.
- All performance numbers below are preserved as **raw diagnostics only**, not interpreted results or a leaderboard.

## 2. Current data coverage

- First complete batch: **2026-09-01 13:35:25 UTC**
- Latest complete batch: **2026-09-01 17:14:53 UTC**
- Complete market batches: **48**
- Market-state observations: **336** (48 × 7)
- Symbols: **AAPL, AMD, META, NVDA, QQQ, SPY, TSLA**
- A–E evaluations: **1,680**

The layers are distinct:

| Layer | Count |
|---|---:|
| Signal observations across A–E | 761 |
| Option candidates across A–E | 320 |
| Executable trade previews across A–E | 320 |
| Scored at 5m / 15m / 30m / 60m | 302 / 283 / 262 / 217 |
| Pending A–E horizon outcomes | 216 |
| Matured but missing/unscorable | 0 |

Eligible structures were 248 bull-call spreads, 65 bear-put spreads, and 7 iron condors. Rejections were: 637 signal below threshold, 282 volatility edge below threshold, 394 no liquid directional structure, and 47 no liquid iron condor. A `NO_TRADE` is not counted as a trade.

## 3. Raw candidate diagnostics — not rankable

### A — cost-filtered momentum

- Hypothesis: sign of 60-minute return above the preregistered volatility-scaled threshold; hold 60 minutes.
- Observations/signals/trades/no-trades: **336 / 172 / 75 / 261**.
- Approximately non-overlapping intended-horizon trades: **7**. Most of the 44 scored rows overlap in time and are not independent.

| Horizon | N | Win | Midpoint | Executable | Mean | Median | Entry | Exit | Best | Worst | Ex-best | Per-symbol executable P&L |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 5m | 69 | 18.8% | -$5.20 | -$629.00 | -$9.12 | -$8.00 | $99.85 | $523.95 | $17 | -$39 | -$646.00 | AAPL -4; NVDA -131; QQQ -181; SPY -290; TSLA -23 |
| 15m | 63 | 7.9% | -$199.00 | -$836.80 | -$13.28 | -$10.00 | $92.35 | $545.45 | $33 | -$80 | -$869.80 | AAPL -3; NVDA -221; QQQ -368.1; SPY -228.7; TSLA -16 |
| 30m | 57 | 19.3% | -$175.45 | -$737.80 | -$12.94 | -$10.00 | $83.35 | $479.00 | $27 | -$60 | -$764.80 | AAPL -14; NVDA -84; QQQ -293; SPY -333.8; TSLA -13 |
| **60m** | **44** | **31.8%** | **-$17.50** | **-$421.80** | **-$9.59** | **-$10.50** | **$62.40** | **$341.90** | **$41** | **-$56** | **-$462.80** | AAPL -16; NVDA +24; QQQ -249; SPY -180.8 |

Underlying signal quality at 5/15/30/60m: N 160/151/138/110; hit rate 43.1%/43.7%/40.6%/45.5%; signal-return correlation -0.016/-0.112/-0.109/**-0.124**. At the intended 60m horizon, the mean signed underlying return was +0.005%, but direction was wrong more often than right.

### B — cost-filtered mean reversion

- Hypothesis: reverse an outsized five-minute return; hold 30 minutes.
- Observations/signals/trades/no-trades: **336 / 198 / 65 / 271**.
- Approximately non-overlapping intended-horizon trades: **17**.

| Horizon | N | Win | Midpoint | Executable | Mean | Median | Entry | Exit | Best | Worst | Ex-best | Per-symbol executable P&L |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 5m | 61 | 16.4% | -$36.15 | -$611.00 | -$10.02 | -$7.00 | $84.35 | $490.50 | $30 | -$87 | -$641.00 | AAPL -4; NVDA -85; QQQ -238; SPY -254; TSLA -30 |
| 15m | 55 | 21.8% | -$100.15 | -$533.00 | -$9.69 | -$11.00 | $76.35 | $356.50 | $33 | -$43 | -$566.00 | AAPL -3; NVDA -97; QQQ -231; SPY -190; TSLA -12 |
| **30m** | **50** | **24.0%** | **-$219.50** | **-$647.90** | **-$12.96** | **-$10.50** | **$68.90** | **$359.50** | **$24** | **-$64** | **-$671.90** | AAPL -14; NVDA -103; QQQ -261.9; SPY -270; TSLA +1 |
| 60m | 41 | 29.3% | -$85.65 | -$456.00 | -$11.12 | -$10.00 | $56.90 | $313.45 | $30 | -$56 | -$486.00 | AAPL -16; NVDA -53; QQQ -267; SPY -121; TSLA +1 |

Underlying signal quality at 5/15/30/60m: N 190/176/165/133; hit rate 44.7%/43.8%/**50.9%**/51.9%; signal-return correlation -0.058/-0.069/**-0.043**/+0.028. The intended-horizon mean signed return was -0.028% despite a 50.9% hit rate.

### C — Lyceum volatility/disagreement

- Hypothesis: ridge forecast of realized move, with disagreement and entropy as inputs, compared with implied move.
- **Validity:** failed. All 336 live disagreement and entropy inputs were zero because the corresponding council rows were absent.
- Observations/signals/trades/no-trades: **336 / 54 / 7 / 329**; only about **2** non-overlapping intended trades.

| Horizon | N | Win | Midpoint | Executable | Mean | Median | Entry | Exit | Best | Worst | Ex-best | Per-symbol executable P&L |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 5m | 7 | 14.3% | +$4.50 | -$63.00 | -$9.00 | -$12.00 | $23.50 | $44.00 | $5 | -$17 | -$68.00 | NVDA -33; TSLA -30 |
| 15m | 7 | 0.0% | +$5.00 | -$85.00 | -$12.14 | -$8.00 | $23.50 | $66.50 | -$2 | -$30 | -$83.00 | NVDA -30; TSLA -55 |
| 30m | 7 | 14.3% | +$22.50 | -$54.00 | -$7.71 | -$8.00 | $23.50 | $53.00 | $1 | -$14 | -$55.00 | NVDA -35; TSLA -19 |
| **60m** | **7** | **0.0%** | **+$23.00** | **-$64.90** | **-$9.27** | **-$9.00** | **$23.50** | **$64.40** | **-$1.90** | **-$15** | **-$63.00** | NVDA -49; TSLA -15.9 |

Among 54 nonzero forecasts with a 60-minute future, mean forecast movement was 0.145% versus mean implied movement 0.937% (forecast/implied 0.150) and mean realized absolute movement 0.610%. Forecast-to-future-absolute-move correlation was 0.162. This cannot be attributed to disagreement because disagreement had no variance. Five of seven midpoint marks were positive at 60m, but **zero of seven** were positive after quoted-side costs.

Therefore today's data cannot answer whether high disagreement meant (A) larger movement, (B) a better volatility forecast, or (C) better option opportunities. It directly shows only (D): the seven constructed structures were not executable winners.

### D — direct economic ridge

- Hypothesis: frozen ridge forward-return prediction mapped to option delta; hold five minutes after a cost hurdle.
- **Validity:** failed. D also requires disagreement and entropy and received zeros instead of live values.
- Observations/signals/trades/no-trades: **336 / 336 / 173 / 163**; approximately **88** non-overlapping five-minute trades.

| Horizon | N | Win | Midpoint | Executable | Mean | Median | Entry | Exit | Best | Worst | Ex-best | Per-symbol executable P&L |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **5m** | **165** | **19.4%** | **+$61.25** | **-$1,943.00** | **-$11.78** | **-$9.00** | **$323.25** | **$1,681.00** | **$35** | **-$105** | **-$1,978.00** | AAPL -268; NVDA -270; QQQ -547; SPY -314.9; TSLA -543.1 |
| 15m | 158 | 24.7% | +$328.90 | -$1,525.90 | -$9.66 | -$7.00 | $310.25 | $1,544.55 | $29 | -$80 | -$1,554.90 | AAPL -199; NVDA -340; QQQ -452; SPY -224.8; TSLA -310.1 |
| 30m | 148 | 30.4% | +$438.50 | -$1,255.70 | -$8.48 | -$8.00 | $291.35 | $1,402.85 | $36 | -$60 | -$1,291.70 | AAPL -204; NVDA -93; QQQ -482.9; SPY -213.7; TSLA -262.1 |
| 60m | 125 | 33.6% | +$261.75 | -$1,260.80 | -$10.09 | -$10.00 | $243.30 | $1,279.25 | $41 | -$76 | -$1,301.80 | AAPL -159; NVDA +87; QQQ -552; SPY -267.8; TSLA -369 |

The raw, invalid-model output aligned with the underlying at 5/15/30/60m at 56.5%/58.8%/58.5%/61.2%, with signal-return correlations 0.119/0.153/0.189/0.265. That is diagnostically interesting but **not evidence for preregistered D**, because its live input vector was wrong.

### E — VWAP reversion baseline

- Hypothesis: reverse a VWAP deviation of at least one daily-RV unit; hold 30 minutes.
- Observations/signals/trades/no-trades: **336 / 1 / 0 / 336**.
- The one signal had no eligible directional structure. There are no option outcomes and no evidence for or against E.

## 4. Fair comparison and baselines

A ranked table is deliberately not produced after the integrity failure. Raw intended-horizon economics are:

| System | Valid sealed implementation? | Intended scored N | Midpoint P&L | Executable P&L | Mean | Note |
|---|---:|---:|---:|---:|---:|---|
| Cash / NO_TRADE | Yes | — | $0 | **$0** | — | Economic leader by default |
| A | Yes in isolation | 44 | -$17.50 | -$421.80 | -$9.59 | Only ~7 non-overlapping observations; NVDA +$24, other symbols negative |
| B | Yes in isolation | 50 | -$219.50 | -$647.90 | -$12.96 | Only ~17 non-overlapping observations |
| C | **No** | 7 | +$23.00 | -$64.90 | -$9.27 | Disagreement hypothesis not tested; zero executable winners |
| D | **No** | 165 | +$61.25 | -$1,943.00 | -$11.78 | Wrong feature vector; exit crossing dominates |
| E | Yes in isolation | 0 | $0 | $0 | — | No eligible trade |
| Simple momentum | Baseline | 63 | -$26.50 | -$715.80 | -$11.36 | Cash wins |
| Simple mean reversion | Baseline | 82 | -$171.00 | -$1,165.90 | -$14.22 | Cash wins |

Removing each system's best trade leaves A -$462.80, B -$671.90, C -$63.00, and D -$1,978.00. No apparent winner depends on a single positive outlier because no aggregate candidate is positive. The raw rows are highly overlapping; nominal N must not be interpreted as independent sample size.

## 5. Actual five-agent production council

The production journal contains **84 complete five-opinion decision sets** after open: 84 opinions per agent, zero model fallbacks, zero journaled errors.

Average distribution order is `[strong_down, down, flat, up, strong_up]`.

| Agent | Mean distribution | Direction | Confidence | Mean absolute consensus contribution | Incremental disagreement | Mean latency |
|---|---|---:|---:|---:|---:|---:|
| TechnicalQuant | [0.040, 0.266, 0.453, 0.214, 0.027] | -0.039 | 0.410 | 0.0162 | +0.0005 | 0 ms |
| OptionsMarket | [0.023, 0.235, 0.501, 0.220, 0.020] | -0.010 | 0.448 | 0.0087 | -0.0023 | 0 ms |
| NewsCatalyst | [0.096, 0.196, 0.500, 0.158, 0.051] | -0.064 | 0.502 | 0.0094 | -0.0043 | 7,987 ms |
| BullAdvocate | [0.050, 0.168, 0.410, 0.311, 0.061] | +0.082 | 0.600 | 0.0357 | -0.0010 | 11,693 ms |
| BearAdvocate | [0.149, 0.286, 0.326, 0.189, 0.051] | -0.146 | 0.613 | 0.0349 | +0.0070 | 11,304 ms |

Council outcomes use the first causal shadow price at/after each horizon. Entries overlap, so these are descriptive, not significance tests. Each cell is `directional hit rate / prediction-return correlation`.

| Variant | 5m (N=84) | 15m (N=77) | 30m (N=71) | 60m (N=63) |
|---|---:|---:|---:|---:|
| Full council | 45.2% / +0.268 | 42.9% / -0.081 | 39.4% / -0.091 | 46.0% / +0.025 |
| Deterministic only | 52.4% / +0.283 | 45.5% / -0.117 | 42.3% / -0.124 | 52.4% / +0.025 |
| Model-backed only | 45.2% / +0.191 | 45.5% / +0.025 | 40.8% / -0.006 | 38.1% / +0.023 |
| Technical alone | 51.2% / +0.299 | 46.8% / -0.062 | 42.3% / -0.072 | 50.8% / +0.055 |
| Options alone | 51.2% / +0.217 | 46.8% / -0.190 | 39.4% / -0.194 | 52.4% / -0.021 |
| News alone | 44.0% / +0.168 | 42.9% / +0.137 | 38.0% / +0.072 | 36.5% / +0.049 |
| Bull alone | 57.1% / +0.157 | 62.3% / -0.107 | 64.8% / -0.169 | 66.7% / -0.082 |
| Bear alone | 40.5% / +0.115 | 37.7% / +0.045 | 35.2% / +0.080 | 31.7% / +0.075 |
| Momentum baseline | 51.2% / +0.092 | 46.8% / +0.021 | 39.4% / -0.072 | 52.4% / -0.013 |
| Mean-reversion baseline | 48.8% / -0.092 | 53.2% / -0.021 | 60.6% / +0.072 | 47.6% / +0.013 |

The bull advocate's high hit rate reflects a persistent positive tendency during a generally rising sample; its 15–60m probability correlation is negative, so it is not evidence of calibrated skill. The full council did not beat the deterministic subset or technical agent at 5m, and was below 50% hit rate at every horizon. **There is no evidence that complexity added directional information today.**

The production council worked; the sealed runner did not ingest its council outputs. These are separate facts.

## 6. Execution economics

Greek attribution is an entry-Greek approximation; residual includes changing Greeks, higher-order terms, quote noise, and model error.

| Candidate / intended horizon | N | Delta | Gamma | Theta | Vega/IV | Residual | Gross midpoint | Entry crossing | Exit crossing | Executable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A / 60m | 44 | -$68.05 | +$6.74 | -$4.91 | +$33.68 | +$15.04 | -$17.50 | -$62.40 | -$341.90 | **-$421.80** |
| B / 30m | 50 | -$136.84 | +$7.86 | -$2.04 | -$90.19 | +$1.70 | -$219.50 | -$68.90 | -$359.50 | **-$647.90** |
| C / 60m | 7 | -$3.01 | -$3.26 | +$1.67 | +$26.20 | +$1.41 | +$23.00 | -$23.50 | -$64.40 | **-$64.90** |
| D / 5m | 165 | +$72.58 | +$4.37 | -$3.15 | -$24.25 | +$11.70 | +$61.25 | -$323.25 | -$1,681.00 | **-$1,943.00** |

The accounting identity is `gross midpoint edge − entry crossing − exit crossing = conservative executable edge`.

- A and B: gross/midpoint economics were already weak or negative; prediction/mapping and cost both hurt.
- C and D raw outputs: gross midpoint totals were positive, but crossing costs—especially exit costs—overwhelmed them.
- The cheapest observed entry crossing was $0.95. Cheap did not imply profitable: examples ranged from +$17 to -$25 depending on direction, horizon, and exit market.
- Only **58 of 266** intended-horizon A–D rows were executable-positive (21.8%), and most are overlapping. Positive symbol/DTE groups were mostly N=1. A's NVDA 60m group was +$24 across 14 overlapping rows; it is not independent evidence.

Primary diagnosis: **H — combination**. A/B show weak or wrong prediction plus costs; C/D show invalid feature delivery plus excessive round-trip cost; D's exit crossing alone was $1,681. Risk constraints mainly prevented additional structures and are not the cause of shadow P&L.

## 7. Trade / no-trade question

Individual positive executable rows existed, but no preregistered candidate with scored intended trades had positive aggregate executable economics. Cash/`NO_TRADE` at $0 beat every raw candidate and both simple option baselines.

The positive rows do not support a tradeable state rule: they are overlapping and fragment into tiny symbol/DTE/time/geometry groups. Describing them as a threshold would optimize on today's sealed evaluation data, which this audit does not do.

## 8. Current production judging account — separate from shadow

Broker snapshot at 17:18 UTC:

- Equity **$99,889.95**; cash **$99,601.95**; buying power **$398,407.80**.
- One parent paper order, filled in two legs.
- Current position: one NVDA 2026-09-09 217.5/202.5 bear-put spread (two option legs).
- Realized P&L **$0**; unrealized P&L **-$110**.

Production journal after open:

- 84 decisions; 79 `NO_TRADE`; 5 option candidates.
- 1 risk-approved; 83 risk-rejected; 1 submitted order.
- Top reason codes from decision payloads: `SKEPTIC_VETO` 80, `NO_TRADE_SELECTED` 79, `MAX_LOSS_PER_TRADE` 3, then one each for spread, cooldown, and duplicate checks.
- The local order row remains `SUBMITTED` while Alpaca reports the parent and both legs `filled`; this is a journal/broker reconciliation gap, not a shadow-test order.

## 9. Claims at this cutoff

### Supported

- The autonomous hybrid council ran with role-specific local-model agents, deterministic agents, no model fallback, deterministic risk, and one paper-only defined-risk execution.
- Quoted-side execution costs, especially exits, materially dominate observed option economics.
- The frozen manifest, decision hash, option timestamps, and horizon pricing remained intact.

### Promising but unproven

- Raw D outputs aligned with short-horizon underlying direction, but D was not run with its preregistered feature vector.
- The local Qwen council operated reliably, but did not outperform simpler components today.

### Not supported

- “Disagreement predicts volatility” from today's sealed test: the disagreement feature was never delivered.
- “The five-agent council added information today.”
- Any profitable or executable A–E edge.

### Disproven / currently failing

- Candidate C's intended disagreement test failed operationally: all disagreement/entropy values were silently zero-filled.
- Candidate D also received an incorrect live feature vector.
- Every candidate with an intended scored option sample had negative aggregate conservative P&L; E produced no trade.

## 10. Hackathon competitiveness

| Dimension | Score | Evidence-based assessment |
|---|---:|---|
| AI architecture | 9/10 | Clear probabilistic roles, strict schema, local model, deterministic safety |
| Quant methodology | 7/10 | Strong preregistration/cost discipline, reduced by the C/D feature-integrity failure |
| Signal quality | 3/10 | A/B weak; C invalid; D raw alignment not attributable to frozen model |
| Option construction | 4/10 | Defined risk and liquidity filters exist, but monetization is negative |
| Execution realism | 8/10 | Causal quoted sides and explicit costs; sub-horizon MFE/MAE defect excluded |
| Risk engineering | 9/10 | Deterministic gates constrained production correctly |
| Autonomy | 8/10 | Council and one paper trade ran autonomously; reconciliation remains incomplete |
| Reproducibility | 7/10 | Frozen hash and append-only data are strong; missing council feature path invalidated two candidates |
| Observed trading | 2/10 | One open paper spread at -$110 unrealized; no demonstrated profit |
| Presentation | 9/10 | Strong, honest, auditable story |

Lyceum is currently competitive as an **AI engineering project** and a **quantitative research methodology project**. It is a functioning **autonomous paper trading system**, but not yet a demonstrated good trader. It is **not** a demonstrated profitable strategy.

## Interim conclusion

There is **no valid current leader**. The most important finding is not a P&L ranking: the frozen feature delivery path omitted the actual council data, invalidating the two candidates meant to test Lyceum's distinctive hypothesis. Separately, the raw option ledger reinforces the prior economic lesson—positive midpoint movement is insufficient when round-trip quoted-side costs dominate.

**Evidence of executable edge: INCONCLUSIVE due to invalid test integrity, with no positive aggregate candidate in the raw diagnostics.**
