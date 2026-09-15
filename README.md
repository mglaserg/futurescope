# Futurescope

Futurescope is a Streamlit research instrument for **futures term structure, relative value, basis, carry, and the VIX complex**.

It keeps three different economic objects separate:

1. **Spot vs dated-futures basis / cash-and-carry** — potentially lockable only when the spot/deliverable leg is economically equivalent and both sides can be carried through settlement.
2. **Calendar-curve relative value / roll** — slope, butterfly, and higher-order curve-shape trades between futures maturities.
3. **VIX term structure** — VX converges to VIX settlement, but VIX itself is not directly purchasable spot, so VX/VIX is not a conventional cash-and-carry arbitrage.

Crypto perpetual carry is intentionally kept outside Futurescope.

## Markets

- GC — COMEX Gold
- CL — NYMEX WTI Crude Oil
- ES — E-mini S&P 500
- ZN — 10-Year U.S. Treasury Note
- VX — Cboe VIX futures
- MES — Micro E-mini S&P 500 (execution leg for the month-end rebalance module)
- ZB — 30-Year U.S. Treasury Bond (experimental execution/translation asset pending CTD/DV01 completion)

Futures curves come from Databento. Official Cboe daily CSVs supply VIX-family index history. GC uses goldprice.dev for recent XAU/USD daily references; Yahoo Finance remains a convenience S&P 500 cash-index reference until the ES timestamp/dividend/funding alignment layer is completed.

## Product workflow and navigation

Futurescope now uses grouped top navigation so the product opens around jobs rather than a flat list of screens:

1. **Start / Monitor** — what is happening now?
2. **Trade** — what exactly is the exposure or basket?
3. **Research** — does the idea have registered historical evidence?
4. **Deep Dive** — raw/reference views when needed.

The default Start page reduces the product to three questions: **See Today → Express It → Prove It**. Page-specific filters remain in the sidebar instead of competing with the global navigation.

## Current pages

- **ES + GC Monitor** — current-state-only vertical slice. Shows curve shape, z-score/percentile location, exchange-listed strategy BBO/depth/volume, and an operational liquidity/cost gate.
- **Synthetic Tenors** — constant-maturity futures points such as 50d and 80d, fixed-DTE slope/z-score history, listed-contract interpolation weights, and exploratory Conductor intent export.
- **Carry Screener** — cross-market carry/basis screen.
- **Curve Explorer** — individual futures curve and basis/carry view.
- **VIX Complex** — VX curve plus official Cboe VIX-family indices.
- **Relative Value** — finite-difference hierarchy: slope, butterfly, double butterfly.
- **Mean Reversion Lab** — registered first-passage analysis from extreme z-scores back to the frozen entry mean or dynamic z=0, including hit-rate uncertainty, time-to-mean, MAE/MFE, censoring, and survival curves.
- **Trade Builder** — exact basket legs, ratios, entry values, point-value economics, and research P&L concepts.
- **Historical Playback** — cached curve replay and explicit retrospective reveals.
- **Daily Opportunities** — historical search/ranking surface; scans are logged as research looks.
- **Month-End Rebalance** — polished current-state 60/40 flow monitor using SPY/IEF for pressure, TLT for duration, and SPY or MES for the equity execution leg.

## Finite-difference hierarchy

For equally spaced contracts, Futurescope uses the long-front trade convention:

```text
Outright       level                      +1
Slope          first finite difference    +1 : -1
Butterfly      second finite difference   +1 : -2 : +1
Double fly     third finite difference    +1 : -3 : +3 : -1
```

The **tradable integer basket** is kept separate from the **time-normalized curve measure**. Uneven days-to-expiry are handled with finite-difference coefficients so irregular tenor spacing is not mistaken for curvature.

## Setup

```powershell
cd futurescope
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set your Databento key in `.env`:

```text
DATABENTO_API_KEY=db-your-real-key-here
```

Do not commit `.env`.

## Run

Windows:

```powershell
run_futurescope.bat
```

or:

```powershell
python run_futurescope.py
```

Optional port:

```powershell
python run_futurescope.py --port 8502
```

The launcher uses the active Python environment.


## React / Node frontend

The incremental frontend migration is now underway. Python remains authoritative for market data and research; the first React + TypeScript + Vite surface talks to a thin FastAPI layer. Streamlit remains available during the migration.

The first migrated workflows are:

- **Today** — current curve and calendar-slope map.
- **Mean Reversion Lab** — registered first-passage research with z-score history and convergence survival.

Run the React version on Windows:

```powershell
run_futurescope_web.bat
```

or:

```powershell
python run_futurescope_web.py
```

On the first run the launcher installs the separate web API requirements and the Node packages if they are missing. React/Vite runs at `http://127.0.0.1:5173`; FastAPI runs at `http://127.0.0.1:8000` with OpenAPI docs at `/docs`. Vite 8 requires Node.js 20.19+ or 22.12+. See `docs/react_frontend.md`.

