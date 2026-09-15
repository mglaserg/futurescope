# React / TypeScript frontend migration

Futurescope is migrating incrementally rather than replacing Streamlit in one rewrite.

## Architecture

- **Python remains authoritative** for market data, curve construction, research, signals, and Conductor intents.
- `futurescope/api.py` is the thin FastAPI boundary.
- `frontend/` is React + TypeScript + Vite.
- TanStack Query owns browser-side server-state fetching/caching.
- Apache ECharts provides interactive financial/research charts.
- Streamlit remains fully usable while screens are migrated.

## First migrated surfaces

The first React iteration deliberately implements real workflows rather than a blank shell:

1. **Today** — current futures curve and calendar-slope map.
2. **Mean Reversion Lab** — registered first-passage research with z-score history, survival curve, hit-rate uncertainty, MAE/MFE, and episode detail.

The next React migrations remain Daily Opportunities, Synthetic/Curve Viewer, and Trade Builder.

## Run

From the repository root on Windows:

```bat
run_futurescope_web.bat
```

or:

```bash
python run_futurescope_web.py
```

On first run the launcher installs `requirements-web.txt` if FastAPI is missing and runs `npm install` inside `frontend/` if `node_modules` is missing. It then starts:

- React/Vite: `http://127.0.0.1:5173`
- FastAPI: `http://127.0.0.1:8000`
- OpenAPI docs: `http://127.0.0.1:8000/docs`

Vite 8 requires Node.js 20.19+ or 22.12+.

### Environment file

The web launcher and FastAPI service both load the repository-root `.env` explicitly before Databento providers are constructed. Keep the file here:

```text
futurescope/
  .env
  run_futurescope_web.py
  frontend/
  futurescope/
```

with:

```text
DATABENTO_API_KEY=db-your-real-key-here
```

At startup the launcher prints whether it found `.env` and whether the Databento key loaded. `/api/health` reports the same status without exposing the key. Restart Futurescope Web after changing `.env`.

## Production build

```bash
cd frontend
npm install
npm run build
cd ..
python -m uvicorn futurescope.api:app --host 127.0.0.1 --port 8000
```

When `frontend/dist` exists, the FastAPI app serves the built frontend as its fallback route.

## Data Manager

The React app now includes a **Data** view for maintaining the local curve-history cache used by the Mean Reversion Lab.

- **Refresh this date** on Today bypasses Futurescope's raw Databento request cache for the selected date.
- **Backfill curve history** downloads/builds snapshots over a chosen range with business-daily, weekly, or month-end sampling.
- Existing `cache/curve_snapshots/<MARKET>/<DATE>.csv` snapshots are skipped unless **Force redownload** is enabled.
- If the selected range includes today, Futurescope queries Databento's schema-specific availability and clips the exclusive request end to the latest available timestamp instead of requesting the next UTC midnight.
- Each uncached date can require Databento parent `definition` and `ohlcv-1d` requests; the provider-level raw request cache is reused by default.
- A single batch is capped at 260 selected dates so large daily histories are intentional and easy to split.

The equivalent CLI is:

```bash
python -m futurescope.data_manager GC 2026-01-01 2026-09-15 --sampling business_daily
```

Add `--force-refresh` only when you deliberately want Databento queried again for dates already present in the raw cache.
