"""The analyzer on synthetic and real lifts (docs/exercises/shoulder-abduction.md)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.analysis.exercises.shoulder_abduction import (
    CONFIG_PATH,
    ISSUES,
    Config,
    analyze_shoulder_abduction,
    load_config,
)
from app.analysis.framework import GOOD_FORM_FEEDBACK, NO_REPS_FEEDBACK
from app.analysis_contract import AnalysisResult
from tests.abduction_keypoints import REST, Pose, keypoints, lift

# Keypoints of a real phone recording, cut down to the joints this exercise uses.
REAL_CLIP = Path(__file__).parent / "fixtures/abduction_5r_5l_2b.keypoints.json"


def analyze(
    keyframes: list, config: Config | None = None, **options: object
) -> AnalysisResult:
    return analyze_shoulder_abduction(keypoints(keyframes, **options), "test", config)


def sides(result: AnalysisResult) -> list[str | None]:
    return [rep.side for rep in result.reps]


def codes(result: AnalysisResult) -> list[list[str]]:
    return [[issue.code for issue in rep.issues] for rep in result.reps]


def test_a_real_recording_counts_every_rep_on_the_right_side() -> None:
    data = json.loads(REAL_CLIP.read_text(encoding="utf-8"))
    result = analyze_shoulder_abduction(data, "test")
    assert sides(result) == ["right"] * 5 + ["left"] * 5 + ["both"] * 2
    assert codes(result) == [["too_fast"]] * 12  # it was recorded quickly


def test_good_lifts_of_each_arm_count_with_their_side() -> None:
    result = analyze(lift(left=95) * 2 + lift(right=100) * 3)
    assert sides(result) == ["left", "left", "right", "right", "right"]
    assert result.rep_count == 5
    assert result.form_score == 100 and result.feedback == [GOOD_FORM_FEEDBACK]
    assert result.reps[0].metrics["max_shoulder_angle_degrees"] == pytest.approx(
        95, abs=1
    )
    assert result.reps[-1].metrics["max_shoulder_angle_degrees"] == pytest.approx(
        100, abs=1
    )


def test_both_arms_together_are_one_rep_with_the_lower_height() -> None:
    result = analyze(lift(left=120, right=95))
    assert sides(result) == ["both"]
    assert result.reps[0].metrics["max_shoulder_angle_degrees"] == pytest.approx(
        95, abs=1
    )


def staggered(delay: float) -> list[tuple[float, Pose]]:
    """The left arm starts lifting, and the right arm follows `delay` seconds later.

    The left arm rises from 5 to 95 degrees in 1.6 s, so both arms' angles are given
    at every keyframe.
    """
    return [
        (delay, Pose(left=5 + 90 * delay / 1.6)),
        (1.6 - delay, Pose(left=95, right=5 + 90 * (1.6 - delay) / 1.6)),
        (delay, Pose(left=95, right=95)),
        (0.8, Pose(left=95, right=95)),
        (1.6, REST),
        (1.0, REST),
    ]


def test_arms_starting_within_a_second_pair_up() -> None:
    assert sides(analyze(staggered(0.6))) == ["both"]


def test_arms_starting_further_apart_stay_separate() -> None:
    keyframes = [
        (1.5, Pose(left=95)),
        (1.5, Pose(left=95, right=95)),
        (1.5, Pose(left=5, right=95)),
        (1.5, REST),
        (1.0, REST),
    ]
    assert sides(analyze(keyframes)) == ["left", "right"]


def test_each_rep_pairs_at_most_once() -> None:
    # The right arm lifts once while the left lifts twice: one both, one left.
    keyframes = [
        (1.0, Pose(left=95, right=95)),
        (1.0, Pose(left=5, right=95)),
        (1.0, Pose(left=95, right=95)),
        (1.0, Pose(left=5, right=5)),
        (1.0, REST),
    ]
    assert sides(analyze(keyframes)) == ["both", "left"]


@pytest.mark.parametrize(
    ("rep", "code"),
    [
        (lift(left=70), "arm_not_high_enough"),
        (lift(left=62), "arm_not_high_enough"),  # only just reaches the count threshold
        (lift(right=95, lean=25), "torso_lean"),
        (lift(left=95, elbow=130), "elbow_bent"),
        (lift(right=95, seconds=1.5), "too_fast"),
    ],
)
def test_each_form_rule(rep: list, code: str) -> None:
    result = analyze(rep * 3)
    assert result.rep_count == 3
    assert codes(result) == [[code]] * 3
    assert result.feedback == [ISSUES[code].tip]


def test_a_both_rep_has_every_issue_of_either_arm_once() -> None:
    # Only the left arm is low; both elbows bend, so elbow_bent must appear once.
    top = Pose(left=70, right=95, elbow=130)
    result = analyze([(1.6, top), (0.8, top), (1.6, REST), (1.0, REST)])
    assert sides(result) == ["both"]
    assert codes(result) == [["arm_not_high_enough", "elbow_bent"]]


def handoff(right_hold: float) -> list[tuple[float, Pose]]:
    """A quick left lift; the right arm follows and holds for `right_hold` seconds."""
    return [
        (0.5, Pose(left=95)),
        (0.3, Pose(left=95, right=30)),
        (0.4, Pose(left=5, right=95)),
        (right_hold, Pose(left=5, right=95)),
        (0.6, REST),
        (1.0, REST),
    ]


@pytest.mark.parametrize(("right_hold", "expected"), [(0.3, ["too_fast"]), (1.2, [])])
def test_too_fast_is_checked_on_the_paired_rep(
    right_hold: float, expected: list[str]
) -> None:
    # The left arm alone always takes under 2 seconds; only the pair's span counts.
    result = analyze(handoff(right_hold))
    assert sides(result) == ["both"]
    assert codes(result) == [expected]


def test_a_small_lift_is_not_a_rep() -> None:
    result = analyze(lift(left=50) * 2)
    assert result.rep_count == 0
    assert result.form_score is None and result.feedback == [NO_REPS_FEEDBACK]


@pytest.mark.parametrize(("gap", "expected"), [(1.0, 1), (0.4, 2)])
def test_losing_an_arm_mid_rep_drops_it_only_after_0_75_seconds(
    gap: float, expected: int
) -> None:
    # The first lift's top is held from 2.6 to 3.4 seconds.
    hidden = {"left_wrist": (2.6, 2.6 + gap)}
    result = analyze(lift(left=95) * 2, hidden=hidden)
    assert result.rep_count == expected


def test_losing_one_arm_does_not_affect_the_other() -> None:
    hidden = {"left_elbow": (2.6, 3.6)}
    result = analyze(lift(left=95, right=95), hidden=hidden)
    assert sides(result) == ["right"]


def test_losing_a_torso_joint_skips_both_arms() -> None:
    hidden = {"left_hip": (2.6, 3.6)}
    assert analyze(lift(left=95, right=95), hidden=hidden).rep_count == 0


def test_no_person_gives_no_reps() -> None:
    result = analyze(lift(left=95) * 2, missing=(0, 100))
    assert result.rep_count == 0 and result.feedback == [NO_REPS_FEEDBACK]


def test_config_file_matches_the_spec() -> None:
    assert load_config() == Config()


def test_editing_the_json_changes_the_rule(tmp_path: Path) -> None:
    raw = json.loads(CONFIG_PATH.read_text("utf-8"))
    raw["shoulder_height_angle"] = 65.0  # a lift to 70 degrees is now high enough
    path = tmp_path / "shoulder_abduction.json"
    path.write_text(json.dumps(raw), "utf-8")
    result = analyze(lift(left=70) * 2, load_config(path))
    assert codes(result) == [[], []]


def test_a_config_can_be_passed_in_code() -> None:
    config = replace(Config(), min_rep_seconds=1.0)
    assert codes(analyze(lift(right=95, seconds=1.5), config)) == [[]]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"start_shoulder_angle": 20.0}, "shoulder angles"),
        ({"count_shoulder_angle": 30.0}, "shoulder angles"),
        ({"min_rep_seconds": float("nan")}, "finite"),
        ({"shoulder_height": 80.0}, "unexpected keyword"),
    ],
)
def test_bad_config_fails_with_a_clear_message(
    change: dict, message: str, tmp_path: Path
) -> None:
    path = tmp_path / "shoulder_abduction.json"
    path.write_text(json.dumps(change), "utf-8")
    with pytest.raises(ValueError, match=message):
        load_config(path)
