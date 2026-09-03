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

Futures curves come from Databento. Official Cboe daily CSVs supply VIX-family index history. GC uses goldprice.dev for recent XAU/USD daily references; Yahoo Finance remains a convenience S&P 500 cash-index reference until the ES timestamp/dividend/funding alignment layer is completed.

## Current pages

- **ES + GC Monitor** — current-state-only vertical slice. Shows curve shape, z-score/percentile location, exchange-listed strategy BBO/depth/volume, and an operational liquidity/cost gate.
- **Carry Screener** — cross-market carry/basis screen.
- **Curve Explorer** — individual futures curve and basis/carry view.
- **VIX Complex** — VX curve plus official Cboe VIX-family indices.
- **Relative Value** — finite-difference hierarchy: slope, butterfly, double butterfly.
- **Trade Builder** — exact basket legs, ratios, entry values, point-value economics, and research P&L concepts.
- **Historical Playback** — cached curve replay and explicit retrospective reveals.
- **Daily Opportunities** — historical search/ranking surface; scans are logged as research looks.

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

## Current roadmap

Immediate focus is to **operate the ES + GC vertical slice and accumulate clean current-state observations**, not to add more protocol layers.

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
