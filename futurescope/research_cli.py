from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from futurescope.research_registry import ResearchRegistry, load_spec, power_from_spec


def _registry(args: argparse.Namespace) -> ResearchRegistry:
    return ResearchRegistry(args.db)


def cmd_register(args: argparse.Namespace) -> int:
    registry = _registry(args)
    experiment_id = registry.register_experiment(args.spec, repo_root=Path.cwd())
    print(f"registered {experiment_id}")
    return 0


def cmd_init_holdouts(args: argparse.Namespace) -> int:
    count = _registry(args).initialize_holdouts(args.config)
    print(f"initialized {count} holdout block(s)")
    return 0


def cmd_allocate(args: argparse.Namespace) -> int:
    _registry(args).allocate_holdout(args.experiment_id, args.block_id)
    print(f"allocated {args.block_id} to {args.experiment_id}")
    return 0


def cmd_power(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    result = power_from_spec(spec)
    registry = _registry(args)
    try:
        registry.record_power(str(spec["experiment_id"]), result)
    except KeyError:
        pass  # Power can be run prospectively before registration.
    print(json.dumps(result.__dict__, indent=2))
    return 0 if result.verdict == "POWER PASS" else 2


def cmd_log(args: argparse.Namespace) -> int:
    payload = json.loads(args.query)
    look_id = _registry(args).log_look(
        query_type=args.query_type,
        query=payload,
        reason=args.reason,
        experiment_id=args.experiment_id,
    )
    print(f"logged research look {look_id}")
    return 0


def _null_dry_run_from_csv(
    path: str,
    signal_col: str,
    outcome_col: str,
    seed: int,
) -> dict[str, float | int | str]:
    frame = pd.read_csv(path)
    if signal_col not in frame.columns or outcome_col not in frame.columns:
        raise KeyError(f"CSV must contain {signal_col!r} and {outcome_col!r}")
    signal = pd.to_numeric(frame[signal_col], errors="coerce")
    outcome = pd.to_numeric(frame[outcome_col], errors="coerce")
    valid = signal.notna() & outcome.notna()
    signal = signal[valid].to_numpy(dtype=float)
    outcome = outcome[valid].to_numpy(dtype=float)
    if len(signal) < 2:
        raise ValueError("dry-run CSV needs at least two valid rows")
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(signal)
    signed = shuffled * outcome
    return {
        "mode": "shuffled-signal",
        "rows": int(len(signed)),
        "seed": int(seed),
        "null_mean_signed_outcome": float(np.mean(signed)),
        "null_std_signed_outcome": float(np.std(signed, ddof=1)),
    }


def cmd_dry_run(args: argparse.Namespace) -> int:
    registry = _registry(args)
    spec = load_spec(args.spec)
    experiment_id = str(spec["experiment_id"])
    if args.csv:
        payload = _null_dry_run_from_csv(args.csv, args.signal_col, args.outcome_col, args.seed)
    else:
        # Plumbing-only null. This intentionally reveals no true holdout statistic.
        power = power_from_spec(spec)
        rng = np.random.default_rng(args.seed)
        synthetic = rng.normal(0.0, power.sigma, max(2, int(round(power.n_eff))))
        payload = {
            "mode": "synthetic-plumbing-null",
            "rows": int(len(synthetic)),
            "seed": int(args.seed),
            "null_mean": float(np.mean(synthetic)),
            "note": (
                "Synthetic plumbing check only. Before a real holdout run, prefer --csv so the "
                "same prepared evaluation table is exercised with the signal shuffled."
            ),
        }
    holdout = spec.get("holdout") or {}
    block_id = holdout.get("block_id") if isinstance(holdout, dict) else None
    registry.record_evaluation(
        experiment_id=experiment_id,
        phase="DRY_RUN",
        payload=payload,
        holdout_block=block_id,
        result_revealed=False,
    )
    print(json.dumps(payload, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    status = _registry(args).status()
    holdouts = status["holdouts"]
    untouched = int((holdouts["status"] == "UNTOUCHED").sum()) if not holdouts.empty else 0
    print(f"Untouched holdout blocks: {untouched}/{len(holdouts)}")
    for name, frame in status.items():
        print(f"\n[{name}] {len(frame)}")
        if not frame.empty:
            print(frame.to_string(index=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal Futurescope/EdgeLab research audit CLI")
    parser.add_argument("--db", default="cache/futurescope_research.sqlite")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("register", help="Register a timestamped experiment specification")
    p.add_argument("spec")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("init-holdouts", help="Create the pre-partitioned holdout budget")
    p.add_argument("config")
    p.set_defaults(func=cmd_init_holdouts)

    p = sub.add_parser("allocate", help="Allocate an untouched holdout block to an experiment")
    p.add_argument("experiment_id")
    p.add_argument("block_id")
    p.set_defaults(func=cmd_allocate)

    p = sub.add_parser("power", help="Run the prospective precision/cost-hurdle gate")
    p.add_argument("spec")
    p.set_defaults(func=cmd_power)

    p = sub.add_parser("log", help="Cheap manual research-look logger")
    p.add_argument("query_type")
    p.add_argument("query", help='JSON object, e.g. {"market":"ES","structure":"F1-F2"}')
    p.add_argument("--reason", default="manual research query")
    p.add_argument("--experiment-id", default=None)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("dry-run", help="Exercise evaluation plumbing with shuffled/synthetic labels")
    p.add_argument("spec")
    p.add_argument("--csv", default=None, help="Prepared evaluation table; signal is shuffled")
    p.add_argument("--signal-col", default="signal")
    p.add_argument("--outcome-col", default="outcome")
    p.add_argument("--seed", type=int, default=1729)
    p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("status", help="Show experiments, holdout budget, looks, and evaluations")
    p.set_defaults(func=cmd_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