## Mean reversion / first passage

The core mean-reversion question is now implemented directly rather than left as a roadmap note:

```text
Extreme z-score -> first passage back to mean -> time / MAE / MFE / P&L / censor reason
```

Futurescope starts non-overlapping episodes only when z crosses into a registered extreme. It supports two targets:

- **Frozen entry mean** — preferred trading interpretation; the equilibrium level seen at entry cannot move toward the trade.
- **Dynamic z = 0** — conventional rolling-z mean crossing.

Roll boundaries and time stops are censored. Cross-roll jumps are not counted as convergence P&L. Historical queries are logged before results are revealed. See `docs/mean_reversion.md`.

## ES + GC Monitor

The Monitor is the preferred current-state workflow while clean observations accumulate.

It may show:

- current futures curve
- current finite-difference values
- DTE-normalized slope / curvature / third difference
- current z-score and percentile
- exchange-listed spread/strategy symbol when Databento can match one
- direct strategy-book bid/ask
- top-of-book depth
- daily strategy volume
- spread width in ticks
- estimated round-turn crossing cost in dollars
- operational liquidity pass/fail

The cost calculation uses the **exchange-listed spread/strategy book** when a matching strategy exists rather than approximating cost by summing outright bid/ask spreads.

Monitor observations are archived to `cache/futurescope_monitor.sqlite` and current curve snapshots continue to accumulate under `cache/curve_snapshots/`.

### Timestamp caveat

ES and GC are not yet treated as validation-ready cash/futures basis models. The monitor records deterministic, DST-aware quote targets, but the external cash/reference timestamp semantics still need explicit certification before basis results can support a validated hypothesis.

- ES target monitor quote time: 4:00 p.m. New York time.
- GC target monitor quote time: 1:30 p.m. New York time.

## Research protocol

Futurescope now separates **current-state inspection** from **historical outcome queries**.

Historical conditional returns, win rates, MAE/MFE, P&L proxies, playback forward reveals, and broad opportunity scans are research looks. Interactive historical pages log those queries to a lightweight SQLite registry before the result is displayed.

The protocol is documented in:

```text
docs/research_protocol.md
```

The month-end flow module is documented in `docs/month_end_rebalance.md`.

Key rules:

1. mechanism/counterparty/falsifier before search
2. spread-market cost/liquidity gate before statistics
3. prospective power/precision gate before holdout allocation
4. finite pre-partitioned holdout budget
5. shuffled/randomized dry run before the true holdout reveal
6. cheap, deduplicated trial logging
7. `VALIDATED`, `FAILED`, `UNRESOLVABLE`, and `EXPLORATORY` are all legitimate outcomes
8. the already-observed GC approximately -3 z-score slope convergence is permanently tagged prior-look / exploratory

### Minimal research CLI

```powershell
python research_cli.py init-holdouts research/holdouts.yaml
python research_cli.py register research/specs/es_calendar_001.yaml
python research_cli.py power research/specs/es_calendar_001.yaml
python research_cli.py dry-run research/specs/es_calendar_001.yaml --csv prepared_eval.csv --signal-col signal --outcome-col outcome
python research_cli.py status
```

The experiment template is at `research/specs/_experiment_template.yaml`. The initial audit files use JSON-compatible YAML (JSON is valid YAML 1.2) so the registry adds no dependency to the locked environment. Example holdout configuration is at `research/holdouts.example.yaml`.

## Spot basis

For a futures price `F`, reference price `S`, and `DTE` days to expiration:

```text
basis_pct = F / S - 1
annualized_implied_carry = (F / S - 1) * 365 / DTE
```

This is a screen, not a universal arbitrage formula. Near-expiry annualization can amplify tiny price/timestamp errors and should not drive rankings without a minimum-DTE or fitted-curve treatment.

Market-specific models remain required:

- **ES:** synchronized cash/futures timestamp, financing, expected dividends, funding spread / fair value.
- **GC:** financing plus storage/carry/lease economics and synchronized spot/futures references.
- **ZN:** CTD, conversion factor, gross/net basis, implied repo, delivery option, DV01.
- **CL:** storage, inventory, seasonality, convenience yield.
- **VX:** VIX-specific expectation/settlement and roll mechanics; no directly buyable spot VIX leg.

