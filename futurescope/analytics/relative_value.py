from __future__ import annotations

from math import comb, factorial
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


STRUCTURE_NAMES = {
    1: "Curve slope / calendar spread",
    2: "Butterfly / curvature",
    3: "Double butterfly / change in curvature",
}


def canonical_trade_weights(order: int) -> np.ndarray:
    """Return long-front finite-difference trade weights.

    The sign convention is intentionally expressed as a trade:

    - order 1: +1, -1
    - order 2: +1, -2, +1
    - order 3: +1, -3, +3, -1

    Odd orders are therefore the negative of the conventional forward-difference
    derivative sign. This keeps the first leg long and makes the coefficients map
    directly to the calendar-spread / butterfly / double-butterfly structures used
    in the dashboard.
    """
    if order < 1:
        raise ValueError("order must be at least 1")
    return np.array(
        [((-1) ** k) * float(comb(order, k)) for k in range(order + 1)],
        dtype=float,
    )


def time_normalized_coefficients(times_years: Iterable[float]) -> np.ndarray:
    """Finite-difference coefficients adjusted for uneven tenor spacing.

    Returns coefficients with the same long-front sign convention as
    :func:`canonical_trade_weights`. For equally spaced tenors separated by h,
    these reduce to canonical_trade_weights(order) / h**order.

    The calculation uses interpolation/divided-difference weights multiplied by
    n! so the result has derivative-like units of price / year**n.
    """
    x = np.asarray(list(times_years), dtype=float)
    order = len(x) - 1
    if order < 1:
        raise ValueError("at least two tenor points are required")
    if not np.all(np.isfinite(x)):
        raise ValueError("times_years must be finite")
    if len(np.unique(x)) != len(x):
        raise ValueError("times_years must be distinct")

    coeffs = np.empty(len(x), dtype=float)
    sign = (-1.0) ** order
    scale = float(factorial(order)) * sign
    for i in range(len(x)):
        denom = 1.0
        for j in range(len(x)):
            if i != j:
                denom *= x[i] - x[j]
        coeffs[i] = scale / denom
    return coeffs


def time_normalized_trade_value(
    prices: Iterable[float],
    times_years: Iterable[float],
) -> float:
    """Return the uneven-tenor-adjusted finite-difference curve measure."""
    y = np.asarray(list(prices), dtype=float)
    coeffs = time_normalized_coefficients(times_years)
    if len(y) != len(coeffs):
        raise ValueError("prices and times_years must have the same length")
    if not np.all(np.isfinite(y)):
        return np.nan
    return float(np.dot(coeffs, y))


def risk_adjusted_trade_weights(
    base_weights: Iterable[float],
    risk_per_contract: Iterable[float],
) -> np.ndarray:
    """Convert target risk coefficients into contract ratios.

    Example: passing DV01 as ``risk_per_contract`` makes each leg's DV01 exposure
    proportional to ``base_weights``. The returned ratios are scaled so the first
    non-zero leg has the same absolute size as the corresponding base weight.

    This is deliberately generic: Treasury futures can pass DV01, while another
    market can later pass a different per-contract risk unit.
    """
    base = np.asarray(list(base_weights), dtype=float)
    risk = np.asarray(list(risk_per_contract), dtype=float)
    if len(base) != len(risk):
        raise ValueError("base_weights and risk_per_contract must have the same length")
    if np.any(~np.isfinite(risk)) or np.any(risk <= 0):
        raise ValueError("risk_per_contract values must be positive and finite")

    raw = base / risk
    non_zero = np.flatnonzero(np.abs(base) > 0)
    if len(non_zero) == 0:
        return raw
    anchor = int(non_zero[0])
    if raw[anchor] == 0:
        return raw
    scale = abs(base[anchor] / raw[anchor])
    return raw * scale


def _format_weights(weights: Iterable[float]) -> str:
    values = np.asarray(list(weights), dtype=float)
    parts: list[str] = []
    for value in values:
        rounded = round(float(value), 6)
        if np.isclose(rounded, round(rounded)):
            parts.append(f"{int(round(rounded)):+d}")
        else:
            parts.append(f"{rounded:+.4f}")
    return " : ".join(parts)


