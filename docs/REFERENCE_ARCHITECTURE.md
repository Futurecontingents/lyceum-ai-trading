# Reference Architecture Review

Research date: 2026-08-29. The repositories below were inspected at their default branches. Review covered each README and tree plus representative orchestration, risk, persistence, test, and dashboard code where present. Lyceum reuses ideas, not source code.

## Repositories inspected

| Repository | Useful ideas extracted | Deliberately rejected |
|---|---|---|
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Specialist analyst roles, bullish/bearish debate, explicit graph state, checkpoint/error tests, separation of analysis from portfolio decision | LangGraph-scale workflow, recursive debates, broad vendor matrix, and free-form final signals are too heavy for a one-day options slice |
| [Alexanderk30/OpenclawDerivativeTrading](https://github.com/Alexanderk30/OpenclawDerivativeTrading) | Layered per-trade/daily/portfolio risk, central strategy registry, paper runner, compact dashboard | Live script, wheel strategy's undefined assignment exposure, file knowledge graph, and configuration postures that can silently relax controls |
| [alpacahq/agentic](https://github.com/alpacahq/agentic) | Current hosted OAuth MCP endpoints, separate paper resource, Codex client ID, MCP + CLI as visible agent interfaces | Live MCP resource and broker APIs; Lyceum registers only `paper-api.alpaca.markets/mcp` |
| [milgar7969/alpaca-options-framework](https://github.com/milgar7969/alpaca-options-framework) | Quote freshness, duplicate-exit protection, daily-loss restore, cooldown, shadow/counterfactual filter evaluation | 0DTE concentration, embedded credentials, forced process exit, and a single monolithic session strategy |
| [GeorgeStatho/agentic-trading-research](https://github.com/GeorgeStatho/agentic-trading-research) | Deterministic option selection after agents, durable SQLite execution journal, explicit worker stages, dashboard status payloads | Multi-container React/Flask deployment, live submission path, scraping platform, and opaque model stages |
| [huygiatrng/AlpacaTradingAgent](https://github.com/huygiatrng/AlpacaTradingAgent) | Safety guardrail tests, structured decisions, chaos/data-fallback tests, regime-aware portfolio concepts | Framework inheritance breadth, multi-provider complexity, and equity/crypto scope outside the options hypothesis |
| [Luadja/alpaca-trading-bot](https://github.com/Luadja/alpaca-trading-bot) | Paper-first defaults, walk-forward research gates, Streamlit from persisted state, broker boundary tests | Strategy proliferation and research platform features not required for the judging narrative |
| [PAT0216/paper-trader](https://github.com/PAT0216/paper-trader) | Clear dashboard snapshots, no-lookahead tests, honest comparison when a model has no edge | Parallel ML/LSTM portfolios and scheduled cloud automation before the core hypothesis is validated |
| [calesthio/OptionsCanvas](https://github.com/calesthio/OptionsCanvas) | Normalized SQLite order lifecycle, broker adapter, property/state-machine tests, automated screenshot capture | Large frontend/backend platform, hidden stop execution, live broker breadth, and mutable manual chart controls |

## Lyceum decisions

1. **Typed council, not chat transcripts.** Every mind emits the same Pydantic probability contract. Invalid or non-normalized output never reaches consensus.
2. **One synchronous vertical slice.** A bounded runner is easier to observe and test than a distributed graph. A failure in one symbol is journaled and isolated.
3. **Disagreement is mathematics.** Confidence-weighted probabilities, normalized entropy, and pairwise Jensen–Shannon divergence replace qualitative “AI scores.”
4. **Deterministic strategy and risk.** Agents supply evidence; code chooses structures and has final veto authority.
5. **`NO_TRADE` is data.** Rejections and abstentions are persisted with the same detail as approvals.
6. **SQLite is the product memory.** Dashboard and counterfactual views query durable records rather than transient process state.
7. **Paper proof at every boundary.** Configuration has no live mode. The CLI gateway checks `alpaca doctor`; the executor repeats this immediately before a paper submission.
8. **Current hosted MCP plus CLI.** MCP is visible for agent-driven account/options tooling; the CLI provides a stable OAuth-backed local bridge for the Python runner.
9. **Streamlit for the demo.** It completes the judging surface today while keeping the data and domain layers independent of UI.
10. **Experiment before claims.** The hourly sanity check reports weak or negative results unchanged and activates no order logic.

## Resulting architecture

```text
Alpaca PAPER CLI / hosted MCP
  -> data gateway
  -> five typed independent minds
  -> consensus math
  -> option selector
  -> skeptic
  -> deterministic risk gate
  -> read-only / simulated / explicitly enabled paper execution
  -> SQLite journal
  -> dashboard, experiment, and counterfactual marks
```

