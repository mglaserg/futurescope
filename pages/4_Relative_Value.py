from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    backtest_relative_value_mean_reversion,
    build_relative_value_history,
    build_relative_value_structures,
    canonical_trade_weights,
    relative_value_statistics,
    relative_value_trade_signal,
    relative_value_zscore_history,
)
from futurescope.config import MARKETS
from futurescope.research_logging import log_dashboard_look
from futurescope.rv_store import (
    CurveSnapshotStore,
    load_cached_curve_history,
    load_relative_value_curve,
)

load_dotenv()
st.set_page_config(page_title="Relative Value | Futurescope", layout="wide")
st.title("Relative Value")
st.caption(
    "Curve slope, curvature, and change-in-curvature trades as first-, second-, and third-order finite differences."
)

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

st.markdown(
    r"""
### Finite-difference hierarchy

For adjacent contracts, Futurescope uses a **long-front trade sign convention**:

- **Spread / slope:** $+F_1-F_2$ → weights `+1 : -1`
- **Butterfly / curvature:** $+F_1-2F_2+F_3$ → weights `+1 : -2 : +1`
- **Double butterfly / change in curvature:** $+F_1-3F_2+3F_3-F_4$ → weights `+1 : -3 : +3 : -1`

The integer-weight trade value is shown separately from the **time-normalized curve measure**. The latter uses uneven-tenor finite-difference coefficients, so a 1-month/1-month fly and a 1-month/3-month fly are not treated as geometrically identical.
"""
)

st.subheader("Trade-weight normalization")
normalization = st.radio(
    "Leg weighting",
    ["Canonical contract counts", "Custom risk per contract"],
    horizontal=True,
    help="Custom risk units convert the canonical curve exposure into contract ratios. For Treasury futures, enter DV01 per contract when available.",
)

risk_units: dict[str, float] | None = None
if normalization == "Custom risk per contract":
    risk_input = curve[["raw_symbol", "expiration", "close"]].copy()
    risk_input["expiration"] = risk_input["expiration"].dt.date
    risk_input["risk_per_contract"] = 1.0
    edited = st.data_editor(
        risk_input,
        use_container_width=True,
        hide_index=True,
        disabled=["raw_symbol", "expiration", "close"],
        column_config={
            "risk_per_contract": st.column_config.NumberColumn(
                "Risk per contract",
                min_value=0.000001,
                step=0.01,
                format="%.4f",
            )
        },
    )
    risk_units = {
        str(row.raw_symbol): float(row.risk_per_contract)
        for row in edited.itertuples(index=False)
        if np.isfinite(row.risk_per_contract) and row.risk_per_contract > 0
    }
    if symbol == "ZN":
        st.caption("For ZN, the intended market-specific implementation is DV01 weighting. Enter current per-contract DV01 values here when available.")

labels = {
    1: "2-leg · Curve slope / calendar spread",
    2: "3-leg · Butterfly / curvature",
    3: "4-leg · Double butterfly / change in curvature",
}

tabs = st.tabs([labels[1], labels[2], labels[3]])
for order, tab in zip((1, 2, 3), tabs):
    with tab:
        structures = build_relative_value_structures(curve, order=order, risk_units=risk_units)
        if structures.empty:
            st.info(f"Need at least {order + 1} live contracts for this structure.")
            continue

        display = structures[
            [
                "tenor_label",
                "leg_symbols",
                "leg_expirations",
                "canonical_weights",
                "trade_weights",
                "canonical_value",
                "trade_value",
                "time_normalized_value",
                "span_days",
            ]
        ].copy()
        display.columns = [
            "Tenors",
            "Contracts",
            "Expiries",
            "Canonical weights",
            "Trade weights",
            "Canonical value",
            "Weighted trade value",
            f"Time-normalized order-{order} measure",
            "Span days",
        ]
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Canonical value": st.column_config.NumberColumn(format="%.6f"),
                "Weighted trade value": st.column_config.NumberColumn(format="%.6f"),
                f"Time-normalized order-{order} measure": st.column_config.NumberColumn(format="%.6f"),
                "Span days": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        st.caption(
            "Canonical value is the raw integer-ratio structure. Time-normalized measure is the finite-difference analogue adjusted for actual expiry spacing."
        )

st.divider()
st.subheader("Local history cache")
st.caption(
    "Every curve you load is saved under cache/curve_snapshots. Historical RV diagnostics use those local snapshots; they do not automatically query Databento again."
)

