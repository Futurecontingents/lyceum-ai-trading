"""Streamlit dashboard for the autonomous decision journal."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from lyceum.config import load_settings
from lyceum.memory import Journal

st.set_page_config(page_title="Lyceum — AI Options Council", page_icon="Λ", layout="wide")
st.markdown(
    """<style>
.stApp{background:radial-gradient(circle at 15% 0%,#172554 0,#080d1a 32%,#050811 100%);color:#eef2ff}
[data-testid="stMetric"]{background:rgba(15,23,42,.72);border:1px solid #26355c;border-radius:14px;padding:14px}
.hero{padding:38px;border:1px solid #27345c;border-radius:24px;background:linear-gradient(135deg,rgba(79,70,229,.22),rgba(15,23,42,.78));margin-bottom:22px}
.hero h1{font-size:64px;margin:0;letter-spacing:-3px}.hero p{font-size:21px;color:#a5b4fc;margin:5px 0}.hero strong{color:#67e8f9}
.panel{background:rgba(15,23,42,.74);border:1px solid #27345c;border-radius:16px;padding:18px;margin:8px 0}
.decision{font-size:36px;font-weight:800;color:#67e8f9}.approved{color:#34d399}.rejected{color:#fb7185}.agent{font-size:13px;color:#a5b4fc}
</style>""",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hero"><h1>Lyceum</h1><p>Multiple minds. One market.</p><strong>Lyceum trades the uncertainty.</strong><br><small>ALPACA PAPER · MCP + CLI VERIFIED · READ ONLY BY DEFAULT</small></div>',
    unsafe_allow_html=True,
)

settings = load_settings()
journal = Journal(settings.database_path)
decisions = journal.recent("decisions", 100)
pnl = journal.recent("pnl_snapshots", 200)

if not decisions:
    st.info("No decisions yet. Run `python -m lyceum run --once --demo` to populate a safe demonstration cycle.")
    st.stop()

decoded = [{**row, "detail": json.loads(row["payload"])} for row in decisions]
symbols = sorted({row["symbol"] for row in decoded})
selected = st.selectbox("Market council ticker", symbols)
current = next(row for row in decoded if row["symbol"] == selected)
detail = current["detail"]
market, consensus, candidate, skeptic, risk = detail["market"], detail["consensus"], detail["candidate"], detail["skeptic"], detail["risk"]

portfolio_cols = st.columns(4)
equity = float(pnl[0]["equity"]) if pnl else 100_000
buying_power = float(pnl[0]["buying_power"]) if pnl else 400_000
for column, label, value in zip(
    portfolio_cols,
    ("Equity", "P&L", "Buying power", "Open positions"),
    (f"${equity:,.0f}", "$0 (no claim)", f"${buying_power:,.0f}", "0"),
    strict=True,
):
    column.metric(label, value)

st.subheader("Market Council")
cards = st.columns(5)
states = ["Strong ↓", "Down", "Flat", "Up", "Strong ↑"]
for column, opinion in zip(cards, detail["opinions"], strict=True):
    probs = opinion["probabilities"]
    values = list(probs.values())
    label = states[values.index(max(values))]
    column.markdown(
        f'<div class="panel"><span class="agent">{opinion["agent"]}</span><h3>{label}</h3><b>{opinion["confidence"]:.0%} confidence</b><p>{opinion["reasoning_summary"]}</p></div>',
        unsafe_allow_html=True,
    )

left, middle, right = st.columns([1.2, 1, 1])
with left:
    st.subheader("Consensus")
    distribution = consensus["distribution"]
    st.bar_chart(
        pd.DataFrame({"Probability": list(distribution.values())}, index=["Strong down", "Down", "Flat", "Up", "Strong up"]),
        color="#67e8f9",
    )
    st.metric("Disagreement", f"{consensus['disagreement']:.3f}")
    st.metric("Normalized entropy", f"{consensus['entropy']:.3f}")
with middle:
    st.subheader("Options")
    st.metric("Underlying", f"${market['price']:,.2f}")
    st.metric("Realized volatility", f"{market['realized_volatility']:.1%}")
    st.metric("Expected move", "—" if candidate["expected_move"] is None else f"${candidate['expected_move']:,.2f}")
    st.metric("Selected expiry", candidate["expiry"] or "None")
with right:
    st.subheader("Decision")
    st.markdown(
        f'<div class="panel"><div class="decision">{candidate["strategy"].replace("_", " ")}</div><p>{candidate["rationale"]}</p></div>',
        unsafe_allow_html=True,
    )
    risk_class = "approved" if risk["status"] == "APPROVED" else "rejected"
    st.markdown(
        f'<div class="panel"><h3 class="{risk_class}">{risk["status"]}</h3><p>{", ".join(risk["reason_codes"])}</p></div>',
        unsafe_allow_html=True,
    )

st.subheader("Skeptic")
st.markdown(
    f'<div class="panel"><b>Strongest objection:</b> {skeptic["strongest_argument_against"]}<br><b>Hidden assumption:</b> {skeptic["hidden_assumption"]}<br><b>Liquidity:</b> {skeptic["liquidity_concern"]}<br><b>IV:</b> {skeptic["iv_concern"]}<br><b>Event risk:</b> {skeptic["event_concern"]}<br><b>Veto confidence:</b> {skeptic["veto_confidence"]:.0%}</div>',
    unsafe_allow_html=True,
)

bottom_left, bottom_right = st.columns(2)
with bottom_left:
    st.subheader("Autonomous timeline")
    st.dataframe(
        pd.DataFrame(
            [
                {"time": row["created_at"][:19], "symbol": row["symbol"], "action": row["action"], "risk": row["risk_status"]}
                for row in decoded[:20]
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
with bottom_right:
    st.subheader("Counterfactual journal")
    counterfactuals = journal.recent("counterfactuals", 20)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "time": row["created_at"][:19],
                    "alternative": row["action"],
                    "outcome": "Pending mark" if row["outcome"] is None else row["outcome"],
                }
                for row in counterfactuals
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

st.caption("Educational paper-trading experiment. No live mode exists. Historical and paper results do not imply future performance.")
