import math

from futurescope.opportunities import opportunity_state, research_score


def test_opportunity_state_distinguishes_signal_from_anomaly():
    assert opportunity_state("LONG", -2.5, 2.0) == "TRADE CANDIDATE"
    assert opportunity_state("NO SIGNAL", 2.5, 2.0) == "RESEARCH"
    assert opportunity_state("NO SIGNAL", 1.6, 2.0) == "UNUSUAL"
    assert opportunity_state("NO SIGNAL", 0.5, 2.0) == "NORMAL"


def test_research_score_is_transparent_and_bounded():
    weak = research_score("NO SIGNAL", 1.0, float("nan"), 0)
    strong = research_score("LONG", -3.0, 0.75, 20)
    assert 0 <= weak < strong <= 100
    assert math.isclose(strong, 80.0)
