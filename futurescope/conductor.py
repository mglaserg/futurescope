from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"


def _iso(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def make_trade_intent(
    *,
    strategy_id: str,
    action: str,
    as_of: date | datetime | str,
    validation_status: str,
    exposures: Sequence[Mapping[str, Any]],
    lifecycle: Mapping[str, Any] | None = None,
    preferred_execution: Mapping[str, Any] | None = None,
    research: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a broker-agnostic handoff from Futurescope to Conductor.

    Futurescope communicates *intent*: what exposure/structure it wants and how
    the strategy knows when the intent is stale or finished. Position sizing,
    portfolio constraints, contract translation, order routing, and broker
    reconciliation belong downstream in Conductor.
    """
    strategy_id = strategy_id.strip()
    action = action.upper().strip()
    validation_status = validation_status.upper().strip()
    if not strategy_id:
        raise ValueError("strategy_id is required")
    if action not in {"ENTER", "EXIT", "REBALANCE", "ROTATE", "HOLD", "FLAT"}:
        raise ValueError(f"Unsupported action: {action}")
    if not validation_status:
        raise ValueError("validation_status is required")

    clean_exposures = [dict(item) for item in exposures]
    return {
        "schema": "conductor.trade_intent",
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "producer": "Futurescope",
        "as_of": _iso(as_of),
        "action": action,
        "validation_status": validation_status,
        "exposures": clean_exposures,
        "preferred_execution": dict(preferred_execution or {}),
        "lifecycle": dict(lifecycle or {}),
        "research": dict(research or {}),
        "metadata": dict(metadata or {}),
    }


def intent_json(intent: Mapping[str, Any]) -> str:
    return json.dumps(dict(intent), indent=2, sort_keys=False, default=str) + "\n"


def relative_value_trade_intent(
    ticket: Mapping[str, Any],
    *,
    as_of: date | datetime | str,
    validation_status: str = "EXPLORATORY",
    target_z: float = 0.0,
    max_holding_sessions: int | None = None,
) -> dict[str, Any]:
    legs = ticket.get("legs")
    if hasattr(legs, "to_dict"):
        leg_rows = legs.to_dict("records")
    else:
        leg_rows = list(legs or [])
    exposures = [
        {
            "type": "futures_leg",
            "contract": str(row["raw_symbol"]),
            "ratio": float(row["signed_weight"]),
            "role": f"leg_{idx + 1}",
        }
        for idx, row in enumerate(leg_rows)
    ]
    lifecycle: dict[str, Any] = {
        "exit_rule": "z_score_mean_cross",
        "target_z": float(target_z),
    }
    if max_holding_sessions is not None:
        lifecycle["max_holding_sessions"] = int(max_holding_sessions)

    return make_trade_intent(
        strategy_id=f"futurescope_{str(ticket['market']).lower()}_rv",
        action="ENTER",
        as_of=as_of,
        validation_status=validation_status,
        exposures=exposures,
        preferred_execution={
            "instrument_type": "exchange_listed_spread_if_available",
            "structure": str(ticket["structure"]),
            "tenor": str(ticket["tenor_label"]),
        },
        lifecycle=lifecycle,
        research={
            "signal": str(ticket["signal"]),
            "canonical_entry_value": float(ticket["canonical_entry_value"]),
            "time_normalized_value": float(ticket["time_normalized_value"]),
        },
        metadata={
            "execution_ratio": str(ticket["execution_ratio"]),
            "sizing_owner": "Conductor",
        },
    )


def month_end_trade_intent(
    *,
    as_of: date | datetime | str,
    phase: str,
    equity_weight: float,
    duration_weight: float,
    equity_vehicle: str,
    duration_vehicle: str,
    pressure_bps: float | None,
    next_transition: date | None,
) -> dict[str, Any]:
    exposures: list[dict[str, Any]] = []
    if equity_weight:
        exposures.append(
            {
                "type": "asset_class_exposure",
                "asset_class": "US_EQUITY",
                "target_units": float(equity_weight),
                "preferred_instrument": equity_vehicle,
            }
        )
    if duration_weight:
        exposures.append(
            {
                "type": "asset_class_exposure",
                "asset_class": "US_LONG_DURATION",
                "target_units": float(duration_weight),
                "reference_instrument": "TLT",
                "preferred_instrument": duration_vehicle,
                "sizing_basis": "DV01" if duration_vehicle.upper() == "ZB" else "notional",
            }
        )

    action = "REBALANCE" if exposures else "FLAT"
    lifecycle: dict[str, Any] = {"exit_rule": "calendar_schedule"}
    if next_transition is not None:
        lifecycle["next_transition"] = next_transition.isoformat()

    research: dict[str, Any] = {"phase": phase}
    if pressure_bps is not None:
        research["rebalance_pressure_bps"] = float(pressure_bps)

    return make_trade_intent(
        strategy_id="futurescope_month_end_rebalance",
        action=action,
        as_of=as_of,
        validation_status="EXPLORATORY_PRIOR_LOOK",
        exposures=exposures,
        preferred_execution={
            "equity": equity_vehicle,
            "duration": duration_vehicle,
            "duration_translation": "TLT reference -> ZB by DV01" if duration_vehicle.upper() == "ZB" else "TLT cash ETF",
        },
        lifecycle=lifecycle,
        research=research,
        metadata={"sizing_owner": "Conductor"},
    )


def cross_market_carry_intent(
    selections: Sequence[Mapping[str, Any]],
    *,
    as_of: date | datetime | str,
    expression: str,
) -> dict[str, Any]:
    expression = expression.lower().strip()
    exposures: list[dict[str, Any]] = []
    for row in selections:
        direction = str(row["direction"]).upper()
        sign = 1.0 if direction == "LONG" else -1.0
        if expression == "calendar_spread":
            exposures.append(
                {
                    "type": "futures_spread",
                    "market": str(row["market"]),
                    "structure": "calendar_spread",
                    "direction": direction,
                    "signal_units": 1.0,
                    "legs": [
                        {"contract": str(row["front_symbol"]), "ratio": sign},
                        {"contract": str(row["second_symbol"]), "ratio": -sign},
                    ],
                }
            )
        elif expression == "outright_front":
            exposures.append(
                {
                    "type": "futures_outright",
                    "market": str(row["market"]),
                    "contract": str(row["front_symbol"]),
                    "direction": direction,
                    "signal_units": 1.0,
                }
            )
        else:
            raise ValueError(f"Unsupported carry expression: {expression}")

    return make_trade_intent(
        strategy_id="futurescope_cross_market_curve_carry",
        action="REBALANCE" if exposures else "FLAT",
        as_of=as_of,
        validation_status="EXPLORATORY",
        exposures=exposures,
        preferred_execution={
            "expression": expression,
            "sizing": "portfolio_risk_budget",
            "native_spreads": expression == "calendar_spread",
        },
        lifecycle={"exit_rule": "ranking_change_or_strategy_schedule"},
        research={"selection_count": len(exposures)},
        metadata={"sizing_owner": "Conductor"},
    )
