# Strategy and Consensus Mathematics

Lyceum treats each mind's output as a categorical probability distribution over states

\[
S = \{-1, -0.5, 0, 0.5, 1\}
\]

corresponding to strong down, down, flat, up, and strong up.

## Confidence-weighted consensus

For mind \(i\), distribution \(p_i\), and confidence \(w_i \in [0,1]\):

\[
\bar{p}_k = \frac{\sum_i w_i p_{i,k}}{\sum_i w_i}
\]

A minimum internal weight of 0.05 prevents one zero-confidence output from causing an undefined denominator. It does not turn that view into conviction.

## Consensus entropy

Normalized Shannon entropy measures uncertainty within the aggregate distribution:

\[
H(\bar{p}) = \frac{-\sum_k \bar{p}_k \ln \bar{p}_k}{\ln 5}
\]

It lies in \([0,1]\). High entropy means the aggregate distribution is diffuse.

## Pairwise Jensen–Shannon divergence

For two minds \(p\) and \(q\), with \(m=(p+q)/2\):

\[
JS(p,q) = \frac{KL(p\|m) + KL(q\|m)}{2\ln 2}
\]

The division by \(\ln 2\) normalizes divergence to \([0,1]\). Aggregate disagreement is the arithmetic mean across every pair of minds.

## Direction

Expected direction is the probability-weighted state score:

\[
D = \sum_k \bar{p}_k S_k
\]

Directional conviction is \(|D|\). Entropy and disagreement are retained separately because a flat consensus can arise from broad shared uncertainty or from polarized agents; those are economically different states.

## Structure mapping

- Positive direction with conviction: bull call spread.
- Negative direction with conviction: bear put spread.
- High pairwise disagreement and entropy with non-expensive IV: long straddle / defined-cost volatility trade.
- Lower directional uncertainty with relatively rich IV: iron condor, only when four liquid defined-risk legs exist.
- Missing chain, duplicate legs, poor liquidity, ambiguous regime, or risk failure: `NO_TRADE`.

Expected move uses the standard annualized-volatility approximation:

\[
EM = Spot \times IV \times \sqrt{DTE / 365}
\]

This is a selection heuristic, not a forecast guarantee. Maximum loss is calculated from leg debit/width before risk approval. Quotes, spreads, and expiry are taken from current Alpaca paper-market data when the real runner is active.

## Historical experiment

At each hourly timestamp, deterministic minds use only trailing returns and volatility. Pairwise disagreement is compared with subsequent absolute return and realized volatility over 1h, 4h, and one trading day. Both Pearson and rank-based Spearman correlations are reported alongside quartile buckets. The experiment is a sanity check, not a backtest of fills or profitability.

