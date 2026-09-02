# High-magnitude option-plausible state screen

Data cutoff: 2026-08-28. The screen tests only causal states with a chance of clearing observed option costs. It evaluates 36 fixed state/direction combinations across extreme gaps, prior-close capitulation, realized-volatility shocks, and extreme first-hour moves in SPY, QQQ, AAPL, NVDA, AMD, META, and TSLA. Historical point-in-time news is unavailable, so catalyst/news states are explicitly untestable rather than retrofitted.

Directional ranking uses:

`positive expected signed return × current reference spot / symbol-specific median delta-adjusted vertical hurdle`.

Absolute movement is reported separately and cannot by itself justify a directional option. Promotion requires ratio >=1.25, N>=30, conservative effective N>=20, positive signed block-bootstrap CI, positive edge in at least 60% of eligible eras, and at least 10 recent confirming observations.

## Leading states

| State | N | Effective N | Expected absolute move | Expected signed edge | Signed 95% CI | SPY option hurdle | Signed move / hurdle | Robustness | Promoted? |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Prior SPY day <=-5%; long next open→close | 22 | 4.4 | $20.36 | $10.32 | 0.156%–2.880% return | $1.75 | **5.89** | Only two eras have >=5 events; recent N=1 | No |
| Prior SPY day <=-3%; long next open→close | 103 | 20.6 | $12.80 | $3.64 | 0.152%–0.946% | $1.75 | **2.08** | Positive in 5/6 eligible eras; recent N=3 | No |
| Prior SPY day <=-2%; long next open→close | 337 | 67.4 | $9.05 | $1.68 | 0.081%–0.417% | $1.75 | **0.96** | Positive in 6/8 eras; recent N=14 confirms sign | No: no 25% cost buffer |
| SPY first hour >=1%; continue to close | 12 | 2.4 | $6.09 | $0.30 | -0.782%–0.820% | $1.75 | 0.17 | One recent regime; signed CI crosses zero | No |
| NVDA first hour >=2%; continue to close | 102 | 20.4 | $2.54 | $0.38 | -0.255%–0.614% | $2.69 | 0.14 | Recent-only; signed CI crosses zero | No |

Extreme gap states frequently produce large absolute movement, but continuation direction is unstable and negative in the modern sample. Volatility-shock states similarly increase movement without supplying stable direction. QQQ's >2% first-hour continuation has ratio 1.28 but N=1.

## Result

**Zero trade-producing candidates are promoted.** The best statistically populated state is prior-day SPY capitulation <=-2%, but its expected signed movement is only 0.96× the SPY-specific median hurdle, leaving no model-error, slippage, or tail buffer. The larger-ratio -3% and -5% states fail recent confirmation/effective-sample requirements.

Machine artifact: `artifacts/long_history/high_magnitude_states.json`.
