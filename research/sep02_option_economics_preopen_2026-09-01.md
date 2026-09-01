# Sep-02 next-generation option economics — pre-open freeze

Frozen at 2026-09-01T10:03:21Z. Development uses only historical underlying bars ending
2026-08-28 and COMPLETE Aug-31 option snapshots from 18:17:46Z–20:00:16Z. The Sep-01
session, its outcomes, and the sealed A–E implementation are excluded.

## New findings

1. **H1 — Directional predictability is too small in option-dollar space. Confirmed.**
   The pre-Aug-31 conditional mean underlying returns imply only $0.08–$0.53 gross per
   one-contract vertical observation across 15/30/60/90-minute horizons. Estimated quoted
   round-trip cost is $39.68–$73.26. None of 4,878 eligible directional structures has positive
   expected gross minus estimated round-trip cost. The correct first-stage target is therefore
   `TRADE / NO_TRADE`, with `expected structure P&L - estimated execution cost`, not direction.

2. **H2 — The signal horizon and option holding horizon are misaligned. Confirmed for the
   captured late session.** At 15/30 minutes, momentum and reversion both lose at midpoint.
   Reversion first becomes positive at midpoint at 60 minutes (+$3.23/structure) and momentum
   at 90 minutes (+$4.52/structure, sparse), but costs remain $69.82 and $58.37 respectively,
   producing -$66.59 and -$53.85 executable means. Extending the hold helps signal realization
   but does not approach break-even before the available tape ends.

3. **H3 — Exit liquidity is a separate, larger loss source. Confirmed.** For 60-minute
   directional structures, momentum paid $19.84 at entry and $25.61 at exit per observation;
   reversion paid $29.05 and $40.77. A fixed entry-spread gate cannot control the larger exit
   bill. The Sep-02 selector should predict round-trip, horizon-specific liquidity, including an
   exit-cost distribution.

4. **H4 — Narrow, longer-DTE verticals dominate wider geometry economically. Confirmed on
   Aug-31, not yet generalized.** The best 60-minute momentum bucket was narrow 22–35 DTE:
   +$6.02 midpoint, $11.63 entry crossing, $16.17 exit crossing, -$21.78 executable mean.
   Its wide counterpart generated -$5.61 midpoint and -$60.27 executable. For 60-minute
   reversion, narrow 22–35 DTE was +$2.95 midpoint and -$27.36 executable versus +$8.26 and
   -$76.00 for wide. Extra gross exposure did not compensate for extra leg liquidity.

5. **H5 — Delta is the useful signal channel; gamma, theta, and vega are secondary over these
   horizons. Confirmed.** In the only positive 60-minute directional aggregate (reversion), the
   per-structure midpoint attribution is delta +$2.30, gamma +$0.05, theta -$0.04, vega +$0.52,
   residual +$0.39 = +$3.23. Entry plus exit crossing is $69.82. The economics fail because the
   directional delta edge is roughly 30 times too small, not because theta alone overwhelms it.

6. **H6 — A realized-move forecast is not sufficient to monetize long volatility. Confirmed.**
   The historical mean absolute 60-minute move is 0.393%, while Aug-31 ATM implied moves average
   0.713%–0.736% across DTE bands. Expected gamma plus theta is $5.29–$9.83 per straddle, versus
   $43.48–$67.87 estimated quoted round-trip cost. A predeclared expected-gross filter selected
   only 28 of 210 60-minute straddle observations; they still lost $234.00 executable in total
   (-$8.36 mean) on Aug-31. A volatility forecast must target option mark/IV dynamics and costs,
   not only future absolute underlying return.

7. **H7 — IV premium does not automatically make a short condor economic intraday. Confirmed.**
   Implied move exceeded the historical absolute-move forecast in every aggregate DTE/horizon
   bucket, yet no condor cleared forecast gamma-plus-theta against estimated round-trip cost.
   At 60 minutes, narrow condors earned only $0.05–$0.19 theta per structure, while expected
   negative gamma made pre-cost gross negative and round-trip cost averaged $21.02–$73.39.

