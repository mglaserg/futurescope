import math

import numpy as np
import pandas as pd

from futurescope.analytics.relative_value import (
    backtest_relative_value_mean_reversion,
    build_relative_value_history,
    build_relative_value_structures,
    canonical_trade_weights,
    relative_value_statistics,
    relative_value_trade_signal,
    risk_adjusted_trade_weights,
    time_normalized_coefficients,
    time_normalized_trade_value,
)


def sample_curve() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "raw_symbol": ["F1", "F2", "F3", "F4"],
            "expiration": pd.to_datetime(
                [
                    "2027-01-01T00:00:00Z",
                    "2027-02-01T00:00:00Z",
                    "2027-03-01T00:00:00Z",
                    "2027-04-01T00:00:00Z",
                ],
                utc=True,
            ),
            "close": [100.0, 102.0, 105.0, 109.0],
        }
    )


def test_canonical_weights():
    assert np.allclose(canonical_trade_weights(1), [1, -1])
    assert np.allclose(canonical_trade_weights(2), [1, -2, 1])
    assert np.allclose(canonical_trade_weights(3), [1, -3, 3, -1])


def test_equal_spacing_time_normalization_matches_canonical_over_h_power():
    h = 0.25
    times = [0.0, h, 2 * h]
    coeffs = time_normalized_coefficients(times)
    expected = np.array([1.0, -2.0, 1.0]) / (h**2)
    assert np.allclose(coeffs, expected)


def test_time_normalized_quadratic_second_difference():
    # y=t^2 has a second derivative of 2; order 2 uses the same sign.
    times = [0.0, 0.2, 0.7]
    prices = [t * t for t in times]
    assert math.isclose(time_normalized_trade_value(prices, times), 2.0, rel_tol=1e-12)


def test_long_front_odd_order_sign():
    # y=t has derivative +1, but the long-front spread convention is -dF/dt.
    assert math.isclose(time_normalized_trade_value([0.0, 0.5], [0.0, 0.5]), -1.0)


def test_build_relative_value_structures():
    curve = sample_curve()
    spread = build_relative_value_structures(curve, order=1)
    fly = build_relative_value_structures(curve, order=2)
    double_fly = build_relative_value_structures(curve, order=3)

    assert len(spread) == 3
    assert len(fly) == 2
    assert len(double_fly) == 1
    assert math.isclose(spread.iloc[0]["canonical_value"], -2.0)
    assert math.isclose(fly.iloc[0]["canonical_value"], 1.0)
    assert math.isclose(double_fly.iloc[0]["canonical_value"], 0.0)
    assert double_fly.iloc[0]["canonical_weights"] == "+1 : -3 : +3 : -1"


def test_risk_adjusted_weights_preserve_target_risk_ratio():
    weights = risk_adjusted_trade_weights([1, -2, 1], [100, 200, 50])
    risk_exposure = weights * np.array([100, 200, 50])
    ratio = risk_exposure / risk_exposure[0]
    assert np.allclose(ratio, [1, -2, 1])
    assert math.isclose(weights[0], 1.0)


def test_history_and_statistics():
    curves = []
    for i, bump in enumerate([0.0, 0.5, 1.0, 0.25, -0.25, 0.75]):
        curve = sample_curve().copy()
        curve["close"] = curve["close"] + np.array([0.0, bump, 0.0, 0.0])
        curve["snapshot_date"] = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        curves.append(curve)
    snapshots = pd.concat(curves, ignore_index=True)
    history = build_relative_value_history(snapshots, order=2, position=1)
    stats = relative_value_statistics(history["value"])

    assert len(history) == 6
    assert stats["observations"] == 6
    assert 0.0 <= stats["percentile"] <= 1.0


def test_mean_reversion_backtest_is_lagged_and_skips_roll_jumps():
    history = pd.DataFrame(
        {
            "snapshot_date": pd.date_range("2026-01-01", periods=8, freq="D"),
            "value": [0.0, 0.1, 0.0, 3.0, 2.0, 0.2, -3.0, -2.0],
            "canonical_value": [0.0, 0.1, 0.0, 3.0, 2.0, 100.0, 99.0, 98.0],
            "leg_symbols": ["A/B"] * 5 + ["B/C"] * 3,
        }
    )
    bt = backtest_relative_value_mean_reversion(history, lookback=3, entry_z=1.0, exit_z=0.25)

    assert len(bt) == len(history)
    assert bt.loc[5, "roll_boundary"]
    assert math.isclose(bt.loc[5, "pnl_price_units"], 0.0)
    assert "signal_zscore" in bt.columns
    assert "cumulative_pnl_price_units" in bt.columns


def _signal_history(moves: list[float], z_side: str = "high") -> pd.DataFrame:
    # Construct a stable basket with enough warm-up variation, then repeated
    # extremes whose canonical forward moves have a known direction.
    n = 60
    values = np.sin(np.linspace(0, 8 * np.pi, n))
    canonical = np.zeros(n)
    for i in range(1, n):
        canonical[i] = canonical[i - 1] + 0.02
    # Force several same-side extremes late enough to have rolling history.
    extreme_indices = [22, 28, 34, 40, 46, 52, 59]
    sign = 1.0 if z_side == "high" else -1.0
    for idx in extreme_indices:
        values[idx] = 8.0 * sign
    # Set one-observation forward canonical moves for historical analogues.
    for idx, move in zip(extreme_indices[:-1], moves):
        canonical[idx + 1] = canonical[idx] + move
    return pd.DataFrame({
        "snapshot_date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "value": values,
        "canonical_value": canonical,
        "leg_symbols": "F1 / F2",
    })


def test_trade_signal_infers_direction_from_historical_forward_moves():
    history = _signal_history([-1.0, -0.8, -1.2, -0.9, -1.1, -0.7], z_side="high")
    result = relative_value_trade_signal(
        history, lookback=10, entry_z=2.0, horizon=1, min_analogs=4, min_win_rate=0.55
    )
    assert result["signal"] == "SHORT"
    assert result["behavior"] == "mean reversion"
    assert result["analogs"] >= 4
    assert result["win_rate"] > 0.5


def test_trade_signal_can_identify_momentum_not_just_mean_reversion():
    history = _signal_history([1.0, 0.8, 1.2, 0.9, 1.1, 0.7], z_side="high")
    result = relative_value_trade_signal(
        history, lookback=10, entry_z=2.0, horizon=1, min_analogs=4, min_win_rate=0.55
    )
    assert result["signal"] == "LONG"
    assert result["behavior"] == "momentum / continuation"


def test_trade_signal_requires_current_extreme():
    history = _signal_history([-1.0, -0.8, -1.2, -0.9, -1.1, -0.7], z_side="high")
    history.loc[history.index[-1], "value"] = 0.0
    result = relative_value_trade_signal(history, lookback=10, entry_z=2.0, horizon=1, min_analogs=4)
    assert result["signal"] == "NO SIGNAL"
