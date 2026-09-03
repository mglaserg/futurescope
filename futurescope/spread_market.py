from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import gcd
from typing import Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    build_relative_value_structures,
    canonical_trade_weights,
)
from futurescope.config import MarketConfig
from futurescope.trading import CONTRACT_SPECS


NEW_YORK = ZoneInfo("America/New_York")

# These are monitor sampling anchors, not settlement certifications.  The purpose
# is to make quote collection deterministic and DST-aware while we continue to
# tighten market-specific reference alignment.
MONITOR_QUOTE_TIMES_ET: dict[str, time] = {
    "ES": time(16, 0),
    "GC": time(13, 30),
}


@dataclass(frozen=True)
class SpreadCostGate:
    """Operational monitor gate, deliberately separate from research hurdles."""

    max_width_ticks: float = 4.0
    min_top_depth: float = 1.0
    min_daily_volume: float = 0.0


def monitor_quote_timestamp(market: str, as_of: date) -> datetime:
    market = market.upper()
    if market not in MONITOR_QUOTE_TIMES_ET:
        raise KeyError(f"No monitor quote time configured for {market}")
    local = datetime.combine(as_of, MONITOR_QUOTE_TIMES_ET[market], tzinfo=NEW_YORK)
    return local.astimezone(timezone.utc)


def _side_sign(value: object) -> float | None:
    """Normalize Databento/CME leg-side representations to +1 buy / -1 sell."""

    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip().upper()
    if text in {"B", "BID", "BUY", "1", "+1"}:
        return 1.0
    if text in {"A", "ASK", "SELL", "S", "2", "-1"}:
        return -1.0
    return None


def _integerize(values: Iterable[float], tol: float = 1e-9) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0 or not np.all(np.isfinite(arr)):
        return arr
    rounded = np.rint(arr)
    if np.all(np.abs(arr - rounded) <= tol):
        ints = rounded.astype(int)
        divisor = 0
        for value in np.abs(ints):
            divisor = gcd(divisor, int(value))
        if divisor > 1:
            ints = ints // divisor
        return ints.astype(float)
    scale = np.nanmin(np.abs(arr[np.abs(arr) > tol]))
    if not np.isfinite(scale) or scale <= 0:
        return arr
    return arr / scale


def _definition_spread_groups(definitions: pd.DataFrame) -> list[dict[str, object]]:
    """Convert Databento strategy-leg definition records into matchable groups.

    Databento publishes one definition row per strategy leg.  Later Modify rows
    may fill in leg symbols, so we keep the latest record per instrument/leg.
    """

    if definitions.empty or "instrument_id" not in definitions.columns:
        return []

    frame = definitions.copy()
    if "ts_event" in frame.columns:
        frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True, errors="coerce")
        frame = frame.sort_values("ts_event")
    if "leg_count" not in frame.columns:
        return []
    frame["leg_count"] = pd.to_numeric(frame["leg_count"], errors="coerce").fillna(0)
    frame = frame[frame["leg_count"] >= 2].copy()
    if frame.empty:
        return []

    if "leg_index" in frame.columns:
        frame["leg_index"] = pd.to_numeric(frame["leg_index"], errors="coerce")
        frame = frame.drop_duplicates(["instrument_id", "leg_index"], keep="last")

    groups: list[dict[str, object]] = []
    for instrument_id, group in frame.groupby("instrument_id", sort=False):
        if "leg_index" in group.columns:
            group = group.sort_values("leg_index")
        leg_count = int(pd.to_numeric(group["leg_count"], errors="coerce").dropna().max())
        if len(group) < leg_count:
            continue

        symbols: list[str] = []
        signed_qty: list[float] = []
        valid = True
        for row in group.head(leg_count).itertuples(index=False):
            symbol = getattr(row, "leg_raw_symbol", None)
            side = _side_sign(getattr(row, "leg_side", None))
            num = pd.to_numeric(getattr(row, "leg_ratio_qty_numerator", 1), errors="coerce")
            den = pd.to_numeric(getattr(row, "leg_ratio_qty_denominator", 1), errors="coerce")
            if symbol is None or pd.isna(symbol) or str(symbol).strip() == "" or side is None or not np.isfinite(num) or not np.isfinite(den) or den == 0:
                valid = False
                break
            symbols.append(str(symbol))
            signed_qty.append(float(side) * float(num) / float(den))
        if not valid:
            continue

        first = group.iloc[-1]
        tick = pd.to_numeric(first.get("min_price_increment", np.nan), errors="coerce")
        raw_symbol = first.get("raw_symbol", "")
        groups.append(
            {
                "instrument_id": int(instrument_id),
                "raw_symbol": str(raw_symbol),
                "leg_symbols": tuple(symbols),
                "signed_qty": _integerize(signed_qty),
                "leg_count": leg_count,
                "min_price_increment": float(tick) if np.isfinite(tick) else np.nan,
            }
        )
    return groups


