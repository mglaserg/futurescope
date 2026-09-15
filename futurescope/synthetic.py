from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SyntheticLeg:
    raw_symbol: str
    expiration: pd.Timestamp
    dte: float
    price: float
    weight: float


@dataclass(frozen=True)
class SyntheticPoint:
    target_dte: float
    price: float
    legs: tuple[SyntheticLeg, ...]

    @property
    def label(self) -> str:
        return f"{self.target_dte:g}d"

    @property
    def weight_text(self) -> str:
        return " + ".join(f"{leg.weight:.3f}×{leg.raw_symbol}" for leg in self.legs)


def _clean_curve(curve: pd.DataFrame) -> pd.DataFrame:
    required = {"raw_symbol", "expiration", "close", "dte"}
    missing = required.difference(curve.columns)
    if missing:
        raise ValueError(f"curve is missing required columns: {sorted(missing)}")

    out = curve.copy()
    out["expiration"] = pd.to_datetime(out["expiration"], utc=True, errors="coerce")
    out["dte"] = pd.to_numeric(out["dte"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["expiration", "dte", "close", "raw_symbol"])
    out = out[(out["dte"] > 0) & np.isfinite(out["close"])].sort_values("dte").reset_index(drop=True)
    if out.empty:
        raise ValueError("curve has no live contracts")
    return out


def interpolate_constant_maturity(curve: pd.DataFrame, target_dte: float) -> SyntheticPoint:
    """Linearly interpolate a fixed-DTE futures point from listed contracts.

    Interpolation is in quoted futures price over calendar DTE. Futurescope does
    not extrapolate beyond the observed curve because that would turn a transparent
    synthetic tenor into a model assumption.
    """
    if not np.isfinite(target_dte) or target_dte <= 0:
        raise ValueError("target_dte must be positive and finite")
    work = _clean_curve(curve)
    target = float(target_dte)
    min_dte = float(work.iloc[0]["dte"])
    max_dte = float(work.iloc[-1]["dte"])
    if target < min_dte or target > max_dte:
        raise ValueError(
            f"target {target:g}d is outside the listed curve ({min_dte:.1f}d to {max_dte:.1f}d); Futurescope does not extrapolate"
        )

    exact = work[np.isclose(work["dte"].astype(float), target, atol=1e-9)]
    if not exact.empty:
        row = exact.iloc[0]
        leg = SyntheticLeg(
            raw_symbol=str(row["raw_symbol"]),
            expiration=pd.Timestamp(row["expiration"]),
            dte=float(row["dte"]),
            price=float(row["close"]),
            weight=1.0,
        )
        return SyntheticPoint(target_dte=target, price=leg.price, legs=(leg,))

    upper_index = int(np.searchsorted(work["dte"].to_numpy(dtype=float), target, side="right"))
    lower = work.iloc[upper_index - 1]
    upper = work.iloc[upper_index]
    lower_dte = float(lower["dte"])
    upper_dte = float(upper["dte"])
    span = upper_dte - lower_dte
    if span <= 0:
        raise ValueError("curve DTEs must be strictly increasing around the target")

    upper_weight = (target - lower_dte) / span
    lower_weight = 1.0 - upper_weight
    lower_leg = SyntheticLeg(
        raw_symbol=str(lower["raw_symbol"]),
        expiration=pd.Timestamp(lower["expiration"]),
        dte=lower_dte,
        price=float(lower["close"]),
        weight=float(lower_weight),
    )
    upper_leg = SyntheticLeg(
        raw_symbol=str(upper["raw_symbol"]),
        expiration=pd.Timestamp(upper["expiration"]),
        dte=upper_dte,
        price=float(upper["close"]),
        weight=float(upper_weight),
    )
    price = lower_leg.weight * lower_leg.price + upper_leg.weight * upper_leg.price
    return SyntheticPoint(target_dte=target, price=float(price), legs=(lower_leg, upper_leg))


def build_constant_maturity_curve(curve: pd.DataFrame, target_dtes: Iterable[float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for target in sorted(set(float(x) for x in target_dtes)):
        point = interpolate_constant_maturity(curve, target)
        rows.append(
            {
                "target_dte": point.target_dte,
                "synthetic_price": point.price,
                "replication": point.weight_text,
                "leg_symbols": " / ".join(leg.raw_symbol for leg in point.legs),
            }
        )
    return pd.DataFrame(rows)


def combine_synthetic_spread_weights(
    near: SyntheticPoint,
    far: SyntheticPoint,
    direction: str = "LONG",
) -> dict[str, float]:
    """Translate +near/-far synthetic exposure into listed-contract weights."""
    if near.target_dte >= far.target_dte:
        raise ValueError("near target must be shorter than far target")
    direction = direction.upper().strip()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
    sign = 1.0 if direction == "LONG" else -1.0
    weights: dict[str, float] = {}
    for leg in near.legs:
        weights[leg.raw_symbol] = weights.get(leg.raw_symbol, 0.0) + sign * float(leg.weight)
    for leg in far.legs:
        weights[leg.raw_symbol] = weights.get(leg.raw_symbol, 0.0) - sign * float(leg.weight)
    return {symbol: weight for symbol, weight in weights.items() if not np.isclose(weight, 0.0, atol=1e-10)}


def synthetic_slope(curve: pd.DataFrame, near_dte: float, far_dte: float) -> dict[str, object]:
    if near_dte >= far_dte:
        raise ValueError("near_dte must be less than far_dte")
    near = interpolate_constant_maturity(curve, near_dte)
    far = interpolate_constant_maturity(curve, far_dte)
    spread = near.price - far.price
    gap = float(far_dte) - float(near_dte)
    log_carry = np.log(near.price / far.price) * 365.25 / gap if near.price > 0 and far.price > 0 else np.nan
    return {
        "near": near,
        "far": far,
        "spread": float(spread),
        "slope_per_day": float(spread / gap),
        "annualized_log_carry": float(log_carry),
        "long_weights": combine_synthetic_spread_weights(near, far, "LONG"),
        "short_weights": combine_synthetic_spread_weights(near, far, "SHORT"),
    }


def synthetic_slope_history(
    snapshots: pd.DataFrame,
    near_dte: float,
    far_dte: float,
) -> pd.DataFrame:
    """Build fixed-DTE slope history from cached daily curve snapshots.

    Dates that do not bracket both target tenors are skipped. Because the target
    DTEs stay fixed, the series is designed to avoid front/second roll jumps.
    """
    if snapshots.empty:
        return pd.DataFrame(columns=["snapshot_date", "value", "near_price", "far_price", "replication"])
    if "snapshot_date" not in snapshots.columns:
        raise ValueError("snapshots must contain snapshot_date")

    rows: list[dict[str, object]] = []
    for snapshot_date, group in snapshots.groupby("snapshot_date", sort=True):
        try:
            result = synthetic_slope(group, near_dte, far_dte)
        except ValueError:
            continue
        near = result["near"]
        far = result["far"]
        assert isinstance(near, SyntheticPoint)
        assert isinstance(far, SyntheticPoint)
        rows.append(
            {
                "snapshot_date": pd.Timestamp(snapshot_date),
                "value": float(result["spread"]),
                "near_price": near.price,
                "far_price": far.price,
                "annualized_log_carry": float(result["annualized_log_carry"]),
                "replication": f"{near.weight_text} | short {far.weight_text}",
            }
        )
    return pd.DataFrame(rows).sort_values("snapshot_date").reset_index(drop=True)
