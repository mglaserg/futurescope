from __future__ import annotations

from datetime import date

import pandas as pd

from futurescope.analytics import enrich_curve
from futurescope.config import MarketConfig
from futurescope.providers import (
    CboeIndexProvider,
    DatabentoProvider,
    GoldSpotReferenceProvider,
    YahooReferenceProvider,
)


def get_reference_price(config: MarketConfig, as_of: date) -> tuple[float | None, str | None]:
    if not config.reference_symbol:
        return None, None
    try:
        if config.reference_symbol == "VIX":
            value = CboeIndexProvider().close_as_of("VIX", as_of)
        elif config.reference_symbol == "XAU-USD-SPOT":
            value = GoldSpotReferenceProvider().close_as_of(as_of)
        else:
            value = YahooReferenceProvider().close_as_of(config.reference_symbol, as_of)
        return value, config.reference_source
    except Exception as exc:
        return None, f"Reference unavailable: {exc}"


def load_market_curve(
    config: MarketConfig,
    as_of: date,
    refresh: bool = False,
) -> tuple[pd.DataFrame, float | None, str | None]:
    provider = DatabentoProvider()
    raw = provider.get_curve(
        dataset=config.dataset,
        parent_symbol=config.parent_symbol,
        as_of=as_of,
        max_contracts=config.max_contracts,
        refresh=refresh,
    )
    spot, spot_source = get_reference_price(config, as_of)
    enriched = enrich_curve(raw, pd.Timestamp(as_of), spot=spot)
    return enriched, spot, spot_source
