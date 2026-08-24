from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from futurescope.analytics import curve_state
from futurescope.config import MARKETS
from futurescope.providers import CboeIndexProvider
from futurescope.services import load_market_curve

load_dotenv()
st.set_page_config(page_title="VIX Complex | Futurescope", layout="wide")
st.title("VIX Complex")
st.caption("VX futures from Databento plus official Cboe daily volatility-index histories.")

c1, c2 = st.columns(2)
with c1:
    as_of = st.date_input("As-of date", value=date.today() - timedelta(days=1))
with c2:
    refresh = st.checkbox("Refresh cached VX futures data", value=False)

try:
    vx, vix_spot, _ = load_market_curve(MARKETS["VX"], as_of, refresh=refresh)
except Exception as exc:
    st.error(f"VX load failed: {exc}")
    st.stop()

indices = CboeIndexProvider().latest_snapshot(["VIX9D", "VIX", "VIX3M", "VIX6M", "VIX1Y", "VVIX", "OVX", "GVZ"])

if not vx.empty:
    front = vx.iloc[0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("VIX", f"{vix_spot:.2f}" if vix_spot is not None else "N/A")
    m2.metric("VX1", f"{front['close']:.2f}")
    m3.metric("VX curve", curve_state(vx))
    if vix_spot:
        premium = float(front["close"]) / vix_spot - 1.0
        m4.metric("VX1 / VIX premium", f"{premium * 100:.1f}%")
    else:
        m4.metric("VX1 / VIX premium", "N/A")

    fig = go.Figure()
    if vix_spot is not None:
        fig.add_trace(go.Scatter(x=[pd.Timestamp(as_of)], y=[vix_spot], mode="markers", name="VIX spot"))
    fig.add_trace(go.Scatter(x=vx["expiration"], y=vx["close"], mode="lines+markers", name="VX futures", text=vx["raw_symbol"]))
    fig.update_layout(title="VIX spot and VX futures term structure", xaxis_title="Date / expiration", yaxis_title="Volatility points")
    st.plotly_chart(fig, use_container_width=True)

    table = vx[["raw_symbol", "expiration", "dte", "close", "basis_pct", "next_spread", "next_spread_pct"]].copy()
    table["basis_pct"] *= 100
    table["next_spread_pct"] *= 100
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "basis_pct": st.column_config.NumberColumn("Vs VIX %", format="%.2f%%"),
            "next_spread_pct": st.column_config.NumberColumn("Next spread %", format="%.2f%%"),
        },
    )

st.subheader("Cboe volatility indices")
st.dataframe(indices, use_container_width=True, hide_index=True)
st.caption("VIX9D/VIX/VIX3M/VIX6M/VIX1Y are option-implied volatility horizons; VVIX is volatility-of-VIX. OVX and GVZ extend the volatility view to oil and gold ETFs.")
