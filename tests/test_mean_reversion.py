import math

import numpy as np
import pandas as pd

from futurescope.mean_reversion import (
    first_passage_mean_reversion_episodes,
    kaplan_meier_mean_reversion,
    mean_reversion_analysis,
    summarize_mean_reversion,
)


def _history() -> pd.DataFrame:
    # Three clear low-z episodes separated by normal observations.  Canonical and
    # normalized values are aligned so long-low mean reversion earns positive P&L.
    values = [0.0, 0.2, -0.1, 0.1, 0.0, 0.1, -5.0, -2.0, 0.2, 0.0,
              0.1, -0.1, 0.0, -5.5, -1.0, 0.3, 0.0, 0.1, -0.1, 0.0,
              -6.0, -3.0, -1.0, 0.2, 0.0, 0.1, -0.1, 0.0, 0.1, 0.0]
    return pd.DataFrame(
        {
            "snapshot_date": pd.date_range("2026-01-01", periods=len(values), freq="D"),
            "value": values,
            "canonical_value": values,
            "leg_symbols": ["F1 / F2"] * len(values),
        }
    )


def test_first_passage_episodes_hit_frozen_entry_mean():
    episodes = first_passage_mean_reversion_episodes(
        _history(), lookback=5, entry_z=2.0, max_horizon=5, target_mode="frozen_entry_mean"
    )
    assert len(episodes) >= 2
    assert episodes["hit_mean"].all()
    assert (episodes["trade_direction"] == "LONG").all()
    assert (episodes["pnl_price_units"] > 0).all()
    assert (episodes["mae_price_units"] <= 0).all()
    assert (episodes["mfe_price_units"] > 0).all()


def test_roll_boundary_censors_episode_without_cross_roll_claim():
    history = _history()
    history.loc[7:, "leg_symbols"] = "F2 / F3"
    episodes = first_passage_mean_reversion_episodes(
        history, lookback=5, entry_z=2.0, max_horizon=5, target_mode="frozen_entry_mean"
    )
    assert not episodes.empty
    assert episodes.iloc[0]["status"] == "CENSORED_ROLL"


def test_summary_has_wilson_interval_and_survival_curve():
    episodes, summary, survival = mean_reversion_analysis(
        _history(), lookback=5, entry_z=2.0, max_horizon=5, target_mode="frozen_entry_mean"
    )
    assert summary.episodes == len(episodes)
    assert 0.0 <= summary.hit_rate_ci_low <= summary.hit_rate <= summary.hit_rate_ci_high <= 1.0
    assert not survival.empty
    assert survival["survival"].between(0.0, 1.0).all()
    assert math.isclose(float(survival.iloc[-1]["survival"]), 0.0, abs_tol=1e-12)


def test_empty_summary_is_explicit():
    summary = summarize_mean_reversion(pd.DataFrame())
    assert summary.episodes == 0
    assert np.isnan(summary.hit_rate)
    assert kaplan_meier_mean_reversion(pd.DataFrame()).empty
