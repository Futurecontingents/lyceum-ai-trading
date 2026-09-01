# Sep-01 forward-test failure

Status: **INVALID AS A COMPLETE PREREGISTERED EXPERIMENT**

Detected: 2026-09-01 21:58 Asia/Dubai (17:58 UTC), during forensic review

Incident snapshot: `artifacts/incidents/sep01_forward_test_failure_20260901T180300Z`

Snapshot state: APFS user-immutable (`uchg`) and read-only; 25 files verified by `SHA256SUMS.prelock`

Code HEAD at freeze: `bc65a71434a474f06b63440a5e31794fbcd5219a`

Frozen manifest SHA-256: `1658477538d34a241c0522f26e37187294e70df4f08c7e0c8fe30c2a1c7f1750`

Failed runner SHA-256: `73b7bb56b251f15a0cbcf5afe636deb29d6ec6414ed1ae95afbef3c6a7279ae1`

## Executive finding

The Sep-01 A–E leaderboard is not repairable as sealed evidence. The scheduled process topology captured raw market and option data but never invoked the council producer. The failed runner nevertheless consumed the absent council record by replacing disagreement, entropy, and expected direction with numeric zero. C and D therefore did not receive their frozen feature vectors. Separately, the outcome scorer attached excursions calculated over 60 minutes to every 5/15/30/60-minute outcome, contaminating all 5/15/30-minute MFE/MAE values with future information.

The original `com.lyceum.forward-test` launch job was unloaded after the immutable snapshot. It has not been restarted. Raw capture and the judging paper service were not restarted or modified by the incident response.

## Root cause and contributing causes

Primary root cause:

- `com.lyceum.shadow-collector.plist` executed only `scripts/market_snapshot_collector.py` every 240 seconds.
- That script calls only `MarketCollector.collect_once()`, which writes `capture_batches`, `underlying_snapshots`, and `option_snapshots`.
- `ShadowHarness.run()` in `src/lyceum/shadow.py` was the only producer of `shadow_results`.
- `scripts/shadow_research.py`, the command that invokes that harness, was documented as a manual research command and was not present in any Sep-01 launch job.
- The scheduled `scripts/forward_test_runner.py` queried `shadow_results` for `config_id='production'`, received no row, set `consensus = {}`, then used `.get("disagreement", 0)`, `.get("entropy", 0)`, and `.get("expected_direction", 0)`.

Contributing causes:

1. The producer and consumer were separately invocable, but the deployment manifest had no dependency or freshness gate between them.
2. No candidate declared a typed, complete feature contract.
3. Missing values were indistinguishable from measured zero in persisted `feature_json`.
4. The runner had no provenance link to a council run or five underlying agent opinions.
5. No preflight checked producer liveness, same-batch council coverage, agent count, schema, or recomputed JSD/entropy.
6. Tests manually called `ShadowHarness.run()` after collection, masking the actual launchd topology.
7. The scorer built one excursion vector with `elapsed <= 60`, outside its horizon loop, and reused it for every outcome horizon.
8. Monitoring checked process/service health and database integrity, but not semantic coverage or temporal causality.

There was no evidence of a wrong database path, failed `shadow_results` transaction, schema mismatch, timestamp join mismatch, or intermittent race. The intended producer never ran at all. The zero-row count was deterministic under the deployed topology.

## Exact affected rows and fields

- Failed database: immutable snapshot `databases/forward_test.db`.
- Decisions: 3,192 rows, 57 distinct captured batches, seven symbols, eight evaluated systems, available from `2026-09-01T13:35:25.062279Z` through `2026-09-01T17:56:36.083910Z`.
- All 3,192 `feature_json` payloads contain `disagreement=0` and `entropy=0` because the common feature builder silently imputed them.
- C: 399 decision rows; required `disagreement` and `entropy` are invalid placeholders. Its signal, strategy, trade count, midpoint/executable P&L, and leaderboard rank are invalid.
- D: 399 decision rows; the same required fields are invalid placeholders. Its ridge prediction, signal, strategy, trade count, P&L, and rank are invalid.
- A, B, E, MOMENTUM, REVERSION, CASH: the unused placeholder council fields are present but do not enter their frozen rules. Their decision/P&L paths remain evaluable subject to the separate metric limitation below.
- `forward_outcomes`: MFE and MAE are invalid for all 601 five-minute rows, 581 fifteen-minute rows, and 558 thirty-minute rows because each used the 60-minute excursion window. The 466 sixty-minute MFE/MAE rows use their correctly named horizon.
- All C/D aggregate rows and any all-candidate ranking are invalid. Raw C/D midpoint gains are not evidence.

