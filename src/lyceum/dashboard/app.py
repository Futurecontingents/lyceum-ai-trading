"""Streamlit dashboard for the autonomous decision journal."""

from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st

from lyceum.config import load_settings
from lyceum.memory import Journal


def safe(value: object) -> str:
    return html.escape(str(value))


def direction_label(value: float) -> str:
    if value > 0.28:
        return "BULLISH"
    if value < -0.28:
        return "BEARISH"
    return "NEUTRAL"


st.set_page_config(page_title="Lyceum — AI Options Council", page_icon="Λ", layout="wide")
st.markdown(
    """<style>
.stApp{background:radial-gradient(circle at 12% 0%,#172554 0,#080d1a 30%,#050811 100%);color:#eef2ff}
[data-testid="stMetric"]{background:rgba(15,23,42,.78);border:1px solid #2c3c67;border-radius:14px;padding:12px 14px}
[data-testid="stMetricLabel"]{color:#9aa9d1}.hero{padding:24px 30px;border:1px solid #30406d;border-radius:22px;background:linear-gradient(135deg,rgba(79,70,229,.24),rgba(15,23,42,.82));margin-bottom:14px}
.hero h1{font-size:46px;margin:0;letter-spacing:-3px;line-height:1}.hero p{font-size:19px;color:#a5b4fc;margin:5px 0 2px}.hero strong{color:#67e8f9}
.pill{display:inline-block;padding:5px 10px;border-radius:999px;margin:9px 6px 0 0;font-size:11px;font-weight:800;letter-spacing:.7px;background:#173d3b;color:#6ee7b7;border:1px solid #2f766b}
.pill.mode{background:#262956;color:#c4b5fd;border-color:#4f46e5}.demo{padding:9px 13px;border:1px solid #d97706;background:rgba(217,119,6,.12);border-radius:10px;color:#fcd34d;font-weight:700;margin-bottom:12px}
.panel{background:rgba(15,23,42,.78);border:1px solid #2c3c67;border-radius:16px;padding:15px;margin:6px 0;min-height:202px}
.panel h3{margin:7px 0 4px}.agent{font-size:12px;color:#a5b4fc}.badge{float:right;font-size:10px;padding:3px 7px;border-radius:8px;background:#23304f;color:#cbd5e1}.badge.model{background:#4338ca;color:#e0e7ff}.badge.fallback{background:#92400e;color:#fef3c7}
.prob{font-family:ui-monospace,monospace;font-size:11px;color:#a5b4fc;line-height:1.65}.reason{font-size:13px;color:#dbe4ff;line-height:1.35}.decision{font-size:28px;font-weight:800;color:#67e8f9}.approved{color:#34d399}.rejected{color:#fb7185}
.why{background:linear-gradient(120deg,rgba(14,116,144,.16),rgba(67,56,202,.14));border:1px solid #375174;border-radius:18px;padding:18px}.why b{color:#67e8f9}
</style>""",
    unsafe_allow_html=True,
)

settings = load_settings()
journal = Journal(settings.database_path)
decisions = journal.recent("decisions", 100)
pnl = journal.recent("pnl_snapshots", 200)

st.markdown(
    f'<div class="hero"><h1>Lyceum</h1><p>Multiple minds. One market.</p><strong>Lyceum trades the uncertainty.</strong><br><span class="pill">PAPER ONLY</span><span class="pill mode">{safe(settings.execution_mode)}</span></div>',
    unsafe_allow_html=True,
)

if not decisions:
    st.info("No decisions yet. Run `python -m lyceum run --once --demo` to populate a safe demonstration cycle.")
    st.stop()

decoded = [{**row, "detail": json.loads(row["payload"])} for row in decisions]
symbols = sorted({row["symbol"] for row in decoded})
selected = st.selectbox("Market council ticker", symbols, label_visibility="collapsed")
current = next(row for row in decoded if row["symbol"] == selected)
detail = current["detail"]
market, consensus = detail["market"], detail["consensus"]
candidate, skeptic, risk = detail["candidate"], detail["skeptic"], detail["risk"]
context = detail.get("run_context", {})
is_demo = bool(context.get("demo", not pnl))
environment_label = "DEMO" if is_demo else ("JUDGING" if settings.alpaca_profile == "judging" else "DEVELOPMENT")
direction = direction_label(float(consensus["expected_direction"]))

if is_demo:
    st.markdown('<div class="demo">DEMO DATA · Synthetic market snapshot · No order or P&amp;L claim</div>', unsafe_allow_html=True)
