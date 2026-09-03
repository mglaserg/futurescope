from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd


VERDICTS = {"EXPLORATORY", "VALIDATED", "FAILED", "UNRESOLVABLE", "PENDING"}


@dataclass(frozen=True)
class PrecisionResult:
    n_eff: float
    expected_effect: float
    sigma: float
    confidence: float
    cost_hurdle: float
    half_width: float
    lower_bound: float
    upper_bound: float
    verdict: str


def prospective_precision_gate(
    *,
    n_eff: float,
    expected_effect: float,
    sigma: float,
    cost_hurdle: float = 0.0,
    confidence: float = 0.95,
) -> PrecisionResult:
    """Prospective CI-width gate for a mean effect before holdout allocation.

    ``n_eff`` is deliberately supplied by the research specification rather than
    inferred from raw row count.  It should already reflect overlapping horizons,
    serial dependence, and the number of genuinely independent episodes.
    """

    if not np.isfinite(n_eff) or n_eff <= 1:
        raise ValueError("n_eff must be > 1")
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma must be positive")
    if not 0.5 < confidence < 1.0:
        raise ValueError("confidence must be between 0.5 and 1")
    alpha = 1.0 - confidence
    zcrit = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    half_width = float(zcrit * sigma / np.sqrt(n_eff))
    lower = float(expected_effect - half_width)
    upper = float(expected_effect + half_width)
    verdict = "POWER PASS" if lower > cost_hurdle else "LIKELY UNRESOLVABLE"
    return PrecisionResult(
        n_eff=float(n_eff),
        expected_effect=float(expected_effect),
        sigma=float(sigma),
        confidence=float(confidence),
        cost_hurdle=float(cost_hurdle),
        half_width=half_width,
        lower_bound=lower,
        upper_bound=upper,
        verdict=verdict,
    )


def _load_json_compatible_yaml(path: str | Path) -> dict[str, Any]:
    """Load the initial audit schema without adding a YAML dependency.

    JSON is a strict subset of YAML 1.2, so the shipped ``.yaml`` templates are
    deliberately JSON-compatible.  This keeps the research registry usable in
    the project's locked environment without silently desynchronizing uv.lock.
    """

    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} must use JSON-compatible YAML syntax (JSON is valid YAML 1.2)"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a top-level mapping/object")
    return data


