from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from futurescope.ui import apply_futurescope_theme, hero

load_dotenv()
st.set_page_config(page_title="Futurescope", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
apply_futurescope_theme()


def home() -> None:
    hero(
        "START HERE · ONE QUESTION AT A TIME",
        "Futurescope",
        "Futurescope is a futures decision system, not a pile of charts. Start with what you want to know: monitor today's market, translate a trade, or run registered research. Advanced reference screens stay out of the way until you need them.",
        ["Databento", "Constant maturity", "Curve RV", "Conductor-ready"],
    )

    key_ok = bool(os.getenv("DATABENTO_API_KEY"))
    if key_ok:
        st.caption("● Databento connected · current-state pages are ready to load.")
    else:
        st.warning("Databento API key not found. Add DATABENTO_API_KEY to `.env` before loading futures curves.")

    st.markdown("## What do you want to do?")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="fs-card fs-workflow-card">
              <div class="fs-kicker">1 · SEE TODAY</div>
              <h4>What is unusual right now?</h4>
              <p>Start with clean current-state measurements. No hidden historical outcome search.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("pages/8_ES_GC_Monitor.py", label="ES + GC Monitor", icon="📡")
        st.page_link("pages/11_Synthetic_Tenors.py", label="Synthetic 50d / 80d", icon="📐")
        st.page_link("pages/9_Month_End_Rebalance.py", label="Month-End Flow", icon="🗓️")
        st.page_link("pages/10_Cross_Market_Curve_Carry.py", label="Cross-Market Carry", icon="↕️")
    with col2:
        st.markdown(
            """
            <div class="fs-card fs-workflow-card">
              <div class="fs-kicker">2 · EXPRESS IT</div>
              <h4>What exactly is the trade?</h4>
              <p>Translate an RV idea into real futures legs and a broker-agnostic Conductor intent.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("pages/5_Trade_Builder.py", label="Trade Builder", icon="🧩")
        st.markdown(
            '<div class="fs-note"><strong>Boundary:</strong> Futurescope says what it wants. Conductor owns sizing, risk permission, integer lots, execution, and reconciliation.</div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """
            <div class="fs-card fs-workflow-card">
              <div class="fs-kicker">3 · PROVE IT</div>
              <h4>Does the idea actually have edge?</h4>
              <p>Historical outcome questions belong in the registered research workflow and count as looks.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("pages/4_Relative_Value.py", label="Relative Value Research", icon="〽️")
        st.page_link("pages/6_Historical_Playback.py", label="Historical Playback", icon="⏪")
        st.page_link("pages/7_Daily_Opportunities.py", label="Opportunity Research", icon="🔬")

    st.divider()
    st.markdown("### The product in one line")
    st.markdown(
        """
        <div class="fs-flow-strip">
          <div><strong>Measure state</strong><span>curve · z-score · carry · liquidity</span></div>
          <div class="arrow">→</div>
          <div><strong>Validate edge</strong><span>registered research · uncertainty · costs</span></div>
          <div class="arrow">→</div>
          <div><strong>Emit intent</strong><span>LONG / SHORT / ROTATE · lifecycle</span></div>
          <div class="arrow">→</div>
          <div><strong>Conductor</strong><span>size · risk · execute · reconcile</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Need the older/raw views? They are still available under **Deep Dive** in the top navigation.")


pages = {
    "": [
        st.Page(home, title="Start", icon="🏠", default=True, url_path="start"),
        st.Page("pages/8_ES_GC_Monitor.py", title="Monitor", icon="📡", url_path="monitor"),
        st.Page("pages/11_Synthetic_Tenors.py", title="Synthetic Tenors", icon="📐", url_path="synthetic-tenors"),
    ],
    "Trade": [
        st.Page("pages/5_Trade_Builder.py", title="Trade Builder", icon="🧩", url_path="trade-builder"),
        st.Page("pages/9_Month_End_Rebalance.py", title="Month-End Rebalance", icon="🗓️", url_path="month-end"),
        st.Page("pages/10_Cross_Market_Curve_Carry.py", title="Curve Carry", icon="↕️", url_path="curve-carry"),
    ],
    "Research": [
        st.Page("pages/4_Relative_Value.py", title="Relative Value", icon="〽️", url_path="relative-value"),
        st.Page("pages/6_Historical_Playback.py", title="Historical Playback", icon="⏪", url_path="playback"),
        st.Page("pages/7_Daily_Opportunities.py", title="Opportunity Research", icon="🔬", url_path="opportunities"),
    ],
    "Deep Dive": [
        st.Page("pages/2_Curve_Explorer.py", title="Curve Explorer", icon="📈", url_path="curve-explorer"),
        st.Page("pages/1_Carry_Screener.py", title="Carry & Basis", icon="⚖️", url_path="carry-basis"),
        st.Page("pages/3_VIX_Complex.py", title="VIX Complex", icon="🌪️", url_path="vix-complex"),
    ],
}

navigation = st.navigation(pages, position="top")
navigation.run()
