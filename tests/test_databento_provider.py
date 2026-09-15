from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from futurescope.providers.databento_provider import DatabentoProvider


class _FakeMetadata:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def get_dataset_range(self, dataset):
        self.calls += 1
        return self.payload


class _FakeTimeseries:
    def __init__(self):
        self.calls = []

    def get_range(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            to_df=lambda: pd.DataFrame(
                {
                    "instrument_id": [1],
                    "ts_event": pd.to_datetime(["2026-09-15T00:00:00Z"]),
                    "close": [100.0],
                }
            )
        )


class _FakeCache:
    def read(self, key):
        return None

    def write(self, key, frame):
        return None


def _provider(available_end="2026-09-15T14:20:00Z"):
    provider = DatabentoProvider.__new__(DatabentoProvider)
    provider.client = SimpleNamespace(
        metadata=_FakeMetadata(
            {
                "start": "2010-06-06T00:00:00Z",
                "end": "2026-09-15T14:25:00Z",
                "schema": {
                    "ohlcv-1d": {
                        "start": "2010-06-06T00:00:00Z",
                        "end": available_end,
                    },
                    "definition": {
                        "start": "2010-06-06T00:00:00Z",
                        "end": "2026-09-15T14:22:00Z",
                    },
                },
            }
        ),
        timeseries=_FakeTimeseries(),
    )
    provider.cache = _FakeCache()
    provider._availability_cache = {}
    provider.db = SimpleNamespace(InstrumentClass=SimpleNamespace(FUTURE="F"))
    return provider


def test_bounded_window_clips_today_to_schema_available_end():
    provider = _provider()
    start, end = provider._bounded_window(
        "GLBX.MDP3",
        "ohlcv-1d",
        "2026-09-05T00:00:00Z",
        "2026-09-16T00:00:00Z",
    )
    assert start == pd.Timestamp("2026-09-05T00:00:00Z")
    assert end == pd.Timestamp("2026-09-15T14:20:00Z")


def test_available_end_prefers_schema_range_and_caches_lookup():
    provider = _provider()
    first = provider._available_end("GLBX.MDP3", "ohlcv-1d")
    second = provider._available_end("GLBX.MDP3", "ohlcv-1d")
    assert first == pd.Timestamp("2026-09-15T14:20:00Z")
    assert second == first
    assert provider.client.metadata.calls == 1


def test_daily_bars_uses_clipped_end_instead_of_next_midnight():
    provider = _provider()
    frame = provider._daily_bars("GLBX.MDP3", "GC.FUT", date(2026, 9, 15), refresh=True)
    assert not frame.empty
    call = provider.client.timeseries.calls[-1]
    assert pd.Timestamp(call["end"]) == pd.Timestamp("2026-09-15T14:20:00Z")
    assert pd.Timestamp(call["end"]) < pd.Timestamp("2026-09-16T00:00:00Z")


def test_bounded_window_returns_none_when_schema_has_no_data_after_start():
    provider = _provider(available_end="2026-09-14T23:59:00Z")
    assert provider._bounded_window(
        "GLBX.MDP3",
        "ohlcv-1d",
        "2026-09-15T00:00:00Z",
        "2026-09-16T00:00:00Z",
    ) is None
