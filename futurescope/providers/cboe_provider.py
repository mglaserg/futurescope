from __future__ import annotations

from datetime import date

import pandas as pd
import requests

from futurescope.config import CBOE_INDEX_URLS


class CboeIndexProvider:
    """Official Cboe daily index CSVs. No API key required."""

    def history(self, symbol: str) -> pd.DataFrame:
        if symbol not in CBOE_INDEX_URLS:
            raise KeyError(f"No Cboe URL configured for {symbol}")
        url = CBOE_INDEX_URLS[symbol]
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        from io import StringIO

        frame = pd.read_csv(StringIO(response.text))
        frame.columns = [str(c).strip().upper() for c in frame.columns]
        frame["DATE"] = pd.to_datetime(frame["DATE"], errors="coerce")
        return frame.dropna(subset=["DATE"]).sort_values("DATE")

    def close_as_of(self, symbol: str, as_of: date) -> float | None:
        frame = self.history(symbol)
        rows = frame[frame["DATE"].dt.date <= as_of]
        if rows.empty:
            return None
        return float(rows.iloc[-1]["CLOSE"])

    def latest_snapshot(self, symbols: list[str]) -> pd.DataFrame:
        rows = []
        for symbol in symbols:
            try:
                frame = self.history(symbol)
                last = frame.iloc[-1]
                rows.append(
                    {
                        "symbol": symbol,
                        "date": last["DATE"],
                        "close": float(last["CLOSE"]),
                    }
                )
            except Exception as exc:  # keep the dashboard alive if one CSV is unavailable
                rows.append({"symbol": symbol, "date": pd.NaT, "close": float("nan"), "error": str(exc)})
        return pd.DataFrame(rows)
