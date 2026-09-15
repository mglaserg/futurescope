from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from typing import Literal

import numpy as np
import pandas as pd

from futurescope.analytics.relative_value import relative_value_zscore_history

TargetMode = Literal["dynamic_zero", "frozen_entry_mean"]


@dataclass(frozen=True)
class MeanReversionSummary:
    episodes: int
    hits: int
    censored_roll: int
    censored_time: int
    hit_rate: float
    hit_rate_ci_low: float
    hit_rate_ci_high: float
    median_time_to_mean_obs: float
    median_time_to_mean_days: float
    mean_pnl_price_units: float
    median_pnl_price_units: float
    mean_mae_price_units: float
    mean_mfe_price_units: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _lagged_benchmarks(values: pd.Series, lookback: int) -> tuple[pd.Series, pd.Series]:
    min_periods = min(lookback, max(3, lookback // 2))
    mean = values.rolling(lookback, min_periods=min_periods).mean().shift(1)
    std = values.rolling(lookback, min_periods=min_periods).std(ddof=1).shift(1)
    return mean, std


def _wilson_interval(successes: int, n: int, zcrit: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return np.nan, np.nan
    p = successes / n
    denom = 1.0 + (zcrit * zcrit) / n
    center = (p + (zcrit * zcrit) / (2.0 * n)) / denom
    half = (zcrit / denom) * sqrt((p * (1.0 - p) / n) + (zcrit * zcrit) / (4.0 * n * n))
    return max(0.0, center - half), min(1.0, center + half)


def first_passage_mean_reversion_episodes(
    history: pd.DataFrame,
    *,
    lookback: int = 20,
    entry_z: float = 2.0,
    max_horizon: int = 20,
    target_mode: TargetMode = "frozen_entry_mean",
) -> pd.DataFrame:
    """Measure non-overlapping extreme-z episodes and first passage back to the mean.

    An episode begins only when the lagged rolling z-score crosses from inside the
    entry band to ``|z| >= entry_z``.  It ends at the first mean crossing, a
    contract-roll boundary, or ``max_horizon`` observations, whichever happens
    first.  This avoids counting every day of one persistent extreme as a separate
    independent event.

    ``dynamic_zero`` targets the contemporaneous rolling z-score crossing zero.
    ``frozen_entry_mean`` freezes the lagged rolling mean observed at entry and
    asks whether the structure itself crosses that level.  The frozen target is
    generally the cleaner trading interpretation because the target cannot move
    toward the trade after entry.

    P&L is expressed in canonical structure price units.  Transaction costs and
    contract multipliers are deliberately excluded here; the result is a research
    diagnostic, not production net P&L.
    """
    required = {"snapshot_date", "value", "canonical_value", "leg_symbols"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"history is missing required columns: {sorted(missing)}")
    if lookback < 3:
        raise ValueError("lookback must be at least 3")
    if entry_z <= 0:
        raise ValueError("entry_z must be positive")
    if max_horizon < 1:
        raise ValueError("max_horizon must be at least 1")
    if target_mode not in {"dynamic_zero", "frozen_entry_mean"}:
        raise ValueError("target_mode must be 'dynamic_zero' or 'frozen_entry_mean'")

    out = relative_value_zscore_history(history, lookback=lookback)
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"], errors="coerce")
    out = out.dropna(subset=["snapshot_date"]).sort_values("snapshot_date").reset_index(drop=True)
    out["benchmark_mean"], out["benchmark_std"] = _lagged_benchmarks(out["value"], lookback)

    rows: list[dict[str, object]] = []
    i = 1
    while i < len(out):
        z = out.loc[i, "signal_zscore"]
        prev_z = out.loc[i - 1, "signal_zscore"]
        if pd.isna(z):
            i += 1
            continue

        crossed_into_extreme = abs(float(z)) >= entry_z and (
            pd.isna(prev_z) or abs(float(prev_z)) < entry_z
        )
        if not crossed_into_extreme:
            i += 1
            continue

        entry_idx = i
        entry_zscore = float(z)
        side = "LOW" if entry_zscore < 0 else "HIGH"
        direction = 1.0 if entry_zscore < 0 else -1.0
        trade_direction = "LONG" if direction > 0 else "SHORT"
        entry_value = float(out.loc[entry_idx, "value"])
        entry_canonical = float(out.loc[entry_idx, "canonical_value"])
        entry_mean = float(out.loc[entry_idx, "benchmark_mean"])
        entry_legs = str(out.loc[entry_idx, "leg_symbols"])
        entry_date = pd.Timestamp(out.loc[entry_idx, "snapshot_date"])

        path_pnl = [0.0]
        status = "CENSORED_TIME"
        exit_idx = min(entry_idx + max_horizon, len(out) - 1)
        hit = False

        for j in range(entry_idx + 1, min(entry_idx + max_horizon, len(out) - 1) + 1):
            if str(out.loc[j, "leg_symbols"]) != entry_legs:
                status = "CENSORED_ROLL"
                exit_idx = j - 1
                break

            current_canonical = float(out.loc[j, "canonical_value"])
            path_pnl.append(direction * (current_canonical - entry_canonical))

            if target_mode == "dynamic_zero":
                current_z = out.loc[j, "signal_zscore"]
                if pd.notna(current_z):
                    hit = float(current_z) >= 0.0 if entry_zscore < 0 else float(current_z) <= 0.0
            else:
                current_value = float(out.loc[j, "value"])
                hit = current_value >= entry_mean if entry_zscore < 0 else current_value <= entry_mean

            if hit:
                status = "HIT_MEAN"
                exit_idx = j
                break
        else:
            exit_idx = min(entry_idx + max_horizon, len(out) - 1)

        # If the first future observation itself rolled, path_pnl contains only zero.
        exit_canonical = float(out.loc[exit_idx, "canonical_value"])
        exit_date = pd.Timestamp(out.loc[exit_idx, "snapshot_date"])
        pnl = direction * (exit_canonical - entry_canonical)
        if len(path_pnl) == 1 and exit_idx > entry_idx:
            pnl = direction * (exit_canonical - entry_canonical)
            path_pnl.append(pnl)

        elapsed_obs = int(exit_idx - entry_idx)
        elapsed_days = float((exit_date - entry_date).total_seconds() / 86400.0)
        rows.append(
            {
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_side": side,
                "trade_direction": trade_direction,
                "entry_zscore": entry_zscore,
                "entry_value": entry_value,
                "entry_mean": entry_mean,
                "entry_canonical_value": entry_canonical,
                "exit_canonical_value": exit_canonical,
                "leg_symbols": entry_legs,
                "status": status,
                "hit_mean": status == "HIT_MEAN",
                "time_to_mean_obs": float(elapsed_obs) if status == "HIT_MEAN" else np.nan,
                "time_to_mean_days": elapsed_days if status == "HIT_MEAN" else np.nan,
                "duration_obs": elapsed_obs,
                "duration_days": elapsed_days,
                "pnl_price_units": pnl,
                "mae_price_units": float(np.min(path_pnl)),
                "mfe_price_units": float(np.max(path_pnl)),
                "target_mode": target_mode,
            }
        )

        # Episodes are non-overlapping.  Continue after the exit/censor observation.
        i = max(exit_idx + 1, entry_idx + 1)

    return pd.DataFrame(rows)


def summarize_mean_reversion(episodes: pd.DataFrame) -> MeanReversionSummary:
    if episodes.empty:
        return MeanReversionSummary(
            episodes=0,
            hits=0,
            censored_roll=0,
            censored_time=0,
            hit_rate=np.nan,
            hit_rate_ci_low=np.nan,
            hit_rate_ci_high=np.nan,
            median_time_to_mean_obs=np.nan,
            median_time_to_mean_days=np.nan,
            mean_pnl_price_units=np.nan,
            median_pnl_price_units=np.nan,
            mean_mae_price_units=np.nan,
            mean_mfe_price_units=np.nan,
        )

    n = int(len(episodes))
    hits = int(episodes["hit_mean"].sum())
    ci_low, ci_high = _wilson_interval(hits, n)
    hit_rows = episodes[episodes["hit_mean"]]
    return MeanReversionSummary(
        episodes=n,
        hits=hits,
        censored_roll=int((episodes["status"] == "CENSORED_ROLL").sum()),
        censored_time=int((episodes["status"] == "CENSORED_TIME").sum()),
        hit_rate=float(hits / n),
        hit_rate_ci_low=float(ci_low),
        hit_rate_ci_high=float(ci_high),
        median_time_to_mean_obs=float(hit_rows["time_to_mean_obs"].median()) if not hit_rows.empty else np.nan,
        median_time_to_mean_days=float(hit_rows["time_to_mean_days"].median()) if not hit_rows.empty else np.nan,
        mean_pnl_price_units=float(episodes["pnl_price_units"].mean()),
        median_pnl_price_units=float(episodes["pnl_price_units"].median()),
        mean_mae_price_units=float(episodes["mae_price_units"].mean()),
        mean_mfe_price_units=float(episodes["mfe_price_units"].mean()),
    )


def kaplan_meier_mean_reversion(episodes: pd.DataFrame) -> pd.DataFrame:
    """Kaplan-Meier estimate of probability an episode has *not* hit the mean yet."""
    if episodes.empty:
        return pd.DataFrame(columns=["duration_obs", "at_risk", "events", "censored", "survival"])

    work = episodes[["duration_obs", "hit_mean"]].copy()
    work["duration_obs"] = work["duration_obs"].astype(int)
    at_risk = len(work)
    survival = 1.0
    rows: list[dict[str, float | int]] = []
    for duration in sorted(work["duration_obs"].unique()):
        bucket = work[work["duration_obs"] == duration]
        events = int(bucket["hit_mean"].sum())
        censored = int(len(bucket) - events)
        if at_risk > 0 and events > 0:
            survival *= 1.0 - (events / at_risk)
        rows.append(
            {
                "duration_obs": int(duration),
                "at_risk": int(at_risk),
                "events": events,
                "censored": censored,
                "survival": float(survival),
            }
        )
        at_risk -= events + censored
    return pd.DataFrame(rows)


def mean_reversion_analysis(
    history: pd.DataFrame,
    *,
    lookback: int = 20,
    entry_z: float = 2.0,
    max_horizon: int = 20,
    target_mode: TargetMode = "frozen_entry_mean",
) -> tuple[pd.DataFrame, MeanReversionSummary, pd.DataFrame]:
    episodes = first_passage_mean_reversion_episodes(
        history,
        lookback=lookback,
        entry_z=entry_z,
        max_horizon=max_horizon,
        target_mode=target_mode,
    )
    return episodes, summarize_mean_reversion(episodes), kaplan_meier_mean_reversion(episodes)
