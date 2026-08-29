# Historical Experiment

This is a pragmatic historical sanity check, not evidence of profitability. Signals use only information available before each forward window.

| Horizon | n | Pearson vs |return| | Spearman vs |return| | Pearson vs realized vol | Spearman vs realized vol |
|---|---:|---:|---:|---:|---:|
| 1h | 213 | -0.030 | -0.051 | -0.030 | -0.051 |
| 4h | 210 | -0.036 | -0.036 | -0.032 | -0.029 |
| 1 trading day | 207 | 0.018 | 0.040 | 0.087 | 0.108 |

## Disagreement buckets

### 1h

| Bucket | n | Mean subsequent |return| | Mean subsequent realized volatility |
|---|---:|---:|---:|
| low | 54 | 0.1829% | 0.1829% |
| mid-low | 53 | 0.1814% | 0.1814% |
| mid-high | 53 | 0.1478% | 0.1478% |
| high | 53 | 0.1423% | 0.1423% |

### 4h

| Bucket | n | Mean subsequent |return| | Mean subsequent realized volatility |
|---|---:|---:|---:|
| low | 53 | 0.3356% | 0.3957% |
| mid-low | 52 | 0.4056% | 0.4218% |
| mid-high | 52 | 0.3608% | 0.4074% |
| high | 53 | 0.3315% | 0.3978% |

### 1 trading day

| Bucket | n | Mean subsequent |return| | Mean subsequent realized volatility |
|---|---:|---:|---:|
| low | 52 | 0.4517% | 0.5403% |
| mid-low | 52 | 0.4916% | 0.5331% |
| mid-high | 51 | 0.4764% | 0.5583% |
| high | 52 | 0.5035% | 0.6063% |

## Interpretation

A positive correlation would support further investigation; a weak or unstable result means disagreement remains an experimental dashboard signal. Lyceum then falls back to a documented combination of market regime, momentum, implied volatility, and consensus. No result here is fabricated or presented as a trading edge.
