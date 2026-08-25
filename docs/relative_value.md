# Futurescope Relative Value

This iteration adds a dedicated Relative Value page without requiring changes to the existing app/service/cache modules.

## Finite-difference hierarchy

Futurescope treats adjacent futures-curve structures as finite differences:

| Structure | Canonical weights | Curve quantity |
| --- | --- | --- |
| Outright | `+1` | level |
| Calendar spread | `+1 : -1` | first difference / slope |
| Butterfly | `+1 : -2 : +1` | second difference / curvature |
| Double butterfly | `+1 : -3 : +3 : -1` | third difference / change in curvature |

The canonical integer ratios are kept separate from the **time-normalized finite-difference measure**. When expirations are unevenly spaced, Futurescope uses the actual tenor distances rather than pretending a raw `1:-2:1` or `1:-3:+3:-1` basket is a geometrically uniform derivative.

## Risk normalization

The page supports optional per-contract risk inputs. These convert canonical target exposures into contract ratios while leaving the pure curve-shape statistic unchanged. For Treasury futures, the intended future implementation is automatic DV01 ingestion; until then, current DV01 values can be entered manually.

## Local history

Curves loaded from the Relative Value page are saved under:

```text
cache/curve_snapshots/<MARKET>/YYYY-MM-DD.csv
```

This is separate from the existing Databento request cache. The page can build/extend local history explicitly, replay cached curves, and calculate:

- historical percentile
- z-score
- lag-1 persistence
- OU-style mean-reversion half-life
- extreme-high / extreme-low flags
- a simple no-lookahead mean-reversion P&L proxy

The P&L proxy resets at contract-roll boundaries and ignores the cross-roll jump. It remains a research diagnostic, not production P&L: contract multipliers, bid/ask, fees, margin, liquidity, explicit roll execution, and market-specific risk scaling still need to be modeled.

## Roadmap carried forward

- richer historical curve/regime playback
- market-specific fair-value models
- equity-index cash + financing - dividends / EFP analysis
- Treasury financing-rate and DV01 ingestion
- volume and open-interest filters
- extreme-curve / rich-cheap alerts
- production-grade basis backtests
- production-grade calendar-spread / butterfly / double-butterfly backtests
- optional Databento Live after the cached historical workflow is solid

Crypto perpetual-basis/funding research remains outside Futurescope's core scope for now.

## Directional signal layer

The diagnostics page now explicitly separates an **anomaly** from a **signal**. A z-score extreme alone is not a trade. For the selected spread, butterfly, or double butterfly, Futurescope computes lagged historical z-scores, finds prior same-side extremes, and measures the canonical basket's forward move over a chosen number of cached observations. Forward windows crossing a raw-contract roll are excluded.

The signal states are `LONG`, `SHORT`, `NO SIGNAL`, and `INSUFFICIENT HISTORY`. LONG/SHORT requires the current z-score to clear the entry threshold, enough historical analogues, and at least a configurable directional win-rate hurdle. Direction is empirical: a positive extreme can produce a SHORT mean-reversion signal or a LONG continuation signal depending on what comparable historical observations actually did.

This is still a gross research signal. Transaction costs, multipliers, margin, liquidity, fair-value filters, and market-specific risk normalization remain prerequisites for a production trade score.