def match_exchange_strategy(
    definitions: pd.DataFrame,
    leg_symbols: Iterable[str],
    target_weights: Iterable[float],
) -> dict[str, object] | None:
    """Find an exchange-listed strategy proportional to the requested basket.

    Returns ``orientation`` +1 when buying the listed strategy matches the
    canonical target basket and -1 when it matches the inverse.
    """

    target_symbols = tuple(str(x) for x in leg_symbols)
    target = _integerize(target_weights)
    target_map = {symbol: float(weight) for symbol, weight in zip(target_symbols, target)}

    for item in _definition_spread_groups(definitions):
        if set(item["leg_symbols"]) != set(target_symbols):
            continue
        actual_map = {
            symbol: float(weight)
            for symbol, weight in zip(item["leg_symbols"], np.asarray(item["signed_qty"], dtype=float))
        }
        actual = np.asarray([actual_map[symbol] for symbol in target_symbols], dtype=float)
        actual = _integerize(actual)
        if actual.size != target.size:
            continue
        if np.allclose(actual, target):
            return {**item, "orientation": 1}
        if np.allclose(actual, -target):
            return {**item, "orientation": -1}
    return None


def canonicalize_quote(row: pd.Series, orientation: int) -> dict[str, float]:
    bid = pd.to_numeric(row.get("bid_px_00", np.nan), errors="coerce")
    ask = pd.to_numeric(row.get("ask_px_00", np.nan), errors="coerce")
    bid_sz = pd.to_numeric(row.get("bid_sz_00", np.nan), errors="coerce")
    ask_sz = pd.to_numeric(row.get("ask_sz_00", np.nan), errors="coerce")
    if orientation == -1 and np.isfinite(bid) and np.isfinite(ask):
        canonical_bid = -float(ask)
        canonical_ask = -float(bid)
        canonical_bid_sz = float(ask_sz) if np.isfinite(ask_sz) else np.nan
        canonical_ask_sz = float(bid_sz) if np.isfinite(bid_sz) else np.nan
    else:
        canonical_bid = float(bid) if np.isfinite(bid) else np.nan
        canonical_ask = float(ask) if np.isfinite(ask) else np.nan
        canonical_bid_sz = float(bid_sz) if np.isfinite(bid_sz) else np.nan
        canonical_ask_sz = float(ask_sz) if np.isfinite(ask_sz) else np.nan
    return {
        "bid": canonical_bid,
        "ask": canonical_ask,
        "bid_size": canonical_bid_sz,
        "ask_size": canonical_ask_sz,
    }