def load_spec(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    data = _load_json_compatible_yaml(path)
    required = ["experiment_id", "family", "mechanism", "falsifiers", "holdout"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"experiment specification missing: {', '.join(missing)}")
    return data


def spec_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_provenance(cwd: str | Path | None = None) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=cwd, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=cwd, text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
        return commit, dirty
    except Exception:
        return None, None


class ResearchRegistry:
    """Small SQLite audit log for Futurescope research looks and holdout use."""

    def __init__(self, path: str | Path = "cache/futurescope_research.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    family TEXT NOT NULL,
                    registered_at_utc TEXT NOT NULL,
                    spec_path TEXT NOT NULL,
                    spec_hash TEXT NOT NULL,
                    mechanism TEXT NOT NULL,
                    falsifiers_json TEXT NOT NULL,
                    prior_look INTEGER NOT NULL DEFAULT 0,
                    holdout_block TEXT,
                    git_commit TEXT,
                    git_dirty INTEGER,
                    power_verdict TEXT,
                    power_json TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING'
                );

                CREATE TABLE IF NOT EXISTS holdout_blocks (
                    block_id TEXT PRIMARY KEY,
                    family TEXT,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'UNTOUCHED',
                    allocated_experiment_id TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS research_looks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    look_hash TEXT NOT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL,
                    experiment_id TEXT,
                    query_type TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    reason TEXT,
                    result_revealed INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'futurescope'
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    run_at_utc TEXT NOT NULL,
                    holdout_block TEXT,
                    result_revealed INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )
            # Lightweight migration for registries created by an earlier iteration.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(experiments)").fetchall()}
            if "power_verdict" not in columns:
                conn.execute("ALTER TABLE experiments ADD COLUMN power_verdict TEXT")
            if "power_json" not in columns:
                conn.execute("ALTER TABLE experiments ADD COLUMN power_json TEXT")

    def register_experiment(self, spec_path: str | Path, repo_root: str | Path | None = None) -> str:
        spec = load_spec(spec_path)
        experiment_id = str(spec["experiment_id"])
        commit, dirty = git_provenance(repo_root)
        holdout = spec.get("holdout") or {}
        block = holdout.get("block_id") if isinstance(holdout, dict) else None
        power_result = None
        if isinstance(spec.get("power"), dict):
            power_result = power_from_spec(spec)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO experiments (
                    experiment_id, family, registered_at_utc, spec_path, spec_hash,
                    mechanism, falsifiers_json, prior_look, holdout_block,
                    git_commit, git_dirty, power_verdict, power_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                ON CONFLICT(experiment_id) DO NOTHING
                """,
                (
                    experiment_id,
                    str(spec["family"]),
                    datetime.now(timezone.utc).isoformat(),
                    str(Path(spec_path)),
                    spec_hash(spec_path),
                    str(spec["mechanism"]),
                    json.dumps(spec.get("falsifiers", []), sort_keys=True),
                    int(bool(spec.get("prior_look", False))),
                    block,
                    commit,
                    None if dirty is None else int(dirty),
                    None if power_result is None else power_result.verdict,
                    None if power_result is None else json.dumps(power_result.__dict__, sort_keys=True),
                ),
            )
        return experiment_id

    def initialize_holdouts(self, config_path: str | Path) -> int:
        data = _load_json_compatible_yaml(config_path)
        blocks = data.get("blocks", [])
        normalized: list[tuple[str, pd.Timestamp, pd.Timestamp]] = []
        for block in blocks:
            start = pd.Timestamp(block["start_date"])
            end = pd.Timestamp(block["end_date"])
            if end < start:
                raise ValueError(f"holdout block {block['block_id']} ends before it starts")
            normalized.append((str(block["block_id"]), start, end))
        for i, (left_id, left_start, left_end) in enumerate(normalized):
            for right_id, right_start, right_end in normalized[i + 1 :]:
                if max(left_start, right_start) <= min(left_end, right_end):
                    raise ValueError(f"holdout blocks {left_id} and {right_id} overlap")
        count = 0
        with self._connect() as conn:
            for block in blocks:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO holdout_blocks (
                        block_id, family, start_date, end_date, status, notes
                    ) VALUES (?, ?, ?, ?, 'UNTOUCHED', ?)
                    """,
                    (
                        str(block["block_id"]),
                        block.get("family"),
                        str(block["start_date"]),
                        str(block["end_date"]),
                        block.get("notes", ""),
                    ),
                )
                count += 1
        return count

    def allocate_holdout(self, experiment_id: str, block_id: str) -> None:
        with self._connect() as conn:
            experiment = conn.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if experiment is None:
                raise KeyError(f"unknown experiment {experiment_id}")
            if experiment["power_verdict"] != "POWER PASS":
                raise RuntimeError(
                    f"experiment {experiment_id} has power verdict {experiment['power_verdict']!r}; "
                    "do not allocate a scarce holdout block until the prospective precision gate passes"
                )
            planned_block = experiment["holdout_block"]
            if planned_block and planned_block != block_id:
                raise RuntimeError(
                    f"experiment {experiment_id} was registered for holdout block {planned_block}, not {block_id}"
                )
            block = conn.execute(
                "SELECT * FROM holdout_blocks WHERE block_id = ?", (block_id,)
            ).fetchone()
            if block is None:
                raise KeyError(f"unknown holdout block {block_id}")
            if block["family"] and block["family"] != experiment["family"]:
                raise RuntimeError(
                    f"holdout block {block_id} belongs to family {block['family']}, "
                    f"not {experiment['family']}"
                )
            if block["status"] != "UNTOUCHED" and block["allocated_experiment_id"] != experiment_id:
                raise RuntimeError(f"holdout block {block_id} is already {block['status']}")
            conn.execute(
                "UPDATE holdout_blocks SET status='ALLOCATED', allocated_experiment_id=? WHERE block_id=?",
                (experiment_id, block_id),
            )
            conn.execute(
                "UPDATE experiments SET holdout_block=? WHERE experiment_id=?",
                (block_id, experiment_id),
            )

    def record_power(self, experiment_id: str, result: PrecisionResult) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE experiments SET power_verdict=?, power_json=? WHERE experiment_id=?",
                (result.verdict, json.dumps(result.__dict__, sort_keys=True), experiment_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"unknown experiment {experiment_id}")

    def log_look(
        self,
        *,
        query_type: str,
        query: dict[str, Any],
        reason: str = "",
        experiment_id: str | None = None,
        result_revealed: bool = True,
        source: str = "futurescope",
    ) -> int:
        canonical = json.dumps(
            {
                "experiment_id": experiment_id,
                "query_type": query_type,
                "query": query,
                "reason": reason,
                "source": source,
            },
            sort_keys=True,
            default=str,
        )
        look_hash = hashlib.sha256(canonical.encode()).hexdigest()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO research_looks (
                    look_hash, created_at_utc, experiment_id, query_type,
                    query_json, reason, result_revealed, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    look_hash,
                    datetime.now(timezone.utc).isoformat(),
                    experiment_id,
                    query_type,
                    json.dumps(query, sort_keys=True, default=str),
                    reason,
                    int(bool(result_revealed)),
                    source,
                ),
            )
            row = conn.execute(
                "SELECT id FROM research_looks WHERE look_hash = ?", (look_hash,)
            ).fetchone()
        return int(row["id"])

    def record_evaluation(
        self,
        *,
        experiment_id: str,
        phase: str,
        payload: dict[str, Any],
        holdout_block: str | None = None,
        result_revealed: bool,
    ) -> int:
        phase = phase.upper()
        if phase not in {"DRY_RUN", "HOLDOUT"}:
            raise ValueError("phase must be DRY_RUN or HOLDOUT")
        with self._connect() as conn:
            experiment = conn.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if experiment is None:
                raise KeyError(f"unknown experiment {experiment_id}")
            if phase == "HOLDOUT":
                if experiment["power_verdict"] != "POWER PASS":
                    raise RuntimeError("true holdout evaluation requires a POWER PASS")
                allocated_block = experiment["holdout_block"]
                if not allocated_block:
                    raise RuntimeError("true holdout evaluation requires an allocated holdout block")
                if holdout_block is None:
                    holdout_block = str(allocated_block)
                if holdout_block != allocated_block:
                    raise RuntimeError(
                        f"experiment {experiment_id} is allocated to {allocated_block}, not {holdout_block}"
                    )
                block = conn.execute(
                    "SELECT * FROM holdout_blocks WHERE block_id = ?", (holdout_block,)
                ).fetchone()
                if (
                    block is None
                    or block["status"] != "ALLOCATED"
                    or block["allocated_experiment_id"] != experiment_id
                ):
                    raise RuntimeError("holdout block is not currently allocated to this experiment")
                dry_runs = conn.execute(
                    "SELECT COUNT(*) AS n FROM evaluations WHERE experiment_id=? AND phase='DRY_RUN' AND result_revealed=0",
                    (experiment_id,),
                ).fetchone()["n"]
                if not dry_runs:
                    raise RuntimeError("run a non-revealing DRY_RUN before the true holdout evaluation")
                prior = conn.execute(
                    "SELECT COUNT(*) AS n FROM evaluations WHERE experiment_id=? AND phase='HOLDOUT' AND result_revealed=1",
                    (experiment_id,),
                ).fetchone()["n"]
                if prior:
                    raise RuntimeError("true holdout result has already been revealed for this experiment")
            cursor = conn.execute(
                """
                INSERT INTO evaluations (
                    experiment_id, phase, run_at_utc, holdout_block,
                    result_revealed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    phase,
                    datetime.now(timezone.utc).isoformat(),
                    holdout_block,
                    int(bool(result_revealed)),
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )
            if phase == "HOLDOUT" and result_revealed:
                if holdout_block:
                    conn.execute(
                        "UPDATE holdout_blocks SET status='BURNED' WHERE block_id=?",
                        (holdout_block,),
                    )
        return int(cursor.lastrowid)

    def status(self) -> dict[str, pd.DataFrame]:
        with self._connect() as conn:
            return {
                "experiments": pd.read_sql_query(
                    "SELECT * FROM experiments ORDER BY registered_at_utc", conn
                ),
                "holdouts": pd.read_sql_query(
                    "SELECT * FROM holdout_blocks ORDER BY start_date", conn
                ),
                "looks": pd.read_sql_query(
                    "SELECT * FROM research_looks ORDER BY created_at_utc", conn
                ),
                "evaluations": pd.read_sql_query(
                    "SELECT * FROM evaluations ORDER BY run_at_utc", conn
                ),
            }


def power_from_spec(spec: dict[str, Any]) -> PrecisionResult:
    power = spec.get("power")
    if not isinstance(power, dict):
        raise ValueError("spec requires a power mapping before holdout allocation")
    return prospective_precision_gate(
        n_eff=float(power["n_eff"]),
        expected_effect=float(power["expected_effect"]),
        sigma=float(power["sigma"]),
        cost_hurdle=float(power.get("cost_hurdle", 0.0)),
        confidence=float(power.get("confidence", 0.95)),
    )
