import pandas as pd

from futurescope.curve_carry import (
    build_cross_market_carry_table,
    front_calendar_carry,
    select_cross_market_carry,
)


def _curve(front: float, second: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "raw_symbol": ["X1", "X2"],
            "expiration": ["2026-10-01", "2026-11-01"],
            "close": [front, second],
        }
    )


def test_backwardation_is_positive_carry():
    row = front_calendar_carry(_curve(105.0, 100.0), "GC")
    assert row["annualized_curve_carry"] > 0
    assert row["state"] == "BACKWARDATION"


def test_contango_is_negative_carry():
    row = front_calendar_carry(_curve(95.0, 100.0), "CL")
    assert row["annualized_curve_carry"] < 0
    assert row["state"] == "CONTANGO"


def test_cross_market_selection_longs_high_and_shorts_low():
    table = build_cross_market_carry_table(
        {
            "GC": _curve(105.0, 100.0),
            "CL": _curve(102.0, 100.0),
            "ES": _curve(100.0, 101.0),
            "VX": _curve(95.0, 100.0),
        }
    )
    selected = select_cross_market_carry(table, long_count=1, short_count=1)
    assert set(selected["market"]) == {"GC", "VX"}
    assert selected.loc[selected["market"] == "GC", "direction"].iloc[0] == "LONG"
    assert selected.loc[selected["market"] == "VX", "direction"].iloc[0] == "SHORT"
