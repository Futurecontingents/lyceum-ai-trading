# Judging Account Runbook

The currently authenticated `paper` profile is development-only. Lyceum never creates or switches Alpaca accounts automatically.

## One-time preparation

1. Create a brand-new Alpaca paper account for judging.
2. Before any trade, verify the account begins with the hackathon-required **$100,000** equity.
3. Authenticate it as a separate CLI profile:

   ```bash
   alpaca profile login --paper --name judging
   ```

4. Compare it with the development profile and verify all of the following:

   - the trading endpoint is `https://paper-api.alpaca.markets`;
   - the judging account ID differs from the development account ID;
   - starting equity is fresh;
   - open positions are zero;
   - open orders are zero.

5. Use a separate journal so development decisions never leak into judging state:

   ```dotenv
   LYCEUM_ALPACA_PROFILE=judging
   LYCEUM_DATABASE_PATH=data/judging.db
   LYCEUM_EXPECT_FRESH_ACCOUNT=true
   LYCEUM_EXECUTION_MODE=READ_ONLY
   LYCEUM_ENABLE_PAPER_ORDERS=false
   ```

6. Run the explicit validation:

   ```bash
   python -m lyceum doctor
   ```

   Confirm the printed profile, paper endpoint, distinct account ID, `ACTIVE` status, equity, zero positions, zero orders, and `READ_ONLY` mode.

7. Run a real-data, read-only smoke test:

   ```bash
   python -m lyceum run --once
   ```

   It may stop at the market-clock check outside trading hours. It must not submit an order.

8. After the initial freshness check passes, set `LYCEUM_EXPECT_FRESH_ACCOUNT=false`. Only after deliberate review may both execution controls be changed to:

   ```dotenv
   LYCEUM_EXECUTION_MODE=PAPER_AUTONOMOUS
   LYCEUM_ENABLE_PAPER_ORDERS=true
   ```

Never copy the development database, journal records, positions, orders, or account identifiers into judging state. Never point Lyceum at a live endpoint; the application rejects one.
