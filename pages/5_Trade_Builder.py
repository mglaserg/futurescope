from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    build_relative_value_history,
    relative_value_trade_signal,
)
from futurescope.config import MARKETS
from futurescope.research_logging import log_dashboard_look
from futurescope.rv_store import CurveSnapshotStore, load_cached_curve_history, load_relative_value_curve
from futurescope.trading import CONTRACT_SPECS, build_trade_ticket

load_dotenv()
st.set_page_config(page_title="Trade Builder | Futurescope", layout="wide")
st.title("Trade Builder")
st.caption("Turn a Futurescope relative-value signal into the exact futures basket, entry value, exit concept, and dollar P&L estimate.")

c1, c2, c3 = st.columns(3)
with c1:
    symbol = st.selectbox("Market", list(MARKETS), index=0)
with c2:
    as_of = st.date_input("As-of date", value=date.today() - timedelta(days=1))
with c3:
    refresh = st.checkbox("Refresh cached market data", value=False)

config = MARKETS[symbol]
try:
    curve = load_relative_value_curve(config, as_of, refresh=refresh)
except Exception as exc:
    st.error(str(exc))
    st.stop()
if curve.empty:
    st.warning("No curve data returned for this date.")
    st.stop()

snapshots = load_cached_curve_history(symbol)
if not snapshots.empty:
    snapshots = snapshots[pd.to_datetime(snapshots["snapshot_date"]).dt.date <= as_of].copy()

labels = {
    1: "2-leg · Curve slope / calendar spread",
    2: "3-leg · Butterfly / curvature",
    3: "4-leg · Double butterfly / change in curvature",
}

s1, s2 = st.columns(2)
with s1:
    order = st.selectbox("Structure", [1, 2, 3], format_func=lambda x: labels[x])
max_position = max(1, len(curve) - order)
with s2:
    position = st.selectbox(
        "Curve location",
        list(range(1, max_position + 1)),
        format_func=lambda pos: "-".join(f"F{i}" for i in range(pos, pos + order + 1)),
    )

history = build_relative_value_history(
    snapshots,
    order=order,
    position=position,
    value_column="time_normalized_value",
) if not snapshots.empty else pd.DataFrame()

st.subheader("Signal settings")
a1, a2, a3, a4 = st.columns(4)
with a1:
    lookback = st.number_input("Z-score lookback", min_value=3, value=20, step=1)
with a2:
    entry_z = st.number_input("Extreme |z|", min_value=0.25, value=2.0, step=0.25)
with a3:
    horizon = st.number_input("Forward horizon", min_value=1, value=5, step=1)
with a4:
    min_analogs = st.number_input("Minimum analogues", min_value=1, value=5, step=1)

if history.empty:
    signal_result = {
        "signal": "INSUFFICIENT HISTORY",
        "reason": "Build local curve history on the Relative Value page to enable an empirical signal.",
        "current_zscore": np.nan,
        "analogs": 0,
        "win_rate": np.nan,
        "mean_forward_change": np.nan,
        "behavior": "unknown",
    }
else:
    trade_builder_look_id = log_dashboard_look(
        "trade_builder_signal",
        {
            "market": symbol,
            "as_of": as_of.isoformat(),
            "order": int(order),
            "position": int(position),
            "lookback": int(lookback),
            "entry_z": float(entry_z),
            "horizon": int(horizon),
            "min_analogs": int(min_analogs),
        },
        "Trade Builder requested historical directional signal / expected move",
    )
    signal_result = relative_value_trade_signal(
        history,
        lookback=int(lookback),
        entry_z=float(entry_z),
        horizon=int(horizon),
        min_analogs=int(min_analogs),
        min_win_rate=0.55,
    )

if not history.empty and trade_builder_look_id is not None:
    st.caption(f"Historical Trade Builder query logged as research look #{trade_builder_look_id}.")
elif not history.empty:
    st.warning("Research registry logging failed for the Trade Builder historical query.")

