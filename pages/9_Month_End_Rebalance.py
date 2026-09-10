from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from futurescope.config import MES_EXECUTION_CONFIG
from futurescope.month_end_rebalance import (
    STRONG_BUYING_THRESHOLD,
    STRONG_SELLING_THRESHOLD,
    calculate_rebalance_signal,
    frozen_signal_from_history,
    nearest_price_on_or_before,
    pressure_path,
    schedule_for_as_of,
    strategy_instruction,
)
from futurescope.services import load_market_curve
from futurescope.ui import apply_futurescope_theme, hero


load_dotenv()
st.set_page_config(page_title="Month-End Rebalance | Futurescope", page_icon="◒", layout="wide")
apply_futurescope_theme()

hero(
    "HIGH PRIORITY · FLOW MONITOR",
    "Month-End Rebalance",
    "A clean current-state implementation of the 60/40 rebalance-pressure trade: SPY and IEF measure the expected flow, TLT expresses duration, and MES can replace SPY as the futures execution leg.",
    ["SPY / MES", "TLT", "60 / 40 flow", "No outcome mining"],
)

with st.sidebar:
    st.header("Trade setup")
    as_of_requested = st.date_input("As-of close", value=date.today())
    equity_vehicle = st.radio("Equity execution", ["MES", "SPY"], horizontal=True)
    leg_notional = st.number_input("Target notional per active leg", min_value=1_000, value=25_000, step=5_000)
    refresh = st.checkbox("Refresh market data", value=False)
    st.divider()
    st.caption("Frozen strategy thresholds")
    st.code("Strong bond selling ≤ -50 bps\nStrong bond buying ≥ +50 bps")
    st.caption("SPY + IEF generate the pressure signal. TLT is the long-duration trading leg.")


@st.cache_data(ttl=900, show_spinner=False)
def _load_macro_history(start: date, end: date) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(
        ["SPY", "IEF", "TLT"],
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        progress=False,
        group_by="column",
        threads=True,
    )
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        field = "Adj Close" if "Adj Close" in raw.columns.get_level_values(0) else "Close"
        frame = raw[field].copy()
    else:
        field = "Adj Close" if "Adj Close" in raw.columns else "Close"
        frame = raw[[field]].rename(columns={field: "SPY"})
    if isinstance(frame, pd.Series):
        frame = frame.to_frame("SPY")
    frame.columns = [str(c).upper() for c in frame.columns]
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    return frame.sort_index()


# Pull enough history to cover the prior month-end anchor plus a little visual context.
load_start = (pd.Timestamp(as_of_requested) - pd.DateOffset(months=2) - pd.Timedelta(days=10)).date()
try:
    if refresh:
        _load_macro_history.clear()
    prices = _load_macro_history(load_start, as_of_requested)
except Exception as exc:
    st.error(f"SPY / IEF / TLT history could not be loaded: {exc}")
    st.stop()

if prices.empty or not {"SPY", "IEF", "TLT"}.issubset(prices.columns):
    st.error("SPY, IEF, and TLT history are required for the month-end monitor.")
    st.stop()

available = prices.dropna(how="all")
data_as_of = min(as_of_requested, available.index[-1].date())
schedule = schedule_for_as_of(data_as_of)
signal, _ = frozen_signal_from_history(prices, schedule)
instruction = strategy_instruction(data_as_of, schedule, signal)

# Indicative pressure is useful before the official signal close, but never substitutes for the frozen signal.
spy_anchor = nearest_price_on_or_before(prices["SPY"], schedule.previous_month_end)
ief_anchor = nearest_price_on_or_before(prices["IEF"], schedule.previous_month_end)
spy_now = nearest_price_on_or_before(prices["SPY"], min(data_as_of, schedule.signal_day))
ief_now = nearest_price_on_or_before(prices["IEF"], min(data_as_of, schedule.signal_day))
indicative_signal = None
if all([spy_anchor, ief_anchor, spy_now, ief_now]):
    indicative_signal = calculate_rebalance_signal(spy_anchor[1], spy_now[1], ief_anchor[1], ief_now[1])

shown_signal = signal or indicative_signal
pressure_bps = shown_signal.pressure_bps if shown_signal else float("nan")
pressure_text = "N/A" if not np.isfinite(pressure_bps) else f"{pressure_bps:+.1f} bps"
regime = shown_signal.regime if shown_signal else "WAITING FOR DATA"
pressure_label = "Frozen pressure" if signal is not None else "Indicative pressure"

