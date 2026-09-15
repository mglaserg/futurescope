from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from futurescope.analytics.relative_value import relative_value_zscore_history
from futurescope.config import MARKETS, ZB_EXECUTION_CONFIG
from futurescope.conductor import constant_maturity_spread_intent, intent_json
from futurescope.rv_store import CurveSnapshotStore, load_relative_value_curve
from futurescope.synthetic import build_constant_maturity_curve, synthetic_slope, synthetic_slope_history
from futurescope.ui import apply_futurescope_theme, hero

load_dotenv()
st.set_page_config(page_title="Synthetic Tenors | Futurescope", page_icon="📐", layout="wide")
apply_futurescope_theme()

hero(
    "CONSTANT-MATURITY CURVE · ROLL-CLEAN MEASUREMENT",
    "Synthetic Tenors",
    "Hold maturity constant instead of chasing F1/F2 through the roll. Futurescope interpolates listed contracts into fixed-DTE points such as 50d and 80d, then translates the synthetic slope back into the actual listed contracts Conductor can execute.",
    ["50d / 80d", "No extrapolation", "Listed-contract replication", "Conductor-ready"],
)

with st.sidebar:
    st.header("Synthetic curve")
    market_options = list(MARKETS) + ["ZB"]
    market = st.selectbox("Market", market_options, index=market_options.index("VX") if "VX" in market_options else 0)
    as_of = st.date_input("As-of close", value=date.today() - timedelta(days=1))
    near_dte = float(st.number_input("Near synthetic DTE", min_value=10, max_value=365, value=50, step=5))
    far_dte = float(st.number_input("Far synthetic DTE", min_value=15, max_value=540, value=80, step=5))
    lookback = int(st.number_input("Z-score lookback", min_value=5, max_value=252, value=40, step=5))
    refresh = st.checkbox("Refresh Databento", value=False)

if near_dte >= far_dte:
    st.error("The near synthetic tenor must be shorter than the far tenor.")
    st.stop()

config = ZB_EXECUTION_CONFIG if market == "ZB" else MARKETS[market]
store = CurveSnapshotStore()
try:
    curve = load_relative_value_curve(config, as_of, refresh=refresh, store=store)
    result = synthetic_slope(curve, near_dte, far_dte)
except Exception as exc:
    st.error(f"Could not build the synthetic curve: {exc}")
    st.stop()

near = result["near"]
far = result["far"]
spread = float(result["spread"])
ann_carry = float(result["annualized_log_carry"])
state = "Backwardation" if spread > 0 else "Contango" if spread < 0 else "Flat"

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"{near_dte:g}d synthetic", f"{near.price:,.3f}")
m2.metric(f"{far_dte:g}d synthetic", f"{far.price:,.3f}")
m3.metric(f"{near_dte:g}d − {far_dte:g}d", f"{spread:+,.3f}", state)
m4.metric("Annualized log slope", f"{ann_carry:+.2%}")

st.markdown(
    f'<div class="fs-note"><strong>How to read this:</strong> Futurescope defines the synthetic slope as <strong>{near_dte:g}d price − {far_dte:g}d price</strong>. Positive is backwardation; negative is contango. Unlike F1/F2, those maturity targets do not change meaning when the listed contracts roll.</div>',
    unsafe_allow_html=True,
)

left, right = st.columns([1.55, 1])
with left:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve["dte"],
            y=curve["close"],
            mode="lines+markers",
            name="Listed curve",
            customdata=curve["raw_symbol"],
            hovertemplate="%{customdata}<br>DTE %{x:.1f}<br>Price %{y:.4f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[near.target_dte, far.target_dte],
            y=[near.price, far.price],
            mode="markers+text",
            text=[f"{near_dte:g}d", f"{far_dte:g}d"],
            textposition="top center",
            marker=dict(size=14, symbol="diamond"),
            name="Synthetic targets",
            hovertemplate="Target %{x:.0f}d<br>Synthetic %{y:.4f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"{market} listed curve + constant-maturity points",
        xaxis_title="Days to expiration",
        yaxis_title="Futures price",
        height=450,
        margin=dict(l=10, r=10, t=55, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.markdown("### How Futurescope builds it")
    synth_table = build_constant_maturity_curve(curve, [near_dte, far_dte])
    st.dataframe(
        synth_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "target_dte": st.column_config.NumberColumn("Target", format="%.0f d"),
            "synthetic_price": st.column_config.NumberColumn("Synthetic price", format="%.4f"),
            "replication": "Listed-contract replication",
            "leg_symbols": "Contracts",
        },
    )
    st.caption("Interpolation is linear in quoted futures price over calendar DTE. Futurescope refuses to extrapolate outside the listed curve.")

