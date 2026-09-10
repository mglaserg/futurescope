from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import numpy as np
import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    DateOffset,
    Easter,
    FR,
    Holiday,
    MO,
    TH,
    nearest_workday,
)
from pandas.tseries.offsets import CustomBusinessDay


STOCK_TARGET = 0.60
BOND_TARGET = 0.40
STRONG_SELLING_THRESHOLD = -0.005
STRONG_BUYING_THRESHOLD = 0.005


class _NyseHolidayCalendar(AbstractHolidayCalendar):
    """Small dependency-free NYSE holiday calendar for scheduling strategy dates.

    This is intentionally limited to recurring full-day closures needed for the
    month-end monitor. Exceptional closures remain an operational caveat.
    """

    rules = [
        Holiday("New Year's Day", month=1, day=1, observance=nearest_workday),
        Holiday(
            "Martin Luther King Jr. Day",
            month=1,
            day=1,
            offset=DateOffset(weekday=MO(3)),
            start_date="1998-01-01",
        ),
        Holiday(
            "Washington's Birthday",
            month=2,
            day=1,
            offset=DateOffset(weekday=MO(3)),
        ),
        Holiday("Good Friday", month=1, day=1, offset=[Easter(), DateOffset(days=-2)]),
        Holiday(
            "Memorial Day",
            month=5,
            day=31,
            offset=DateOffset(weekday=MO(-1)),
        ),
        Holiday(
            "Juneteenth",
            month=6,
            day=19,
            observance=nearest_workday,
            start_date="2022-01-01",
        ),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        Holiday(
            "Labor Day",
            month=9,
            day=1,
            offset=DateOffset(weekday=MO(1)),
        ),
        Holiday(
            "Thanksgiving",
            month=11,
            day=1,
            offset=DateOffset(weekday=TH(4)),
        ),
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


NYSE_BUSINESS_DAY = CustomBusinessDay(calendar=_NyseHolidayCalendar())


@dataclass(frozen=True)
class MonthEndSchedule:
    signal_month: pd.Period
    previous_month_end: date
    signal_day: date
    final_five: tuple[date, ...]
    month_end: date
    first_five_next_month: tuple[date, ...]
    early_exit: date


@dataclass(frozen=True)
class RebalanceSignal:
    pressure: float
    pressure_bps: float
    regime: str
    stock_return: float
    bond_return: float
    stock_trade: float
    bond_trade: float


@dataclass(frozen=True)
class StrategyInstruction:
    phase: str
    headline: str
    detail: str
    equity_weight: float
    tlt_weight: float
    action_date: date | None
    next_transition: date | None

    @property
    def is_cash(self) -> bool:
        return self.equity_weight == 0.0 and self.tlt_weight == 0.0


def _month_sessions(period: pd.Period) -> pd.DatetimeIndex:
    start = period.start_time.normalize()
    end = period.end_time.normalize()
    return pd.date_range(start, end, freq=NYSE_BUSINESS_DAY)


def _previous_session_before(day: pd.Timestamp) -> pd.Timestamp:
    candidates = pd.date_range(day - pd.Timedelta(days=10), day - pd.Timedelta(days=1), freq=NYSE_BUSINESS_DAY)
    if len(candidates) == 0:
        raise ValueError(f"Could not resolve a prior NYSE session before {day.date()}")
    return candidates[-1]


def build_month_end_schedule(year: int, month: int) -> MonthEndSchedule:
    period = pd.Period(f"{year:04d}-{month:02d}", freq="M")
    sessions = _month_sessions(period)
    if len(sessions) < 6:
        raise ValueError(f"Not enough NYSE sessions in {period}")

    signal_day = sessions[-6]
    final_five = sessions[-5:]
    month_end = sessions[-1]
    previous_month_end = _previous_session_before(sessions[0])

    next_period = period + 1
    next_sessions = _month_sessions(next_period)
    first_five = next_sessions[:5]
    if len(first_five) < 5:
        raise ValueError(f"Not enough NYSE sessions in {next_period}")

    return MonthEndSchedule(
        signal_month=period,
        previous_month_end=previous_month_end.date(),
        signal_day=signal_day.date(),
        final_five=tuple(ts.date() for ts in final_five),
        month_end=month_end.date(),
        first_five_next_month=tuple(ts.date() for ts in first_five),
        early_exit=first_five[-1].date(),
    )


def schedule_for_as_of(as_of: date) -> MonthEndSchedule:
    current_period = pd.Period(pd.Timestamp(as_of), freq="M")
    current = build_month_end_schedule(current_period.year, current_period.month)

    # During the first five sessions of a new month, the live position belongs
    # to the previous month's frozen pressure signal.
    previous_period = current_period - 1
    previous = build_month_end_schedule(previous_period.year, previous_period.month)
    if previous.month_end < as_of <= previous.early_exit:
        return previous
    return current


def implied_rebalance_trades(
    stock_return: float,
    bond_return: float,
    target_stock_weight: float = STOCK_TARGET,
    target_bond_weight: float = BOND_TARGET,
) -> tuple[float, float]:
    if target_stock_weight <= 0 or target_bond_weight <= 0:
        raise ValueError("Target weights must be positive")
    if not np.isclose(target_stock_weight + target_bond_weight, 1.0):
        raise ValueError("Target weights must sum to 1")
    if stock_return <= -1 or bond_return <= -1:
        raise ValueError("Returns must be greater than -100%")

    stock_value = target_stock_weight * (1.0 + float(stock_return))
    bond_value = target_bond_weight * (1.0 + float(bond_return))
    portfolio_value = stock_value + bond_value
    current_stock_weight = stock_value / portfolio_value
    current_bond_weight = bond_value / portfolio_value
    return (
        target_stock_weight - current_stock_weight,
        target_bond_weight - current_bond_weight,
    )


def classify_pressure(
    pressure: float,
    selling_threshold: float = STRONG_SELLING_THRESHOLD,
    buying_threshold: float = STRONG_BUYING_THRESHOLD,
) -> str:
    if selling_threshold >= buying_threshold:
        raise ValueError("Selling threshold must be below buying threshold")
    if pressure <= selling_threshold:
        return "STRONG BOND SELLING"
    if pressure >= buying_threshold:
        return "STRONG BOND BUYING"
    return "NO EXTREME PRESSURE"


def calculate_rebalance_signal(
    stock_start: float,
    stock_end: float,
    bond_start: float,
    bond_end: float,
    selling_threshold: float = STRONG_SELLING_THRESHOLD,
    buying_threshold: float = STRONG_BUYING_THRESHOLD,
) -> RebalanceSignal:
    values = [stock_start, stock_end, bond_start, bond_end]
    if any(not np.isfinite(v) or v <= 0 for v in values):
        raise ValueError("Prices must be positive finite values")
    stock_return = float(stock_end / stock_start - 1.0)
    bond_return = float(bond_end / bond_start - 1.0)
    stock_trade, bond_trade = implied_rebalance_trades(stock_return, bond_return)
    return RebalanceSignal(
        pressure=bond_trade,
        pressure_bps=bond_trade * 10_000.0,
        regime=classify_pressure(bond_trade, selling_threshold, buying_threshold),
        stock_return=stock_return,
        bond_return=bond_return,
        stock_trade=stock_trade,
        bond_trade=bond_trade,
    )


def strategy_instruction(
    as_of: date,
    schedule: MonthEndSchedule,
    signal: RebalanceSignal | None,
    selling_threshold: float = STRONG_SELLING_THRESHOLD,
    buying_threshold: float = STRONG_BUYING_THRESHOLD,
) -> StrategyInstruction:
    """Return the position appropriate *after the close* of ``as_of``."""

    if as_of < schedule.signal_day:
        return StrategyInstruction(
            phase="WAITING",
            headline="No position yet",
            detail=f"The signal freezes at the {schedule.signal_day:%b %d} close.",
            equity_weight=0.0,
            tlt_weight=0.0,
            action_date=schedule.signal_day,
            next_transition=schedule.signal_day,
        )

    if signal is None:
        return StrategyInstruction(
            phase="DATA REQUIRED",
            headline="Signal close is due, but the frozen pressure is unavailable",
            detail="Refresh SPY/IEF data through the signal close before translating the trade.",
            equity_weight=0.0,
            tlt_weight=0.0,
            action_date=schedule.signal_day,
            next_transition=schedule.month_end,
        )

    if schedule.signal_day <= as_of < schedule.month_end:
        if signal.pressure <= selling_threshold:
            return StrategyInstruction(
                phase="FINAL FIVE",
                headline="Long equities into month-end",
                detail="Strong expected bond selling: own the equity leg through the month-end close.",
                equity_weight=1.0,
                tlt_weight=0.0,
                action_date=schedule.signal_day,
                next_transition=schedule.month_end,
            )
        return StrategyInstruction(
            phase="FINAL FIVE",
            headline="Long TLT into month-end",
            detail="No strong bond-selling pressure: own long-duration Treasuries through the month-end close.",
            equity_weight=0.0,
            tlt_weight=1.0,
            action_date=schedule.signal_day,
            next_transition=schedule.month_end,
        )

    if schedule.month_end <= as_of <= schedule.early_exit:
        if signal.pressure >= buying_threshold:
            return StrategyInstruction(
                phase="EARLY MONTH",
                headline="Long equities / short TLT",
                detail="Strong month-end bond buying: position for the flow reversal over the first five sessions.",
                equity_weight=1.0,
                tlt_weight=-1.0,
                action_date=schedule.month_end,
                next_transition=schedule.early_exit,
            )
        return StrategyInstruction(
            phase="EARLY MONTH",
            headline="Cash",
            detail="The strong bond-buying condition was not met, so the early-month reversal trade is skipped.",
            equity_weight=0.0,
            tlt_weight=0.0,
            action_date=schedule.month_end,
            next_transition=schedule.early_exit,
        )

    return StrategyInstruction(
        phase="CASH",
        headline="Cash until the next signal window",
        detail="The first-five-day window is complete.",
        equity_weight=0.0,
        tlt_weight=0.0,
        action_date=None,
        next_transition=None,
    )


def pressure_path(
    spy: pd.Series,
    ief: pd.Series,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    prices = pd.concat([spy.rename("SPY"), ief.rename("IEF")], axis=1).dropna().sort_index()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    window = prices.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)].copy()
    if window.empty:
        return pd.DataFrame(columns=["date", "spy", "ief", "spy_return", "ief_return", "pressure", "pressure_bps"])
    first = window.iloc[0]
    rows: list[dict[str, object]] = []
    for dt, row in window.iterrows():
        sig = calculate_rebalance_signal(float(first["SPY"]), float(row["SPY"]), float(first["IEF"]), float(row["IEF"]))
        rows.append(
            {
                "date": dt,
                "spy": float(row["SPY"]),
                "ief": float(row["IEF"]),
                "spy_return": sig.stock_return,
                "ief_return": sig.bond_return,
                "pressure": sig.pressure,
                "pressure_bps": sig.pressure_bps,
            }
        )
    return pd.DataFrame(rows)


