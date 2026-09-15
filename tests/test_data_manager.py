from datetime import date

import pandas as pd
import pytest

from futurescope.data_manager import backfill_curve_history, cache_status, planned_snapshot_dates
from futurescope.rv_store import CurveSnapshotStore


def test_planned_snapshot_dates_business_daily():
    dates = planned_snapshot_dates(date(2026, 9, 11), date(2026, 9, 15), "business_daily")
    assert dates == [date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15)]


def test_planned_snapshot_dates_rejects_reverse_range():
    with pytest.raises(ValueError):
        planned_snapshot_dates(date(2026, 9, 15), date(2026, 9, 11), "business_daily")


def test_backfill_reuses_existing_snapshots(tmp_path, monkeypatch):
    store = CurveSnapshotStore(tmp_path / "snapshots")
    existing_date = date(2026, 9, 14)
    store.write(
        "GC",
        existing_date,
        pd.DataFrame({"raw_symbol": ["GCZ6"], "expiration": pd.to_datetime(["2026-12-29"], utc=True), "close": [3700.0]}),
    )

    calls: list[date] = []

    def fake_load(config, as_of, refresh=False, store=None):
        calls.append(as_of)
        frame = pd.DataFrame({"raw_symbol": ["GCZ6"], "expiration": pd.to_datetime(["2026-12-29"], utc=True), "close": [3700.0]})
        store.write("GC", as_of, frame)
        return frame

    monkeypatch.setattr("futurescope.data_manager.load_futurescope_env", lambda: None)
    monkeypatch.setattr("futurescope.data_manager.load_relative_value_curve", fake_load)

    result = backfill_curve_history(
        "GC",
        date(2026, 9, 14),
        date(2026, 9, 15),
        sampling="business_daily",
        store=store,
    )

    assert calls == [date(2026, 9, 15)]
    assert result["downloaded"] == 1
    assert result["skipped_cached"] == 1
    assert result["status"]["snapshots"] == 2


def test_backfill_force_refresh_redownloads_existing(tmp_path, monkeypatch):
    store = CurveSnapshotStore(tmp_path / "snapshots")
    snapshot_date = date(2026, 9, 15)
    store.write(
        "GC",
        snapshot_date,
        pd.DataFrame({"raw_symbol": ["GCZ6"], "expiration": pd.to_datetime(["2026-12-29"], utc=True), "close": [3700.0]}),
    )
    seen_refresh: list[bool] = []

    def fake_load(config, as_of, refresh=False, store=None):
        seen_refresh.append(refresh)
        return pd.DataFrame({"raw_symbol": ["GCZ6"], "expiration": pd.to_datetime(["2026-12-29"], utc=True), "close": [3701.0]})

    monkeypatch.setattr("futurescope.data_manager.load_futurescope_env", lambda: None)
    monkeypatch.setattr("futurescope.data_manager.load_relative_value_curve", fake_load)

    result = backfill_curve_history(
        "GC", snapshot_date, snapshot_date, force_refresh=True, store=store
    )

    assert seen_refresh == [True]
    assert result["downloaded"] == 1
    assert result["skipped_cached"] == 0


def test_cache_status_empty(tmp_path):
    status = cache_status("ES", CurveSnapshotStore(tmp_path / "snapshots"))
    assert status.snapshots == 0
    assert status.first_snapshot is None
    assert status.last_snapshot is None