m1, m2, m3, m4 = st.columns(4)
m1.metric("Current phase", instruction.phase)
m2.metric(pressure_label, "N/A" if not np.isfinite(pressure_bps) else f"{pressure_bps:+.0f} bps")
m3.metric("Flow regime", regime.title())
m4.metric("Market data through", data_as_of.strftime("%b %d, %Y"))

st.markdown(
    f"""
    <div class="fs-signal">
      <div class="eyebrow">Futurescope instruction · after {data_as_of:%b %d} close</div>
      <div class="headline">{instruction.headline}</div>
      <div class="detail">{instruction.detail}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")

# Pressure gauge: display a generous ±100 bps band while preserving the exact ±50 bps strategy thresholds.
clamped = max(-100.0, min(100.0, pressure_bps if np.isfinite(pressure_bps) else 0.0))
marker_left = (clamped + 100.0) / 200.0 * 100.0
st.markdown(
    f"""
    <div class="fs-pressure">
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:end;">
        <div><div class="fs-kicker">REBALANCE PRESSURE</div><div style="font-size:1.55rem;font-weight:850;color:#0f172a;margin-top:3px;">{pressure_text}</div></div>
        <div style="color:#64748b;font-size:.84rem;text-align:right;">Negative = expected bond selling<br>Positive = expected bond buying</div>
      </div>
      <div class="fs-pressure-track">
        <div class="fs-pressure-threshold" style="left:25%;"></div>
        <div class="fs-pressure-threshold" style="left:75%;"></div>
        <div class="fs-pressure-marker" style="left:{marker_left:.2f}%;"></div>
      </div>
      <div class="fs-pressure-labels"><span>−100 bps</span><span>−50 sell threshold</span><span>0</span><span>+50 buy threshold</span><span>+100 bps</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Calendar map")
if data_as_of < schedule.signal_day:
    active_step = 0
elif data_as_of < schedule.month_end:
    active_step = 1
elif data_as_of <= schedule.early_exit:
    active_step = 2
else:
    active_step = 3
steps = [
    ("Anchor", schedule.previous_month_end, "Previous month-end"),
    ("Signal", schedule.signal_day, "Freeze 60/40 pressure"),
    ("Rotate", schedule.month_end, "Close final-five / set reversal"),
    ("Exit", schedule.early_exit, "Fifth session of new month"),
]
step_html = "".join(
    f'<div class="fs-step {"active" if i == active_step else ""}"><div class="n">{label}</div><div class="d">{dt:%b %d}</div><div class="t">{text}</div></div>'
    for i, (label, dt, text) in enumerate(steps)
)
st.markdown(f'<div class="fs-timeline">{step_html}</div>', unsafe_allow_html=True)

st.subheader("Execution ticket")
latest_spy = nearest_price_on_or_before(prices["SPY"], data_as_of)
latest_tlt = nearest_price_on_or_before(prices["TLT"], data_as_of)
mes_symbol = None
mes_price = None
mes_error = None
if equity_vehicle == "MES" and instruction.equity_weight != 0:
    try:
        mes_curve, _, _ = load_market_curve(MES_EXECUTION_CONFIG, data_as_of, refresh=refresh)
        if not mes_curve.empty:
            mes_symbol = str(mes_curve.iloc[0]["raw_symbol"])
            mes_price = float(mes_curve.iloc[0]["close"])
    except Exception as exc:
        mes_error = str(exc)

legs: list[dict[str, str]] = []
if instruction.equity_weight != 0:
    side = "BUY" if instruction.equity_weight > 0 else "SELL"
    if equity_vehicle == "MES":
        if mes_price and mes_price > 0:
            qty = max(1, int(round(float(leg_notional) / (mes_price * 5.0))))
            approx = qty * mes_price * 5.0
            meta = f"{qty} contract{'s' if qty != 1 else ''} · ≈ ${approx:,.0f} notional · ${mes_price:,.2f} index"
            legs.append({"side": side, "symbol": mes_symbol or "MES front", "meta": meta})
        else:
            legs.append({"side": side, "symbol": "MES front", "meta": "Databento quote unavailable — contract sizing pending"})
    elif latest_spy:
        qty = max(1, int(round(float(leg_notional) / latest_spy[1])))
        approx = qty * latest_spy[1]
        legs.append({"side": side, "symbol": "SPY", "meta": f"{qty} shares · ≈ ${approx:,.0f} notional · ${latest_spy[1]:,.2f}"})

if instruction.tlt_weight != 0 and latest_tlt:
    side = "BUY" if instruction.tlt_weight > 0 else "SELL"
    qty = max(1, int(round(float(leg_notional) / latest_tlt[1])))
    approx = qty * latest_tlt[1]
    legs.append({"side": side, "symbol": "TLT", "meta": f"{qty} shares · ≈ ${approx:,.0f} notional · ${latest_tlt[1]:,.2f}"})

if not legs:
    st.markdown('<div class="fs-card"><h4>No trade ticket</h4><p>The strategy is currently in cash or waiting for the scheduled signal close.</p></div>', unsafe_allow_html=True)
else:
    leg_html = "".join(
        f'<div class="fs-leg {"fs-buy" if leg["side"] == "BUY" else "fs-sell"}"><div class="side">{leg["side"]}</div><div class="symbol">{leg["symbol"]}</div><div class="meta">{leg["meta"]}</div></div>'
        for leg in legs
    )
    st.markdown(f'<div class="fs-ticket">{leg_html}</div>', unsafe_allow_html=True)
    if len(legs) == 2:
        st.caption("Pair ticket uses equal target notional per leg as an execution translation. That sizing convention is not yet a validated risk-neutral hedge ratio.")
if mes_error:
    st.warning(f"MES sizing could not be loaded from Databento: {mes_error}")

st.subheader("What created the signal?")
left, right = st.columns([1.3, 1])
with left:
    path_end = min(data_as_of, schedule.signal_day)
    ppath = pressure_path(prices["SPY"], prices["IEF"], schedule.previous_month_end, path_end)
    if not ppath.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ppath["date"], y=ppath["pressure_bps"], mode="lines", name="Bond rebalance pressure", line=dict(width=3)))
        fig.add_hline(y=-50.0, line_dash="dash", annotation_text="−50 bps · strong selling")
        fig.add_hline(y=50.0, line_dash="dash", annotation_text="+50 bps · strong buying")
        fig.add_hline(y=0.0, line_dash="dot")
        fig.update_layout(
            title="60/40 implied bond rebalance pressure",
            xaxis_title="Trading date",
            yaxis_title="Basis points of portfolio value",
            margin=dict(l=10, r=10, t=55, b=10),
            height=390,
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, use_container_width=True)
with right:
    display_signal = signal or indicative_signal
    if display_signal:
        st.markdown(
            f"""
            <div class="fs-card">
              <div class="fs-kicker">60 / 40 DRIFT</div>
              <h4 style="font-size:1.35rem;margin-top:7px;">SPY {display_signal.stock_return:+.2%} · IEF {display_signal.bond_return:+.2%}</h4>
              <p style="margin-top:7px;">To restore 60/40, the model implies a bond trade of <strong>{display_signal.bond_trade:+.2%}</strong> of portfolio value, or <strong>{display_signal.pressure_bps:+.1f} bps</strong>.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
    st.markdown(
        """
        <div class="fs-card">
          <div class="fs-kicker">ROLE OF EACH INSTRUMENT</div>
          <h4 style="margin-top:7px;">SPY + IEF measure. MES / SPY + TLT trade.</h4>
          <p style="margin-top:7px;">IEF is deliberately the bond proxy used to estimate 60/40 drift. TLT expresses the long-duration flow. MES is the default Futurescope translation of the equity leg; SPY remains available for a cash-equity implementation.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with st.expander("Strategy map · frozen source rules"):
    st.markdown(
        """
        **At the sixth-last trading-day close**

        - pressure ≤ **−50 bps** → **long equity** for the final five sessions
        - otherwise → **long TLT** for the final five sessions

        **At the month-end close**

        - pressure ≥ **+50 bps** → **long equity / short TLT** for the first five sessions of the new month
        - otherwise → **cash**

        **At the fifth trading-day close of the new month** → close everything.

        Futurescope freezes the rebalance pressure at the sixth-last close. It does not silently optimize these thresholds.
        """
    )

st.markdown(
    """
    <div class="fs-note"><strong>Research boundary.</strong> This page calculates today’s observable calendar state and translates the frozen strategy rules into a ticket. It does not reveal historical conditional returns, optimize thresholds, or claim the imported strategy is validated inside Futurescope. Any internal historical test belongs in the registered EdgeLab workflow.</div>
    """,
    unsafe_allow_html=True,
)
