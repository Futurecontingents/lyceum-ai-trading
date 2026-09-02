# Sep-03 preregistration

Status: **FROZEN READ-ONLY SHADOW SPECIFICATION**.

- Frozen at: `2026-09-02T12:46:30Z`—24 hours 43 minutes before the 2026-09-03 regular-session open.
- Historical data cutoff: `2026-08-28`.
- Frozen code commit: `1cea74314043ca9a35eaa3a0ebd335ef443db541`.
- Machine specification: `research/forward_test_2026-09-03.json`.
- Parameter changes after freeze: **PROHIBITED**.
- Order submission: **PROHIBITED**.

## Frozen candidates

### CONTROL

Cash/`NO_TRADE`, SPY observation persistence only, zero quantity and zero max loss.

### NEXTGEN_A

Prior adjusted SPY close-to-close return <=-2.0%; observe the next regular-session open-to-close signed return and absolute movement. The frozen signed move/cost ratio is 0.9577. A trade-producing state requires a frozen minimum ratio of 1.25, so this candidate is `NO_TRADE`. It is observation-only and cannot cross the execution surface.

No model candidate is included, so the frozen model-hash set is explicitly empty. Neither candidate requires council output. Candidate hashes, runner hash, data hashes, paths, thresholds, target, holding horizon, option rule, execution rule, and risk rule are frozen in the JSON specification.

## Split readiness gates

### Static pre-market preflight

Checks frozen commit/timestamp, candidate hashes, model hashes, data cutoff, SQLite schema and quick-check, Alpaca paper-only endpoint, runner hash and absence of execution calls, no future data, scoring logic, persistence paths, and a temporary-database scorer probe. It intentionally does **not** inspect quote freshness.

Result: **PASS**. Artifact: `artifacts/long_history/sep03_static_preflight.json`.

### Live market canary

Checks fresh required-symbol underlying quotes, fresh valid required-symbol option quotes, five-agent rows only when a frozen candidate requires them, causal timestamps, a valid option snapshot, and read-only scorer persistence. It always reports `orders_submitted=0`.

The off-hours diagnostic is expected to fail only its freshness stages; causal timestamp, option snapshot presence, and scorer health pass. It must be rerun during the live Sep-03 session before any forward observations are accepted. Artifact: `artifacts/long_history/sep03_live_canary.json`.

No service or production configuration was changed or restarted.
