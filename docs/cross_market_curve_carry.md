# Cross-Market Curve Carry

Futurescope's **Cross-Market Curve Carry** module is the dated-futures analogue of a cross-sectional carry strategy.

## Current-state score

For the first two live contracts in each market:

```text
annualized_curve_carry = log(F1 / F2) * 365.25 / expiry_gap_days
```

- positive = backwardation
- negative = contango

The score is a **common curve-state object**, not a claim that every market shares the same financing mechanism.

## Two expression modes

1. **Outright front / classic carry factor**
   - long front futures in the highest-carry/backwardated markets
   - short front futures in the lowest-carry/contangoed markets

2. **Calendar spread / curve RV**
   - long `+1 F1 / -1 F2` in the most backwardated markets
   - short `-1 F1 / +1 F2` in the most contangoed markets

The calendar-spread expression isolates the curve more directly; the outright expression is closer to the classic futures carry factor.

## Conductor boundary

Futurescope selects the current ranking and emits **trade intent**. Conductor owns:

- portfolio risk budget
- sizing
- concentration / correlation checks
- margin
- exact contract translation / rolls
- native spread routing
- execution
- lifecycle reconciliation

The module is `EXPLORATORY` until the profitability hypothesis is registered and validated through the Futurescope / EdgeLab process.

## ZB caveat

ZB can be displayed as an experimental curve object, but production Treasury carry requires CTD, conversion-factor, implied-repo, and DV01 treatment. Raw ZB F1/F2 carry is not a substitute for the Treasury-specific model.
