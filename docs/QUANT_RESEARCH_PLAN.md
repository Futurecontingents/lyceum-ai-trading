# Quant research map

This program is read-only research. It never imports Lyceum's execution module, changes production configuration, or uses an Alpaca trading command.

## Evidence constraints

The first dataset contains 24 correlated intraday captures from one session. Chronological splits and embargoes can prevent direct outcome overlap, but cannot create independent trading days or market regimes. Holdout results are therefore candidate-ranking evidence only, never a claim of statistical significance.

## Research layers

1. **Market prediction:** compare cash, momentum, reversal, council direction, and regularized tabular models.
2. **Volatility/regime prediction:** compare IV/RV, realized-volatility persistence, and direct long/short-volatility P&L labels.
3. **Option structure selection:** enumerate supported bull call spreads, bear put spreads, long straddles, and iron condors under the unchanged $500 maximum-loss constraint.
4. **Execution/cost filtering:** require fresh two-sided quotes, displayed size and observed volume, then rank by crossing cost or liquidity-adjusted risk before any signal is applied.

## Causal validation

The initial tournament targets five-minute executable option P&L because it permits a genuinely untouched final block in the short capture. Batches 1–11 train, 12–13 are purged, 14–16 validate, 17–18 are embargoed, and 19–22 are the untouched holdout; later batches supply labels only. Features come from the entry batch. No model or threshold sees holdout labels during selection.

Longer horizons are reported as diagnostics where labels exist. Each horizon uses the first batch completed at or after the requested horizon, and an option outcome exists only when every original leg has a trustworthy two-sided quote at both entry and exit.

## Literature-guided hypotheses

- Intraday momentum can be regime- and time-of-day dependent; compare it with short-horizon reversal rather than assuming persistence.
- HAR-style volatility models motivate multi-horizon realized-volatility features, but one session cannot estimate daily/weekly HAR components; use causal short-horizon persistence as a deliberately limited proxy.
- Variance-risk-premium research motivates IV versus subsequent realized movement, but quoted option spreads can consume the premium. Test short volatility only after liquidity-first construction.
- Option-return research repeatedly finds that bid/ask costs materially change conclusions. Midpoint is diagnostic; ranking is always by ask-to-bid executable P&L and stressed variants.
- Overlapping outcomes require chronological splitting plus purge/embargo gaps. Adjacent snapshots are not treated as independent observations.

## Research tree and pruning rule

- Direction: momentum -> volatility/cost filter; reversal -> volatility/cost filter; council -> conviction/cost filter.
- Volatility: IV/RV short condor -> liquidity-first; RV expansion long straddle -> liquidity-first.
- ML: ridge direct-P&L -> cost-aware threshold; random forest direct-P&L when available.
- Execution: current selector baseline -> minimum crossing -> liquidity-adjusted return/risk.

A branch is pruned after two related variants fail for the same diagnosed reason. A positive result is marked fragile unless it survives holdout, cost stress, nearby parameters, symbol decomposition, removal of its best trade, removal of its best symbol, and its relevant simple baseline.

