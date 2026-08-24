# Futurescope

Futurescope is a Streamlit research dashboard for **futures term structure, basis, carry, and the VIX complex**.

It is designed for the Futures/Carry section of a broader trading playbook. It keeps three ideas separate:

1. **Spot vs dated-futures basis / cash-and-carry** — convergence at expiration can lock the gross basis when the spot and futures legs are truly equivalent and can be carried to settlement.
2. **Calendar-curve carry / roll** — the shape between futures maturities can create carry, but this is not the same thing as spot-futures arbitrage.
3. **VIX term-structure carry** — VX converges to VIX settlement, but VIX itself is not a directly buyable spot asset, so VX/VIX basis is not a cash-and-carry arbitrage.

## V1 markets

- GC — COMEX Gold
- CL — NYMEX WTI Crude Oil
- ES — E-mini S&P 500
- ZN — 10-Year U.S. Treasury Note
- VX — Cboe VIX futures

Futures curves come from Databento. Official Cboe daily CSVs supply VIX-family index history. GC uses goldprice.dev for recent XAU/USD daily spot references; Yahoo Finance is used only as a convenience reference for the S&P 500 cash index.

## Setup

Python 3.10+ is recommended.

```powershell
cd futurescope
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create your local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set:

```text
DATABENTO_API_KEY=db-your-real-key-here
```

Do **not** commit `.env`. It is already ignored by `.gitignore`.

## Run

Before the first run, make sure the Databento client and DBN decoder match the pinned versions:

```powershell
python -m pip install -r requirements.txt --upgrade
python -c "from importlib.metadata import version; print('databento', version('databento')); print('databento-dbn', version('databento-dbn'))"
```

Expected versions for this release:

```text
databento 0.82.0
databento-dbn 0.63.0
```

Then start the app:

```powershell
streamlit run app.py
```

If you see `can't decode newer version of DBN. Decoder version is 2, input version is 3`, stop Streamlit and force an upgrade in the active virtual environment:

```powershell
python -m pip install --upgrade --no-cache-dir --force-reinstall databento==0.82.0 databento-dbn==0.63.0
```

Restart Streamlit after the install; a running Python process can keep the old native decoder loaded in memory.

Start with **Curve Explorer → GC**. This is the easiest connection test because GC has a natural spot reference.

## What the calculations mean

### Spot basis

For a futures price `F`, spot/reference price `S`, and `DTE` days to expiration:

```text
basis_pct = F / S - 1
annualized_implied_carry = (F / S - 1) * 365 / DTE
```

The dashboard also computes a simple fair-carry hurdle:

```text
fair_carry = financing_rate + storage_rate - income_yield
excess_carry = annualized_implied_carry - fair_carry
```

This is a **screen**, not a complete arbitrage model. Before trading, incorporate the economics of the specific market: deliverability, financing/repo, storage, insurance, dividends/coupons, lease rates/convenience yield, exchange and brokerage fees, bid/ask, tax, and variation-margin liquidity.

### Calendar curve

For each deferred future, Futurescope measures its premium/discount to the front contract and annualizes it over the difference in expiration dates. This is useful for seeing contango/backwardation and comparing curve steepness across markets.

### VIX

VX is treated specially. Futurescope shows VIX spot, VX1/VIX premium, the VX curve, VIX9D, VIX3M, VIX6M, VIX1Y, VVIX, OVX, and GVZ. Do not interpret VX1/VIX as a lockable spot-futures arbitrage; VIX is an index, not a directly purchasable spot asset.

## Databento usage

The code uses parent symbology (`GC.FUT`, `CL.FUT`, `ES.FUT`, `ZN.FUT`, `VX.FUT`) and the `definition` + `ohlcv-1d` schemas. CME products use `GLBX.MDP3`; VX uses `XCBF.PITCH`.

V1 uses the **Historical** client so you can build/research without requiring a live market-data license. Every requested as-of snapshot is cached to `cache/`. Check **Refresh cached market data** only when you intentionally want to re-query.

## Tests

```powershell
pytest -q
```

## Next build steps

- historical curve playback
- carry percentile/z-score by market
- persistence of contango/backwardation
- proper market-specific fair-value models
- Treasury curve / financing-rate ingestion
- volume and open-interest filters
- alerts for historically extreme curves
- backtest engine for cash-and-carry and calendar spreads
- crypto perpetual-funding module
- optional Databento Live mode


### Gold spot reference

GC no longer uses the unreliable Yahoo `XAUUSD=X` symbol. Recent XAU/USD daily spot bars come from goldprice.dev and are cached locally. No key is required for recent daily data. You may optionally set `GOLDPRICE_API_KEY` to raise anonymous request limits. Older historical spot windows may require a paid goldprice.dev tier or a future dedicated historical spot backfill.
