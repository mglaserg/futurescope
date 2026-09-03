# Futurescope research protocol

Futurescope Monitor answers **what exists now**. Historical outcome questions are research looks and must be counted.

## Frozen rules

1. **Mechanism before search.** Write the counterparty/constraint story, expected direction, falsifiers, candidate universe, cost hurdle, power assumptions, and holdout plan into a committed experiment specification before the historical-outcome search. The shipped `.yaml` files intentionally use JSON-compatible YAML so the minimal registry stays dependency-free.
2. **Costs before statistics.** A candidate must first clear the exchange-listed spread-market liquidity/cost gate when an exchange strategy exists. Do not approximate a listed calendar spread by summing outright bid/ask widths.
3. **Power before holdout.** Use effective independent episodes (`N_eff`), not raw daily rows. If the prospective confidence interval cannot clear the frozen cost hurdle, return `LIKELY UNRESOLVABLE` and preserve the holdout block.
4. **Finite holdout budget.** Partition holdout data into `K` disjoint blocks up front. Each true revealed validation consumes a block/look according to its family allocation.
5. **Dry run first.** Exercise the evaluation plumbing with shuffled/randomized signals before the true holdout result is revealed.
6. **Cheap logging.** Current state is free to inspect. Conditional forward returns, historical win rates, MAE/MFE, and "what happened last time" are logged research looks. Logging should be one command/action, not a bureaucratic gate.
7. **Terminal uncertainty is allowed.** Valid outcomes include `VALIDATED`, `FAILED`, `UNRESOLVABLE`, and `EXPLORATORY`. Do not respond to an unresolvable sample by automatically adding features or XGBoost.
8. **GC slope prior look.** The already-observed GC approximately -3 z-score calendar-slope convergence is permanently tagged exploratory/prior-look and cannot serve as untouched architecture validation.

## Minimal CLI

```powershell
python research_cli.py init-holdouts research/holdouts.yaml
python research_cli.py register research/specs/es_calendar_001.yaml
python research_cli.py power research/specs/es_calendar_001.yaml
python research_cli.py dry-run research/specs/es_calendar_001.yaml --csv prepared_eval.csv --signal-col signal --outcome-col outcome
python research_cli.py status
```

For an ad-hoc historical query that is not part of a registered experiment:

```powershell
python research_cli.py log conditional_forward "{\"market\":\"ES\",\"structure\":\"F1-F2\",\"horizon\":5}" --reason "manual slope follow-up"
```

The registry is intentionally small SQLite plumbing under `cache/`; the committed experiment specification and Git commit hash provide the auditable pre-search record.
