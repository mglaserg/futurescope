from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from futurescope.ui import apply_futurescope_theme, hero

load_dotenv()

st.set_page_config(page_title="Futurescope", page_icon="📈", layout="wide")
apply_futurescope_theme()
hero(
    "FUTURES RESEARCH INSTRUMENT",
    "Futurescope",
    "A disciplined workspace for futures curves, relative value, carry, basis, calendar flows, and VIX term structure — with current-state monitoring kept separate from registered historical research.",
    ["Databento", "Curve RV", "Trade Builder", "Audit-first research"],
)

key_ok = bool(os.getenv("DATABENTO_API_KEY"))
if key_ok:
    st.success("Databento API key detected.")
else:
    st.warning("Databento API key not found. Add DATABENTO_API_KEY to a .env file before loading futures curves.")

st.markdown(
    """
### Current workflow

- **Month-End Rebalance** — **high-priority flow monitor**. SPY/IEF estimate 60/40 rebalance pressure; execute the equity leg with MES or SPY and the duration leg with TLT.
- **ES + GC Monitor** — preferred current-state curve screen. Shows curve shape, current z-score/percentile, and exchange-listed spread-book liquidity/costs without revealing conditional forward outcomes.
- **Relative Value** — slope, butterfly, and double-butterfly finite-difference research. Historical diagnostics are logged as research looks.
- **Trade Builder** — translates LONG/SHORT RV structures into exact futures baskets and dollar economics.
- **Historical Playback** — replay cached curves; explicit future-outcome reveals are logged.
- **Daily Opportunities** — historical grid-search surface; every scan is logged before results are shown.
- **Carry Screener / Curve Explorer / VIX Complex** — original market and term-structure views.

Futurescope keeps **spot-vs-futures basis**, **calendar-curve relative value**, and **VIX term structure** conceptually separate. Crypto perpetual carry remains outside the Futurescope core project.

The research rule is now simple: **current state is cheap to inspect; historical outcome questions are counted.** See `docs/research_protocol.md` and `research_cli.py` for the lightweight SQLite/YAML audit workflow.
"""
)

st.info("For the new calendar-flow trade, start with **Month-End Rebalance**. For curve RV, start with **ES + GC Monitor**.")
