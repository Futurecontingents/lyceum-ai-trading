# Sep-01 diagnostic reconstruction

Label: **POST-HOC RECONSTRUCTION — NOT SEALED FORWARD EVIDENCE**

## What could and could not be recovered

The exact timestamped Sep-01 raw underlying and option snapshots survive. The exact shadow-cadence council outputs do not: `shadow_results` contains zero Sep-01 rows, and the deployed collector never invoked the council. Production judging council decisions exist at a different cadence and cannot be substituted for the missing frozen-input observations.

To diagnose the effect of the missing fields, the original deterministic council and original frozen runner were replayed over the 58 complete captured batches in an APFS clone of the immutable database. This uses only information captured at each original timestamp, but the agent outputs were computed after the fact. It therefore cannot replace, repair, or rerank the failed leaderboard.

## Reproduction

Frozen source was retained at HEAD `bc65a71434a474f06b63440a5e31794fbcd5219a`. From a writable clone of the incident database:

```bash
.venv/bin/python scripts/shadow_research.py --database "$CLONE/shadow.db" --latest-batches 58
.venv/bin/python scripts/forward_test_runner.py \
  --shadow "$CLONE/shadow.db" \
  --database "$CLONE/forward_reconstructed.db" \
  --manifest research/forward_test_2026-09-01.json \
  --leaderboard "$CLONE/leaderboard.json"
```

The reconstruction created 13,398 shadow decisions (58 batches × 7 symbols × 33 configurations) and 2,030 frozen/benchmark decisions.

## Diagnostic results

| System | Intended horizon | Scored trades | Executable P&L | Mean | Median | Positive trades | Crossing cost | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A | 60m | 66 | -$743.90 | -$11.27 | -$10.50 | 19 | $647.20 | Post-hoc extended-cutoff diagnostic; original agreed evaluable result is -$421.80 |
| B | 30m | 68 | -$751.90 | -$11.06 | -$9.00 | 17 | $598.90 | Post-hoc extended-cutoff diagnostic; original agreed evaluable result is -$647.90 |
| C | 60m | 144 | -$2,032.00 | -$14.11 | -$14.00 | 8 | $1,836.60 | Missing features materially change behavior; still uneconomic; not sealed evidence |
| D | 5m | 45 | -$441.80 | -$9.82 | -$8.90 | 9 | $393.75 | Missing features materially change behavior; still uneconomic; not sealed evidence |
| E | 30m | 0 | $0.00 | — | — | 0 | $0.00 | No trades |
| CASH | — | 0 | $0.00 | — | — | 0 | $0.00 | Best aggregate |

The reconstructed C and D results refute any attempt to interpret their failed-run midpoint gains as a hidden edge. Crossing costs overwhelm both. They also demonstrate why silent defaults are unacceptable: recomputed features materially alter trade selection and P&L.

## Valid Sep-01 conclusions

1. The complete A–E preregistered comparison is invalid.
2. A and B were evaluable and economically poor at the agreed cutoff: -$421.80 and -$647.90 executable P&L.
3. Cash/NO_TRADE beat every raw aggregate examined.
4. Full-council directional value-add has not been demonstrated.
5. Exit crossing is a dominant loss source.
6. Sub-60-minute MFE/MAE in the failed database must not be used.
7. The reconstruction is development diagnostics only; Sep-01 is not OOS for any strategy influenced by it.
