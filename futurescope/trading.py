from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    build_relative_value_structures,
    canonical_trade_weights,
    risk_adjusted_trade_weights,
)


@dataclass(frozen=True)
class FuturesContractSpec:
    """Dollar economics for one quoted futures price point."""

    symbol: str
    point_value_usd: float
    contract_description: str
    source_note: str


# One quoted price point times these values gives approximate P&L for one
# contract. Treasury futures are represented in price points here; DV01-neutral
# weighting is a separate risk-normalization problem.
CONTRACT_SPECS: dict[str, FuturesContractSpec] = {
    "GC": FuturesContractSpec(
        symbol="GC",
        point_value_usd=100.0,
        contract_description="COMEX Gold · 100 troy ounces",
        source_note="GC is quoted in USD per troy ounce; one 1.00 price-point move is $100 per contract.",
    ),
    "CL": FuturesContractSpec(
        symbol="CL",
        point_value_usd=1000.0,
        contract_description="NYMEX WTI Crude Oil · 1,000 barrels",
        source_note="CL is quoted in USD per barrel; one 1.00 price-point move is $1,000 per contract.",
    ),
    "ES": FuturesContractSpec(
        symbol="ES",
        point_value_usd=50.0,
        contract_description="E-mini S&P 500 · $50 × index",
        source_note="ES has a $50 multiplier, so one 1.00 index-point move is $50 per contract.",
    ),
    "ZN": FuturesContractSpec(
        symbol="ZN",
        point_value_usd=1000.0,
        contract_description="10-Year U.S. Treasury Note · $100,000 face",
        source_note="ZN price is expressed in points; one full price point is $1,000 per contract. Use DV01 for risk-neutral RV ratios.",
    ),
    "VX": FuturesContractSpec(
        symbol="VX",
        point_value_usd=1000.0,
        contract_description="Cboe VIX Futures · $1,000 multiplier",
        source_note="VX has a $1,000 multiplier, so one 1.00 volatility-point move is $1,000 per contract.",
    ),
}


def format_trade_ratio(weights: np.ndarray | list[float]) -> str:
    values = np.asarray(weights, dtype=float)
    parts: list[str] = []
    for value in values:
        if np.isclose(value, round(value)):
            parts.append(f"{int(round(value)):+d}")
        else:
            parts.append(f"{value:+.4f}")
    return " : ".join(parts)


def directional_trade_weights(order: int, signal: str) -> np.ndarray:
    signal = signal.upper().strip()
    if signal not in {"LONG", "SHORT"}:
        raise ValueError("signal must be LONG or SHORT")
    weights = canonical_trade_weights(order)
    return weights if signal == "LONG" else -weights


def build_trade_ticket(
    curve: pd.DataFrame,
    market: str,
    order: int,
    position: int,
    signal: str,
    expected_canonical_move: float | None = None,
    round_turn_cost_per_contract: float = 0.0,
    risk_units: Mapping[str, float] | None = None,
) -> dict[str, object]:
    """Translate an RV signal into exact futures legs and dollar economics.

    ``expected_canonical_move`` is the expected future change in the *long-front
    canonical structure value* returned by the historical signal engine. For a
    SHORT signal it should normally be negative; P&L is correctly signed by the
    basket direction.

    Dollar expectancy is exact for canonical integer ratios when all legs share
    the market's point value. Risk-adjusted fractional ratios are shown for
    research, but users should convert them to executable integer lots before
    trading.
    """
    market = market.upper().strip()
    if market not in CONTRACT_SPECS:
        raise KeyError(f"No contract spec configured for {market}")
    if round_turn_cost_per_contract < 0:
        raise ValueError("round_turn_cost_per_contract must be non-negative")

    structures = build_relative_value_structures(curve, order=order, risk_units=risk_units)
    match = structures[structures["position"] == position]
    if match.empty:
        raise ValueError(f"No order-{order} structure at position {position}")
    structure = match.iloc[0]

    work = curve.copy()
    work["expiration"] = pd.to_datetime(work["expiration"], utc=True, errors="coerce")
    work = work.dropna(subset=["expiration", "close"]).sort_values("expiration").reset_index(drop=True)
    legs = work.iloc[position - 1 : position + order].copy()
    if len(legs) != order + 1:
        raise ValueError("Curve does not contain enough legs for the selected structure")

    canonical_position_weights = directional_trade_weights(order, signal)
    if risk_units is None:
        execution_weights = canonical_position_weights.copy()
    else:
        per_contract_risk = np.array(
            [float(risk_units.get(str(symbol), 1.0)) for symbol in legs["raw_symbol"]],
            dtype=float,
        )
        execution_weights = risk_adjusted_trade_weights(canonical_position_weights, per_contract_risk)

    spec = CONTRACT_SPECS[market]
    leg_rows: list[dict[str, object]] = []
    for weight, row in zip(execution_weights, legs.itertuples(index=False)):
        side = "BUY" if weight > 0 else "SELL"
        leg_rows.append(
            {
                "side": side,
                "raw_symbol": str(row.raw_symbol),
                "expiration": pd.Timestamp(row.expiration),
                "contracts": abs(float(weight)),
                "signed_weight": float(weight),
                "entry_price": float(row.close),
                "usd_per_point_per_contract": spec.point_value_usd,
            }
        )
    leg_frame = pd.DataFrame(leg_rows)

    canonical_entry_value = float(structure["canonical_value"])
    basket_entry_value = canonical_entry_value if signal.upper() == "LONG" else -canonical_entry_value
    total_contract_equivalents = float(np.abs(execution_weights).sum())
    estimated_cost = total_contract_equivalents * float(round_turn_cost_per_contract)

    expected_move = np.nan if expected_canonical_move is None else float(expected_canonical_move)
    direction_sign = 1.0 if signal.upper() == "LONG" else -1.0
    if np.isfinite(expected_move):
        expected_gross_pnl = direction_sign * expected_move * spec.point_value_usd
        expected_target_canonical_value = canonical_entry_value + expected_move
        expected_net_pnl = expected_gross_pnl - estimated_cost
    else:
        expected_gross_pnl = np.nan
        expected_target_canonical_value = np.nan
        expected_net_pnl = np.nan

    return {
        "market": market,
        "structure": STRUCTURE_NAMES[order],
        "order": order,
        "position": position,
        "tenor_label": str(structure["tenor_label"]),
        "signal": signal.upper(),
        "canonical_ratio": format_trade_ratio(canonical_position_weights),
        "execution_ratio": format_trade_ratio(execution_weights),
        "canonical_entry_value": canonical_entry_value,
        "basket_entry_value": basket_entry_value,
        "time_normalized_value": float(structure["time_normalized_value"]),
        "expected_canonical_move": expected_move,
        "expected_target_canonical_value": expected_target_canonical_value,
        "point_value_usd": spec.point_value_usd,
        "contract_description": spec.contract_description,
        "source_note": spec.source_note,
        "total_contract_equivalents": total_contract_equivalents,
        "estimated_round_turn_cost": estimated_cost,
        "expected_gross_pnl_usd": expected_gross_pnl,
        "expected_net_pnl_usd": expected_net_pnl,
        "legs": leg_frame,
    }