def build_relative_value_structures(
    curve: pd.DataFrame,
    order: int,
    risk_units: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Build adjacent spread/fly/double-fly structures from one futures curve.

    ``curve`` must contain ``raw_symbol``, ``expiration`` and ``close``. The
    returned ``canonical_value`` is the raw finite-difference trade value using
    integer coefficients. ``time_normalized_value`` adjusts for unequal expiry
    spacing. ``trade_weights`` optionally applies user-supplied per-contract risk
    units (for example DV01) without changing the pure curve-shape measure.
    """
    if order not in STRUCTURE_NAMES:
        raise ValueError(f"supported orders are {sorted(STRUCTURE_NAMES)}")
    required = {"raw_symbol", "expiration", "close"}
    missing = required.difference(curve.columns)
    if missing:
        raise ValueError(f"curve is missing required columns: {sorted(missing)}")
    if len(curve) < order + 1:
        return pd.DataFrame()

    work = curve.copy()
    work["expiration"] = pd.to_datetime(work["expiration"], utc=True, errors="coerce")
    work = work.dropna(subset=["expiration", "close"]).sort_values("expiration").reset_index(drop=True)
    base_weights = canonical_trade_weights(order)

    rows: list[dict] = []
    for start in range(0, len(work) - order):
        legs = work.iloc[start : start + order + 1].copy()
        symbols = legs["raw_symbol"].astype(str).tolist()
        prices = legs["close"].astype(float).to_numpy()
        expiries = legs["expiration"].tolist()
        first_expiry = expiries[0]
        times_years = np.array(
            [(expiry - first_expiry).total_seconds() / (365.25 * 86400.0) for expiry in expiries],
            dtype=float,
        )

        normalized_coeffs = time_normalized_coefficients(times_years)
        canonical_value = float(np.dot(base_weights, prices))
        normalized_value = float(np.dot(normalized_coeffs, prices))

        if risk_units is None:
            trade_weights = base_weights.copy()
            leg_risk_units = np.ones(len(base_weights), dtype=float)
        else:
            leg_risk_units = np.array([float(risk_units.get(symbol, 1.0)) for symbol in symbols])
            trade_weights = risk_adjusted_trade_weights(base_weights, leg_risk_units)

        rows.append(
            {
                "order": order,
                "structure": STRUCTURE_NAMES[order],
                "position": start + 1,
                "tenor_label": "-".join(f"F{i}" for i in range(start + 1, start + order + 2)),
                "leg_symbols": " / ".join(symbols),
                "leg_expirations": " / ".join(pd.Timestamp(x).strftime("%Y-%m-%d") for x in expiries),
                "canonical_weights": _format_weights(base_weights),
                "trade_weights": _format_weights(trade_weights),
                "risk_units": " / ".join(f"{x:.4f}" for x in leg_risk_units),
                "canonical_value": canonical_value,
                "trade_value": float(np.dot(trade_weights, prices)),
                "time_normalized_value": normalized_value,
                "span_days": (expiries[-1] - expiries[0]).total_seconds() / 86400.0,
                "time_normalized_coefficients": _format_weights(normalized_coeffs),
            }
        )

    return pd.DataFrame(rows)


def build_relative_value_history(
    snapshots: pd.DataFrame,
    order: int,
    position: int = 1,
    value_column: str = "time_normalized_value",
) -> pd.DataFrame:
    """Build a tenor-relative RV history from cached curve snapshots.

    ``position=1`` means F1-F2 for order 1, F1-F2-F3 for order 2, etc. This
    deliberately follows relative contract slots through time rather than a fixed
    raw symbol. Contract-roll changes are retained in ``leg_symbols`` so later
    backtests can explicitly handle roll boundaries.
    """
    if snapshots.empty:
        return pd.DataFrame(columns=["snapshot_date", value_column, "leg_symbols"])
    if "snapshot_date" not in snapshots.columns:
        raise ValueError("snapshots must contain snapshot_date")
    if position < 1:
        raise ValueError("position must be >= 1")

    rows: list[dict] = []
    for snapshot_date, group in snapshots.groupby("snapshot_date", sort=True):
        structures = build_relative_value_structures(group, order=order)
        match = structures[structures["position"] == position]
        if match.empty:
            continue
        row = match.iloc[0]
        rows.append(
            {
                "snapshot_date": pd.Timestamp(snapshot_date),
                "value": float(row[value_column]),
                "canonical_value": float(row["canonical_value"]),
                "leg_symbols": row["leg_symbols"],
                "span_days": float(row["span_days"]),
            }
        )
    return pd.DataFrame(rows).sort_values("snapshot_date").reset_index(drop=True)



def backtest_relative_value_mean_reversion(
    history: pd.DataFrame,
    lookback: int = 20,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
) -> pd.DataFrame:
    """Simple no-lookahead mean-reversion research backtest in price units.

    Signals use ``value`` (normally the time-normalized curve measure) while P&L
    uses changes in ``canonical_value``. Rolling mean/std are shifted one
    observation so the current observation is not included in its own benchmark.

    When the raw leg symbols change, Futurescope treats that as a roll boundary:
    the position is reset and the cross-roll P&L change is ignored. This avoids
    pretending that a jump between different contract baskets is executable P&L.
    Transaction costs, multipliers, margin, and explicit roll execution are not
    included, so the result is a research proxy rather than production P&L.
    """
    required = {"snapshot_date", "value", "canonical_value", "leg_symbols"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"history is missing required columns: {sorted(missing)}")
    if lookback < 3:
        raise ValueError("lookback must be at least 3")
    if entry_z <= 0 or exit_z < 0 or exit_z >= entry_z:
        raise ValueError("require entry_z > exit_z >= 0")

    out = history.copy().sort_values("snapshot_date").reset_index(drop=True)
    min_periods = min(lookback, max(3, lookback // 2))
    rolling_mean = out["value"].rolling(lookback, min_periods=min_periods).mean().shift(1)
    rolling_std = out["value"].rolling(lookback, min_periods=min_periods).std(ddof=1).shift(1)
    out["signal_zscore"] = (out["value"] - rolling_mean) / rolling_std.replace(0.0, np.nan)

    positions: list[float] = []
    position = 0.0
    previous_legs: str | None = None
    for row in out.itertuples(index=False):
        legs = str(row.leg_symbols)
        zscore = float(row.signal_zscore) if pd.notna(row.signal_zscore) else np.nan
        if previous_legs is not None and legs != previous_legs:
            position = 0.0

        if np.isfinite(zscore):
            if position == 0.0:
                if zscore >= entry_z:
                    position = -1.0
                elif zscore <= -entry_z:
                    position = 1.0
            elif abs(zscore) <= exit_z:
                position = 0.0

        positions.append(position)
        previous_legs = legs

    out["position"] = positions
    out["roll_boundary"] = out["leg_symbols"].ne(out["leg_symbols"].shift(1))
    out.loc[out.index[0], "roll_boundary"] = False
    price_change = out["canonical_value"].diff()
    same_legs = out["leg_symbols"].eq(out["leg_symbols"].shift(1))
    out["pnl_price_units"] = out["position"].shift(1).fillna(0.0) * price_change.fillna(0.0)
    out.loc[~same_legs, "pnl_price_units"] = 0.0
    out["cumulative_pnl_price_units"] = out["pnl_price_units"].cumsum()
    return out


def relative_value_zscore_history(
    history: pd.DataFrame,
    lookback: int = 20,
) -> pd.DataFrame:
    """Return the lagged rolling z-score series used by the RV signal engine.

    The rolling mean and standard deviation are shifted one observation so the
    current structure value is compared only with information that was already
    available before that observation. This makes the plotted z-score identical
    to the z-score used by :func:`relative_value_trade_signal`.
    """
    if "value" not in history.columns:
        raise ValueError("history is missing required column: value")
    if lookback < 3:
        raise ValueError("lookback must be at least 3")

    out = history.copy()
    if "snapshot_date" in out.columns:
        out = out.sort_values("snapshot_date")
    out = out.reset_index(drop=True)

    min_periods = min(lookback, max(3, lookback // 2))
    rolling_mean = out["value"].rolling(lookback, min_periods=min_periods).mean().shift(1)
    rolling_std = out["value"].rolling(lookback, min_periods=min_periods).std(ddof=1).shift(1)
    out["signal_zscore"] = (out["value"] - rolling_mean) / rolling_std.replace(0.0, np.nan)
    return out


def relative_value_trade_signal(
    history: pd.DataFrame,
    lookback: int = 20,
    entry_z: float = 2.0,
    horizon: int = 5,
    min_analogs: int = 5,
    min_win_rate: float = 0.55,
) -> dict[str, float | int | str]:
    """Turn an RV anomaly into a directional research signal.

    The signal is empirical rather than mechanically mean-reverting. Each
    historical observation gets a lagged rolling z-score. Futurescope then finds
    prior observations on the *same side* of the requested z-score threshold and
    asks what the canonical tradable basket did over the next ``horizon`` cached
    observations. Forward moves that cross a contract-roll boundary are excluded.

    A LONG/SHORT signal is emitted only when:

    1. the current absolute z-score is at least ``entry_z``;
    2. there are at least ``min_analogs`` valid historical analogues; and
    3. the historical directional win rate is at least ``min_win_rate``.

    Importantly, the direction is inferred from history. A positive extreme can
    therefore produce SHORT (mean reversion) *or* LONG (momentum) if that is what
    comparable historical observations actually did. Results are in raw
    canonical price units and do not yet include transaction costs or multipliers.
    """
    required = {"snapshot_date", "value", "canonical_value", "leg_symbols"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"history is missing required columns: {sorted(missing)}")
    if lookback < 3:
        raise ValueError("lookback must be at least 3")
    if entry_z <= 0:
        raise ValueError("entry_z must be positive")
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    if min_analogs < 1:
        raise ValueError("min_analogs must be at least 1")
    if not 0.5 <= min_win_rate <= 1.0:
        raise ValueError("min_win_rate must be between 0.5 and 1.0")

    out = relative_value_zscore_history(history, lookback=lookback)
    if out.empty:
        return {
            "signal": "INSUFFICIENT HISTORY",
            "reason": "No cached history is available.",
            "current_zscore": np.nan,
            "analogs": 0,
            "mean_forward_change": np.nan,
            "median_forward_change": np.nan,
            "win_rate": np.nan,
            "behavior": "unknown",
            "horizon": horizon,
        }

    forward_change = np.full(len(out), np.nan, dtype=float)
    for i in range(len(out) - horizon):
        # Do not call a move executable if the tenor-relative basket rolled into
        # different raw contracts anywhere during the forward holding window.
        legs = out.loc[i : i + horizon, "leg_symbols"]
        if legs.nunique(dropna=False) != 1:
            continue
        forward_change[i] = (
            float(out.loc[i + horizon, "canonical_value"])
            - float(out.loc[i, "canonical_value"])
        )
    out["forward_change"] = forward_change

    current_z = float(out.iloc[-1]["signal_zscore"]) if pd.notna(out.iloc[-1]["signal_zscore"]) else np.nan
    base = {
        "current_zscore": current_z,
        "analogs": 0,
        "mean_forward_change": np.nan,
        "median_forward_change": np.nan,
        "win_rate": np.nan,
        "behavior": "unknown",
        "horizon": horizon,
    }

    if not np.isfinite(current_z):
        return {
            **base,
            "signal": "INSUFFICIENT HISTORY",
            "reason": f"Need more observations to estimate a lagged {lookback}-observation z-score.",
        }

    if abs(current_z) < entry_z:
        return {
            **base,
            "signal": "NO SIGNAL",
            "reason": f"Current |z|={abs(current_z):.2f} is below the {entry_z:.2f} entry threshold.",
        }

    historical = out.iloc[:-1].dropna(subset=["signal_zscore", "forward_change"]).copy()
    if current_z > 0:
        analogs = historical[historical["signal_zscore"] >= entry_z]
    else:
        analogs = historical[historical["signal_zscore"] <= -entry_z]

    n = int(len(analogs))
    base["analogs"] = n
    if n < min_analogs:
        return {
            **base,
            "signal": "INSUFFICIENT HISTORY",
            "reason": f"Only {n} valid same-side historical analogues; require at least {min_analogs}.",
        }

    moves = analogs["forward_change"].astype(float)
    mean_move = float(moves.mean())
    median_move = float(moves.median())
    if np.isclose(mean_move, 0.0):
        return {
            **base,
            "signal": "NO SIGNAL",
            "reason": "Comparable historical extremes had approximately zero average forward move.",
            "mean_forward_change": mean_move,
            "median_forward_change": median_move,
            "win_rate": 0.5,
        }

    direction = "LONG" if mean_move > 0 else "SHORT"
    wins = moves > 0 if mean_move > 0 else moves < 0
    win_rate = float(wins.mean())
    behavior = "mean reversion" if np.sign(mean_move) == -np.sign(current_z) else "momentum / continuation"

    result = {
        **base,
        "mean_forward_change": mean_move,
        "median_forward_change": median_move,
        "win_rate": win_rate,
        "behavior": behavior,
    }
    if win_rate < min_win_rate:
        return {
            **result,
            "signal": "NO SIGNAL",
            "reason": f"Historical directional win rate {win_rate:.1%} is below the {min_win_rate:.1%} quality threshold.",
        }

    return {
        **result,
        "signal": direction,
        "reason": (
            f"{n} comparable historical extremes moved {direction.lower()} over the next "
            f"{horizon} observations with a {win_rate:.1%} directional win rate."
        ),
    }

def estimate_mean_reversion_half_life(values: pd.Series) -> float:
    """Estimate an OU-style half-life in observations from Δx ~ a + b*x[-1]."""
    series = pd.Series(values, dtype=float).dropna()
    if len(series) < 4:
        return np.nan
    lagged = series.shift(1)
    delta = series.diff()
    frame = pd.concat([lagged.rename("lagged"), delta.rename("delta")], axis=1).dropna()
    if len(frame) < 3:
        return np.nan
    x = np.column_stack([np.ones(len(frame)), frame["lagged"].to_numpy()])
    y = frame["delta"].to_numpy()
    _, beta = np.linalg.lstsq(x, y, rcond=None)[0]
    if beta >= 0 or np.isclose(beta, 0.0):
        return np.nan
    return float(-np.log(2.0) / beta)


def relative_value_statistics(values: pd.Series) -> dict[str, float]:
    """Current percentile/z-score plus simple persistence/mean-reversion diagnostics."""
    series = pd.Series(values, dtype=float).dropna()
    if series.empty:
        return {
            "observations": 0.0,
            "latest": np.nan,
            "mean": np.nan,
            "std": np.nan,
            "zscore": np.nan,
            "percentile": np.nan,
            "autocorr_1": np.nan,
            "half_life": np.nan,
        }

    latest = float(series.iloc[-1])
    mean = float(series.mean())
    std = float(series.std(ddof=1)) if len(series) > 1 else np.nan
    zscore = (latest - mean) / std if np.isfinite(std) and std > 0 else np.nan
    percentile = float((series <= latest).mean())
    autocorr = float(series.autocorr(lag=1)) if len(series) >= 3 else np.nan
    return {
        "observations": float(len(series)),
        "latest": latest,
        "mean": mean,
        "std": std,
        "zscore": float(zscore) if np.isfinite(zscore) else np.nan,
        "percentile": percentile,
        "autocorr_1": autocorr,
        "half_life": estimate_mean_reversion_half_life(series),
    }
