from datetime import date

import pandas as pd

from futurescope.monitor import MonitorArchive, build_monitor_structures


def _curve(snapshot_date: str, bump: float = 0.0) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "raw_symbol": ["ESU6", "ESZ6", "ESH7", "ESM7"],
            "expiration": pd.to_datetime(
                ["2026-09-18", "2026-12-18", "2027-03-19", "2027-06-18"], utc=True
            ),
            "close": [6500.0, 6510.0 + bump, 6520.0, 6530.0],
        }
    )
    frame["snapshot_date"] = pd.Timestamp(snapshot_date)
    return frame


def test_monitor_structure_table_is_current_state_only():
    curves = [_curve(f"2026-08-{day:02d}", bump=(day % 5) * 0.5) for day in range(1, 26)]
    snapshots = pd.concat(curves, ignore_index=True)
    current = _curve("2026-08-25", bump=3.0).drop(columns="snapshot_date")
    out = build_monitor_structures(current, snapshots, lookback=10)
    assert not out.empty
    assert "zscore" in out.columns
    assert "percentile" in out.columns
    assert "win_rate" not in out.columns
    assert "mean_forward_change" not in out.columns


def test_monitor_archive_deduplicates_identical_observation(tmp_path):
    archive = MonitorArchive(tmp_path / "monitor.sqlite")
    curve = _curve("2026-08-25").drop(columns="snapshot_date")
    structures = pd.DataFrame({"order": [1], "canonical_value": [-10.0]})
    costs = pd.DataFrame({"order": [1], "width_ticks": [1.0]})
    archive.write("ES", date(2026, 8, 25), curve, structures, costs)
    archive.write("ES", date(2026, 8, 25), curve, structures, costs)
    stored = archive.list("ES")
    assert len(stored) == 1