st.subheader("Trade translation")
direction = st.segmented_control(
    "Synthetic slope direction",
    options=["LONG", "SHORT"],
    default="LONG",
    help=f"LONG means +{near_dte:g}d synthetic / −{far_dte:g}d synthetic. SHORT is the reverse.",
)
weights = result["long_weights"] if direction == "LONG" else result["short_weights"]
weight_rows = []
price_map = curve.set_index("raw_symbol")["close"].to_dict()
expiry_map = curve.set_index("raw_symbol")["expiration"].to_dict()
for symbol, weight in weights.items():
    weight_rows.append(
        {
            "side": "BUY" if weight > 0 else "SELL",
            "contract": symbol,
            "ratio": abs(float(weight)),
            "signed_weight": float(weight),
            "price": float(price_map.get(symbol, np.nan)),
            "expiration": pd.Timestamp(expiry_map[symbol]).date() if symbol in expiry_map else None,
        }
    )
weight_frame = pd.DataFrame(weight_rows)
st.dataframe(
    weight_frame[["side", "contract", "ratio", "expiration", "price"]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "ratio": st.column_config.NumberColumn("Synthetic ratio", format="%.4f"),
        "price": st.column_config.NumberColumn("Current price", format="%.4f"),
    },
)
st.caption("These are exposure ratios, not final integer contract counts. Conductor owns integerization, portfolio sizing, risk, and execution.")

intent = constant_maturity_spread_intent(
    market=market,
    as_of=as_of,
    near_dte=near_dte,
    far_dte=far_dte,
    direction=str(direction),
    listed_weights=weights,
)
with st.expander("Conductor trade intent"):
    st.code(intent_json(intent), language="json")
    st.download_button(
        "Download Conductor intent",
        data=intent_json(intent),
        file_name=f"futurescope_{market.lower()}_{near_dte:g}d_{far_dte:g}d_{str(direction).lower()}.json",
        mime="application/json",
        use_container_width=True,
    )

st.subheader("Current richness vs your local history")
snapshots = store.read_all(market)
history = synthetic_slope_history(snapshots, near_dte, far_dte)
if len(history) >= 3:
    zhist = relative_value_zscore_history(history[["snapshot_date", "value"]], lookback=lookback)
    current_z = zhist["signal_zscore"].iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Cached observations", len(history))
    c2.metric("Current z-score", "—" if pd.isna(current_z) else f"{float(current_z):+.2f}")
    percentile = float((history["value"] <= history["value"].iloc[-1]).mean())
    c3.metric("Current percentile", f"{percentile:.1%}")

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Scatter(x=history["snapshot_date"], y=history["value"], mode="lines", name="Synthetic slope"))
    fig_hist.update_layout(
        title=f"{near_dte:g}d − {far_dte:g}d synthetic slope history",
        yaxis_title="Price spread",
        height=330,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    fig_z = go.Figure()
    fig_z.add_trace(go.Scatter(x=zhist["snapshot_date"], y=zhist["signal_zscore"], mode="lines", name="Lagged z-score"))
    for level in (-2, 0, 2):
        fig_z.add_hline(y=level, line_dash="dot", opacity=0.55)
    fig_z.update_layout(
        title="Lagged rolling z-score",
        yaxis_title="Z-score",
        height=300,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig_z, use_container_width=True)
    st.caption("This is descriptive current-state context only. Asking whether extreme synthetic slopes subsequently make money is a registered research question under the Futurescope audit workflow.")
else:
    st.info("Futurescope needs at least a few cached curve snapshots to show a synthetic-tenor history. Each time you load this page, the current curve snapshot is added to the local archive.")

if market == "ZB":
    st.warning("ZB synthetic tenors are experimental until the Treasury layer includes CTD, conversion factors, implied repo, and DV01-aware economics.")
