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

## Production build

```bash
cd frontend
npm install
npm run build
cd ..
python -m uvicorn futurescope.api:app --host 127.0.0.1 --port 8000
```

When `frontend/dist` exists, the FastAPI app serves the built frontend as its fallback route.
