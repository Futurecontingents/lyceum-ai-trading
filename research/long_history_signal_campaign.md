# Long-history signal campaign

## Verdict

One phenomenon survives the full long-history evidence gates: **SPY close-to-open drift (A01)**. It is long-history supported as an underlying effect, but it is **not option-tradeable on the evidence collected**. No directional ML result is promoted. HAR-ridge improves volatility forecast error versus simple trailing-RV baselines, but a forecast is not a monetizable option edge.

## Frozen chronology

These boundaries were chosen before fitting or ranking models:

| Split | Dates | Purpose |
|---|---|---|
| Early discovery/train | 1993-01-29–2006-12-29 | Definitions and linear model estimation |
| Middle validation | 2007-01-01–2015-12-31 | First chronological validation |
| Recent validation | 2016-01-01–2022-12-30 | Second chronological validation |
| Sealed historical holdout | 2023-01-01–2026-08-28 | Untouched final historical test |

No random time-series splits were used. Expanding volatility models use only observations strictly before each prediction.

## Registered tests and inference

The ledger contains 19 preregistered hypotheses: 15 return/event rules across overnight, intraday, momentum, reversal, capitulation, trend-conditioned reversal, gaps, and cross-sectional selection; plus four volatility-shock/transition tests. HAR OLS, HAR ridge, trailing-5-day RV, and trailing-22-day RV are evaluated separately. Recent 5-minute bridges cover 5/15/30/60/90/120 minutes, close, and overnight.

For return rules the campaign reports N, dependence-adjusted effective N, Newey-West/HAC standard error, t-statistic, event-sequence Sharpe, hit rate, magnitude, sequential drawdown, worst/best event, remove-best-event mean, 500-sample moving-block bootstrap intervals, and 500 block-sign surrogate nulls. Benjamini-Hochberg controls FDR at 10% across all 15 registered return hypotheses; the four volatility-state tests have their own family correction. This is the declared selection-bias control instead of an unsupported deflated-Sharpe claim.

## Evidence-ranked top five

Ranking applies evidence gates first, then sealed-holdout HAC t-stat. It does not refit parameters.

| Rank | ID | Exact rule | Full N | Full mean | HAC t | BH q | Holdout mean | Holdout bootstrap 95% lower | Supported? |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | A01 | Long SPY prior adjusted close to next adjusted open | 8,452 | 0.0403% | 5.82 | 0.0150 | 0.0494% | 0.0109% | **YES** |
| 2 | C03 | Sign of trailing 126-session return × next 21-session return | 8,306 | 0.5092% | 2.86 | 0.0150 | 0.7502% | -0.1706% | No: holdout CI crosses zero |
| 3 | D02 | Opposite sign of trailing 5-session return × next 5-session return | 8,443 | 0.1478% | 4.06 | 0.0150 | 0.0145% | -0.1792% | No: recent decay/holdout CI |
| 4 | H01 | Long 5 sessions after <=-2% day while above prior 200-DMA | 137 | 0.7528% | 2.59 | 0.0659 | 1.3973% (N=9) | undefined | No: insufficient holdout N |
| 5 | E01 | Long 5 sessions after <=-2% day | 337 | 0.8264% | 2.65 | 0.0150 | 1.2311% (N=15) | -0.5689% | No: insufficient N and CI |

The cross-sectional “worst ETF rebounds” result initially looked positive in raw returns. Against the contemporaneous equal-weight SPY/QQQ/IWM/DIA baseline, full-history excess return is only 0.0036% and sealed-holdout excess is 0.0006%; it fails. This failure is preserved rather than promoted.

## Best signal by chronological period

A01 means: early **0.0510%** (N=3,507), middle **0.0253%** (N=2,266), recent **0.0336%** (N=1,762), sealed holdout **0.0494%** (N=917). Full-history mean after removing its single best event remains **0.0396%**. The middle-period bootstrap includes zero, and calendar-year/regime variation is material; promotion is therefore “moderate underlying evidence,” not “proven trade.”

## Volatility forecasting

Target: square root of the sum of the next five daily squared log returns. Features are current absolute return and trailing 5-/22-day RMS return.

| Model | OOS N | Correlation | MAE | OOS R² vs pre-2016 unconditional mean |
|---|---:|---:|---:|---:|
| HAR ridge | 2,674 | 0.6758 | 0.007226 | **0.4641** |
| HAR OLS | 2,674 | 0.6758 | 0.007226 | 0.4641 |
| trailing-5-day RV | 2,674 | 0.6776 | 0.008083 | 0.3672 |
| trailing-22-day RV | 2,674 | 0.5952 | 0.008211 | 0.2755 |

Ridge beats the simple baselines on MAE and OOS R², but only marginally beats OLS. Complexity beyond a linear HAR form is not justified. RV-shock and VIX-transition event tests have promising full-history magnitudes but fail sealed-holdout N or confidence requirements; none is promoted.

## Research linkage

- **Cost-aware selection hypothesis:** include expected transaction cost in option selection, consistent with [Option Return Predictability with Machine Learning and Big Data](https://academic.oup.com/rfs/article/36/9/3548/7056660).
- **Execution-hurdle hypothesis:** demand-liquidity costs can be economically large in listed options, motivating quoted-side rather than midpoint promotion; see [Option Auctions](https://academic.oup.com/rfs/article/39/3/783/8193725).
- **Liquidity-state hypothesis:** option illiquidity is itself priced risk, so wider contracts cannot be treated as noiseless leverage; see [Illiquidity Premia in the Equity Options Market](https://academic.oup.com/rfs/article-abstract/31/3/811/4371415).
- **Horizon-alignment hypothesis:** information horizon and option maturity should be commensurate; see [Do Informed Investors Time the Horizon?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2467719).

The public EdgeStack submission describes 33 years, surrogate-null tests, drop-one-era checks, and disjoint validations. That is useful methodological inspiration, but its [public claim](https://lablab.ai/submissions/qdsq1ru606rmyssgsg2afaan) does not by itself establish 33 years of executable point-in-time option NBBO evidence. Lyceum makes no equivalence claim.

Machine results: `artifacts/long_history/experiment_ledger.json` and `artifacts/long_history/signal_leaderboard.json`.
