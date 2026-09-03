"""Tests for adaptive exam engine (SPEC-EXAM-002)."""

from app.v1.exam_adaptive import (
    AdaptiveAssessmentConfig,
    AdaptiveItem,
    AdaptiveResponse,
    estimate_theta,
    is_adaptive_assessment_type,
    select_next_item,
    should_stop_exam,
)


def test_is_adaptive_type():
    assert is_adaptive_assessment_type("adaptive")
    assert is_adaptive_assessment_type("ADAPTIVE")
    assert is_adaptive_assessment_type("printed") is False
    assert is_adaptive_assessment_type(None, explicit="adaptive")


def test_stop_at_max_items():
    cfg = AdaptiveAssessmentConfig(min_items=3, max_items=5, min_error=0.2)
    assert should_stop_exam(5, 0.5, cfg)
    assert not should_stop_exam(4, 0.5, cfg)


def test_stop_when_min_items_and_low_se():
    cfg = AdaptiveAssessmentConfig(min_items=3, max_items=10, min_error=0.3)
    assert should_stop_exam(3, 0.25, cfg)
    assert not should_stop_exam(2, 0.1, cfg)


def test_select_next_item_prefers_informative():
    items = [
        AdaptiveItem("q1", 1, 1.0, -2.0),
        AdaptiveItem("q2", 2, 1.2, 0.0),
        AdaptiveItem("q3", 3, 0.8, 2.0),
    ]
    nxt = select_next_item(0.0, items, set())
    assert nxt is not None
    assert nxt.question_id == "q2"


def test_theta_increases_with_correct_answers():
    items = {
        "q1": AdaptiveItem("q1", 1, 1.0, -2.0),
        "q2": AdaptiveItem("q2", 2, 1.0, -1.0),
    }
    theta0, _ = estimate_theta([], items, initial_theta=0.0)
    theta1, _ = estimate_theta(
        [AdaptiveResponse("q1", True), AdaptiveResponse("q2", True)],
        items,
        initial_theta=0.0,
    )
    assert theta1 > theta0
