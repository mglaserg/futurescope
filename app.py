from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Futurescope", page_icon="📈", layout="wide")

st.title("Futurescope")
st.caption("Futures term structure, basis, carry, and VIX-complex research")

key_ok = bool(os.getenv("DATABENTO_API_KEY"))
if key_ok:
    st.success("Databento API key detected.")
else:
    st.warning("Databento API key not found. Add DATABENTO_API_KEY to a .env file before loading futures curves.")

st.markdown(
    """
### V1 workflow

Use the pages in the sidebar:

- **Carry Screener** — compare GC, CL, ES, ZN, and VX at one as-of date.
- **Curve Explorer** — inspect an individual curve, spot basis when available, and implied carry.
- **VIX Complex** — view VX futures alongside official Cboe VIX-family indices.

Futurescope distinguishes **spot-vs-futures basis** from **calendar-curve carry**. A positive basis is not automatically an arbitrage: financing, storage, dividends/income, execution, and margin liquidity still matter.

V1 intentionally uses Databento's **historical API** rather than requiring a live exchange-data license. Requests are cached locally in `cache/`.
"""
)

st.info("Start with Curve Explorer → GC to validate your Databento connection, then open the screener.")
