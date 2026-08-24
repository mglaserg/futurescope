from __future__ import annotations

from datetime import date, timedelta
import os

import pandas as pd

from futurescope.cache import LocalFrameCache


class DatabentoProvider:
    def __init__(self, api_key: str | None = None, cache_dir: str = "cache") -> None:
        self.api_key = api_key or os.getenv("DATABENTO_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "DATABENTO_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        import databento as db

        self.db = db
        self.client = db.Historical(self.api_key)
        self.cache = LocalFrameCache(cache_dir)

    @staticmethod
    def _flatten(frame: pd.DataFrame) -> pd.DataFrame:
        if isinstance(frame.index, pd.MultiIndex) or frame.index.name is not None:
            frame = frame.reset_index()
        return frame.copy()

    def _definitions(
        self,
        dataset: str,
        parent_symbol: str,
        as_of: date,
        refresh: bool = False,
    ) -> pd.DataFrame:
        key = f"definitions|{dataset}|{parent_symbol}|{as_of.isoformat()}"
        if not refresh:
            cached = self.cache.read(key)
            if cached is not None:
                cached["expiration"] = pd.to_datetime(cached["expiration"], utc=True)
                return cached

        start = as_of - timedelta(days=3)
        end = as_of + timedelta(days=1)
        data = self.client.timeseries.get_range(
            dataset=dataset,
            symbols=parent_symbol,
            stype_in="parent",
            schema="definition",
            start=start.isoformat(),
            end=end.isoformat(),
        )
        frame = self._flatten(data.to_df())
        if frame.empty:
            return frame

        # Parent symbology can include calendar spreads. Keep outright futures only.
        if "instrument_class" in frame.columns:
            frame = frame[frame["instrument_class"] == self.db.InstrumentClass.FUTURE]

        keep = [c for c in ["ts_event", "instrument_id", "raw_symbol", "expiration"] if c in frame.columns]
        frame = frame[keep].copy()
        frame["expiration"] = pd.to_datetime(frame["expiration"], utc=True, errors="coerce")
        if "ts_event" in frame.columns:
            frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True, errors="coerce")
            frame = frame.sort_values("ts_event")
        frame = frame.dropna(subset=["instrument_id", "expiration"]).drop_duplicates(
            subset=["instrument_id"], keep="last"
        )
        self.cache.write(key, frame)
        return frame

    def _daily_bars(
        self,
        dataset: str,
        parent_symbol: str,
        as_of: date,
        refresh: bool = False,
    ) -> pd.DataFrame:
        key = f"daily-bars|{dataset}|{parent_symbol}|{as_of.isoformat()}"
        if not refresh:
            cached = self.cache.read(key)
            if cached is not None:
                if "ts_event" in cached.columns:
                    cached["ts_event"] = pd.to_datetime(cached["ts_event"], utc=True)
                return cached

        # Look back far enough to survive weekends/holidays, then keep each contract's last bar.
        start = as_of - timedelta(days=10)
        end = as_of + timedelta(days=1)
        data = self.client.timeseries.get_range(
            dataset=dataset,
            symbols=parent_symbol,
            stype_in="parent",
            schema="ohlcv-1d",
            start=start.isoformat(),
            end=end.isoformat(),
        )
        frame = self._flatten(data.to_df())
        if frame.empty:
            return frame
        if "ts_event" in frame.columns:
            frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True, errors="coerce")
            frame = frame.sort_values("ts_event")
        self.cache.write(key, frame)
        return frame

    def get_curve(
        self,
        dataset: str,
        parent_symbol: str,
        as_of: date,
        max_contracts: int = 12,
        refresh: bool = False,
    ) -> pd.DataFrame:
        definitions = self._definitions(dataset, parent_symbol, as_of, refresh=refresh)
        bars = self._daily_bars(dataset, parent_symbol, as_of, refresh=refresh)
        if definitions.empty or bars.empty:
            return pd.DataFrame()

        if "instrument_id" not in bars.columns:
            raise RuntimeError("Databento OHLCV response did not include instrument_id.")

        bars = bars.dropna(subset=["instrument_id", "close"]).copy()
        if "ts_event" in bars.columns:
            bars = bars.sort_values("ts_event").drop_duplicates("instrument_id", keep="last")
        else:
            bars = bars.drop_duplicates("instrument_id", keep="last")

        curve = definitions.merge(
            bars[[c for c in ["instrument_id", "ts_event", "close", "volume"] if c in bars.columns]],
            on="instrument_id",
            how="inner",
            suffixes=("_def", "_bar"),
        )
        curve = curve[curve["expiration"] > pd.Timestamp(as_of, tz="UTC")]
        curve = curve.sort_values("expiration").head(max_contracts).reset_index(drop=True)
        return curve
