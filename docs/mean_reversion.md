# Mean Reversion Lab

Futurescope treats curve mean reversion as a **first-passage** problem, not as a synonym for stationarity.

For a selected tenor-relative structure (calendar slope, butterfly, or double butterfly), the lab:

1. computes the existing lagged rolling z-score;
2. starts a new episode only when z crosses from inside the entry band to `|z| >= threshold`;
3. freezes the entry structure and tracks it until the mean is reached, the basket rolls, or the maximum horizon expires;
4. records time-to-mean, canonical-structure P&L, MAE, MFE, and censor reason;
5. estimates a Kaplan-Meier-style survival curve for the probability an episode has **not** reached the mean yet.

## Mean targets

### Frozen entry mean — preferred trade interpretation

The rolling mean observed at entry is frozen. A low-z trade succeeds when the structure rises through that level; a high-z trade succeeds when it falls through it.

This avoids a false success where the rolling mean moves toward the trade while the structure barely changes.

### Dynamic z = 0

The episode ends when the contemporaneous rolling z-score crosses zero. This is useful as a conventional statistical diagnostic, but its target moves through time.

## Episode accounting

Episodes are non-overlapping. Futurescope does not count every day spent beyond ±2σ as another independent observation.

A contract-roll boundary censors the episode. Cross-roll changes are never presented as executable convergence P&L. A time stop is also censored rather than silently called a mean-reversion failure.

## Outputs

- hit probability and 95% Wilson interval
- median observations/calendar days to mean
- first-passage survival curve
- MAE and MFE before exit/censor
- canonical-price-unit P&L at the chosen exit/censor point
- full episode table with contract basket and status

These are **research diagnostics**. Contract multipliers, native spread-market execution costs, slippage, and the registered cost hurdle must be applied before a result can be called tradeable.

## Research governance

Opening current z-score state is monitoring. Asking what happened historically after an extreme is research. Both the Streamlit page and React API log the historical query before revealing the result.
