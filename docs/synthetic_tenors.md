# Synthetic Tenors / Constant-Maturity Futures

## Why this exists

`F1/F2` changes meaning every day because both contracts lose DTE and eventually roll. Futurescope's constant-maturity layer instead asks for fixed targets such as **50 days** and **80 days** so the measurement refers to the same part of the curve through time.

## Construction

For a target maturity `T` bracketed by listed contracts at `T1 < T < T2`, Futurescope uses transparent linear interpolation in quoted futures price:

```text
w1 = (T2 - T) / (T2 - T1)
w2 = (T - T1) / (T2 - T1)
F_T = w1 * F_T1 + w2 * F_T2
```

No extrapolation is allowed. If the requested DTE is outside the listed curve, the page refuses to construct it.

The default synthetic slope is:

```text
F_50d - F_80d
```

Positive = backwardation; negative = contango.

## Tradable translation

The synthetic points are measurements/target exposures, not exchange contracts. Futurescope expands `+F_50d - F_80d` into the current listed contracts and combines any overlapping interpolation legs. For example:

```text
F_50d = 0.6 F2 + 0.4 F3
F_80d = 0.3 F3 + 0.7 F4

LONG 50d/80d = +0.6 F2 +0.1 F3 -0.7 F4
```

Those are exposure ratios. Futurescope exports them to Conductor; Conductor owns portfolio sizing, integerization, margin/risk checks, and order execution.

## Research boundary

The page may show current synthetic slope, percentile, and lagged rolling z-score from locally cached curve snapshots. It does **not** claim that an extreme synthetic slope predicts future profit. Conditional forward outcomes, mean reversion, first passage to z=0, or optimized target tenors are registered research questions and must run through the Futurescope/EdgeLab audit workflow.