else:
    st.markdown(
        f'<div class="demo">{safe(environment_label)} · Alpaca Paper profile {safe(settings.alpaca_profile)} · Journal {safe(settings.database_path)}</div>',
        unsafe_allow_html=True,
    )

equity_value = "DEMO $100K" if is_demo else (f"${float(pnl[0]['equity']):,.0f}" if pnl else "—")
values = (
    ("Mode", str(context.get("execution_mode", settings.execution_mode))),
    ("Symbol", selected),
    ("Council", direction),
    ("Disagreement", f"{consensus['disagreement']:.3f}"),
    ("Strategy", candidate["strategy"].replace("_", " ")),
    ("Risk", risk["status"]),
    ("Equity", equity_value),
    ("P&L", "NOT TRACKED" if is_demo else (f"${float(pnl[0]['pnl']):,.0f}" if pnl else "—")),
)
for row_values in (values[:4], values[4:]):
    metric_columns = st.columns(4)
    for column, (label, value) in zip(metric_columns, row_values, strict=True):
        column.metric(label, value)

st.subheader("Market Council")
cards = st.columns(5)
states = ["Strong ↓", "Down", "Flat", "Up", "Strong ↑"]
probability_keys = ["strong_down", "down", "flat", "up", "strong_up"]
probability_labels = ["SD", "D", "F", "U", "SU"]
for column, opinion in zip(cards, detail["opinions"], strict=True):
    probs = opinion["probabilities"]
    probability_values = [float(probs[key]) for key in probability_keys]
    label = states[probability_values.index(max(probability_values))]
    implementation = opinion.get("implementation", "deterministic")
    fallback = bool(opinion.get("fallback_used", False))
    badge_class = "fallback" if fallback else implementation
    badge_text = "FALLBACK" if fallback else implementation.upper()
    probability_line = " · ".join(f"{name} {value:.0%}" for name, value in zip(probability_labels, probability_values, strict=True))
    metadata = ""
    if implementation == "model" or fallback:
        metadata = f'<div class="agent">{safe(opinion.get("provider"))} · {safe(opinion.get("model_name"))} · {float(opinion.get("latency_ms", 0)):.0f}ms</div>'
    column.markdown(
        f'<div class="panel"><span class="agent">{safe(opinion["agent"])}</span><span class="badge {badge_class}">{badge_text}</span><h3>{label}</h3><b>{float(opinion["confidence"]):.0%} confidence</b><div class="prob">{probability_line}</div><p class="reason">{safe(opinion["reasoning_summary"])}</p>{metadata}</div>',
        unsafe_allow_html=True,
    )

st.subheader("Why this decision?")
iv = market.get("implied_volatility")
iv_context = "Unavailable" if iv is None else f"{float(iv):.1%} implied vs {float(market['realized_volatility']):.1%} realized"
st.markdown(
    f'<div class="why"><b>Consensus:</b> {direction} ({float(consensus["directional_conviction"]):.0%} conviction) &nbsp;·&nbsp; <b>Disagreement:</b> {float(consensus["disagreement"]):.3f} &nbsp;·&nbsp; <b>IV context:</b> {iv_context}<br><b>Skeptic:</b> {safe(skeptic["strongest_argument_against"])}<br><b>Final risk decision:</b> {safe(risk["status"])} — {safe(", ".join(risk["reason_codes"]))}</div>',
    unsafe_allow_html=True,
)

left, middle, right = st.columns([1.15, 1, 1])
with left:
    st.subheader("Consensus distribution")
    distribution = consensus["distribution"]
    st.bar_chart(
        pd.DataFrame({"Probability": list(distribution.values())}, index=["Strong down", "Down", "Flat", "Up", "Strong up"]),
        color="#67e8f9",
    )
with middle:
    st.subheader("Options context")
    st.metric("Underlying", f"${market['price']:,.2f}")
    st.metric("Expected move", "—" if candidate["expected_move"] is None else f"${candidate['expected_move']:,.2f}")
    st.metric("Selected expiry", candidate["expiry"] or "None")
with right:
    st.subheader("Candidate")
    risk_class = "approved" if risk["status"] == "APPROVED" else "rejected"
    st.markdown(
        f'<div class="panel"><div class="decision">{safe(candidate["strategy"].replace("_", " "))}</div><p>{safe(candidate["rationale"])}</p><h3 class="{risk_class}">{safe(risk["status"])}</h3></div>',
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
        width="stretch",
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
        width="stretch",
    )

st.caption(
    "Educational paper-trading experiment. No live mode exists. Historical, demo, and paper results do not imply future performance."
)
