import math
from datetime import date

import pandas as pd

from futurescope.month_end_rebalance import (
    build_month_end_schedule,
    calculate_rebalance_signal,
    classify_pressure,
    implied_rebalance_trades,
    strategy_instruction,
    schedule_for_as_of,
)


def test_september_2026_schedule():
    s = build_month_end_schedule(2026, 9)
    assert s.previous_month_end == date(2026, 8, 31)
    assert s.signal_day == date(2026, 9, 23)
    assert s.final_five == (
        date(2026, 9, 24),
        date(2026, 9, 25),
        date(2026, 9, 28),
        date(2026, 9, 29),
        date(2026, 9, 30),
    )
    assert s.month_end == date(2026, 9, 30)
    assert s.early_exit == date(2026, 10, 7)


def test_rebalance_trade_is_zero_when_assets_match():
    stock_trade, bond_trade = implied_rebalance_trades(0.10, 0.10)
    assert math.isclose(stock_trade, 0.0, abs_tol=1e-12)
    assert math.isclose(bond_trade, 0.0, abs_tol=1e-12)


def test_stock_outperformance_creates_bond_buying_pressure():
    sig = calculate_rebalance_signal(100.0, 110.0, 100.0, 100.0)
    assert sig.bond_trade > 0
    assert sig.stock_trade < 0


def test_pressure_classification_thresholds():
    assert classify_pressure(-0.005) == "STRONG BOND SELLING"
    assert classify_pressure(0.005) == "STRONG BOND BUYING"
    assert classify_pressure(0.0) == "NO EXTREME PRESSURE"


def test_final_five_strong_selling_is_long_equity():
    schedule = build_month_end_schedule(2026, 9)
    sig = calculate_rebalance_signal(100.0, 95.0, 100.0, 105.0)
    # Force an unambiguous strong-selling example if the chosen moves are not enough.
    if sig.pressure > -0.005:
        sig = calculate_rebalance_signal(100.0, 80.0, 100.0, 120.0)
    ins = strategy_instruction(date(2026, 9, 24), schedule, sig)
    assert ins.phase == "FINAL FIVE"
    assert ins.equity_weight == 1.0
    assert ins.tlt_weight == 0.0


def test_early_month_strong_buying_is_long_equity_short_tlt():
    schedule = build_month_end_schedule(2026, 9)
    sig = calculate_rebalance_signal(100.0, 120.0, 100.0, 90.0)
    assert sig.pressure >= 0.005
    ins = strategy_instruction(date(2026, 10, 2), schedule, sig)
    assert ins.phase == "EARLY MONTH"
    assert ins.equity_weight == 1.0
    assert ins.tlt_weight == -1.0


def test_after_fifth_session_is_cash():
    schedule = build_month_end_schedule(2026, 9)
    sig = calculate_rebalance_signal(100.0, 120.0, 100.0, 90.0)
    ins = strategy_instruction(date(2026, 10, 8), schedule, sig)
    assert ins.phase == "CASH"
    assert ins.is_cash


def test_schedule_for_as_of_uses_previous_signal_month_during_early_month():
    s = schedule_for_as_of(date(2026, 10, 2))
    assert s.signal_month == pd.Period("2026-09", freq="M")
    assert s.month_end == date(2026, 9, 30)
    assert s.early_exit == date(2026, 10, 7)