store = CurveSnapshotStore()
cached_dates = store.dates(symbol)
cache_col1, cache_col2 = st.columns([1, 2])
with cache_col1:
    st.metric("Cached snapshots", len(cached_dates))
    if cached_dates:
        st.caption(f"{min(cached_dates)} → {max(cached_dates)}")
with cache_col2:
    st.write(
        "Use the optional builder below only when you want to add history. Existing Databento request-cache files are reused; uncached dates can create new historical-data requests."
    )

with st.expander("Build / extend local history"):
    h1, h2, h3 = st.columns(3)
    with h1:
        history_start = st.date_input("History start", value=as_of - timedelta(days=90), key="rv_history_start")
    with h2:
        history_end = st.date_input("History end", value=as_of, key="rv_history_end")
    with h3:
        sampling = st.selectbox("Sampling", ["Weekly", "Business daily", "Month end"], index=0)

    if history_end < history_start:
        requested_dates: list[date] = []
        st.error("History end must be on or after history start.")
    else:
        freq = {"Weekly": "W-FRI", "Business daily": "B", "Month end": "ME"}[sampling]
        requested_dates = [ts.date() for ts in pd.date_range(history_start, history_end, freq=freq)]
        if history_end not in requested_dates and history_end.weekday() < 5:
            requested_dates.append(history_end)
        requested_dates = sorted(set(d for d in requested_dates if d <= date.today()))
        st.caption(
            f"{len(requested_dates)} snapshot dates selected. Each uncached date can require Databento definition + OHLCV historical queries."
        )

    if len(requested_dates) > 260:
        st.error("Select 260 or fewer snapshot dates per batch.")
    elif st.button("Build local history cache", disabled=not requested_dates):
        progress = st.progress(0.0)
        status = st.empty()
        failures: list[str] = []
        for i, snapshot_date in enumerate(requested_dates, start=1):
            status.write(f"Loading {snapshot_date} ({i}/{len(requested_dates)})")
            try:
                load_relative_value_curve(config, snapshot_date, refresh=False)
            except Exception as exc:
                failures.append(f"{snapshot_date}: {exc}")
            progress.progress(i / len(requested_dates))
        status.write("History cache build complete.")
        if failures:
            with st.expander("History load warnings"):
                for failure in failures:
                    st.write("•", failure)
        cached_dates = store.dates(symbol)

if cached_dates:
    st.subheader("Cached curve playback")
    playback_date = st.select_slider(
        "Snapshot",
        options=cached_dates,
        value=cached_dates[-1],
        format_func=lambda x: x.isoformat(),
    )
    playback = store.read(symbol, playback_date)
    if playback is not None and not playback.empty:
        fig = px.line(
            playback,
            x="expiration",
            y="close",
            markers=True,
            hover_name="raw_symbol",
            title=f"{symbol} curve · {playback_date}",
        )
        fig.update_layout(xaxis_title="Expiration", yaxis_title=config.units)
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Historical relative-value diagnostics")

snapshots = load_cached_curve_history(symbol)
if snapshots.empty:
    st.info("Load or build at least a few curve snapshots to enable historical diagnostics.")
