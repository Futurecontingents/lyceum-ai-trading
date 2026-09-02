# Lyceum — A Market of AI Minds

**AI proposes. Math validates. Alpaca executes.**

Lyceum is an autonomous, paper-only options research-and-trading system. Five specialized agents produce probability distributions rather than opaque `BUY`/`SELL` labels. Consensus mathematics turns entropy and Jensen–Shannon disagreement into measurable uncertainty; quantitative signals and a cost-aware selector then propose a defined-risk option—or `NO_TRADE`—before an adversarial skeptic and deterministic risk gate decide whether it may reach Alpaca paper execution.

## Why it is different

Lyceum does not present “five agents voting” as an edge. It treats the agents as competing beliefs, measures their disagreement, tests those beliefs against decades of causal market data, and asks whether any forecast survives real option crossing costs. Deterministic code can reject the AI, and invalid observations are excluded from scoring.

## Alpaca infrastructure

Lyceum uses the Alpaca Trading API and `alpaca-py` for market, account, option, and paper-execution primitives; an authenticated Alpaca CLI profile as an OAuth/data bridge; and Alpaca’s hosted paper MCP. There is no live mode. The endpoint is asserted as paper immediately before execution.

## Research conclusion

The research campaign covers 33.58 years / 8,453 SPY sessions, a 56.65-year S&P 500 proxy, 361,439 five-minute observations / 666 recent sessions, 19 registered long-history hypotheses, and 9,627 recent real option-structure observations.

Close-to-open SPY drift and HAR-style volatility forecasting are statistically supported. The full LLM council has not demonstrated directional or executable value-add. Ordinary expected moves are generally too small relative to option round-trip costs; rare capitulation states are not robust enough to promote. No profitable executable option edge has been demonstrated.

The Sep-01 A–E shadow experiment was invalidated because the deployed collector never invoked the council producer and missing disagreement/entropy were silently imputed as zero; sub-60-minute excursion metrics also contained future information. Lyceum preserved the failure, labeled reconstruction post-hoc, and repaired the V2 path to fail closed. Sep-03 is a separately frozen, observation-only `NO_TRADE` test.

## Judge links

- [Public demo](https://futurecontingents.github.io/lyceum-ai-trading/)
- [Public repository](https://github.com/Futurecontingents/lyceum-ai-trading)
- [Final research report](../research/FINAL_RESEARCH_REPORT.md)
- [Current results](../artifacts/submission/current_results.md)
- [Sep-01 incident](../research/incidents/SEP01_FORWARD_TEST_FAILURE.md)
- [Sep-03 preregistration](../research/sep03_preregistration.md)
- [Architecture](ARCHITECTURE.md)
- [Official requirement audit](HACKATHON_FINAL_REQUIREMENTS.md)
