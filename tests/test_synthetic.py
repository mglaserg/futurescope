import numpy as np
import pandas as pd
import pytest

from futurescope.synthetic import (
    build_constant_maturity_curve,
    combine_synthetic_spread_weights,
    interpolate_constant_maturity,
    synthetic_slope,
    synthetic_slope_history,
)


def curve() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "raw_symbol": ["F1", "F2", "F3", "F4"],
            "expiration": pd.to_datetime(["2026-10-01", "2026-11-01", "2026-12-01", "2027-01-01"], utc=True),
            "dte": [20.0, 50.0, 80.0, 110.0],
            "close": [100.0, 103.0, 106.0, 109.0],
        }
    )


def test_exact_constant_maturity_uses_one_contract():
    point = interpolate_constant_maturity(curve(), 50)
    assert point.price == 103.0
    assert len(point.legs) == 1
    assert point.legs[0].raw_symbol == "F2"
    assert point.legs[0].weight == 1.0


def test_interpolates_between_bracketing_contracts():
    point = interpolate_constant_maturity(curve(), 65)
    assert np.isclose(point.price, 104.5)
    assert [leg.raw_symbol for leg in point.legs] == ["F2", "F3"]
    assert np.allclose([leg.weight for leg in point.legs], [0.5, 0.5])


def test_no_extrapolation():
    with pytest.raises(ValueError, match="does not extrapolate"):
        interpolate_constant_maturity(curve(), 10)


def test_50_80_slope_and_trade_translation():
    result = synthetic_slope(curve(), 50, 80)
    assert np.isclose(result["spread"], -3.0)
    assert result["long_weights"] == {"F2": 1.0, "F3": -1.0}
    assert result["short_weights"] == {"F2": -1.0, "F3": 1.0}


def test_overlapping_interpolation_combines_shared_leg():
    near = interpolate_constant_maturity(curve(), 65)  # .5 F2 + .5 F3
    far = interpolate_constant_maturity(curve(), 95)   # .5 F3 + .5 F4
    weights = combine_synthetic_spread_weights(near, far, "LONG")
    assert np.isclose(weights["F2"], 0.5)
    assert "F3" not in weights  # shared interpolation leg cancels
    assert np.isclose(weights["F4"], -0.5)


def test_build_curve_and_history_skip_unbracketed_dates():
    current = build_constant_maturity_curve(curve(), [50, 80])
    assert current["target_dte"].tolist() == [50.0, 80.0]

    snapshots = pd.concat(
        [
            curve().assign(snapshot_date=pd.Timestamp("2026-09-11")),
            curve().assign(close=[101.0, 104.0, 107.0, 110.0], snapshot_date=pd.Timestamp("2026-09-12")),
        ],
        ignore_index=True,
    )
    history = synthetic_slope_history(snapshots, 50, 80)
    assert len(history) == 2
    assert np.allclose(history["value"], [-3.0, -3.0])
