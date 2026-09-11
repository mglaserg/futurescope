from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from futurescope.config import MARKETS, ZB_EXECUTION_CONFIG
from futurescope.conductor import cross_market_carry_intent, intent_json
from futurescope.curve_carry import build_cross_market_carry_table, select_cross_market_carry
from futurescope.services import load_market_curve
from futurescope.ui import apply_futurescope_theme, hero

load_dotenv()
st.set_page_config(page_title="Cross-Market Curve Carry | Futurescope", page_icon="↕", layout="wide")
apply_futurescope_theme()

hero(
    "RESEARCH CANDIDATE · FUTURES CARRY FACTOR",
    "Cross-Market Curve Carry",
    "The DirtyCarry idea for dated futures: rank markets by the current F1/F2 curve, own the most backwardated, short the most contangoed, and hand the resulting intent to Conductor. Current state only — no hidden historical edge claim.",
    ["Backwardation long", "Contango short", "Conductor-ready", "Current state only"],
)

with st.sidebar:
    st.header("Carry cross-section")
    as_of = st.date_input("As-of close", value=date.today() - timedelta(days=1))
    default_markets = [m for m in ["GC", "CL", "ES", "ZN", "VX"] if m in MARKETS]
    selected_markets = st.multiselect("Markets", default_markets + ["ZB"], default=default_markets)
    include_zb = "ZB" in selected_markets
    expression_label = st.radio(
        "Expression",
        ["Calendar spread · cleaner curve RV", "Outright front · classic carry factor"],
        index=0,
    )
    expression = "calendar_spread" if expression_label.startswith("Calendar") else "outright_front"
    long_count = st.number_input("Long top N", min_value=0, max_value=5, value=1, step=1)
    short_count = st.number_input("Short bottom N", min_value=0, max_value=5, value=1, step=1)
    require_sign = st.checkbox("Require actual backwardation / contango", value=True)
    refresh = st.checkbox("Refresh Databento", value=False)

configs = {k: v for k, v in MARKETS.items() if k in selected_markets}
if include_zb:
    configs["ZB"] = ZB_EXECUTION_CONFIG

curves: dict[str, pd.DataFrame] = {}
errors: dict[str, str] = {}
with st.spinner("Loading current futures curves…"):
    for market, config in configs.items():
        try:
            curve, _, _ = load_market_curve(config, as_of, refresh=refresh)
            if not curve.empty:
                curves[market] = curve
        except Exception as exc:
            errors[market] = str(exc)

carry = build_cross_market_carry_table(curves)
if carry.empty:
    st.error("No two-contract curves were available for the selected markets.")
    if errors:
        st.json(errors)
    st.stop()

selected = select_cross_market_carry(
    carry,
    long_count=int(long_count),
    short_count=int(short_count),
    require_sign=require_sign,
)

best = carry.iloc[0]
worst = carry.iloc[-1]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Most backwardated", str(best["market"]), f"{best['carry_pct']:+.1f}% ann. curve slope")
m2.metric("Most contangoed", str(worst["market"]), f"{worst['carry_pct']:+.1f}% ann. curve slope")
m3.metric("Markets loaded", len(carry))
m4.metric("Selected intents", len(selected))

left, right = st.columns([1.4, 1])
with left:
    fig = go.Figure()
    colors = ["#047857" if x > 0 else "#b91c1c" if x < 0 else "#64748b" for x in carry["carry_pct"]]
    fig.add_trace(
        go.Bar(
            x=carry["market"],
            y=carry["carry_pct"],
            marker_color=colors,
            text=[f"{x:+.1f}%" for x in carry["carry_pct"]],
            textposition="outside",
            hovertemplate="%{x}<br>Annualized F1/F2 curve carry: %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dot")
    fig.update_layout(
        title="Current front-calendar carry cross-section",
        xaxis_title="Market",
        yaxis_title="Annualized log curve carry (%)",
        height=430,
        margin=dict(l=10, r=10, t=60, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.markdown(
        """
        <div class="fs-card">
          <div class="fs-kicker">SIGN CONVENTION</div>
          <h4 style="font-size:1.25rem;margin-top:7px;">Positive = backwardation</h4>
          <p>Futurescope measures <strong>log(F1/F2)</strong> and annualizes it over the actual expiry gap. Positive means the front is above the second contract; negative means contango.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown(
        """
        <div class="fs-card">
          <div class="fs-kicker">IMPORTANT</div>
          <h4 style="margin-top:7px;">Common object, different mechanisms.</h4>
          <p>GC, CL, ES, Treasuries, and VX can all be ranked by curve shape, but the economics underneath differ. This page is a current-state research candidate, not proof that raw carry is directly comparable or profitable across every market.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.subheader("Carry board")
display = carry[[
    "rank", "market", "state", "carry_pct", "cross_section_z", "front_symbol", "second_symbol", "gap_days", "mechanism"
]].copy()
st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "rank": st.column_config.NumberColumn("Rank", format="%d"),
        "market": "Market",
        "state": "Curve state",
        "carry_pct": st.column_config.NumberColumn("Ann. curve carry", format="%+.2f%%"),
        "cross_section_z": st.column_config.NumberColumn("Cross-sec z", format="%+.2f"),
        "front_symbol": "Front",
        "second_symbol": "Second",
        "gap_days": st.column_config.NumberColumn("Expiry gap", format="%.0f d"),
        "mechanism": "Economic mechanism",
    },
)

st.subheader("Proposed portfolio intent")
if selected.empty:
    st.info("No markets satisfy the selected long/short sign requirements. Futurescope emits no carry trade intent.")
else:
    cards: list[str] = []
    for row in selected.itertuples(index=False):
        is_long = row.direction == "LONG"
        basket = (
            f"+1 {row.front_symbol} / -1 {row.second_symbol}"
            if is_long else f"-1 {row.front_symbol} / +1 {row.second_symbol}"
        )
        if expression == "outright_front":
            basket = f"{'BUY' if is_long else 'SELL'} {row.front_symbol}"
        cards.append(
            f'''<div class="fs-leg {'fs-buy' if is_long else 'fs-sell'}"><div class="side">{row.direction}</div><div class="symbol">{row.market}</div><div class="meta">{basket}<br>{row.carry_pct:+.2f}% annualized curve carry</div></div>'''
        )
    st.markdown(f'<div class="fs-ticket">{"".join(cards)}</div>', unsafe_allow_html=True)
    st.caption("Futurescope selects the relative ordering. Conductor owns portfolio sizing, margin, concentration limits, contract roll handling, and execution permission.")

    intent = cross_market_carry_intent(selected.to_dict("records"), as_of=as_of, expression=expression)
    with st.expander("Conductor trade intent"):
        st.code(intent_json(intent), language="json")
        st.download_button(
            "Download Conductor intent",
            data=intent_json(intent),
            file_name=f"futurescope_curve_carry_{as_of.isoformat()}.json",
            mime="application/json",
            use_container_width=True,
        )

if include_zb:
    st.warning("ZB is included here as an experimental curve object only. Production Treasury carry/RV still needs CTD, conversion-factor, implied-repo, and DV01 treatment before Futurescope should call ZB carry economically validated.")
if errors:
    with st.expander("Markets that could not load"):
        st.json(errors)

st.markdown(
    """
    <div class="fs-note"><strong>Research boundary.</strong> This is the current cross-section only. The profitable claim — whether high backwardation outperforms deep contango, and whether outright or calendar-spread expression is better — must be registered and tested inside the Futurescope/EdgeLab workflow before promotion to LIVE_APPROVED.</div>
    """,
    unsafe_allow_html=True,
)