## Databento usage

The project uses parent symbology such as `GC.FUT` and `ES.FUT`. Parent futures symbology includes outright futures **and exchange-listed futures spreads**, so the Monitor preserves strategy-leg definition fields and matches current Futurescope baskets to listed spread instruments where possible.

Core schemas now include:

- `definition` — outrights plus spread/strategy leg metadata
- `ohlcv-1d` — curve closes and strategy daily volume
- `bbo-1m` — direct top-of-book spread/strategy bid/ask near the monitor timestamp

Requests are cached locally. Use refresh only when you intentionally want a new provider query.

## Tests

```powershell
python -m pytest -q
```

## Conductor handoff

Futurescope now emits a broker-agnostic **trade intent** for Conductor instead of pretending strategy pages should own final sizing and execution. Trade Builder, Synthetic Tenors, Month-End Rebalance, and Cross-Market Curve Carry can export `conductor.trade_intent` JSON.

Core boundary:

```text
Futurescope = what / why / lifecycle
Conductor   = how much / permission / execution / reconciliation
```

The month-end module preserves **TLT as the reference duration exposure** and can prefer **ZB** for futures execution. ZB contract quantity is deliberately delegated to Conductor until CTD-derived DV01 sizing is production-ready.

## Synthetic / constant-maturity futures

Futurescope can now construct fixed-DTE futures points such as **50d** and **80d** by linearly interpolating the listed contracts that bracket each target maturity. It does not extrapolate beyond the available curve.

A synthetic slope is defined consistently through time:

```text
synthetic_slope = F_50d - F_80d
```

Positive means backwardation and negative means contango under the Futurescope sign convention. Because the maturity targets stay fixed, the measurement avoids the changing-DTE meaning and roll discontinuity of a naive F1/F2 history. The page also collapses the two synthetic points back into current listed-contract exposure ratios and exports those ratios as an exploratory Conductor intent. Conductor still owns integer contract sizing and execution. See `docs/synthetic_tenors.md`.

## Cross-Market Curve Carry

The new Cross-Market Curve Carry page is the "DirtyCarry of futures" research candidate. It ranks the current F1/F2 curve using an annualized `log(F1/F2)` slope and can express the ranking either as classic outright-front carry or as calendar-spread curve RV. It is current-state-only and exports an exploratory Conductor intent; profitability remains subject to registered validation. See `docs/cross_market_curve_carry.md`.

## Current roadmap

**Product/UI track:** Phase 1 of the Node/React migration is now implemented: React + TypeScript + Vite plus a thin FastAPI boundary, with real **Today** and **Mean Reversion Lab** workflows. Streamlit remains supported while migration continues. Next React screens: Daily Opportunities, Curve/Synthetic Viewer, Trade Builder, then the remaining monitors.

**Measurement/research track:** synthetic/constant-maturity tenors are available for roll-clean 50d/80d-style measurements, and first-passage mean-reversion research for calendar spreads / butterflies is now implemented. The next work is to apply registered cost hurdles, dependence-adjusted uncertainty/N_eff, and market-specific validation rather than adding another generic signal layer.

**Highest-priority strategy additions:** operate and harden the **SPY / MES + TLT/ZB Month-End Rebalance** monitor and research the new **Cross-Market Curve Carry** candidate. The imported hypothesis is frozen at ±50 bps of 60/40 bond rebalance pressure, with the signal measured at the sixth-last trading-day close. Futurescope keeps this page current-state-only; internal historical validation belongs in the registered EdgeLab workflow.

Immediate Futurescope infrastructure focus remains to **operate the ES + GC vertical slice and accumulate clean current-state observations**, not to add more protocol layers.

Next research work, only after the audit/power plumbing has real data to consume:

- synchronized ES cash/futures/dividend/funding measurement
- stronger GC reference alignment
- effective-N / dependence-aware confidence intervals
- registered conditional forward-return studies inside the audit framework
- simple linear/logistic/regularized models before XGBoost
- XGBoost only if it adds genuine walk-forward/holdout value over the simple baselines
- add ZN, CL, and VX one market at a time after the ES/GC architecture proves usable
- ZN CTD/implied-repo/DV01 module
- CL storage/inventory/convenience-yield module
- Cboe VX settlement/roll integration
- cross-market carry PCA only after each market has an economically correct measurement object

### Gold spot reference

GC no longer uses the unreliable Yahoo `XAUUSD=X` symbol. Recent XAU/USD daily spot bars come from goldprice.dev and are cached locally. No key is required for recent daily data. `GOLDPRICE_API_KEY` is optional for higher limits.