q1, q2, q3, q4 = st.columns(4)
q1.metric("Futurescope signal", str(signal_result["signal"]))
q2.metric("Signal z-score", "N/A" if pd.isna(signal_result["current_zscore"]) else f"{signal_result['current_zscore']:.2f}")
q3.metric("Historical analogues", int(signal_result["analogs"]))
q4.metric("Win rate", "N/A" if pd.isna(signal_result["win_rate"]) else f"{signal_result['win_rate']:.1%}")
st.caption(str(signal_result["reason"]))

mode = st.radio(
    "Trade direction",
    ["Use Futurescope signal", "Manual LONG", "Manual SHORT"],
    horizontal=True,
    help="LONG/SHORT refers to the whole slope/fly/double-fly basket, not the front month by itself.",
)
if mode == "Use Futurescope signal":
    selected_signal = str(signal_result["signal"])
elif mode == "Manual LONG":
    selected_signal = "LONG"
else:
    selected_signal = "SHORT"

if selected_signal not in {"LONG", "SHORT"}:
    st.info("There is no executable directional basket from the current research rule. Choose Manual LONG/SHORT only if you want to inspect the basket for planning or demo trading.")
    st.stop()

cost = st.number_input(
    "Estimated round-turn cost per contract ($)",
    min_value=0.0,
    value=0.0,
    step=1.0,
    help="Optional rough commission + bid/ask/slippage assumption for one contract-equivalent over entry and exit.",
)
expected_move = signal_result["mean_forward_change"] if mode == "Use Futurescope signal" else np.nan
if pd.isna(expected_move):
    expected_move = None

ticket = build_trade_ticket(
    curve,
    market=symbol,
    order=order,
    position=position,
    signal=selected_signal,
    expected_canonical_move=expected_move,
    round_turn_cost_per_contract=float(cost),
)

st.divider()
st.subheader(f"{ticket['signal']} {ticket['structure']} · {ticket['tenor_label']}")
st.success(
    f"Trade the basket as {ticket['execution_ratio']}. This direction applies to the entire RV structure, not to the first contract alone."
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Canonical entry value", f"{ticket['canonical_entry_value']:.4f}")
m2.metric("Normalized measure", f"{ticket['time_normalized_value']:.6f}")
m3.metric("$ / point / contract", f"${ticket['point_value_usd']:,.0f}")
m4.metric("Contract equivalents", f"{ticket['total_contract_equivalents']:.2f}")

legs = ticket["legs"].copy()
legs["expiration"] = pd.to_datetime(legs["expiration"]).dt.date
st.dataframe(
    legs,
    use_container_width=True,
    hide_index=True,
    column_config={
        "side": st.column_config.TextColumn("Side"),
        "raw_symbol": st.column_config.TextColumn("Contract"),
        "expiration": st.column_config.DateColumn("Expiry"),
        "contracts": st.column_config.NumberColumn("Contracts", format="%.4f"),
        "signed_weight": st.column_config.NumberColumn("Signed weight", format="%+.4f"),
        "entry_price": st.column_config.NumberColumn("Entry price", format="%.4f"),
        "usd_per_point_per_contract": st.column_config.NumberColumn("$ / point", format="$%.0f"),
    },
)
st.caption(str(ticket["source_note"]))

st.subheader("Historical exit / P&L concept")
if np.isfinite(float(ticket["expected_gross_pnl_usd"])):
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Historical mean move", f"{ticket['expected_canonical_move']:+.4f} points")
    p2.metric("Mean-move target", f"{ticket['expected_target_canonical_value']:.4f}")
    p3.metric("Estimated gross P&L", f"${ticket['expected_gross_pnl_usd']:,.0f}")
    p4.metric("After entered cost assumption", f"${ticket['expected_net_pnl_usd']:,.0f}")
    st.write(
        f"Research exit concept: hold for up to **{int(horizon)} cached observations**, or exit earlier when the z-score normalizes back inside the chosen neutral zone. "
        "The mean-move target is a historical conditional-expectancy reference, not a guaranteed price target."
    )
else:
    st.info("No historical expected-move estimate is attached to this manual/demo basket. The exact legs and entry value are still valid, but Futurescope is not assigning an expected dollar P&L.")

st.warning("Trade Builder is a research/execution-planning aid. Margin, exchange/broker fees, live bid/ask, liquidity, market-specific fair value, and DV01 weighting for Treasury structures are not yet production-integrated.")
