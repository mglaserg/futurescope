from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import requests

from futurescope.cache import LocalFrameCache


class GoldSpotReferenceProvider:
    """XAU/USD daily spot reference from goldprice.dev.

    The endpoint supports recent daily XAU/USD bars without requiring a key.
    We cache each as-of lookup locally so revisiting the same date does not
    make another network request. An optional GOLDPRICE_API_KEY can be supplied
    to lift anonymous request limits, but it is not required for recent data.
    """

    BASE_URL = "https://api.goldprice.dev/v1"

    def __init__(self, cache: LocalFrameCache | None = None) -> None:
        self.cache = cache or LocalFrameCache()

    def _headers(self) -> dict[str, str]:
        key = os.getenv("GOLDPRICE_API_KEY")
        return {"Authorization": f"Bearer {key}"} if key else {}

    def close_as_of(self, as_of: date, refresh: bool = False) -> float | None:
        cache_key = f"goldprice.dev:XAU-USD-SPOT:1d:{as_of.isoformat()}"
        if not refresh:
            cached = self.cache.read(cache_key)
            if cached is not None and not cached.empty and "close" in cached.columns:
                value = pd.to_numeric(cached["close"], errors="coerce").dropna()
                if not value.empty:
                    return float(value.iloc[-1])

        # Request a small window so weekends/holidays can fall back to the most
        # recent settled daily bar at or before the requested date.
        start = as_of - timedelta(days=7)
        response = requests.get(
            f"{self.BASE_URL}/bars",
            params={
                "symbol": "XAU-USD-SPOT",
                "interval": "1d",
                "from": start.isoformat(),
                "to": as_of.isoformat(),
                "limit": 20,
            },
            headers=self._headers(),
            timeout=15,
        )
        if response.status_code == 429:
            raise RuntimeError(
                "goldprice.dev anonymous rate limit reached. Wait and retry, or set optional GOLDPRICE_API_KEY."
            )
        if response.status_code in {400, 403}:
            detail = response.text[:250]
            raise RuntimeError(
                "XAU/USD history is unavailable for that date on the current goldprice.dev access window. "
                f"Recent daily history is free; older history may require a paid tier. Provider response: {detail}"
            )
        response.raise_for_status()

        payload = response.json()
        bars = payload.get("bars", []) if isinstance(payload, dict) else []
        if not bars:
            return None

        frame = pd.DataFrame(bars)
        if "bar_start" not in frame.columns or "close" not in frame.columns:
            return None
        frame["bar_start"] = pd.to_datetime(frame["bar_start"], utc=True, errors="coerce")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=["bar_start", "close"])
        frame = frame[frame["bar_start"].dt.date <= as_of].sort_values("bar_start")
        if frame.empty:
            return None

        selected = frame.tail(1)[["bar_start", "close"]].copy()
        self.cache.write(cache_key, selected)
        return float(selected["close"].iloc[0])


class YahooReferenceProvider:
    """Convenience provider for cash indices still sourced from Yahoo in V1."""

    def close_as_of(self, symbol: str, as_of: date) -> float | None:
        import yfinance as yf

        start = as_of - timedelta(days=10)
        end = as_of + timedelta(days=1)
        frame = yf.download(
            symbol,
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=False,
        )
        if frame.empty:
            return None
        close = frame["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if close.empty:
            return None
        return float(close.iloc[-1])
