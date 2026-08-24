from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from futurescope.analytics import curve_state, excess_carry
from futurescope.config import MARKETS
from futurescope.services import load_market_curve

load_dotenv()
st.set_page_config(page_title="Carry Screener | Futurescope", layout="wide")
st.title("Carry Screener")
st.caption("Cross-market futures curve snapshot. Spot-based carry is shown only where a usable reference is configured.")

c1, c2, c3 = st.columns(3)
with c1:
    as_of = st.date_input("As-of date", value=date.today() - timedelta(days=1))
with c2:
    financing_pct = st.number_input("Financing rate (%)", value=4.0, step=0.25)
with c3:
    refresh = st.checkbox("Refresh cached market data", value=False)

rows: list[dict] = []
errors: list[str] = []

with st.spinner("Loading futures curves..."):
    for symbol, config in MARKETS.items():
        try:
            curve, spot, spot_source = load_market_curve(config, as_of, refresh=refresh)
            if curve.empty:
                errors.append(f"{symbol}: no curve returned")
                continue
            front = curve.iloc[0]
            second = curve.iloc[1] if len(curve) > 1 else None
            implied = float(front["ann_implied_carry"]) if pd.notna(front["ann_implied_carry"]) else np.nan
            rows.append(
                {
                    "Market": symbol,
                    "Name": config.name,
                    "State": curve_state(curve),
                    "Reference": spot,
                    "Front": float(front["close"]),
                    "Front expiry": front["expiration"].date(),
                    "DTE": round(float(front["dte"]), 1),
                    "Spot basis %": 100 * float(front["basis_pct"]) if pd.notna(front["basis_pct"]) else np.nan,
                    "Ann. implied carry %": 100 * implied if pd.notna(implied) else np.nan,
                    "Excess vs financing %": 100 * excess_carry(implied, financing_pct / 100.0) if pd.notna(implied) else np.nan,
                    "M1→M2 %": 100 * (float(second["close"]) / float(front["close"]) - 1.0) if second is not None else np.nan,
                    "Reference source": spot_source,
                }
            )
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")

result = pd.DataFrame(rows)
if not result.empty:
    st.dataframe(
        result,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Reference": st.column_config.NumberColumn(format="%.3f"),
            "Front": st.column_config.NumberColumn(format="%.3f"),
            "Spot basis %": st.column_config.NumberColumn(format="%.2f%%"),
            "Ann. implied carry %": st.column_config.NumberColumn(format="%.2f%%"),
            "Excess vs financing %": st.column_config.NumberColumn(format="%.2f%%"),
            "M1→M2 %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

    spot_rank = result.dropna(subset=["Excess vs financing %"]).sort_values("Excess vs financing %", ascending=False)
    if not spot_rank.empty:
        best = spot_rank.iloc[0]
        st.info(
            f"Highest simple spot-basis excess in this snapshot: {best['Market']} at "
            f"{best['Excess vs financing %']:.2f}% annualized before market-specific storage/income/execution adjustments."
        )
else:
    st.error("No markets loaded. Confirm DATABENTO_API_KEY and your dataset entitlements.")

if errors:
    with st.expander("Load warnings"):
        for error in errors:
            st.write("•", error)

st.caption("Important: 'Excess vs financing' is a first-pass screen, not a trade signal. Market-specific carry terms must be added before treating basis as excess return.")
