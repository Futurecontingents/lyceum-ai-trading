# SPY reconciliation finding — 2026-04-20

The single strict reconciliation failure is resolved diagnostically but remains a **FAIL** in the manifest. No evidence was changed.

| Field | Yahoo chart API | Nasdaq public historical API | Independent web confirmations |
|---|---:|---:|---:|
| Raw open | 708.78 | 710.14 | 708.78 |
| Raw high | 709.91 | 710.14 | 709.91 |
| Raw low | 706.14 | 710.14 | 706.14 |
| **Raw close** | **708.7199707** | **710.14** | **708.72** |
| Volume | 43,546,800 | N/A | approximately 43.5 million |

The exact reconciled field was raw close, with an absolute discrepancy of **$1.4200293**. Yahoo's adjusted close was about $706.90, but that is not what was compared; the comparison used raw close on both sides. The $710.14 Nasdaq value exactly duplicates the prior session's 2026-04-17 raw close. Nasdaq also reports open=high=low=close=710.14 and volume=`N/A` for 2026-04-20, which is a placeholder pattern rather than a market bar.

[Yahoo's public history](https://ca.finance.yahoo.com/quote/SPY/history/) and two independent public histories—[FinanceCharts](https://www.financecharts.com/etfs/SPY/summary/price) and [ChartExchange](https://chartexchange.com/symbol/nyse-spy/historical/)—agree on the 2026-04-20 OHLC and $708.72 close. The relevant quarterly SPY ex-dividend date was 2026-03-20, not April 20; the next was June 18.

Classification:

- adjusted versus raw: **NO**;
- corporate action: **NO**;
- provider revision/placeholder defect: **YES — Nasdaq duplicated the prior close in an incomplete placeholder row**;
- timezone/calendar: **NO**;
- missing session: **NO — April 20 was a real trading session**;
- genuine unexplained disagreement: **NO; the discrepancy is explained, but strict equality still fails**.

The primary Yahoo observation remains unchanged. `data_manifest.json` records `NASDAQ_PLACEHOLDER_DUPLICATING_PRIOR_CLOSE`, `evidence_modified=false`, and overall independent reconciliation `FAIL`.
