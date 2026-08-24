from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


class LocalFrameCache:
    """Tiny CSV cache for market-data frames.

    Historical snapshots are immutable enough for our V1 use case, so the cache key
    includes the requested as-of date. Use refresh=True to bypass it.
    """

    def __init__(self, directory: str | Path = "cache") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        return self.directory / f"{digest}.csv"

    def read(self, key: str) -> pd.DataFrame | None:
        path = self._path(key)
        if not path.exists():
            return None
        return pd.read_csv(path)

    def write(self, key: str, frame: pd.DataFrame) -> None:
        frame.to_csv(self._path(key), index=False)