def build_spread_cost_table(
    market: str,
    curve: pd.DataFrame,
    definitions: pd.DataFrame,
    bbo: pd.DataFrame,
    daily_volume: pd.DataFrame | None = None,
    gate: SpreadCostGate | None = None,
) -> pd.DataFrame:
    """Match current RV baskets to listed strategy books and compute crossing cost."""

    gate = gate or SpreadCostGate()
    market = market.upper()
    point_value = CONTRACT_SPECS[market].point_value_usd
    rows: list[dict[str, object]] = []

    bbo_latest = pd.DataFrame()
    if not bbo.empty and "instrument_id" in bbo.columns:
        bbo_latest = bbo.copy()
        for column in ("ts_recv", "ts_event"):
            if column in bbo_latest.columns:
                bbo_latest[column] = pd.to_datetime(bbo_latest[column], utc=True, errors="coerce")
        quote_time_col = "ts_recv" if "ts_recv" in bbo_latest.columns else "ts_event"
        if quote_time_col in bbo_latest.columns:
            bbo_latest = bbo_latest.sort_values(quote_time_col)
        bbo_latest = bbo_latest.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")

    volume_map: dict[int, float] = {}
    if daily_volume is not None and not daily_volume.empty and "instrument_id" in daily_volume.columns:
        volume_frame = daily_volume.copy()
        volume_frame["volume"] = pd.to_numeric(volume_frame.get("volume"), errors="coerce")
        volume_map = (
            volume_frame.groupby("instrument_id")["volume"].sum(min_count=1).dropna().astype(float).to_dict()
        )

    for order in (1, 2, 3):
        structures = build_relative_value_structures(curve, order=order)
        target_weights = canonical_trade_weights(order)
        for structure in structures.itertuples(index=False):
            leg_symbols = tuple(str(x).strip() for x in str(structure.leg_symbols).split("/"))
            match = match_exchange_strategy(definitions, leg_symbols, target_weights)
            base = {
                "order": order,
                "structure": STRUCTURE_NAMES[order],
                "position": int(structure.position),
                "curve_location": str(structure.tenor_label),
                "leg_symbols": " / ".join(leg_symbols),
                "canonical_value": float(structure.canonical_value),
                "matched_exchange_strategy": bool(match),
            }
            if not match:
                rows.append(
                    {
                        **base,
                        "exchange_symbol": "",
                        "instrument_id": np.nan,
                        "orientation": np.nan,
                        "bid": np.nan,
                        "ask": np.nan,
                        "width_points": np.nan,
                        "width_ticks": np.nan,
                        "bid_size": np.nan,
                        "ask_size": np.nan,
                        "top_depth": np.nan,
                        "daily_volume": np.nan,
                        "round_turn_crossing_cost_usd": np.nan,
                        "liquidity_pass": False,
                        "liquidity_reason": "No matching listed strategy definition",
                        "quote_ts": pd.NaT,
                    }
                )
                continue

            instrument_id = int(match["instrument_id"])
            quote = None
            if not bbo_latest.empty and instrument_id in bbo_latest.index:
                quote = bbo_latest.loc[instrument_id]
                if isinstance(quote, pd.DataFrame):
                    quote = quote.iloc[-1]
            if quote is None:
                rows.append(
                    {
                        **base,
                        "exchange_symbol": str(match["raw_symbol"]),
                        "instrument_id": instrument_id,
                        "orientation": int(match["orientation"]),
                        "bid": np.nan,
                        "ask": np.nan,
                        "width_points": np.nan,
                        "width_ticks": np.nan,
                        "bid_size": np.nan,
                        "ask_size": np.nan,
                        "top_depth": np.nan,
                        "daily_volume": volume_map.get(instrument_id, np.nan),
                        "round_turn_crossing_cost_usd": np.nan,
                        "liquidity_pass": False,
                        "liquidity_reason": "No BBO near monitor timestamp",
                        "quote_ts": pd.NaT,
                    }
                )
                continue

            q = canonicalize_quote(quote, int(match["orientation"]))
            width = q["ask"] - q["bid"] if np.isfinite(q["ask"]) and np.isfinite(q["bid"]) else np.nan
            tick = float(match["min_price_increment"])
            width_ticks = width / tick if np.isfinite(width) and np.isfinite(tick) and tick > 0 else np.nan
            sizes = [x for x in (q["bid_size"], q["ask_size"]) if np.isfinite(x)]
            top_depth = min(sizes) if len(sizes) == 2 else np.nan
            volume = volume_map.get(instrument_id, np.nan)

            checks: list[bool] = []
            reasons: list[str] = []
            if np.isfinite(width_ticks):
                ok = width_ticks <= float(gate.max_width_ticks)
                checks.append(ok)
                if not ok:
                    reasons.append(f"width {width_ticks:.1f} ticks > {gate.max_width_ticks:g}")
            else:
                checks.append(False)
                reasons.append("width unavailable")
            if np.isfinite(top_depth):
                ok = top_depth >= float(gate.min_top_depth)
                checks.append(ok)
                if not ok:
                    reasons.append(f"top depth {top_depth:g} < {gate.min_top_depth:g}")
            else:
                checks.append(False)
                reasons.append("top depth unavailable")
            if float(gate.min_daily_volume) > 0:
                ok = np.isfinite(volume) and volume >= float(gate.min_daily_volume)
                checks.append(ok)
                if not ok:
                    reasons.append(f"daily volume {volume if np.isfinite(volume) else 'N/A'} < {gate.min_daily_volume:g}")

            quote_ts = quote.get("ts_recv", quote.get("ts_event", pd.NaT))
            rows.append(
                {
                    **base,
                    "exchange_symbol": str(match["raw_symbol"]),
                    "instrument_id": instrument_id,
                    "orientation": int(match["orientation"]),
                    "bid": q["bid"],
                    "ask": q["ask"],
                    "width_points": width,
                    "width_ticks": width_ticks,
                    "bid_size": q["bid_size"],
                    "ask_size": q["ask_size"],
                    "top_depth": top_depth,
                    "daily_volume": volume,
                    "round_turn_crossing_cost_usd": width * point_value if np.isfinite(width) else np.nan,
                    "liquidity_pass": bool(all(checks)),
                    "liquidity_reason": "PASS" if all(checks) else "; ".join(reasons),
                    "quote_ts": quote_ts,
                }
            )

    return pd.DataFrame(rows)


def load_exchange_spread_costs(
    config: MarketConfig,
    curve: pd.DataFrame,
    as_of: date,
    gate: SpreadCostGate | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch listed-strategy definitions + BBO/volume and build current cost table."""

    from futurescope.providers import DatabentoProvider

    provider = DatabentoProvider()
    definitions = provider.get_strategy_definitions(
        dataset=config.dataset,
        parent_symbol=config.parent_symbol,
        as_of=as_of,
        refresh=refresh,
    )
    matches: list[int] = []
    for order in (1, 2, 3):
        structures = build_relative_value_structures(curve, order=order)
        for structure in structures.itertuples(index=False):
            symbols = tuple(str(x).strip() for x in str(structure.leg_symbols).split("/"))
            match = match_exchange_strategy(definitions, symbols, canonical_trade_weights(order))
            if match:
                matches.append(int(match["instrument_id"]))
    matches = sorted(set(matches))
    if not matches:
        return build_spread_cost_table(config.symbol, curve, definitions, pd.DataFrame(), gate=gate)

    quote_ts = monitor_quote_timestamp(config.symbol, as_of)
    bbo = provider.get_bbo_snapshot(
        dataset=config.dataset,
        instrument_ids=matches,
        snapshot_ts=quote_ts,
        refresh=refresh,
    )
    volume = provider.get_daily_instrument_volume(
        dataset=config.dataset,
        instrument_ids=matches,
        as_of=as_of,
        refresh=refresh,
    )
    return build_spread_cost_table(config.symbol, curve, definitions, bbo, volume, gate=gate)
