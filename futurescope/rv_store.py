from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from futurescope.analytics.curve import enrich_curve
from futurescope.config import MarketConfig
from futurescope.providers import DatabentoProvider


class CurveSnapshotStore:
    """Human-readable local history of enriched futures-curve snapshots.

    The existing Databento provider already caches raw historical requests. This
    store adds a second, market/date-organized cache specifically for curve-RV
    playback and historical diagnostics.
    """

    def __init__(self, directory: str | Path = "cache/curve_snapshots") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _market_dir(self, symbol: str) -> Path:
        path = self.directory / symbol.upper()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path(self, symbol: str, as_of: date) -> Path:
        return self._market_dir(symbol) / f"{as_of.isoformat()}.csv"

    def write(self, symbol: str, as_of: date, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        out = frame.copy()
        if "snapshot_date" in out.columns:
            out = out.drop(columns=["snapshot_date"])
        out.insert(0, "snapshot_date", pd.Timestamp(as_of).date().isoformat())
        out.to_csv(self._path(symbol, as_of), index=False)

    def read(self, symbol: str, as_of: date) -> pd.DataFrame | None:
        path = self._path(symbol, as_of)
        if not path.exists():
            return None
        return self._parse(pd.read_csv(path))

    def read_all(self, symbol: str) -> pd.DataFrame:
        files = sorted(self._market_dir(symbol).glob("*.csv"))
        if not files:
            return pd.DataFrame()
        return pd.concat([self._parse(pd.read_csv(path)) for path in files], ignore_index=True)

    def dates(self, symbol: str) -> list[date]:
        dates: list[date] = []
        for path in sorted(self._market_dir(symbol).glob("*.csv")):
            try:
                dates.append(pd.Timestamp(path.stem).date())
            except ValueError:
                continue
        return dates

    @staticmethod
    def _parse(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        if "snapshot_date" in out.columns:
            out["snapshot_date"] = pd.to_datetime(out["snapshot_date"], errors="coerce")
        if "expiration" in out.columns:
            out["expiration"] = pd.to_datetime(out["expiration"], utc=True, errors="coerce")
        if "ts_event" in out.columns:
            out["ts_event"] = pd.to_datetime(out["ts_event"], utc=True, errors="coerce")
        return out


def load_relative_value_curve(
    config: MarketConfig,
    as_of: date,
    refresh: bool = False,
    store: CurveSnapshotStore | None = None,
) -> pd.DataFrame:
    """Load a futures curve without fetching an external spot reference.

    This deliberately bypasses ``services.load_market_curve`` so the RV iteration
    can be installed additively even when the app's service layer has changed.
    Databento's existing request cache is still reused.
    """
    provider = DatabentoProvider()
    raw = provider.get_curve(
        dataset=config.dataset,
        parent_symbol=config.parent_symbol,
        as_of=as_of,
        max_contracts=config.max_contracts,
        refresh=refresh,
    )
    curve = enrich_curve(raw, pd.Timestamp(as_of), spot=None)
    (store or CurveSnapshotStore()).write(config.symbol, as_of, curve)
    return curve


def load_cached_curve_history(symbol: str, store: CurveSnapshotStore | None = None) -> pd.DataFrame:
    return (store or CurveSnapshotStore()).read_all(symbol)
