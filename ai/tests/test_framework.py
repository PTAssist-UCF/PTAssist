"""Contract-level checks for the reusable analysis framework."""

import math
import re

import pytest

from app.analysis.framework import (
    GOOD_FORM_FEEDBACK,
    NO_REPS_FEEDBACK,
    HoldObservation,
    IssueDefinition,
    RepObservation,
    RepSplitter,
    RepWindow,
    build_hold_result,
    build_rep_result,
)

ISSUES = {
    "lean": IssueDefinition("You leaned forward.", "Keep your chest up.", 30),
    "shallow": IssueDefinition("Your movement was shallow.", "Go lower.", 10),
    "fast": IssueDefinition("This rep was fast.", "Move more slowly.", 10),
    "extra": IssueDefinition("Another issue.", "Try again.", 10),
}


def test_placeholder_analyzer_counts_only_complete_movements() -> None:
    splitter = RepSplitter(155, 145, 165, "lower")
    measurements = [
        (170, 0.0),
        (153, 0.2),
        (160, 0.3),
        (170, 0.4),  # partial dip
        (170, 1.0),
        (153, 1.2),
        (143, 1.4),
        (148, 1.6),
        (140, 1.8),
        (140, 2.4),
        (150, 3.0),
        (166, 3.4),
    ]
    windows = [
        window
        for value, time in measurements
        if (window := splitter.update(value, time))
    ]
    assert windows == [RepWindow(1.2, 3.4)]

    # A placeholder analyzer reports an issue; the framework builds the result.
    observations = [
        RepObservation(window.start_seconds, window.end_seconds, ("shallow",))
        for window in windows
    ]
    result = build_rep_result(observations, ISSUES, "0.2.0")
    assert result.rep_count == 1
    assert result.reps[0].score == result.form_score == 90
    assert result.reps[0].issues[0].message == ISSUES["shallow"].message
    assert result.feedback == [ISSUES["shallow"].tip]


def test_rep_splitter_discards_tracking_gap_and_waits_for_rest() -> None:
    splitter = RepSplitter(155, 145, 165, "lower")
    assert splitter.update(170, 0.0) is None
    assert splitter.update(140, 0.2) is None
    assert splitter.update(None, 0.3) is None
    assert splitter.update(170, 1.1) is None  # gap exceeds 0.75 s
    assert splitter.update(140, 1.2) is None
    assert splitter.update(166, 1.8) == RepWindow(1.2, 1.8)


def test_rep_splitter_supports_rising_measurements() -> None:
    splitter = RepSplitter(30, 45, 20, "higher")
    assert splitter.update(10, 0.0) is None
    assert splitter.update(35, 0.2) is None
    assert splitter.update(50, 0.4) is None
    assert splitter.update(10, 1.0) == RepWindow(0.2, 1.0)


@pytest.mark.parametrize(
    ("thresholds", "direction", "message"),
    [
        ((155, 145, 150), "lower", "count <= start < rest"),
        ((30, 25, 20), "higher", "count >= start > rest"),
        ((155, 145, math.inf), "lower", "finite"),
        ((155, 145, 165), "sideways", "direction"),
    ],
)
def test_rep_splitter_rejects_invalid_thresholds(
    thresholds: tuple[float, float, float], direction: str, message: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        RepSplitter(*thresholds, direction)  # type: ignore[arg-type]


def test_hold_observation_requires_good_form_time() -> None:
    with pytest.raises(TypeError):
        HoldObservation(0, 5)  # type: ignore[call-arg]


def test_rep_scoring_floor_average_rounding_and_feedback_rank() -> None:
    observations = [
        RepObservation(0, 1, ("lean", "shallow", "fast", "extra")),
        RepObservation(2, 3, ("shallow", "fast")),
        RepObservation(4, 5, ("lean", "fast")),
        RepObservation(6, 7, ()),
    ]
    result = build_rep_result(observations, ISSUES, "0.2.0")
    assert [rep.score for rep in result.reps] == [40, 80, 60, 100]
    assert result.form_score == 70
    assert result.feedback == [
        ISSUES["lean"].tip,
        ISSUES["fast"].tip,
        ISSUES["shallow"].tip,
    ]

    one_point = {"minor": IssueDefinition("Minor issue.", "Adjust slightly.", 1)}
    half = build_rep_result(
        [RepObservation(0, 1, ("minor",)), RepObservation(2, 3)],
        one_point,
        "0.2.0",
    )
    assert half.form_score == 100  # 99.5 rounds up


def test_rep_score_never_falls_below_zero() -> None:
    severe = {"issue": IssueDefinition("Problem.", "Fix it.", 120)}
    result = build_rep_result([RepObservation(0, 1, ("issue",))], severe, "0.2.0")
    assert result.reps[0].score == result.form_score == 0


def test_empty_and_clean_results_have_distinct_feedback() -> None:
    empty = build_rep_result([], ISSUES, "0.2.0")
    clean = build_rep_result([RepObservation(0, 1)], ISSUES, "0.2.0")
    assert empty.rep_count == 0 and empty.form_score is None
    assert empty.feedback == [NO_REPS_FEEDBACK]
    assert clean.form_score == 100 and clean.feedback == [GOOD_FORM_FEEDBACK]


def test_hold_scores_use_good_form_time_and_weight_by_duration() -> None:
    observations = [
        HoldObservation(0, 10, ("lean",), good_form_seconds=5),
        HoldObservation(12, 42, (), good_form_seconds=30),
    ]
    result = build_hold_result(observations, ISSUES, "0.2.0")
    assert result.rep_count is None and result.hold_seconds == 30
    assert [hold.score for hold in result.reps] == [50, 100]
    assert [hold.metrics["good_form_seconds"] for hold in result.reps] == [5, 30]
    assert result.form_score == 88  # 35 good seconds out of 40, exact half up
    assert result.feedback == [ISSUES["lean"].tip]


def test_empty_hold_and_invalid_observations() -> None:
    result = build_hold_result([], ISSUES, "0.2.0")
    assert result.hold_seconds == 0 and result.form_score is None
    assert result.feedback == [NO_REPS_FEEDBACK]
    with pytest.raises(ValueError, match="good form time"):
        build_hold_result([HoldObservation(0, 5, good_form_seconds=6)], ISSUES, "0.2.0")
    with pytest.raises(ValueError, match="only once"):
        build_rep_result([RepObservation(0, 1, ("lean", "lean"))], ISSUES, "0.2.0")


def test_hold_accepts_time_equal_to_duration_after_float_subtraction() -> None:
    result = build_hold_result(
        [HoldObservation(0.1, 0.3, good_form_seconds=0.2)], ISSUES, "0.2.0"
    )
    assert result.form_score == 100
