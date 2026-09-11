from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


MECHANISM_NOTES = {
    "GC": "financing / storage / lease economics",
    "CL": "inventory / storage / convenience yield",
    "ES": "funding / dividends / dealer balance sheet",
    "ZN": "Treasury delivery / repo / CTD economics",
    "ZB": "Treasury delivery / repo / CTD economics",
    "VX": "volatility expectations / term-structure roll",
}


def front_calendar_carry(curve: pd.DataFrame, market: str) -> dict[str, object]:
    """Describe the current F1/F2 curve slope as an annualized percentage rate.

    Positive means backwardation (front above second); negative means contango.
    This is a *common curve-state object*, not a claim that every market shares
    the same financing/arbitrage mechanism.
    """
    required = {"raw_symbol", "expiration", "close"}
    missing = required.difference(curve.columns)
    if missing:
        raise ValueError(f"curve is missing required columns: {sorted(missing)}")

    work = curve.copy()
    work["expiration"] = pd.to_datetime(work["expiration"], utc=True, errors="coerce")
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work.dropna(subset=["expiration", "close"]).sort_values("expiration").reset_index(drop=True)
    if len(work) < 2:
        raise ValueError("At least two live contracts are required")

    front = work.iloc[0]
    second = work.iloc[1]
    f1 = float(front["close"])
    f2 = float(second["close"])
    if f1 <= 0 or f2 <= 0:
        raise ValueError("Futures prices must be positive for log carry")
    gap_days = (second["expiration"] - front["expiration"]).total_seconds() / 86400.0
    if gap_days <= 0:
        raise ValueError("Second expiry must be after front expiry")

    carry = float(np.log(f1 / f2) * 365.25 / gap_days)
    slope_points = f1 - f2
    state = "BACKWARDATION" if carry > 0 else "CONTANGO" if carry < 0 else "FLAT"
    return {
        "market": market.upper(),
        "front_symbol": str(front["raw_symbol"]),
        "second_symbol": str(second["raw_symbol"]),
        "front_expiration": pd.Timestamp(front["expiration"]),
        "second_expiration": pd.Timestamp(second["expiration"]),
        "front_price": f1,
        "second_price": f2,
        "gap_days": float(gap_days),
        "slope_points": float(slope_points),
        "annualized_curve_carry": carry,
        "carry_pct": carry * 100.0,
        "state": state,
        "mechanism": MECHANISM_NOTES.get(market.upper(), "market-specific curve economics"),
    }


def build_cross_market_carry_table(curves: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for market, curve in curves.items():
        try:
            rows.append(front_calendar_carry(curve, market))
        except (ValueError, KeyError):
            continue
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("annualized_curve_carry", ascending=False).reset_index(drop=True)
    n = len(out)
    out["rank"] = np.arange(1, n + 1)
    if n > 1:
        out["cross_section_percentile"] = (n - out["rank"]) / (n - 1)
        std = float(out["annualized_curve_carry"].std(ddof=0))
        mean = float(out["annualized_curve_carry"].mean())
        out["cross_section_z"] = 0.0 if np.isclose(std, 0.0) else (out["annualized_curve_carry"] - mean) / std
    else:
        out["cross_section_percentile"] = 0.5
        out["cross_section_z"] = 0.0
    return out


def select_cross_market_carry(
    table: pd.DataFrame,
    *,
    long_count: int = 1,
    short_count: int = 1,
    require_sign: bool = True,
) -> pd.DataFrame:
    """Select high-carry longs and low-carry shorts from the current cross-section."""
    if table.empty:
        return pd.DataFrame()
    if long_count < 0 or short_count < 0:
        raise ValueError("long_count and short_count must be non-negative")

    work = table.sort_values("annualized_curve_carry", ascending=False).copy()
    longs = work[work["annualized_curve_carry"] > 0] if require_sign else work
    shorts = work[work["annualized_curve_carry"] < 0] if require_sign else work
    long_rows = longs.head(long_count).copy()
    short_rows = shorts.tail(short_count).copy()
    long_rows["direction"] = "LONG"
    short_rows["direction"] = "SHORT"
    selected = pd.concat([long_rows, short_rows], ignore_index=True)
    if selected.empty:
        return selected
    selected["signal_units"] = 1.0
    return selected.sort_values(["direction", "annualized_curve_carry"], ascending=[True, False]).reset_index(drop=True)
