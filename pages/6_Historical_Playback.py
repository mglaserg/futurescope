from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    build_relative_value_history,
    build_relative_value_structures,
    relative_value_trade_signal,
    relative_value_zscore_history,
)
from futurescope.config import MARKETS
from futurescope.rv_store import CurveSnapshotStore, load_cached_curve_history

load_dotenv()
st.set_page_config(page_title="Historical Curve Playback | Futurescope", layout="wide")
st.title("Historical Curve Playback")
st.caption("Scrub cached futures curves through time and inspect the exact slope, butterfly, double-butterfly, z-score, and signal that existed on each snapshot.")

symbol = st.selectbox("Market", list(MARKETS), index=0)
config = MARKETS[symbol]
store = CurveSnapshotStore()
cached_dates = store.dates(symbol)
if not cached_dates:
    st.info("No cached curve snapshots yet. Open Relative Value and build/extend local history first.")
    st.stop()

playback_date = st.select_slider(
    "Playback date",
    options=cached_dates,
    value=cached_dates[-1],
    format_func=lambda x: x.isoformat(),
)
current = store.read(symbol, playback_date)
if current is None or current.empty:
    st.warning("Selected snapshot could not be loaded.")
    st.stop()

compare_previous = st.checkbox("Overlay previous cached curve", value=True)
previous = None
previous_date = None
idx = cached_dates.index(playback_date)
if compare_previous and idx > 0:
    previous_date = cached_dates[idx - 1]
    previous = store.read(symbol, previous_date)

fig = go.Figure()
if previous is not None and not previous.empty:
    fig.add_trace(
        go.Scatter(
            x=previous["expiration"],
            y=previous["close"],
            mode="lines+markers",
            name=f"Previous · {previous_date}",
            text=previous["raw_symbol"],
        )
    )
fig.add_trace(
    go.Scatter(
        x=current["expiration"],
        y=current["close"],
        mode="lines+markers",
        name=f"Selected · {playback_date}",
        text=current["raw_symbol"],
    )
)
fig.update_layout(title=f"{symbol} historical curve playback", xaxis_title="Expiration", yaxis_title=config.units)
st.plotly_chart(fig, use_container_width=True)

labels = {
    1: "2-leg · Curve slope / calendar spread",
    2: "3-leg · Butterfly / curvature",
    3: "4-leg · Double butterfly / change in curvature",
}
c1, c2 = st.columns(2)
with c1:
    order = st.selectbox("Structure", [1, 2, 3], format_func=lambda x: labels[x])
max_position = max(1, len(current) - order)
with c2:
    position = st.selectbox(
        "Curve location",
        list(range(1, max_position + 1)),
        format_func=lambda pos: "-".join(f"F{i}" for i in range(pos, pos + order + 1)),
    )

structures = build_relative_value_structures(current, order=order)
selected = structures[structures["position"] == position]
if selected.empty:
    st.info("Selected snapshot does not have enough live contracts for this structure.")
    st.stop()
row = selected.iloc[0]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Contracts", str(row["leg_symbols"]))
k2.metric("Canonical value", f"{row['canonical_value']:.4f}")
k3.metric(f"Order-{order} normalized", f"{row['time_normalized_value']:.6f}")
k4.metric("Canonical LONG ratio", str(row["canonical_weights"]))

snapshots = load_cached_curve_history(symbol)
snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
cutoff = snapshots[snapshots["snapshot_date"].dt.date <= playback_date].copy()
history = build_relative_value_history(cutoff, order=order, position=position, value_column="time_normalized_value")

st.subheader("Signal as it existed on this date")
s1, s2, s3, s4 = st.columns(4)
with s1:
    lookback = st.number_input("Z-score lookback", min_value=3, value=20, step=1)
with s2:
    entry_z = st.number_input("Extreme |z|", min_value=0.25, value=2.0, step=0.25)
with s3:
    horizon = st.number_input("Forward horizon", min_value=1, value=5, step=1)
with s4:
    min_analogs = st.number_input("Minimum analogues", min_value=1, value=5, step=1)

signal = relative_value_trade_signal(
    history,
    lookback=int(lookback),
    entry_z=float(entry_z),
    horizon=int(horizon),
    min_analogs=int(min_analogs),
    min_win_rate=0.55,
)
q1, q2, q3, q4 = st.columns(4)
q1.metric("Signal", str(signal["signal"]))
q2.metric("Lagged z-score", "N/A" if pd.isna(signal["current_zscore"]) else f"{signal['current_zscore']:.2f}")
q3.metric("Historical analogues", int(signal["analogs"]))
q4.metric("Win rate", "N/A" if pd.isna(signal["win_rate"]) else f"{signal['win_rate']:.1%}")
st.caption(str(signal["reason"]))

measure_fig = go.Figure()
measure_fig.add_trace(go.Scatter(x=history["snapshot_date"], y=history["value"], mode="lines+markers", name="Normalized measure"))
measure_fig.add_vline(x=pd.Timestamp(playback_date).timestamp() * 1000, line_dash="dash")
measure_fig.update_layout(title=f"{STRUCTURE_NAMES[order]} history through {playback_date}", xaxis_title="Snapshot date", yaxis_title=f"Order-{order} normalized measure")
st.plotly_chart(measure_fig, use_container_width=True)

z_history = relative_value_zscore_history(history, lookback=int(lookback))
z_fig = go.Figure()
z_fig.add_trace(go.Scatter(x=z_history["snapshot_date"], y=z_history["signal_zscore"], mode="lines+markers", name="Signal z-score"))
z_fig.add_hline(y=0.0, line_dash="dot")
z_fig.add_hline(y=float(entry_z), line_dash="dash", annotation_text=f"+{float(entry_z):.2f}")
z_fig.add_hline(y=-float(entry_z), line_dash="dash", annotation_text=f"-{float(entry_z):.2f}")
z_fig.add_vline(x=pd.Timestamp(playback_date).timestamp() * 1000, line_dash="dash")
z_fig.update_layout(title="Lagged rolling z-score at playback date", xaxis_title="Snapshot date", yaxis_title="Z-score")
st.plotly_chart(z_fig, use_container_width=True)

with st.expander("Reveal what happened next"):
    st.caption("This section intentionally uses future cached snapshots for retrospective study. It is not used in the signal shown above.")
    full_history = build_relative_value_history(snapshots, order=order, position=position, value_column="time_normalized_value")
    full_history["snapshot_date"] = pd.to_datetime(full_history["snapshot_date"])
    matches = full_history.index[full_history["snapshot_date"].dt.date == playback_date].tolist()
    if not matches:
        st.info("No matching RV history row for this date.")
    else:
        i = matches[-1]
        j = i + int(horizon)
        if j >= len(full_history):
            st.info("Not enough later cached observations to reveal the selected forward horizon.")
        else:
            window = full_history.loc[i:j, "leg_symbols"]
            if window.nunique(dropna=False) != 1:
                st.info("The selected forward window crosses a contract-roll boundary, so Futurescope does not treat it as clean executable RV P&L.")
            else:
                move = float(full_history.loc[j, "canonical_value"] - full_history.loc[i, "canonical_value"])
                st.metric(f"Actual {int(horizon)}-observation canonical move", f"{move:+.4f}")
                st.write(f"Basket remained **{full_history.loc[i, 'leg_symbols']}** through the measured forward window.")