## Unaffected evidence

- Raw timestamped underlying and option snapshots remain intact and passed SQLite `quick_check`.
- Entry and exit bid/ask arithmetic and conservative P&L use timestamped quotes; forensic sampling found no outcome scored before its requested horizon.
- Candidate A and B did not depend on council fields. At the agreed terminal cutoff their intended executable results were A 60-minute **-$421.80** and B 30-minute **-$647.90**. They were economically poor.
- Cash/NO_TRADE beat every observed raw strategy aggregate.
- The immutable preregistration manifest, code, logs, databases, launch plists, leaderboard, and prior audit are preserved.
- This incident does not imply an Alpaca execution or account safety failure. No order was submitted, cancelled, or modified during diagnosis or repair.

## Complete lineage audit

| Transition | Produced | Persisted/timestamped | Consumer/schema | Missing behavior | Causal | Sep-01 test coverage |
|---|---|---|---|---|---|---|
| Market observation → capture batch | Yes | Yes; batch and quote timestamps | Raw collector schema valid | Capture batch marked failed on collection error | Yes | Collector unit path covered |
| Capture → council invocation | **No** | No council-run record existed | No deployed consumer/producer dependency | **No failure signal** | N/A | Actual launch topology not tested |
| Council → five agent outputs | **No for shadow cadence** | No agent-opinion rows | `ShadowHarness.run()` would create in memory only | No persisted invariant | N/A | Only manual in-process harness test |
| Opinions → consensus/JSD | **No** | No exact input opinions or council ID | Failed runner expected a production shadow payload | Absent row became `{}` | N/A | Consensus math unit-tested, lineage not tested |
| Consensus → feature vector | **No valid C/D values** | Zero placeholders persisted | Untyped dict | **Silent zero imputation** | Numerically causal but semantically invalid | Missing-row case absent |
| Feature vector → candidate | A/B/E yes; C/D invalid | Decision rows timestamped | Frozen candidate code | Evaluation continued | A/B/E causal | Determinism only |
| Candidate → option preview | Yes where selected | Legs and entry quotes persisted | Quote validity filters | NO_TRADE on no structure | Yes | Partial |
| Preview → outcome | Yes | Exit batch/time persisted | Bid/ask conservative scorer | Skips unavailable quote | Horizon exit causal | Partial |
| Outcome → MFE/MAE | **Incorrect for <60m** | Values persisted | One 60m vector reused | No violation signal | **No for 5/15/30m** | Absent |
| Outcome → leaderboard | Yes | JSON artifact | Included invalid C/D rows | No coverage exclusion | Mixed | No semantic preflight |

## Why monitoring missed it

The overnight safety heartbeat verified service availability, paper endpoint, HALT state, disk, database integrity, and broker state. Those checks correctly covered operational safety but not research validity. A healthy raw collector, a healthy judging service, and a structurally valid SQLite database can still contain zero rows from an unscheduled semantic producer. The forward process also exited successfully because missing data was deliberately converted to zero. There was no invariant on feature coverage, exact agent count, consensus recomputation, or horizon-bounded excursions.

## Repair boundary

The failed runner and database are preserved and never rewritten. Post-incident code uses a separate v2 schema and runner. It:

- persists exact five-agent opinions, their hash, recomputed consensus, producer/schema versions, batch/symbol, and timestamps;
- rejects missing, null, non-finite, malformed, unproven, or temporally impossible required features as `INVALID_FEATURE_VECTOR`;
- records explicit reasons and provenance;
- excludes invalid observations from scoring and leaderboards;
- computes MFE/MAE inside each horizon window;
- requires a paper-only, read-only, producer-aware preflight;
- runs a real-data canary through MARKET/COUNCIL/PERSIST/FEATURES/OPTIONS/CAUSALITY/SCORER.

The repair validates infrastructure behavior only. It does not validate A–E, recover the failed sealed experiment, prove profitability, or establish production readiness.
