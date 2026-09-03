import json
from pathlib import Path

import pytest

from futurescope.research_registry import (
    ResearchRegistry,
    load_spec,
    power_from_spec,
    prospective_precision_gate,
)


def _write_spec(path: Path) -> None:
    data = {
        "experiment_id": "ES_001",
        "family": "es_calendar_rv",
        "mechanism": "dealer balance-sheet constraint",
        "falsifiers": ["no convergence after costs"],
        "prior_look": False,
        "power": {
            "n_eff": 100,
            "expected_effect": 1.0,
            "sigma": 2.0,
            "cost_hurdle": 0.25,
            "confidence": 0.95,
        },
        "holdout": {"block_id": "H1", "evaluations_allowed": 1},
    }
    path.write_text(json.dumps(data, indent=2))


def test_precision_gate_can_refuse_unresolvable_experiment():
    strong = prospective_precision_gate(n_eff=100, expected_effect=1.0, sigma=2.0, cost_hurdle=0.25)
    weak = prospective_precision_gate(n_eff=10, expected_effect=0.5, sigma=3.0, cost_hurdle=0.25)
    assert strong.verdict == "POWER PASS"
    assert strong.lower_bound > strong.cost_hurdle
    assert weak.verdict == "LIKELY UNRESOLVABLE"


def test_registry_tracks_holdout_budget_and_deduplicates_looks(tmp_path):
    spec_path = tmp_path / "spec.yaml"
    _write_spec(spec_path)
    holdouts = tmp_path / "holdouts.yaml"
    holdouts.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "block_id": "H1",
                        "family": "es_calendar_rv",
                        "start_date": "2025-01-01",
                        "end_date": "2025-12-31",
                    }
                ]
            },
            indent=2,
        )
    )
    registry = ResearchRegistry(tmp_path / "registry.sqlite")
    registry.initialize_holdouts(holdouts)
    registry.register_experiment(spec_path, repo_root=tmp_path)
    registry.allocate_holdout("ES_001", "H1")

    look1 = registry.log_look(
        query_type="conditional_forward",
        query={"market": "ES", "horizon": 5},
        reason="test",
    )
    look2 = registry.log_look(
        query_type="conditional_forward",
        query={"market": "ES", "horizon": 5},
        reason="test",
    )
    assert look1 == look2

    registry.record_evaluation(
        experiment_id="ES_001",
        phase="DRY_RUN",
        payload={"shuffled": True},
        holdout_block="H1",
        result_revealed=False,
    )
    registry.record_evaluation(
        experiment_id="ES_001",
        phase="HOLDOUT",
        payload={"result": 1.0},
        holdout_block="H1",
        result_revealed=True,
    )
    with pytest.raises(RuntimeError):
        registry.record_evaluation(
            experiment_id="ES_001",
            phase="HOLDOUT",
            payload={"result": 2.0},
            holdout_block="H1",
            result_revealed=True,
        )

    status = registry.status()
    assert len(status["looks"]) == 1
    assert status["holdouts"].iloc[0]["status"] == "BURNED"
    assert len(status["evaluations"]) == 2


def test_power_can_be_loaded_from_yaml_spec(tmp_path):
    spec_path = tmp_path / "spec.yaml"
    _write_spec(spec_path)
    spec = load_spec(spec_path)
    result = power_from_spec(spec)
    assert result.verdict == "POWER PASS"


def test_true_holdout_requires_dry_run(tmp_path):
    spec_path = tmp_path / "spec.yaml"
    _write_spec(spec_path)
    holdouts = tmp_path / "holdouts.yaml"
    holdouts.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "block_id": "H1",
                        "family": "es_calendar_rv",
                        "start_date": "2025-01-01",
                        "end_date": "2025-12-31",
                    }
                ]
            }
        )
    )
    registry = ResearchRegistry(tmp_path / "registry.sqlite")
    registry.initialize_holdouts(holdouts)
    registry.register_experiment(spec_path, repo_root=tmp_path)
    registry.allocate_holdout("ES_001", "H1")
    with pytest.raises(RuntimeError, match="DRY_RUN"):
        registry.record_evaluation(
            experiment_id="ES_001",
            phase="HOLDOUT",
            payload={"result": 1.0},
            holdout_block="H1",
            result_revealed=True,
        )


def test_holdout_family_must_match_experiment(tmp_path):
    spec_path = tmp_path / "spec.yaml"
    _write_spec(spec_path)
    data = json.loads(spec_path.read_text())
    data["holdout"]["block_id"] = "H_GC"
    spec_path.write_text(json.dumps(data))
    holdouts = tmp_path / "holdouts.yaml"
    holdouts.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "block_id": "H_GC",
                        "family": "gc_calendar_rv",
                        "start_date": "2025-01-01",
                        "end_date": "2025-12-31",
                    }
                ]
            }
        )
    )
    registry = ResearchRegistry(tmp_path / "registry.sqlite")
    registry.initialize_holdouts(holdouts)
    registry.register_experiment(spec_path, repo_root=tmp_path)
    with pytest.raises(RuntimeError, match="belongs to family"):
        registry.allocate_holdout("ES_001", "H_GC")
