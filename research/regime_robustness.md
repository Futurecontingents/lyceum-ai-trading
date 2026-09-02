# Regime robustness

## Outcome-independent eras

The campaign fixes eras by macro/market chronology, never by strategy outcome: dot-com (1993–2002), pre-GFC (2003–2006), GFC (2007–2009), post-GFC recovery (2010–2012), low-volatility 2010s (2013–2019), COVID (2020–2021), 2022 inflation/rate shock, and modern 2023–2026.

A01 is positive in seven of eight eras. It is negative during 2022 (-0.0533%, t=-1.02), positive but weak through the GFC and recovery, and strongest in the dot-com and modern holdout eras. That makes it variable, not crisis-dependent.

## Mandatory drop-one-era result for A01

| Re-estimation sample | N | Mean | Block-bootstrap 95% lower |
|---|---:|---:|---:|
| All history | 8,452 | 0.0403% | 0.0270% |
| Without dot-com | 5,952 | 0.0336% | 0.0177% |
| Without GFC | 7,696 | 0.0429% | 0.0310% |
| Without COVID | 7,947 | 0.0387% | 0.0254% |
| Without 2022 | 8,201 | 0.0432% | 0.0299% |
| Without recent 2024–2026 | 7,785 | 0.0387% | 0.0258% |

All remain positive after removal of any mandated era. C03, D02, H01, and E01 also remain arithmetically positive in drop-one windows where tested, but they fail the separate sealed-holdout or sample-size gates and therefore are not promoted.

## Causal rolling regimes

The machine artifact also conditions signals on states knowable at the time:

- trend: current close versus trailing 200-session average;
- realized volatility: trailing 22-session volatility versus the expanding past median, shifted one session;
- drawdown: current close versus trailing 252-session high using fixed 10%/20% bands;
- VIX: official current close in fixed <20, 20–30, >30 bands;
- rates: current FRED DGS10 versus its 63-session lag using fixed +/-50 bp bands.

No future quantile, full-sample regime threshold, or strategy result defines these states. Complete conditional counts and metrics are in `artifacts/long_history/regime_results.json`.

## Classification

- A01: **LONG-HISTORY SUPPORTED; regime-variable**.
- C03 and D02: **historically suggestive but not sealed-holdout supported**.
- H01/E01: **rare-event, underpowered**.
- G01/K01/K02: **volatility-state signals with strong full-history association but inadequate sealed-holdout certainty/event count**.
- Gap continuation, ETF selection alpha, ordinary intraday drift: **rejected**.
