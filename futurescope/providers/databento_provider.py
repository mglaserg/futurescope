from __future__ import annotations

from datetime import date, timedelta
import os
from typing import Any

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
        self._availability_cache: dict[tuple[str, str], pd.Timestamp] = {}

    @staticmethod
    def _flatten(frame: pd.DataFrame) -> pd.DataFrame:
        if isinstance(frame.index, pd.MultiIndex) or frame.index.name is not None:
            frame = frame.reset_index()
        return frame.copy()

    @staticmethod
    def _utc_timestamp(value: Any) -> pd.Timestamp:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            return ts.tz_localize("UTC")
        return ts.tz_convert("UTC")

    def _available_end(self, dataset: str, schema: str) -> pd.Timestamp:
        """Return Databento's exclusive available end for one schema.

        Historical availability can stop intraday on the current date.  Asking
        for the next UTC midnight therefore produces Databento's
        ``data_end_after_available_end`` 422.  Cache the metadata lookup for the
        lifetime of this provider and prefer the schema-specific range when it
        is supplied.
        """
        cache_key = (dataset, schema)
        cached = self._availability_cache.get(cache_key)
        if cached is not None:
            return cached

        available = self.client.metadata.get_dataset_range(dataset=dataset)
        schema_ranges = available.get("schema", {}) if isinstance(available, dict) else {}
        schema_range = schema_ranges.get(schema, {}) if isinstance(schema_ranges, dict) else {}
        raw_end = schema_range.get("end") if isinstance(schema_range, dict) else None
        if not raw_end and isinstance(available, dict):
            raw_end = available.get("end")
        if not raw_end:
            raise RuntimeError(f"Databento did not report an available end for {dataset}/{schema}.")

        end = self._utc_timestamp(raw_end)
        self._availability_cache[cache_key] = end
        return end

    def _bounded_window(
        self,
        dataset: str,
        schema: str,
        start: Any,
        end: Any,
    ) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        """Clamp a historical request to Databento's actual schema range."""
        start_ts = self._utc_timestamp(start)
        requested_end = self._utc_timestamp(end)
        safe_end = min(requested_end, self._available_end(dataset, schema))
        if safe_end <= start_ts:
            return None
        return start_ts, safe_end

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

        window = self._bounded_window(
            dataset, "definition", as_of - timedelta(days=3), as_of + timedelta(days=1)
        )
        if window is None:
            return pd.DataFrame()
        start, end = window
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
        # Current-day requests are clipped to Databento's schema-specific available end.
        window = self._bounded_window(
            dataset, "ohlcv-1d", as_of - timedelta(days=10), as_of + timedelta(days=1)
        )
        if window is None:
            return pd.DataFrame()
        start, end = window
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


    def get_strategy_definitions(
        self,
        dataset: str,
        parent_symbol: str,
        as_of: date,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Return raw parent definitions including exchange-listed spread legs.

        Parent futures symbology includes both outrights and futures spreads.
        Unlike ``_definitions`` this method intentionally preserves the ``leg_*``
        fields so callers can match exchange-listed calendars/flies to the
        canonical Futurescope baskets.
        """
        key = f"strategy-definitions|{dataset}|{parent_symbol}|{as_of.isoformat()}"
        if not refresh:
            cached = self.cache.read(key)
            if cached is not None:
                for column in ("expiration", "ts_event"):
                    if column in cached.columns:
                        cached[column] = pd.to_datetime(cached[column], utc=True, errors="coerce")
                return cached

        window = self._bounded_window(
            dataset, "definition", as_of - timedelta(days=3), as_of + timedelta(days=1)
        )
        if window is None:
            return pd.DataFrame()
        start, end = window
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

        keep_candidates = [
            "ts_event",
            "instrument_id",
            "raw_symbol",
            "instrument_class",
            "security_update_action",
            "expiration",
            "min_price_increment",
            "leg_count",
            "leg_index",
            "leg_instrument_id",
            "leg_raw_symbol",
            "leg_side",
            "leg_ratio_qty_numerator",
            "leg_ratio_qty_denominator",
        ]
        frame = frame[[c for c in keep_candidates if c in frame.columns]].copy()
        if "expiration" in frame.columns:
            frame["expiration"] = pd.to_datetime(frame["expiration"], utc=True, errors="coerce")
        if "ts_event" in frame.columns:
            frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True, errors="coerce")
            frame = frame.sort_values("ts_event")
        self.cache.write(key, frame)
        return frame

    def get_bbo_snapshot(
        self,
        dataset: str,
        instrument_ids: list[int],
        snapshot_ts,
        refresh: bool = False,
        lookback_minutes: int = 15,
    ) -> pd.DataFrame:
        """Return the last one-minute BBO at/before ``snapshot_ts`` per instrument."""
        if not instrument_ids:
            return pd.DataFrame()
        snapshot = pd.Timestamp(snapshot_ts)
        if snapshot.tzinfo is None:
            snapshot = snapshot.tz_localize("UTC")
        else:
            snapshot = snapshot.tz_convert("UTC")
        ids = sorted({int(x) for x in instrument_ids})
        key = (
            f"bbo-1m|{dataset}|{','.join(map(str, ids))}|"
            f"{snapshot.isoformat()}|{lookback_minutes}"
        )
        if not refresh:
            cached = self.cache.read(key)
            if cached is not None:
                for column in ("ts_recv", "ts_event"):
                    if column in cached.columns:
                        cached[column] = pd.to_datetime(cached[column], utc=True, errors="coerce")
                return cached

        requested_start = snapshot - pd.Timedelta(minutes=int(lookback_minutes))
        requested_end = snapshot + pd.Timedelta(minutes=1)
        window = self._bounded_window(dataset, "bbo-1m", requested_start, requested_end)
        if window is None:
            return pd.DataFrame()
        start, end = window
        data = self.client.timeseries.get_range(
            dataset=dataset,
            symbols=[str(x) for x in ids],
            stype_in="instrument_id",
            schema="bbo-1m",
            start=start.isoformat(),
            end=end.isoformat(),
        )
        frame = self._flatten(data.to_df())
        if frame.empty:
            return frame
        for column in ("ts_recv", "ts_event"):
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
        # BBO interval records are timestamped by ts_recv at the interval boundary.
        # ts_event can refer to the last trade/update carried in the record, so it
        # is not the right field for an as-of interval cutoff.
        timestamp_col = "ts_recv" if "ts_recv" in frame.columns else "ts_event"
        if timestamp_col in frame.columns:
            frame = frame[frame[timestamp_col] <= snapshot].sort_values(timestamp_col)
        if "instrument_id" in frame.columns:
            frame = frame.drop_duplicates("instrument_id", keep="last")
        self.cache.write(key, frame)
        return frame

    def get_daily_instrument_volume(
        self,
        dataset: str,
        instrument_ids: list[int],
        as_of: date,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Return daily traded volume for listed strategy instruments."""
        if not instrument_ids:
            return pd.DataFrame()
        ids = sorted({int(x) for x in instrument_ids})
        key = f"strategy-volume|{dataset}|{','.join(map(str, ids))}|{as_of.isoformat()}"
        if not refresh:
            cached = self.cache.read(key)
            if cached is not None:
                if "ts_event" in cached.columns:
                    cached["ts_event"] = pd.to_datetime(cached["ts_event"], utc=True, errors="coerce")
                return cached

        window = self._bounded_window(dataset, "ohlcv-1d", as_of, as_of + timedelta(days=1))
        if window is None:
            return pd.DataFrame()
        start, end = window
        data = self.client.timeseries.get_range(
            dataset=dataset,
            symbols=[str(x) for x in ids],
            stype_in="instrument_id",
            schema="ohlcv-1d",
            start=start.isoformat(),
            end=end.isoformat(),
        )
        frame = self._flatten(data.to_df())
        if frame.empty:
            return frame
        keep = [c for c in ["ts_event", "instrument_id", "volume"] if c in frame.columns]
        frame = frame[keep].copy()
        if "ts_event" in frame.columns:
            frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True, errors="coerce")
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
