from datetime import date

import pandas as pd

from futurescope.conductor import (
    cross_market_carry_intent,
    intent_json,
    month_end_trade_intent,
    relative_value_trade_intent,
)


def test_month_end_zb_intent_delegates_to_dv01():
    intent = month_end_trade_intent(
        as_of=date(2026, 9, 30),
        phase="EARLY MONTH",
        equity_weight=1.0,
        duration_weight=-1.0,
        equity_vehicle="MES",
        duration_vehicle="ZB",
        pressure_bps=72.0,
        next_transition=date(2026, 10, 7),
    )
    duration = [x for x in intent["exposures"] if x.get("asset_class") == "US_LONG_DURATION"][0]
    assert duration["reference_instrument"] == "TLT"
    assert duration["preferred_instrument"] == "ZB"
    assert duration["sizing_basis"] == "DV01"
    assert intent["metadata"]["sizing_owner"] == "Conductor"


def test_relative_value_intent_preserves_basket_ratios():
    ticket = {
        "market": "GC",
        "structure": "Curve slope / calendar spread",
        "tenor_label": "F1-F2",
        "signal": "LONG",
        "canonical_entry_value": -21.0,
        "time_normalized_value": -1.0,
        "execution_ratio": "+1 : -1",
        "legs": pd.DataFrame(
            [
                {"raw_symbol": "GCV6", "signed_weight": 1.0},
                {"raw_symbol": "GCZ6", "signed_weight": -1.0},
            ]
        ),
    }
    intent = relative_value_trade_intent(ticket, as_of=date(2026, 9, 11), max_holding_sessions=10)
    assert [leg["ratio"] for leg in intent["exposures"]] == [1.0, -1.0]
    assert intent["lifecycle"]["target_z"] == 0.0
    assert '"producer": "Futurescope"' in intent_json(intent)


def test_cross_market_intent_can_express_calendar_spreads():
    rows = [
        {"market": "GC", "direction": "LONG", "front_symbol": "GCV6", "second_symbol": "GCZ6"},
        {"market": "VX", "direction": "SHORT", "front_symbol": "VXU6", "second_symbol": "VXV6"},
    ]
    intent = cross_market_carry_intent(rows, as_of=date(2026, 9, 11), expression="calendar_spread")
    assert intent["action"] == "REBALANCE"
    assert intent["exposures"][0]["legs"][0]["ratio"] == 1.0
    assert intent["exposures"][1]["legs"][0]["ratio"] == -1.0


def test_constant_maturity_intent_delegates_integerization_to_conductor():
    from futurescope.conductor import constant_maturity_spread_intent

    intent = constant_maturity_spread_intent(
        market="VX",
        as_of=date(2026, 9, 14),
        near_dte=50,
        far_dte=80,
        direction="LONG",
        listed_weights={"VX2": 0.6, "VX3": 0.1, "VX4": -0.7},
    )
    assert intent["strategy_id"] == "futurescope_vx_50d_80d_synthetic"
    assert [x["ratio"] for x in intent["exposures"]] == [0.6, 0.1, -0.7]
    assert intent["preferred_execution"]["integerization_owner"] == "Conductor"
