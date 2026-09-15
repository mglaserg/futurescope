from __future__ import annotations

import pandas as pd
import streamlit as st

from futurescope.analytics.relative_value import build_relative_value_history, relative_value_zscore_history
from futurescope.config import MARKETS
from futurescope.mean_reversion import mean_reversion_analysis
from futurescope.research_logging import log_dashboard_look
from futurescope.rv_store import load_cached_curve_history
from futurescope.ui import apply_futurescope_theme, hero

apply_futurescope_theme()
hero(
    "REGISTERED RESEARCH · FIRST PASSAGE",
    "Mean Reversion Lab",
    "When a calendar spread or butterfly reaches an extreme z-score, does the structure itself come back to the mean before a roll or time stop? This page measures episodes rather than pretending every extreme day is independent.",
    ["z → mean", "first passage", "MAE / MFE", "roll-censored"],
)

with st.sidebar:
    st.header("Research specification")
    market = st.selectbox("Market", list(MARKETS), index=0)
    order = st.selectbox("Structure", [1, 2, 3], format_func=lambda x: {1: "Slope / calendar", 2: "Butterfly", 3: "Double butterfly"}[x])
    position = st.number_input("Curve slot", min_value=1, value=1, step=1)
    lookback = st.number_input("Z-score lookback", min_value=3, value=20, step=1)
    entry_z = st.number_input("Entry |z|", min_value=0.5, value=2.0, step=0.25)
    max_horizon = st.number_input("Max holding observations", min_value=1, value=20, step=1)
    target_label = st.selectbox("Mean target", ["Frozen entry mean", "Dynamic z = 0"])
    reason = st.text_input("Reason for look", value="Test first passage from extreme z-score back to the mean")
    run = st.button("Log + run analysis", type="primary", use_container_width=True)

st.markdown(
    """
    <div class="fs-note"><strong>Why frozen entry mean?</strong> A rolling z-score can return to zero partly because the rolling mean moves toward the trade. Frozen-entry mode asks whether the structure itself crosses the equilibrium level that existed when the trade was identified.</div>
    """,
    unsafe_allow_html=True,
)

if run:
    snapshots = load_cached_curve_history(market)
    if snapshots.empty:
        st.error(f"No cached snapshots for {market}. Refresh/run the monitor first.")
        st.stop()

    history = build_relative_value_history(
        snapshots,
        order=int(order),
        position=int(position),
        value_column="time_normalized_value",
    )
    if history.empty:
        st.error("No history exists for that curve position.")
        st.stop()

    target_mode = "frozen_entry_mean" if target_label == "Frozen entry mean" else "dynamic_zero"
    look_id = log_dashboard_look(
        "mean_reversion_first_passage",
        {
            "market": market,
            "order": int(order),
            "position": int(position),
            "lookback": int(lookback),
            "entry_z": float(entry_z),
            "max_horizon": int(max_horizon),
            "target_mode": target_mode,
        },
        reason,
    )
    if look_id is None:
        st.warning("Research look could not be logged. Treat results as unaudited.")
    else:
        st.caption(f"Registered as research look #{look_id} before results were revealed.")

    episodes, summary, survival = mean_reversion_analysis(
        history,
        lookback=int(lookback),
        entry_z=float(entry_z),
        max_horizon=int(max_horizon),
        target_mode=target_mode,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episodes", summary.episodes)
    c2.metric(
        "Hit mean",
        "N/A" if pd.isna(summary.hit_rate) else f"{summary.hit_rate:.1%}",
        help="Non-overlapping extreme-z episodes that crossed the chosen mean target before roll/time censoring.",
    )
    c3.metric("Median time", "N/A" if pd.isna(summary.median_time_to_mean_obs) else f"{summary.median_time_to_mean_obs:.1f} obs")
    c4.metric("Mean P&L", "N/A" if pd.isna(summary.mean_pnl_price_units) else f"{summary.mean_pnl_price_units:.3f} price units")

    if not pd.isna(summary.hit_rate_ci_low):
        st.caption(f"95% Wilson interval for hit rate: {summary.hit_rate_ci_low:.1%} to {summary.hit_rate_ci_high:.1%}. Episode count is still not a full dependence-adjusted N_eff.")

    z_hist = relative_value_zscore_history(history, lookback=int(lookback))
    z_plot = z_hist[["snapshot_date", "signal_zscore"]].dropna().set_index("snapshot_date")
    st.markdown("### Z-score path")
    st.line_chart(z_plot, height=300)
    st.caption(f"Entry bands: ±{entry_z:.2f}. The first passage test starts only when z crosses into an extreme from inside the band.")

    st.markdown("### First-passage survival")
    if survival.empty:
        st.info("No qualifying episodes yet.")
    else:
        surv_plot = survival.set_index("duration_obs")[["survival"]]
        st.line_chart(surv_plot, height=300)
        st.caption("Survival = probability an extreme episode has not yet returned to the mean. Rolls/time stops are treated as censored observations.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mean MAE", "N/A" if pd.isna(summary.mean_mae_price_units) else f"{summary.mean_mae_price_units:.3f}")
    m2.metric("Mean MFE", "N/A" if pd.isna(summary.mean_mfe_price_units) else f"{summary.mean_mfe_price_units:.3f}")
    m3.metric("Roll censored", summary.censored_roll)
    m4.metric("Time censored", summary.censored_time)

    st.markdown("### Episodes")
    if episodes.empty:
        st.info("No threshold-crossing episodes under this specification.")
    else:
        columns = [
            "entry_date", "exit_date", "trade_direction", "entry_zscore", "status",
            "duration_obs", "pnl_price_units", "mae_price_units", "mfe_price_units", "leg_symbols",
        ]
        st.dataframe(episodes[columns], use_container_width=True, hide_index=True)

    st.warning("Research output is still in canonical price units. Actual spread-market costs, multipliers, and the registered cost hurdle must be applied before calling this tradeable edge.")
else:
    st.info("Choose a pre-specified structure in the sidebar, then log and run the first-passage analysis. No historical outcomes are revealed until you do.")