8. **H8 — Disagreement improves volatility accuracy, but not enough to matter economically.
   Confirmed.** At 60 minutes, adding disagreement raises historical walk-forward correlation
   from 0.773998 to 0.779987 and reduces MAE from 0.00142741 to 0.00140322. The MAE gain is
   0.00002419 of spot: only $0.019 on a $767 underlying, or an intentionally generous $1.86
   upper bound at 100-delta-share exposure. That is below even the cheapest observed straddle
   round-trip costs. Disagreement is useful as a forecast feature but does not create an
   executable volatility edge by itself.

## Sep-02 candidate-generation implications

- Make `NO_TRADE` the default class and train/rank on conservative structure-level expected net
  P&L, with a margin above the full estimated round trip.
- Restrict initial directional research to narrow 22–35 DTE structures and model exit liquidity
  separately; retain wider spreads only if their incremental expected exposure clears incremental
  cost.
- Match directional signals to at least 60-minute monetization tests. Do not infer viability from
  the sparse 90-minute sample.
- For long volatility, predict option mark change or IV repricing jointly with realized move.
  For short volatility, require forecast theta/variance-premium capture to exceed negative gamma,
  vega risk, and both crossings.
- Test execution-aware ranking under quoted-spread stress and 30% effective-spread assumptions,
  but keep quoted-side execution as the conservative acceptance criterion until fill data exists.

## Research-linked hypotheses

- **Cost-aware ranking:** H1/H3 follow the method of subtracting expected transaction cost before
  portfolio sorting in [Option Return Predictability with Machine Learning and Big Data](https://academic.oup.com/rfs/article/36/9/3548/7056660).
- **Effective versus quoted spread:** H3 and the stress design use the 30% effective-to-quoted
  assumption in [Can Equity Option Returns Be Explained by a Factor Model? IPCA Says Yes](https://academic.oup.com/rfs/article/38/6/1783/8010873), while conservative acceptance retains full quoted crossing.
- **Execution timing and price improvement:** H3 motivates a future fill-quality model because
  [Options Trading Costs Are Lower than You Think](https://academic.oup.com/rfs/article-abstract/33/11/4973/5732665)
  finds execution timing materially reduces effective spreads, and [Option Auctions](https://academic.oup.com/rfs/article/39/3/783/8193725)
  reports price improvement but still high round-trip break-even requirements.
- **Economically evaluated volatility forecasts:** H6/H7 follow the economic, straddle-based
  evaluation in [Realized Volatility Forecasting and Option Pricing](https://www.sciencedirect.com/science/article/pii/S030440760800122X)
  and the finding that IV-surface predictability largely disappears after costs in
  [Can We Forecast the Implied Volatility Surface Dynamics?](https://www.sciencedirect.com/science/article/pii/S037842661400199X).
- **Intraday horizon/liquidity:** H2/H3 are consistent with persistent within-session liquidity
  and half-day economic frequency in [Intraday Option Return: A Tale of Two Momentum](https://www3.nd.edu/~zda/IntraOption.pdf)
  and with U-shaped option-market activity in [Intraday Trading Patterns in the Equity Options Markets](https://onlinelibrary.wiley.com/doi/10.1111/j.1475-6803.1993.tb00148.x).

## Reproduction and audit

Command:

```bash
.venv/bin/python scripts/nextgen_option_economics.py \
  --output artifacts/nextgen_research/option_economics_preopen_freeze_2026-09-01.json
```

- Script SHA-256: `fb50560e34b2ab2065f463754a5781d46016da1de0bbb7d0ee2af80df8b3a862`
- Result SHA-256: `bb2940cd07cc0703626e0734bcab204d6e27471bd67a2e80f3c1a58950c6a702`
- Quarantined source-extract SHA-256: `940f4e1768e4a8ea6fabaa3083a5818e321faa7521d5caa9d22f1dfe15d822a1`
- Historical model-results SHA-256: `8d5a270448aa2342c1a2ae996827ff1b3078a64dd91ec6f470efa44e2d2c0027`
- Observations: 9,627 structure/horizon observations; 24 COMPLETE batches; 7 symbols.
- Important limitation: one late-session option-capture date is diagnostic evidence, not a
  generalizable backtest. The 90-minute cells are especially sparse.
