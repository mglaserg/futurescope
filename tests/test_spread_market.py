from datetime import date

import math
import pandas as pd

from futurescope.spread_market import (
    SpreadCostGate,
    build_spread_cost_table,
    match_exchange_strategy,
    monitor_quote_timestamp,
)


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


def definitions() -> pd.DataFrame:
    rows = [
        # Listed GCZ6/GCG7 calendar: buy front, sell second.
        {
            "ts_event": "2026-09-03T12:00:00Z",
            "instrument_id": 100,
            "raw_symbol": "GCZ6-GCG7",
            "leg_count": 2,
            "leg_index": 0,
            "leg_raw_symbol": "GCZ6",
            "leg_side": "B",
            "leg_ratio_qty_numerator": 1,
            "leg_ratio_qty_denominator": 1,
            "min_price_increment": 0.1,
        },
        {
            "ts_event": "2026-09-03T12:00:00Z",
            "instrument_id": 100,
            "raw_symbol": "GCZ6-GCG7",
            "leg_count": 2,
            "leg_index": 1,
            "leg_raw_symbol": "GCG7",
            "leg_side": "A",
            "leg_ratio_qty_numerator": 1,
            "leg_ratio_qty_denominator": 1,
            "min_price_increment": 0.1,
        },
        # Listed F1/F2/F3 fly using +1:-2:+1.
        {
            "ts_event": "2026-09-03T12:00:00Z",
            "instrument_id": 200,
            "raw_symbol": "GCZ6-GCG7-GCJ7-FLY",
            "leg_count": 3,
            "leg_index": 0,
            "leg_raw_symbol": "GCZ6",
            "leg_side": "B",
            "leg_ratio_qty_numerator": 1,
            "leg_ratio_qty_denominator": 1,
            "min_price_increment": 0.1,
        },
        {
            "ts_event": "2026-09-03T12:00:00Z",
            "instrument_id": 200,
            "raw_symbol": "GCZ6-GCG7-GCJ7-FLY",
            "leg_count": 3,
            "leg_index": 1,
            "leg_raw_symbol": "GCG7",
            "leg_side": "A",
            "leg_ratio_qty_numerator": 2,
            "leg_ratio_qty_denominator": 1,
            "min_price_increment": 0.1,
        },
        {
            "ts_event": "2026-09-03T12:00:00Z",
            "instrument_id": 200,
            "raw_symbol": "GCZ6-GCG7-GCJ7-FLY",
            "leg_count": 3,
            "leg_index": 2,
            "leg_raw_symbol": "GCJ7",
            "leg_side": "B",
            "leg_ratio_qty_numerator": 1,
            "leg_ratio_qty_denominator": 1,
            "min_price_increment": 0.1,
        },
    ]
    return pd.DataFrame(rows)


def test_match_exchange_strategy_handles_calendar_and_fly_ratios():
    defs = definitions()
    cal = match_exchange_strategy(defs, ["GCZ6", "GCG7"], [1, -1])
    fly = match_exchange_strategy(defs, ["GCZ6", "GCG7", "GCJ7"], [1, -2, 1])
    assert cal is not None and cal["instrument_id"] == 100 and cal["orientation"] == 1
    assert fly is not None and fly["instrument_id"] == 200 and fly["orientation"] == 1


def test_spread_cost_table_uses_listed_strategy_book_not_leg_sum():
    bbo = pd.DataFrame(
        {
            "instrument_id": [100, 200],
            "ts_recv": pd.to_datetime(["2026-09-03T17:30:00Z", "2026-09-03T17:30:00Z"], utc=True),
            "ts_event": pd.to_datetime(["2026-09-03T17:29:00Z", "2026-09-03T17:29:00Z"], utc=True),
            "bid_px_00": [-21.1, -13.0],
            "ask_px_00": [-20.9, -12.8],
            "bid_sz_00": [5, 3],
            "ask_sz_00": [6, 4],
        }
    )
    volume = pd.DataFrame({"instrument_id": [100, 200], "volume": [300, 75]})
    table = build_spread_cost_table(
        "GC",
        sample_curve(),
        definitions(),
        bbo,
        volume,
        gate=SpreadCostGate(max_width_ticks=3, min_top_depth=2, min_daily_volume=50),
    )
    cal = table[(table["order"] == 1) & (table["position"] == 1)].iloc[0]
    fly = table[(table["order"] == 2) & (table["position"] == 1)].iloc[0]
    assert bool(cal["matched_exchange_strategy"])
    assert math.isclose(cal["width_points"], 0.2, abs_tol=1e-9)
    assert math.isclose(cal["width_ticks"], 2.0, abs_tol=1e-9)
    assert math.isclose(cal["round_turn_crossing_cost_usd"], 20.0, abs_tol=1e-9)
    assert bool(cal["liquidity_pass"])
    assert pd.Timestamp(cal["quote_ts"]) == pd.Timestamp("2026-09-03T17:30:00Z")
    assert bool(fly["liquidity_pass"])


def test_monitor_quote_time_is_dst_aware():
    as_of = date(2026, 9, 3)
    assert monitor_quote_timestamp("ES", as_of).isoformat() == "2026-09-03T20:00:00+00:00"
    assert monitor_quote_timestamp("GC", as_of).isoformat() == "2026-09-03T17:30:00+00:00"
