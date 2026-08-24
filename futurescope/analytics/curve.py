from __future__ import annotations

import numpy as np
import pandas as pd


def annualized_basis(future_price: float, spot_price: float, dte: float) -> float:
    """Simple annualized basis, returned as a decimal rate."""
    if spot_price <= 0 or dte <= 0:
        return np.nan
    return (future_price / spot_price - 1.0) * (365.0 / dte)


def fair_carry_rate(
    financing_rate: float,
    storage_rate: float = 0.0,
    income_yield: float = 0.0,
) -> float:
    """Simple fair carry approximation r + storage - income, decimal rate."""
    return financing_rate + storage_rate - income_yield


def excess_carry(
    implied_carry: float,
    financing_rate: float,
    storage_rate: float = 0.0,
    income_yield: float = 0.0,
) -> float:
    if pd.isna(implied_carry):
        return np.nan
    return implied_carry - fair_carry_rate(financing_rate, storage_rate, income_yield)


def enrich_curve(
    frame: pd.DataFrame,
    as_of: pd.Timestamp,
    spot: float | None = None,
) -> pd.DataFrame:
    """Add DTE, spot basis, and calendar-curve metrics to a futures curve."""
    if frame.empty:
        return frame.copy()

    out = frame.copy()
    out["expiration"] = pd.to_datetime(out["expiration"], utc=True, errors="coerce")
    as_of_ts = pd.Timestamp(as_of)
    if as_of_ts.tzinfo is None:
        as_of_ts = as_of_ts.tz_localize("UTC")
    else:
        as_of_ts = as_of_ts.tz_convert("UTC")

    out["dte"] = (out["expiration"] - as_of_ts).dt.total_seconds() / 86400.0
    out = out[out["dte"] > 0].sort_values("expiration").reset_index(drop=True)
    out["contract_number"] = np.arange(1, len(out) + 1)

    if spot is not None and np.isfinite(spot) and spot > 0:
        out["spot"] = float(spot)
        out["basis_pct"] = out["close"] / float(spot) - 1.0
        out["ann_implied_carry"] = [
            annualized_basis(float(px), float(spot), float(dte))
            for px, dte in zip(out["close"], out["dte"])
        ]
    else:
        out["spot"] = np.nan
        out["basis_pct"] = np.nan
        out["ann_implied_carry"] = np.nan

    front_px = float(out.iloc[0]["close"])
    front_dte = float(out.iloc[0]["dte"])
    out["vs_front_pct"] = out["close"] / front_px - 1.0

    cal_carry: list[float] = []
    for px, dte in zip(out["close"], out["dte"]):
        delta_days = float(dte) - front_dte
        if delta_days <= 0:
            cal_carry.append(np.nan)
        else:
            cal_carry.append((float(px) / front_px - 1.0) * 365.0 / delta_days)
    out["ann_calendar_carry_vs_front"] = cal_carry

    out["next_spread"] = out["close"].shift(-1) - out["close"]
    out["next_spread_pct"] = out["close"].shift(-1) / out["close"] - 1.0
    return out


def curve_state(frame: pd.DataFrame) -> str:
    if frame.empty or len(frame) < 2:
        return "Insufficient data"
    first = float(frame.iloc[0]["close"])
    second = float(frame.iloc[1]["close"])
    if second > first:
        return "Contango"
    if second < first:
        return "Backwardation"
    return "Flat"
