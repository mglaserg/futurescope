from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from futurescope.config import MARKETS
from futurescope.monitor import MonitorArchive, build_monitor_structures
from futurescope.rv_store import CurveSnapshotStore, load_cached_curve_history
from futurescope.services import load_market_curve
from futurescope.spread_market import SpreadCostGate, load_exchange_spread_costs, monitor_quote_timestamp


load_dotenv()
st.set_page_config(page_title="ES + GC Monitor | Futurescope", layout="wide")
st.title("ES + GC Monitor")
st.caption(
    "Current-state instrument only: curve shape, statistical location, and exchange-listed spread liquidity/costs. "
    "No conditional forward returns or win-rate search is performed on this page."
)

c1, c2, c3 = st.columns(3)
with c1:
    symbol = st.selectbox("Market", ["ES", "GC"], index=0)
with c2:
    as_of = st.date_input("As-of date", value=date.today() - timedelta(days=1))
with c3:
    refresh = st.checkbox("Refresh Databento/cache", value=False)

st.subheader("Operational liquidity gate")
g1, g2, g3, g4 = st.columns(4)
with g1:
    max_width_ticks = st.number_input("Max listed-spread width (ticks)", min_value=0.25, value=4.0, step=0.25)
with g2:
    min_depth = st.number_input("Min top-of-book depth", min_value=0.0, value=1.0, step=1.0)
with g3:
    min_volume = st.number_input("Min listed-strategy daily volume", min_value=0.0, value=0.0, step=1.0)
with g4:
    lookback = st.number_input("Current-state z lookback", min_value=3, value=20, step=1)

st.caption(
    "These are operational monitor filters, not a registered research cost hurdle. A research experiment must freeze its own cost/liquidity hurdle before historical outcomes are revealed."
)

config = MARKETS[symbol]
try:
    curve, reference_price, reference_source = load_market_curve(config, as_of, refresh=refresh)
except Exception as exc:
    st.error(f"Curve load failed: {exc}")
    st.stop()
if curve.empty:
    st.warning("No futures curve returned for this date.")
    st.stop()

# Current-state curve history is useful for z-score/percentile location only. Save
# the snapshot before reading history so the current observation is reproducible.
curve_store = CurveSnapshotStore()
curve_store.write(symbol, as_of, curve)
snapshots = load_cached_curve_history(symbol)
if not snapshots.empty:
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
    snapshots = snapshots[snapshots["snapshot_date"].dt.date <= as_of].copy()

spread_cost_error = None
try:
    gate = SpreadCostGate(
        max_width_ticks=float(max_width_ticks),
        min_top_depth=float(min_depth),
        min_daily_volume=float(min_volume),
    )
    spread_costs = load_exchange_spread_costs(
        config,
        curve,
        as_of,
        gate=gate,
        refresh=refresh,
    )
except Exception as exc:
    spread_cost_error = str(exc)
    spread_costs = pd.DataFrame()

structures = build_monitor_structures(
    curve,
    snapshots,
    spread_costs=spread_costs,
    lookback=int(lookback),
    unusual_z=2.0,
)

archive = MonitorArchive()
archive_record = archive.write(
    market=symbol,
    as_of_date=as_of,
    curve=curve,
    structures=structures,
    spread_costs=spread_costs,
    reference_price=reference_price,
    reference_source=reference_source,
    notes=(
        "Monitor-only observation. Cash/futures reference timestamp alignment is not validation-certified. "
        "Spread BBO target is market-specific and DST-aware."
    ),
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Front contract", str(curve.iloc[0]["raw_symbol"]))
m2.metric("Front price", f"{float(curve.iloc[0]['close']):,.4f}")
m3.metric("Reference", "N/A" if reference_price is None else f"{float(reference_price):,.4f}")
m4.metric("Archived", archive_record.as_of_date.isoformat())

quote_target = monitor_quote_timestamp(symbol, as_of)
st.caption(
    f"Listed-strategy BBO target: **{quote_target.isoformat()}**. Reference source: **{reference_source or 'none'}**. "
    "The monitor records these source semantics rather than treating daily cash and futures observations as perfectly synchronized."
)
if symbol == "ES":
    st.warning(
        "ES fair-value/basis validation is still provisional until cash-index, dividend, and futures reference timestamps are explicitly synchronized. Use the current basis as a monitor value, not validated alpha."
    )
else:
    st.warning(
        "GC XAU/USD is a daily reference and is not yet timestamp-certified against the futures settlement. Curve-relative spreads are cleaner than cash/futures basis for current research."
    )

st.subheader("Current futures curve")
curve_cols = [
    c
    for c in [
        "contract_number",
        "raw_symbol",
        "expiration",
        "dte",
        "close",
        "volume",
        "basis_pct",
        "ann_implied_carry",
        "next_spread",
    ]
    if c in curve.columns
]
show_curve = curve[curve_cols].copy()
if "expiration" in show_curve.columns:
    show_curve["expiration"] = pd.to_datetime(show_curve["expiration"]).dt.date
st.dataframe(
    show_curve,
    use_container_width=True,
    hide_index=True,
    column_config={
        "basis_pct": st.column_config.NumberColumn("Spot basis", format="%.2%%"),
        "ann_implied_carry": st.column_config.NumberColumn("Annualized simple carry", format="%.2%%"),
        "dte": st.column_config.NumberColumn("DTE", format="%.1f"),
    },
)

st.subheader("Current curve-relative structures")
if structures.empty:
    st.info("No relative-value structures could be built.")
else:
    display_cols = [
        c
        for c in [
            "current_state",
            "structure",
            "curve_location",
            "leg_symbols",
            "canonical_weights",
            "canonical_value",
            "normalized_value",
            "zscore",
            "percentile",
            "exchange_symbol",
            "bid",
            "ask",
            "width_ticks",
            "top_depth",
            "daily_volume",
            "round_turn_crossing_cost_usd",
            "liquidity_pass",
            "liquidity_reason",
        ]
        if c in structures.columns
    ]
    st.dataframe(
        structures[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "zscore": st.column_config.NumberColumn("Current z-score", format="%.2f"),
            "percentile": st.column_config.NumberColumn("Current percentile", format="%.1%%"),
            "round_turn_crossing_cost_usd": st.column_config.NumberColumn(
                "Est. round-turn crossing cost", format="$%.0f"
            ),
            "liquidity_pass": st.column_config.CheckboxColumn("Liquidity gate"),
            "width_ticks": st.column_config.NumberColumn("Spread width (ticks)", format="%.2f"),
        },
    )

if spread_cost_error:
    st.warning(
        "Exchange-listed spread BBO/volume could not be loaded, so the monitor retained the curve observation but left the cost gate unavailable. "
        f"Provider message: {spread_cost_error}"
    )
else:
    matched = int(spread_costs["matched_exchange_strategy"].sum()) if not spread_costs.empty else 0
    passed = int(spread_costs["liquidity_pass"].sum()) if not spread_costs.empty else 0
    st.caption(f"Matched listed strategies: {matched}. Passed current operational liquidity gate: {passed}.")

st.info(
    "Protocol boundary: this page may show current z-score/percentile and liquidity. Asking what happened historically after a pattern is a research look and should be logged before the result is revealed."
)
