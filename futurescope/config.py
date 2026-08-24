from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketConfig:
    symbol: str
    name: str
    dataset: str
    parent_symbol: str
    reference_symbol: str | None = None
    reference_source: str | None = None
    units: str = "price"
    max_contracts: int = 12


MARKETS: dict[str, MarketConfig] = {
    "GC": MarketConfig(
        symbol="GC",
        name="COMEX Gold",
        dataset="GLBX.MDP3",
        parent_symbol="GC.FUT",
        reference_symbol="XAU-USD-SPOT",
        reference_source="goldprice.dev XAU/USD spot",
        units="USD/oz",
    ),
    "CL": MarketConfig(
        symbol="CL",
        name="NYMEX WTI Crude Oil",
        dataset="GLBX.MDP3",
        parent_symbol="CL.FUT",
        reference_symbol=None,
        reference_source=None,
        units="USD/bbl",
    ),
    "ES": MarketConfig(
        symbol="ES",
        name="E-mini S&P 500",
        dataset="GLBX.MDP3",
        parent_symbol="ES.FUT",
        reference_symbol="^GSPC",
        reference_source="Yahoo S&P 500 index",
        units="index points",
    ),
    "ZN": MarketConfig(
        symbol="ZN",
        name="10-Year U.S. Treasury Note",
        dataset="GLBX.MDP3",
        parent_symbol="ZN.FUT",
        reference_symbol=None,
        reference_source=None,
        units="price points",
    ),
    "VX": MarketConfig(
        symbol="VX",
        name="Cboe VIX Futures",
        dataset="XCBF.PITCH",
        parent_symbol="VX.FUT",
        reference_symbol="VIX",
        reference_source="Cboe VIX index",
        units="vol points",
    ),
}

CBOE_INDEX_URLS = {
    "VIX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
    "VIX9D": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv",
    "VIX3M": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv",
    "VIX6M": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX6M_History.csv",
    "VIX1Y": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX1Y_History.csv",
    "VVIX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv",
    "OVX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/OVX_History.csv",
    "GVZ": "https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv",
}
