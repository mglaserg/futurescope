# Month-End Rebalance Monitor

This module is a **current-state implementation** of the imported 60/40 month-end rebalance-pressure hypothesis. It is deliberately separated from historical outcome research.

## Signal construction

At the close before the final five trading sessions of each month (the sixth-last session), measure SPY and IEF total returns from the prior month-end close. Reconstruct how a hypothetical 60/40 portfolio drifted, then calculate the trade required to restore 60/40.

The bond-side rebalance trade is the pressure signal:

- pressure <= -50 bps of portfolio value: strong expected bond selling
- pressure >= +50 bps: strong expected bond buying
- otherwise: neutral / modest bond buying

SPY and IEF are **measurement proxies**. TLT is the long-duration trade leg. The stock leg can be expressed with SPY or translated to the front MES contract.

## Frozen trading map

At the sixth-last trading-day close:

- strong bond selling -> long equity for the final five sessions
- otherwise -> long TLT for the final five sessions

At the month-end close:

- strong bond buying -> long equity / short TLT for the first five sessions of the new month
- otherwise -> cash

At the fifth trading-day close of the new month: close all positions.

## Futurescope research boundary

The Streamlit page can display the current calendar state, pressure, thresholds, price path used to calculate the pressure, and an execution ticket. It does **not** display historical conditional outcome statistics or optimize thresholds.

Any internal backtest, threshold study, forward-return analysis, or model comparison should be registered before results are revealed and run through the Futurescope / EdgeLab audit workflow.

## MES sizing

MES has a $5 x S&P 500 index multiplier. The page translates a user-selected target equity notional into an approximate front-MES contract count. For the early-month long-equity / short-TLT pair, the initial implementation uses equal target notional per leg as an execution convenience, **not** as a validated risk-neutral hedge ratio.