else:
    d1, d2 = st.columns(2)
    with d1:
        selected_order = st.selectbox(
            "Structure",
            options=[1, 2, 3],
            format_func=lambda order: labels[order],
        )
    max_position = max(1, len(curve) - selected_order)
    with d2:
        selected_position = st.selectbox(
            "Curve location",
            options=list(range(1, max_position + 1)),
            format_func=lambda pos: "-".join(f"F{i}" for i in range(pos, pos + selected_order + 1)),
        )

    history = build_relative_value_history(
        snapshots,
        order=selected_order,
        position=selected_position,
        value_column="time_normalized_value",
    )

    if history.empty:
        st.info("The cached snapshots do not contain enough contracts for this structure.")
    else:
        diagnostics_look_id = log_dashboard_look(
            "rv_historical_diagnostics",
            {
                "market": symbol,
                "as_of": as_of.isoformat(),
                "order": int(selected_order),
                "position": int(selected_position),
                "history_end": str(pd.to_datetime(history["snapshot_date"]).max()),
            },
            "Relative Value page historical persistence/half-life diagnostics",
        )
        if diagnostics_look_id is not None:
            st.caption(f"Research look logged as #{diagnostics_look_id} before historical diagnostics were shown.")
        else:
            st.warning("Research registry logging failed; these historical diagnostics are being shown without an audit entry.")
        stats = relative_value_statistics(history["value"])
        zscore = stats["zscore"]
        anomaly = "Normal"
        if pd.notna(zscore) and zscore >= 2.0:
            anomaly = "Extreme high"
        elif pd.notna(zscore) and zscore <= -2.0:
            anomaly = "Extreme low"

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Observations", int(stats["observations"]))
        m2.metric("Current z-score", "N/A" if pd.isna(zscore) else f"{zscore:.2f}")
        m3.metric("Historical percentile", f"{100 * stats['percentile']:.1f}%")
        m4.metric("Lag-1 persistence", "N/A" if pd.isna(stats["autocorr_1"]) else f"{stats['autocorr_1']:.2f}")
        m5.metric("Anomaly flag", anomaly)
        st.caption(
            "Estimated mean-reversion half-life: "
            + ("N/A" if pd.isna(stats["half_life"]) else f"{stats['half_life']:.1f} observations")
        )

        st.markdown("### Directional signal")
        long_weights = canonical_trade_weights(selected_order)
        short_weights = -long_weights
        long_ratio = " : ".join(f"{int(x):+d}" for x in long_weights)
        short_ratio = " : ".join(f"{int(x):+d}" for x in short_weights)
        st.caption(
            f"LONG/SHORT refers to the selected {STRUCTURE_NAMES[selected_order]} as a basket, not to the front month alone. "
            f"LONG = {long_ratio}; SHORT = {short_ratio}. An extreme z-score is only an anomaly: high does not automatically mean SHORT and low does not automatically mean LONG. "
            "The directional signal asks what comparable historical extremes actually did next, without crossing contract-roll boundaries."
        )
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            signal_lookback = st.number_input("Signal lookback", min_value=3, value=20, step=1, key="rv_signal_lookback")
        with s2:
            signal_entry_z = st.number_input("Extreme |z|", min_value=0.25, value=2.0, step=0.25, key="rv_signal_entry_z")
        with s3:
            signal_horizon = st.number_input("Forward horizon (observations)", min_value=1, value=5, step=1, key="rv_signal_horizon")
        with s4:
            signal_min_analogs = st.number_input("Minimum analogues", min_value=1, value=5, step=1, key="rv_signal_min_analogs")

        signal_look_id = log_dashboard_look(
            "rv_directional_signal",
            {
                "market": symbol,
                "as_of": as_of.isoformat(),
                "order": int(selected_order),
                "position": int(selected_position),
                "lookback": int(signal_lookback),
                "entry_z": float(signal_entry_z),
                "horizon": int(signal_horizon),
                "min_analogs": int(signal_min_analogs),
            },
            "Directional signal requested from historical conditional outcomes",
        )
        signal_result = relative_value_trade_signal(
            history,
            lookback=int(signal_lookback),
            entry_z=float(signal_entry_z),
            horizon=int(signal_horizon),
            min_analogs=int(signal_min_analogs),
            min_win_rate=0.55,
        )
        signal_name = str(signal_result["signal"])
        if signal_look_id is not None:
            st.caption(f"Directional historical query logged as research look #{signal_look_id}.")
        else:
            st.warning("Research registry logging failed for this directional historical query.")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Signal", signal_name)
        q2.metric("Signal z-score", "N/A" if pd.isna(signal_result["current_zscore"]) else f"{signal_result['current_zscore']:.2f}")
        q3.metric("Historical analogues", int(signal_result["analogs"]))
        q4.metric("Directional win rate", "N/A" if pd.isna(signal_result["win_rate"]) else f"{signal_result['win_rate']:.1%}")

        st.write(signal_result["reason"])
        if signal_name in {"LONG", "SHORT"}:
            raw_weights = canonical_trade_weights(selected_order)
            if signal_name == "SHORT":
                raw_weights = -raw_weights
            trade_ratio = " : ".join(f"{int(x):+d}" for x in raw_weights)
            st.success(
                f"{signal_name} {STRUCTURE_NAMES[selected_order]} · canonical trade ratio {trade_ratio}. "
                f"Historical behavior: {signal_result['behavior']}. "
                f"Mean {int(signal_horizon)}-observation move: {signal_result['mean_forward_change']:.6f} canonical price units."
            )
        else:
            st.info("No directional trade is being recommended by the research rule at the current settings.")
        st.caption(
            "This is a gross research signal, not yet a production trade score. Transaction costs, contract multipliers, margin, liquidity, fair value, and market-specific risk normalization still need to clear before execution."
        )

        fig = px.line(
            history,
            x="snapshot_date",
            y="value",
            markers=True,
            title=f"{STRUCTURE_NAMES[selected_order]} · position F{selected_position}",
        )
        fig.update_layout(xaxis_title="Snapshot date", yaxis_title=f"Order-{selected_order} normalized measure")
        st.plotly_chart(fig, use_container_width=True)

        z_history = relative_value_zscore_history(history, lookback=int(signal_lookback))
        z_fig = px.line(
            z_history,
            x="snapshot_date",
            y="signal_zscore",
            markers=True,
            title=f"Lagged rolling z-score · {int(signal_lookback)}-observation lookback",
        )
        z_fig.add_hline(y=0.0, line_dash="dot", annotation_text="0")
        z_fig.add_hline(
            y=float(signal_entry_z),
            line_dash="dash",
            annotation_text=f"+{float(signal_entry_z):.2f} threshold",
        )
        z_fig.add_hline(
            y=-float(signal_entry_z),
            line_dash="dash",
            annotation_text=f"-{float(signal_entry_z):.2f} threshold",
        )
        z_fig.update_layout(xaxis_title="Snapshot date", yaxis_title="Signal z-score")
        st.plotly_chart(z_fig, use_container_width=True)
        st.caption(
            "This is the same lagged rolling z-score used by the directional signal. The ± threshold lines mark where an observation becomes eligible for historical analogue testing; crossing a line alone does not force a mean-reversion trade."
        )

        st.dataframe(
            history.sort_values("snapshot_date", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "snapshot_date": st.column_config.DateColumn("Date"),
                "value": st.column_config.NumberColumn("Time-normalized value", format="%.6f"),
                "canonical_value": st.column_config.NumberColumn("Canonical value", format="%.6f"),
                "span_days": st.column_config.NumberColumn("Span days", format="%.1f"),
            },
        )
        st.caption(
            "The history follows relative curve slots (F1/F2/etc.), not fixed raw symbols. Contract-roll changes are shown explicitly in the table. Full executable P&L backtests should handle roll boundaries, contract multipliers, transaction costs, and market-specific risk scaling."
        )

        run_proxy = st.checkbox("Run mean-reversion backtest proxy (logs a research look)", value=False)
        if run_proxy:
            b1, b2, b3 = st.columns(3)
            with b1:
                lookback = st.number_input("Signal lookback (observations)", min_value=3, value=20, step=1)
            with b2:
                entry_z = st.number_input("Entry |z|", min_value=0.25, value=2.0, step=0.25)
            with b3:
                exit_z = st.number_input("Exit |z|", min_value=0.0, value=0.5, step=0.25)

            if exit_z >= entry_z:
                st.warning("Exit |z| must be smaller than entry |z|.")
            else:
                proxy_look_id = log_dashboard_look(
                    "rv_mean_reversion_proxy",
                    {
                        "market": symbol,
                        "as_of": as_of.isoformat(),
                        "order": int(selected_order),
                        "position": int(selected_position),
                        "lookback": int(lookback),
                        "entry_z": float(entry_z),
                        "exit_z": float(exit_z),
                    },
                    "Mean-reversion P&L proxy requested from historical RV series",
                )
                if proxy_look_id is not None:
                    st.caption(f"Backtest proxy logged as research look #{proxy_look_id} before P&L was shown.")
                else:
                    st.warning("Research registry logging failed for this backtest proxy.")
                bt = backtest_relative_value_mean_reversion(
                    history,
                    lookback=int(lookback),
                    entry_z=float(entry_z),
                    exit_z=float(exit_z),
                )
                trade_changes = bt["position"].diff().abs().fillna(bt["position"].abs())
                entries = int((trade_changes > 0).sum())
                r1, r2, r3 = st.columns(3)
                r1.metric("Gross P&L proxy", f"{bt['pnl_price_units'].sum():.4f} price units")
                r2.metric("Position changes", entries)
                r3.metric("Roll boundaries skipped", int(bt["roll_boundary"].sum()))

                pnl_fig = px.line(
                    bt,
                    x="snapshot_date",
                    y="cumulative_pnl_price_units",
                    title="Cumulative mean-reversion P&L proxy",
                )
                pnl_fig.update_layout(xaxis_title="Snapshot date", yaxis_title="Canonical price units")
                st.plotly_chart(pnl_fig, use_container_width=True)
                st.caption(
                    "Research proxy only: signal statistics are lagged to avoid look-ahead, and cross-roll P&L is set to zero. Contract multipliers, fees, bid/ask, margin, and explicit roll execution are not included."
                )
