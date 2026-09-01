from __future__ import annotations

import numpy as np
import pandas as pd

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    build_relative_value_history,
    build_relative_value_structures,
    relative_value_trade_signal,
)
from futurescope.trading import CONTRACT_SPECS, format_trade_ratio, directional_trade_weights


def opportunity_state(signal: str, zscore: float, entry_z: float) -> str:
    signal = str(signal).upper()
    if signal in {"LONG", "SHORT"}:
        return "TRADE CANDIDATE"
    if np.isfinite(zscore) and abs(float(zscore)) >= float(entry_z):
        return "RESEARCH"
    if np.isfinite(zscore) and abs(float(zscore)) >= max(1.0, 0.75 * float(entry_z)):
        return "UNUSUAL"
    return "NORMAL"


def research_score(signal: str, zscore: float, win_rate: float, analogs: int) -> float:
    """Transparent 0-100 ranking score for research triage, not net expectancy.

    40 points: extremeness, saturated at |z|=3.
    40 points: directional win-rate evidence above 50%, only for active signals.
    20 points: sample support, saturated at 20 analogues.
    """
    if not np.isfinite(zscore):
        return 0.0
    extremeness = 40.0 * min(abs(float(zscore)) / 3.0, 1.0)
    sample = 20.0 * min(max(int(analogs), 0) / 20.0, 1.0)
    directional = 0.0
    if str(signal).upper() in {"LONG", "SHORT"} and np.isfinite(win_rate):
        directional = 40.0 * min(max((float(win_rate) - 0.5) / 0.5, 0.0), 1.0)
    return float(min(extremeness + directional + sample, 100.0))


def scan_market_opportunities(
    market: str,
    curve: pd.DataFrame,
    snapshots: pd.DataFrame,
    lookback: int = 20,
    entry_z: float = 2.0,
    horizon: int = 5,
    min_analogs: int = 5,
    min_win_rate: float = 0.55,
) -> pd.DataFrame:
    """Evaluate every adjacent slope/fly/double-fly on the current curve."""
    market = market.upper()
    point_value = CONTRACT_SPECS[market].point_value_usd if market in CONTRACT_SPECS else np.nan
    rows: list[dict[str, object]] = []

    for order in (1, 2, 3):
        current = build_relative_value_structures(curve, order=order)
        for structure in current.itertuples(index=False):
            history = build_relative_value_history(
                snapshots,
                order=order,
                position=int(structure.position),
                value_column="time_normalized_value",
            )
            if history.empty:
                continue
            signal = relative_value_trade_signal(
                history,
                lookback=lookback,
                entry_z=entry_z,
                horizon=horizon,
                min_analogs=min_analogs,
                min_win_rate=min_win_rate,
            )
            signal_name = str(signal["signal"])
            z = float(signal["current_zscore"]) if pd.notna(signal["current_zscore"]) else np.nan
            win_rate = float(signal["win_rate"]) if pd.notna(signal["win_rate"]) else np.nan
            analogs = int(signal["analogs"])
            mean_move = (
                float(signal["mean_forward_change"])
                if pd.notna(signal["mean_forward_change"])
                else np.nan
            )
            expected_gross = (
                abs(mean_move) * point_value
                if signal_name in {"LONG", "SHORT"} and np.isfinite(mean_move) and np.isfinite(point_value)
                else np.nan
            )
            ratio = ""
            if signal_name in {"LONG", "SHORT"}:
                ratio = format_trade_ratio(directional_trade_weights(order, signal_name))

            rows.append(
                {
                    "market": market,
                    "order": order,
                    "structure": STRUCTURE_NAMES[order],
                    "curve_location": str(structure.tenor_label),
                    "contracts": str(structure.leg_symbols),
                    "canonical_value": float(structure.canonical_value),
                    "normalized_value": float(structure.time_normalized_value),
                    "signal": signal_name,
                    "trade_ratio": ratio,
                    "behavior": str(signal["behavior"]),
                    "zscore": z,
                    "analogs": analogs,
                    "win_rate": win_rate,
                    "mean_forward_change": mean_move,
                    "expected_gross_pnl_usd": expected_gross,
                    "state": opportunity_state(signal_name, z, entry_z),
                    "research_score": research_score(signal_name, z, win_rate, analogs),
                    "reason": str(signal["reason"]),
                }
            )

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    state_rank = {"TRADE CANDIDATE": 0, "RESEARCH": 1, "UNUSUAL": 2, "NORMAL": 3}
    out["_state_rank"] = out["state"].map(state_rank).fillna(9)
    out = out.sort_values(
        ["_state_rank", "research_score", "win_rate", "zscore"],
        ascending=[True, False, False, False],
        na_position="last",
    ).drop(columns="_state_rank")
    return out.reset_index(drop=True)
