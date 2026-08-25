from datetime import date

import pandas as pd

from futurescope.rv_store import CurveSnapshotStore


def test_curve_snapshot_store_round_trip(tmp_path):
    store = CurveSnapshotStore(tmp_path / "curve_snapshots")
    frame = pd.DataFrame(
        {
            "raw_symbol": ["X1", "X2"],
            "expiration": pd.to_datetime(["2027-01-01", "2027-02-01"], utc=True),
            "close": [100.0, 101.0],
        }
    )
    as_of = date(2026, 12, 1)
    store.write("XX", as_of, frame)

    loaded = store.read("XX", as_of)
    all_loaded = store.read_all("XX")

    assert loaded is not None
    assert len(loaded) == 2
    assert len(all_loaded) == 2
    assert store.dates("XX") == [as_of]
    assert "snapshot_date" in all_loaded.columns
