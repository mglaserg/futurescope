import math

import pandas as pd

from futurescope.analytics.curve import annualized_basis, enrich_curve, excess_carry


def test_annualized_basis():
    result = annualized_basis(105.0, 100.0, 365.0)
    assert math.isclose(result, 0.05, rel_tol=1e-12)


def test_excess_carry():
    assert math.isclose(excess_carry(0.08, 0.04, 0.01, 0.00), 0.03)


def test_enrich_curve_calendar_metrics():
    frame = pd.DataFrame(
        {
            "raw_symbol": ["X1", "X2"],
            "expiration": ["2027-01-01T00:00:00Z", "2027-04-01T00:00:00Z"],
            "close": [100.0, 103.0],
        }
    )
    out = enrich_curve(frame, pd.Timestamp("2026-10-01"), spot=98.0)
    assert len(out) == 2
    assert out.iloc[0]["basis_pct"] > 0
    assert out.iloc[1]["ann_calendar_carry_vs_front"] > 0
