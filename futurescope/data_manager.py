from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from futurescope.config import MARKETS
from futurescope.environment import load_futurescope_env
from futurescope.rv_store import CurveSnapshotStore, load_relative_value_curve

Sampling = Literal["business_daily", "weekly", "month_end"]


@dataclass(frozen=True)
class CacheStatus:
    market: str
    snapshots: int
    first_snapshot: str | None
    last_snapshot: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def planned_snapshot_dates(start: date, end: date, sampling: Sampling = "business_daily") -> list[date]:
    if end < start:
        raise ValueError("end must be on or after start")
    frequency = {
        "business_daily": "B",
        "weekly": "W-FRI",
        "month_end": "BME",
    }.get(sampling)
    if frequency is None:
        raise ValueError(f"Unsupported sampling: {sampling}")

    dates = [ts.date() for ts in pd.date_range(start, end, freq=frequency)]
    # For weekly/month-end requests, include the requested end date when it is a
    # weekday so an operator can always explicitly add the latest observation.
    if sampling != "business_daily" and end.weekday() < 5:
        dates.append(end)
    today = date.today()
    return sorted({d for d in dates if d <= today})


def cache_status(symbol: str, store: CurveSnapshotStore | None = None) -> CacheStatus:
    dates = (store or CurveSnapshotStore()).dates(symbol)
    return CacheStatus(
        market=symbol.upper(),
        snapshots=len(dates),
        first_snapshot=min(dates).isoformat() if dates else None,
        last_snapshot=max(dates).isoformat() if dates else None,
    )


def all_cache_status(store: CurveSnapshotStore | None = None) -> list[CacheStatus]:
    target = store or CurveSnapshotStore()
    return [cache_status(symbol, target) for symbol in MARKETS]


def backfill_curve_history(
    market: str,
    start: date,
    end: date,
    sampling: Sampling = "business_daily",
    force_refresh: bool = False,
    max_dates: int = 260,
    store: CurveSnapshotStore | None = None,
) -> dict[str, object]:
    symbol = market.upper()
    config = MARKETS.get(symbol)
    if config is None:
        raise ValueError(f"Unknown market {symbol}")
    load_futurescope_env()
    target = store or CurveSnapshotStore()
    dates = planned_snapshot_dates(start, end, sampling)
    if not dates:
        return {
            "market": symbol,
            "requested": 0,
            "downloaded": 0,
            "skipped_cached": 0,
            "failures": [],
            "status": cache_status(symbol, target).to_dict(),
        }
    if len(dates) > max_dates:
        raise ValueError(
            f"This batch contains {len(dates)} snapshot dates; the maximum is {max_dates}. "
            "Split the request into smaller ranges."
        )

    existing = set(target.dates(symbol))
    downloaded = 0
    skipped = 0
    failures: list[dict[str, str]] = []
    for snapshot_date in dates:
        if snapshot_date in existing and not force_refresh:
            skipped += 1
            continue
        try:
            curve = load_relative_value_curve(
                config,
                as_of=snapshot_date,
                refresh=force_refresh,
                store=target,
            )
            if curve.empty:
                failures.append({"date": snapshot_date.isoformat(), "error": "Databento returned an empty curve"})
                continue
            downloaded += 1
            existing.add(snapshot_date)
        except Exception as exc:  # operator-facing batch should continue past individual failures
            failures.append({"date": snapshot_date.isoformat(), "error": str(exc)})

    return {
        "market": symbol,
        "sampling": sampling,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "requested": len(dates),
        "downloaded": downloaded,
        "skipped_cached": skipped,
        "failures": failures,
        "status": cache_status(symbol, target).to_dict(),
        "note": (
            "Each uncached snapshot uses the existing Databento parent-definition and OHLCV-1d cache. "
            "Current-day requests are clipped to Databento's schema-specific available end. "
            "force_refresh=true bypasses that raw request cache."
        ),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill Futurescope curve snapshots from Databento.")
    parser.add_argument("market", choices=list(MARKETS))
    parser.add_argument("start", type=date.fromisoformat)
    parser.add_argument("end", type=date.fromisoformat)
    parser.add_argument("--sampling", choices=["business_daily", "weekly", "month_end"], default="business_daily")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    result = backfill_curve_history(
        args.market,
        args.start,
        args.end,
        sampling=args.sampling,
        force_refresh=args.force_refresh,
    )
    print(
        f"{result['market']}: downloaded {result['downloaded']}, "
        f"skipped {result['skipped_cached']}, failures {len(result['failures'])}."
    )
    status = result["status"]
    print(f"Cache: {status['snapshots']} snapshots · {status['first_snapshot']} -> {status['last_snapshot']}")
    for failure in result["failures"]:
        print(f"WARNING {failure['date']}: {failure['error']}")
    return 0 if not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
