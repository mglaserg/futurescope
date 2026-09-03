from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Futurescope", page_icon="📈", layout="wide")

st.title("Futurescope")
st.caption("Futures curve relative value, carry, basis, and VIX-complex research")

key_ok = bool(os.getenv("DATABENTO_API_KEY"))
if key_ok:
    st.success("Databento API key detected.")
else:
    st.warning("Databento API key not found. Add DATABENTO_API_KEY to a .env file before loading futures curves.")

st.markdown(
    """
### Current workflow

- **ES + GC Monitor** — preferred current-state screen. Shows curve shape, current z-score/percentile, and exchange-listed spread-book liquidity/costs without revealing conditional forward outcomes.
- **Relative Value** — slope, butterfly, and double-butterfly finite-difference research. Historical diagnostics are logged as research looks.
- **Trade Builder** — translates LONG/SHORT RV structures into exact futures baskets and dollar economics.
- **Historical Playback** — replay cached curves; explicit future-outcome reveals are logged.
- **Daily Opportunities** — historical grid-search surface; every scan is logged before results are shown.
- **Carry Screener / Curve Explorer / VIX Complex** — original market and term-structure views.

Futurescope keeps **spot-vs-futures basis**, **calendar-curve relative value**, and **VIX term structure** conceptually separate. Crypto perpetual carry remains outside the Futurescope core project.

The research rule is now simple: **current state is cheap to inspect; historical outcome questions are counted.** See `docs/research_protocol.md` and `research_cli.py` for the lightweight SQLite/YAML audit workflow.
"""
)

st.info("Start with **ES + GC Monitor** for the validation-safe current-state workflow.")
