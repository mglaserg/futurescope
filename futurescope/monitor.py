from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    build_relative_value_history,
    build_relative_value_structures,
    relative_value_zscore_history,
)


@dataclass(frozen=True)
class MonitorArchiveRecord:
    market: str
    as_of_date: date
    observed_at_utc: datetime
    observation_hash: str


class MonitorArchive:
    """Append-only current-state archive for Futurescope Monitor observations."""

    def __init__(self, path: str | Path = "cache/futurescope_monitor.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    observed_at_utc TEXT NOT NULL,
                    observation_hash TEXT NOT NULL UNIQUE,
                    reference_price REAL,
                    reference_source TEXT,
                    curve_json TEXT NOT NULL,
                    structures_json TEXT NOT NULL,
                    spread_costs_json TEXT NOT NULL,
                    notes TEXT
                )
                """
            )

    @staticmethod
    def _frame_json(frame: pd.DataFrame) -> str:
        if frame is None or frame.empty:
            return "[]"
        return frame.to_json(orient="records", date_format="iso", double_precision=12)

    def write(
        self,
        market: str,
        as_of_date: date,
        curve: pd.DataFrame,
        structures: pd.DataFrame,
        spread_costs: pd.DataFrame,
        reference_price: float | None = None,
        reference_source: str | None = None,
        notes: str = "",
    ) -> MonitorArchiveRecord:
        payload = {
            "market": market.upper(),
            "as_of_date": as_of_date.isoformat(),
            "curve": self._frame_json(curve),
            "structures": self._frame_json(structures),
            "spread_costs": self._frame_json(spread_costs),
            "reference_price": reference_price,
            "reference_source": reference_source,
            "notes": notes,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        observed_at = datetime.now(timezone.utc)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO monitor_observations (
                    market, as_of_date, observed_at_utc, observation_hash,
                    reference_price, reference_source, curve_json,
                    structures_json, spread_costs_json, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    market.upper(),
                    as_of_date.isoformat(),
                    observed_at.isoformat(),
                    digest,
                    reference_price,
                    reference_source,
                    payload["curve"],
                    payload["structures"],
                    payload["spread_costs"],
                    notes,
                ),
            )
        return MonitorArchiveRecord(market.upper(), as_of_date, observed_at, digest)

    def list(self, market: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM monitor_observations"
        params: tuple[object, ...] = ()
        if market:
            query += " WHERE market = ?"
            params = (market.upper(),)
        query += " ORDER BY observed_at_utc"
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=params)


def _empirical_percentile(values: pd.Series, current: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty or not np.isfinite(current):
        return np.nan
    return float((clean <= float(current)).mean())


def build_monitor_structures(
    curve: pd.DataFrame,
    snapshots: pd.DataFrame,
    spread_costs: pd.DataFrame | None = None,
    lookback: int = 20,
    unusual_z: float = 2.0,
) -> pd.DataFrame:
    """Current-state-only structure table with no forward-outcome statistics."""

    rows: list[dict[str, object]] = []
    for order in (1, 2, 3):
        current = build_relative_value_structures(curve, order=order)
        for structure in current.itertuples(index=False):
            history = (
                build_relative_value_history(
                    snapshots,
                    order=order,
                    position=int(structure.position),
                    value_column="time_normalized_value",
                )
                if snapshots is not None and not snapshots.empty
                else pd.DataFrame()
            )
            zscore = np.nan
            percentile = np.nan
            observations = 0
            if not history.empty:
                zhist = relative_value_zscore_history(history, lookback=int(lookback))
                if not zhist.empty:
                    zscore = pd.to_numeric(zhist.iloc[-1]["signal_zscore"], errors="coerce")
                observations = len(history)
                percentile = _empirical_percentile(history["value"], float(structure.time_normalized_value))

            row = {
                "order": order,
                "structure": STRUCTURE_NAMES[order],
                "position": int(structure.position),
                "curve_location": str(structure.tenor_label),
                "leg_symbols": str(structure.leg_symbols),
                "canonical_weights": str(structure.canonical_weights),
                "canonical_value": float(structure.canonical_value),
                "normalized_value": float(structure.time_normalized_value),
                "span_days": float(structure.span_days),
                "zscore": float(zscore) if np.isfinite(zscore) else np.nan,
                "percentile": percentile,
                "history_observations": observations,
                "current_state": (
                    "UNUSUAL" if np.isfinite(zscore) and abs(float(zscore)) >= float(unusual_z) else "NORMAL"
                ),
            }
            rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty or spread_costs is None or spread_costs.empty:
        return out
    merge_cols = [
        "order",
        "position",
        "exchange_symbol",
        "matched_exchange_strategy",
        "bid",
        "ask",
        "width_points",
        "width_ticks",
        "bid_size",
        "ask_size",
        "top_depth",
        "daily_volume",
        "round_turn_crossing_cost_usd",
        "liquidity_pass",
        "liquidity_reason",
        "quote_ts",
    ]
    available = [c for c in merge_cols if c in spread_costs.columns]
    return out.merge(spread_costs[available], on=["order", "position"], how="left")
