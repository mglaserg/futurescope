from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from futurescope.analytics.relative_value import (
    STRUCTURE_NAMES,
    build_relative_value_history,
    build_relative_value_structures,
    relative_value_zscore_history,
)
from futurescope.config import MARKETS
from futurescope.mean_reversion import mean_reversion_analysis
from futurescope.research_logging import log_dashboard_look
from futurescope.rv_store import CurveSnapshotStore, load_cached_curve_history, load_relative_value_curve


class MeanReversionRequest(BaseModel):
    market: str = Field(pattern="^[A-Za-z]{1,4}$")
    order: int = Field(default=1, ge=1, le=3)
    position: int = Field(default=1, ge=1)
    lookback: int = Field(default=20, ge=3, le=504)
    entry_z: float = Field(default=2.0, gt=0, le=10)
    max_horizon: int = Field(default=20, ge=1, le=252)
    target_mode: Literal["dynamic_zero", "frozen_entry_mean"] = "frozen_entry_mean"
    reason: str = Field(default="Mean-reversion first-passage analysis from React lab", min_length=3, max_length=500)


def _json_value(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
        return None if not np.isfinite(value) else value
    if isinstance(value, float):
        return None if not np.isfinite(value) else value
    if pd.isna(value):
        return None
    return value


def _records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def create_app() -> FastAPI:
    app = FastAPI(title="Futurescope API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "databento_configured": bool(os.getenv("DATABENTO_API_KEY")),
            "markets": list(MARKETS),
        }

    @app.get("/api/today/{market}")
    def today(
        market: str,
        as_of: date | None = Query(default=None),
        refresh: bool = False,
    ) -> dict[str, object]:
        symbol = market.upper()
        config = MARKETS.get(symbol)
        if config is None:
            raise HTTPException(status_code=404, detail=f"Unknown market {symbol}")
        effective_as_of = as_of or date.today()
        try:
            curve = load_relative_value_curve(config, as_of=effective_as_of, refresh=refresh)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        structures: dict[str, list[dict]] = {}
        for order in (1, 2, 3):
            structures[str(order)] = _records(build_relative_value_structures(curve, order=order))
        return {
            "market": symbol,
            "market_name": config.name,
            "as_of": effective_as_of.isoformat(),
            "curve": _records(curve),
            "structures": structures,
        }

    @app.post("/api/research/mean-reversion")
    def mean_reversion(request: MeanReversionRequest) -> dict[str, object]:
        symbol = request.market.upper()
        if symbol not in MARKETS:
            raise HTTPException(status_code=404, detail=f"Unknown market {symbol}")

        snapshots = load_cached_curve_history(symbol)
        if snapshots.empty:
            raise HTTPException(
                status_code=409,
                detail=f"No cached curve snapshots for {symbol}. Run/refresh the monitor first.",
            )
        history = build_relative_value_history(
            snapshots,
            order=request.order,
            position=request.position,
            value_column="time_normalized_value",
        )
        if history.empty:
            raise HTTPException(status_code=409, detail="No history for this curve structure/position.")

        look_id = log_dashboard_look(
            "mean_reversion_first_passage",
            {
                "market": symbol,
                "order": request.order,
                "position": request.position,
                "lookback": request.lookback,
                "entry_z": request.entry_z,
                "max_horizon": request.max_horizon,
                "target_mode": request.target_mode,
            },
            request.reason,
        )

        episodes, summary, survival = mean_reversion_analysis(
            history,
            lookback=request.lookback,
            entry_z=request.entry_z,
            max_horizon=request.max_horizon,
            target_mode=request.target_mode,
        )
        z_history = relative_value_zscore_history(history, lookback=request.lookback)
        history_view = z_history[["snapshot_date", "value", "canonical_value", "signal_zscore", "leg_symbols"]].copy()
        return {
            "research_look_id": look_id,
            "market": symbol,
            "structure": STRUCTURE_NAMES[request.order],
            "order": request.order,
            "position": request.position,
            "target_mode": request.target_mode,
            "summary": summary.to_dict(),
            "episodes": _records(episodes),
            "survival": _records(survival),
            "history": _records(history_view),
            "note": "Descriptive first-passage research in canonical price units; costs/multipliers are not applied here.",
        }

    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    if (frontend_dist / "index.html").exists():
        @app.get("/{full_path:path}", include_in_schema=False)
        def frontend(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
