import math

import pandas as pd

from futurescope.trading import build_trade_ticket, directional_trade_weights


def sample_curve() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "raw_symbol": ["GCZ6", "GCG7", "GCJ7", "GCM7"],
            "expiration": pd.to_datetime(
                ["2026-12-28", "2027-02-24", "2027-04-28", "2027-06-28"], utc=True
            ),
            "close": [4331.9, 4352.9, 4360.0, 4370.0],
        }
    )


def test_directional_trade_weights_apply_to_whole_structure():
    assert directional_trade_weights(1, "LONG").tolist() == [1.0, -1.0]
    assert directional_trade_weights(2, "SHORT").tolist() == [-1.0, 2.0, -1.0]


def test_gc_long_slope_ticket_and_demo_pnl_economics():
    ticket = build_trade_ticket(
        sample_curve(),
        market="GC",
        order=1,
        position=1,
        signal="LONG",
        expected_canonical_move=10.4,
    )
    assert ticket["canonical_ratio"] == "+1 : -1"
    assert math.isclose(ticket["canonical_entry_value"], -21.0)
    assert math.isclose(ticket["expected_gross_pnl_usd"], 1040.0)
    legs = ticket["legs"]
    assert legs.iloc[0]["side"] == "BUY"
    assert legs.iloc[1]["side"] == "SELL"


def test_short_butterfly_inverts_whole_basket():
    ticket = build_trade_ticket(sample_curve(), market="GC", order=2, position=1, signal="SHORT")
    assert ticket["canonical_ratio"] == "-1 : +2 : -1"
    assert ticket["legs"]["side"].tolist() == ["SELL", "BUY", "SELL"]
