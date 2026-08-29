# Lyceum — Hackathon Submission

**Multiple minds. One market. Lyceum trades the uncertainty.**

Lyceum is a paper-only multi-agent options system built around a modest question: can disagreement among calibrated market perspectives help describe short-horizon uncertainty? It turns five probability distributions into explicit entropy and Jensen–Shannon disagreement measurements, then selects a defined-risk options candidate—or `NO_TRADE`.

## Hybrid architecture

- `TechnicalQuantAgent` and `OptionsMarketAgent` always remain deterministic and market-derived.
- `NewsCatalystAgent`, `BullAdvocateAgent`, and `BearAdvocateAgent` are deterministic by default and may optionally use an OpenAI-compatible model.
- Model output crosses a strict Pydantic boundary with JSON extraction, finite-number validation, bounded retries/timeouts, and automatic deterministic fallback.
- Every opinion records its actual implementation, provider, model, prompt version, latency, timestamp, and fallback state.
- Consensus mathematics, strategy selection, the adversarial skeptic, pre-trade risk, paper-endpoint verification, and execution do not depend on a model provider.

The governing rule is: **AI proposes. Math validates. Alpaca executes.** No model can bypass `HALT`, loss limits, portfolio constraints, liquidity checks, duplicate/cooldown checks, or the paper-only endpoint assertion.

## Alpaca integration

Lyceum uses the authenticated Alpaca CLI as a local OAuth bridge for account, market-clock, bars, option-chain, Greeks, position, and order data. The project also declares Alpaca's hosted paper MCP endpoint for agent-accessible tooling. Multi-leg requests are constructed only at the execution boundary, and there is no live mode.

## Evidence and limitations

The repository includes a deterministic demo, SQLite decision/counterfactual memory, a Streamlit council dashboard, automated tests, and a historical disagreement experiment. The current historical correlations are weak and are reported as such. Lyceum does **not** claim that model disagreement is proven alpha, that paper performance predicts live execution, or that any result is investment advice.
