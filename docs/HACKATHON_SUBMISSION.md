# Lyceum — A Market of AI Minds

**Multiple minds. One market. Lyceum trades the uncertainty.**

Lyceum is an autonomous, paper-only options research and trading system. Five specialized agents produce probability distributions rather than opaque `BUY`/`SELL` labels. Consensus mathematics turns entropy and Jensen–Shannon disagreement into measurable uncertainty; a cost-aware selector then proposes a defined-risk option—or `NO_TRADE`—before an adversarial skeptic and deterministic risk gate decide whether it may reach Alpaca paper execution.

## AI logic

The technical and options agents are deterministic. In hybrid mode, a local Qwen3 model serves the news, bull, and bear roles through distinct prompts and an OpenAI-compatible interface. Every role must emit the same strict `AgentOpinion` schema. Invalid output, malformed JSON, timeout, or runtime failure automatically activates the deterministic fallback. Model output cannot alter consensus mathematics, risk limits, endpoint checks, or execution controls.

Lyceum's governing rule is: **AI proposes. Math validates. Alpaca executes.**

## Alpaca infrastructure

Lyceum uses the Alpaca Trading API and `alpaca-py` for market/account/execution primitives, the authenticated Alpaca CLI as an OAuth/data bridge, and Alpaca's hosted paper MCP for agent-accessible tooling. The judging service uses a dedicated fresh $100,000 paper account. There is no live mode; the configured endpoint is asserted immediately before execution.

## Risk gates and auditability

The deterministic gate checks maximum loss, daily loss, portfolio heat, concentration, position count, buying power, liquidity, bid/ask width, quote freshness, duplicates, cooldowns, skeptic veto, and the emergency `HALT` state. Paper orders require two independent configuration flags. Every observation, opinion, rejection, preview, order, position, P&L snapshot, latency, and fallback is journaled in SQLite.

## Research evidence

Historical work covers **361,439 five-minute bars**, **666 sessions**, seven liquid symbols, and 2024-01-02 through 2026-08-28. Chronological walk-forward tests indicate that direction is weak, realized volatility is more predictable, and disagreement adds modest incremental volatility information. The harder result is economic: quoted-side entry and exit costs often overwhelm gross option movement.

Five candidates were preregistered before the 2026-09-01 session and run as a sealed, shadow-only forward test. Definitions, thresholds, models, construction rules, and scoring are frozen. Lyceum deliberately distinguishes statistical prediction, development diagnostics, untouched forward evidence, and paper execution. It makes no profitability or proven-edge claim.

## Judge links

- [Public demo](https://futurecontingents.github.io/lyceum-ai-trading/)
- [Public repository](https://github.com/Futurecontingents/lyceum-ai-trading)
- [Current results](../artifacts/submission/current_results.md)
- [Frozen manifest](../research/forward_test_2026-09-01.json)
- [Architecture](ARCHITECTURE.md)
- [Official requirement audit](HACKATHON_FINAL_REQUIREMENTS.md)
