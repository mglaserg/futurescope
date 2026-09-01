from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from futurescope.config import MARKETS
from futurescope.opportunities import scan_market_opportunities
from futurescope.rv_store import load_cached_curve_history, load_relative_value_curve

load_dotenv()
st.set_page_config(page_title="Daily Opportunities | Futurescope", layout="wide")
st.title("Daily Opportunity Dashboard")
st.caption("Rank slope, butterfly, and double-butterfly relative-value structures across Futurescope markets using current extremeness plus historical directional evidence.")

c1, c2 = st.columns(2)
with c1:
    as_of = st.date_input("As-of date", value=date.today() - timedelta(days=1))
with c2:
    refresh = st.checkbox("Refresh cached market data", value=False)

st.subheader("Research signal settings")
s1, s2, s3, s4 = st.columns(4)
with s1:
    lookback = st.number_input("Z-score lookback", min_value=3, value=20, step=1)
with s2:
    entry_z = st.number_input("Extreme |z|", min_value=0.25, value=2.0, step=0.25)
with s3:
    horizon = st.number_input("Forward horizon", min_value=1, value=5, step=1)
with s4:
    min_analogs = st.number_input("Minimum analogues", min_value=1, value=5, step=1)

st.caption(
    "Research score is deliberately transparent and not transaction-cost-adjusted: 40% extremeness (saturates at |z|=3), 40% directional win-rate evidence above 50%, and 20% historical sample support (saturates at 20 analogues)."
)

if st.button("Scan Futurescope markets", type="primary"):
    all_rows: list[pd.DataFrame] = []
    errors: list[str] = []
    progress = st.progress(0.0)
    status = st.empty()
    items = list(MARKETS.items())
    for i, (symbol, config) in enumerate(items, start=1):
        status.write(f"Scanning {symbol} ({i}/{len(items)})")
        try:
            curve = load_relative_value_curve(config, as_of, refresh=refresh)
            snapshots = load_cached_curve_history(symbol)
            if snapshots.empty:
                errors.append(f"{symbol}: no local history yet")
                progress.progress(i / len(items))
                continue
            snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
            snapshots = snapshots[snapshots["snapshot_date"].dt.date <= as_of].copy()
            rows = scan_market_opportunities(
                symbol,
                curve,
                snapshots,
                lookback=int(lookback),
                entry_z=float(entry_z),
                horizon=int(horizon),
                min_analogs=int(min_analogs),
                min_win_rate=0.55,
            )
            if not rows.empty:
                all_rows.append(rows)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
        progress.progress(i / len(items))
    status.write("Scan complete.")
    st.session_state["futurescope_opportunity_rows"] = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    st.session_state["futurescope_opportunity_errors"] = errors

result = st.session_state.get("futurescope_opportunity_rows", pd.DataFrame())
errors = st.session_state.get("futurescope_opportunity_errors", [])

if not result.empty:
    state_rank = {"TRADE CANDIDATE": 0, "RESEARCH": 1, "UNUSUAL": 2, "NORMAL": 3}
    result = result.copy()
    result["_state_rank"] = result["state"].map(state_rank).fillna(9)
    result = result.sort_values(["_state_rank", "research_score"], ascending=[True, False]).drop(columns="_state_rank")

    candidates = result[result["state"] == "TRADE CANDIDATE"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Structures scanned", len(result))
    m2.metric("Trade candidates", len(candidates))
    m3.metric("Markets with candidates", candidates["market"].nunique() if not candidates.empty else 0)

    st.subheader("Ranked opportunities")
    show_all = st.checkbox("Show normal structures too", value=False)
    display = result if show_all else result[result["state"] != "NORMAL"]
    cols = [
        "market",
        "state",
        "research_score",
        "structure",
        "curve_location",
        "contracts",
        "signal",
        "trade_ratio",
        "zscore",
        "behavior",
        "win_rate",
        "analogs",
        "mean_forward_change",
        "expected_gross_pnl_usd",
    ]
    st.dataframe(
        display[cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "research_score": st.column_config.ProgressColumn("Research score", min_value=0, max_value=100, format="%.0f"),
            "zscore": st.column_config.NumberColumn("Z-score", format="%.2f"),
            "win_rate": st.column_config.NumberColumn("Win rate", format="%.1%%"),
            "mean_forward_change": st.column_config.NumberColumn("Mean forward move", format="%+.4f"),
            "expected_gross_pnl_usd": st.column_config.NumberColumn("Gross historical $ expectancy", format="$%.0f"),
        },
    )

    if not candidates.empty:
        st.subheader("Best active candidate per market")
        best = candidates.sort_values("research_score", ascending=False).groupby("market", as_index=False).first()
        st.dataframe(
            best[["market", "structure", "curve_location", "signal", "trade_ratio", "zscore", "win_rate", "expected_gross_pnl_usd", "research_score"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "zscore": st.column_config.NumberColumn("Z-score", format="%.2f"),
                "win_rate": st.column_config.NumberColumn("Win rate", format="%.1%%"),
                "expected_gross_pnl_usd": st.column_config.NumberColumn("Gross historical $ expectancy", format="$%.0f"),
                "research_score": st.column_config.ProgressColumn("Research score", min_value=0, max_value=100, format="%.0f"),
            },
        )

    st.warning("TRADE CANDIDATE means the statistical rule produced LONG/SHORT with adequate historical evidence. It is not yet a production trade-quality score: live bid/ask, commissions, liquidity, margin, fair value, and market-specific risk normalization still need to clear.")
    st.caption("VX futures curves currently come from the configured futures provider; official Cboe VIX-family index data are already used by Futurescope. Cboe daily VX settlement data can be added as an alternate futures-curve source without changing the signal architecture.")
elif "futurescope_opportunity_rows" in st.session_state:
    st.info("No opportunity rows were produced. Build more local history for the markets you want to rank.")
else:
    st.info("Click **Scan Futurescope markets** to load the as-of curves and rank the cached-history RV structures.")

if errors:
    with st.expander("Scan warnings"):
        for error in errors:
            st.write("•", error)