def nearest_price_on_or_before(series: pd.Series, when: date) -> tuple[date, float] | None:
    clean = pd.to_numeric(series, errors="coerce").dropna().copy()
    if clean.empty:
        return None
    clean.index = pd.to_datetime(clean.index).tz_localize(None)
    eligible = clean.loc[:pd.Timestamp(when)]
    if eligible.empty:
        return None
    return eligible.index[-1].date(), float(eligible.iloc[-1])


def frozen_signal_from_history(
    prices: pd.DataFrame,
    schedule: MonthEndSchedule,
) -> tuple[RebalanceSignal | None, dict[str, date | float | None]]:
    required = {"SPY", "IEF"}
    if not required.issubset(prices.columns):
        return None, {}
    spy_start = nearest_price_on_or_before(prices["SPY"], schedule.previous_month_end)
    ief_start = nearest_price_on_or_before(prices["IEF"], schedule.previous_month_end)
    spy_end = nearest_price_on_or_before(prices["SPY"], schedule.signal_day)
    ief_end = nearest_price_on_or_before(prices["IEF"], schedule.signal_day)
    if not all([spy_start, ief_start, spy_end, ief_end]):
        return None, {}
    if spy_end[0] < schedule.signal_day or ief_end[0] < schedule.signal_day:
        return None, {
            "spy_start_date": spy_start[0],
            "ief_start_date": ief_start[0],
            "spy_end_date": spy_end[0],
            "ief_end_date": ief_end[0],
        }
    signal = calculate_rebalance_signal(spy_start[1], spy_end[1], ief_start[1], ief_end[1])
    return signal, {
        "spy_start_date": spy_start[0],
        "ief_start_date": ief_start[0],
        "spy_end_date": spy_end[0],
        "ief_end_date": ief_end[0],
        "spy_start": spy_start[1],
        "ief_start": ief_start[1],
        "spy_end": spy_end[1],
        "ief_end": ief_end[1],
    }


def normalized_growth(series: pd.Series, start_date: date, end_date: date) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().copy()
    clean.index = pd.to_datetime(clean.index).tz_localize(None)
    window = clean.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)]
    if window.empty:
        return window
    return window / float(window.iloc[0]) * 100.0
