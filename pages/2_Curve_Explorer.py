from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from futurescope.analytics import curve_state, excess_carry, fair_carry_rate
from futurescope.config import MARKETS
from futurescope.services import load_market_curve

load_dotenv()
st.set_page_config(page_title="Curve Explorer | Futurescope", layout="wide")
st.title("Curve Explorer")

c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    symbol = st.selectbox("Market", list(MARKETS), index=0)
with c2:
    as_of = st.date_input("As-of date", value=date.today() - timedelta(days=1))
with c3:
    refresh = st.checkbox("Refresh cached market data", value=False)

config = MARKETS[symbol]

try:
    curve, spot, spot_source = load_market_curve(config, as_of, refresh=refresh)
except Exception as exc:
    st.error(str(exc))
    st.stop()

if curve.empty:
    st.warning("No curve data returned for this date.")
    st.stop()

front = curve.iloc[0]
state = curve_state(curve)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Curve state", state)
m2.metric("Front", f"{front['close']:.3f}")
m3.metric("Front DTE", f"{front['dte']:.0f}")
if spot is not None:
    m4.metric("Reference", f"{spot:.3f}")
else:
    m4.metric("Reference", "N/A")

plot_frame = curve.copy()
plot_frame["expiry_label"] = plot_frame["expiration"].dt.strftime("%Y-%m-%d")
fig = px.line(plot_frame, x="expiration", y="close", markers=True, hover_name="raw_symbol", title=f"{symbol} futures curve")
fig.update_layout(xaxis_title="Expiration", yaxis_title=config.units)
st.plotly_chart(fig, use_container_width=True)

if spot is not None:
    st.caption(f"Spot/reference source: {spot_source}")
    st.subheader("Spot basis / cash-and-carry screen")
    a, b, c = st.columns(3)
    with a:
        financing_pct = st.number_input("Financing rate (%)", value=4.0, step=0.25)
    with b:
        storage_pct = st.number_input("Storage / carry cost (%)", value=0.0, step=0.10)
    with c:
        income_pct = st.number_input("Income / convenience yield (%)", value=0.0, step=0.10)

    fair = fair_carry_rate(financing_pct / 100, storage_pct / 100, income_pct / 100)
    display = curve[["raw_symbol", "expiration", "dte", "close", "basis_pct", "ann_implied_carry"]].copy()
    display["fair_carry"] = fair
    display["excess_carry"] = display["ann_implied_carry"].apply(
        lambda x: excess_carry(x, financing_pct / 100, storage_pct / 100, income_pct / 100)
    )
    for col in ["basis_pct", "ann_implied_carry", "fair_carry", "excess_carry"]:
        display[col] *= 100
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "basis_pct": st.column_config.NumberColumn("Basis %", format="%.2f%%"),
            "ann_implied_carry": st.column_config.NumberColumn("Ann. implied carry", format="%.2f%%"),
            "fair_carry": st.column_config.NumberColumn("Fair carry", format="%.2f%%"),
            "excess_carry": st.column_config.NumberColumn("Excess carry", format="%.2f%%"),
        },
    )
else:
    st.info("No spot/reference is configured for this market in V1, so the page shows calendar-curve carry rather than cash-and-carry basis.")

st.subheader("Calendar curve")
calendar_cols = ["raw_symbol", "expiration", "dte", "close", "vs_front_pct", "ann_calendar_carry_vs_front", "next_spread", "next_spread_pct"]
calendar = curve[calendar_cols].copy()
for col in ["vs_front_pct", "ann_calendar_carry_vs_front", "next_spread_pct"]:
    calendar[col] *= 100
st.dataframe(
    calendar,
    use_container_width=True,
    hide_index=True,
    column_config={
        "vs_front_pct": st.column_config.NumberColumn("Vs front %", format="%.2f%%"),
        "ann_calendar_carry_vs_front": st.column_config.NumberColumn("Ann. curve carry vs front", format="%.2f%%"),
        "next_spread_pct": st.column_config.NumberColumn("Next spread %", format="%.2f%%"),
    },
)
