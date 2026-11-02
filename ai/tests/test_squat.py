"""The squat state machine on synthetic keypoints."""

import json
import math
from dataclasses import replace

import pytest

from app.analysis.exercises.squat import (
    CONFIG_PATH,
    Config,
    SquatAnalyzer,
    analyze_squat,
    load_config,
)
from app.analysis.landmarks import Landmark

FPS = 15
SIZE = 1000


def pose(knee_angle: float, lean: float = 10.0) -> dict[str, Landmark]:
    """A side-on pose (both legs together) with the given knee angle and torso lean."""
    knee = (0.5, 0.6)
    hip = (0.5, 0.4)
    theta = math.radians(knee_angle)
    ankle = (knee[0] + 0.2 * math.sin(theta), knee[1] - 0.2 * math.cos(theta))
    tilt = math.radians(lean)
    shoulder = (hip[0] + 0.2 * math.sin(tilt), hip[1] - 0.2 * math.cos(tilt))
    points = {
        "shoulder": shoulder,
        "hip": hip,
        "knee": knee,
        "ankle": ankle,
        "heel": (ankle[0] - 0.02, ankle[1] + 0.01),
        "foot_index": (ankle[0] + 0.05, ankle[1] + 0.01),
    }
    landmarks = {
        f"{side}_{joint}": Landmark(*xy, 0.95, 0.95)
        for joint, xy in points.items()
        for side in ("left", "right")
    }
    landmarks["nose"] = Landmark(0.5, 0.1, 0.95, 0.95)
    return landmarks


def squat_angles(bottom: float, seconds: float, lean: float = 10.0):
    """Knee angles for one squat: stand, go down to `bottom`, and stand again."""
    frames = int(seconds * FPS)
    half = frames // 2
    down = [175 - (175 - bottom) * i / half for i in range(half)]
    up = [bottom + (175 - bottom) * i / (frames - half) for i in range(frames - half)]
    return [(angle, lean) for angle in down + up]


def feed(analyzer, movements, rest_frames=8):
    """Feed (knee_angle, lean) samples, standing still before and between squats.

    Returns the FrameResult of every frame.
    """
    frames = []
    standing = [(175.0, 10.0)] * rest_frames
    for samples in [standing, *[m + standing for m in movements]]:
        for angle, lean in samples:
            frames.append(
                analyzer.update(
                    pose(angle, lean), round(len(frames) / FPS, 3), SIZE, SIZE
                )
            )
    return frames


def messages(frames) -> list[str]:
    """The distinct running messages, in order."""
    out: list[str] = []
    for frame in frames:
        if not out or out[-1] != frame.feedback:
            out.append(frame.feedback)
    return out


def test_config_file_differs_from_the_prototype_only_in_the_far_leg_limits() -> None:
    # In a side view the far leg is hidden behind the near one, so its confidence is
    # low at the bottom of a squat. The prototype's 0.65 / 0.6 dropped those frames
    # (found on a real recording), so squat.json lowers both.
    assert load_config() == replace(
        Config(),
        min_opposite_ankle_confidence=0.3,
        min_opposite_foot_confidence=0.3,
    )


def test_full_rep_is_counted_with_a_running_message_on_every_frame() -> None:
    analyzer = SquatAnalyzer()
    frames = feed(analyzer, [squat_angles(90, 3)])
    assert all(frame.feedback for frame in frames)
    assert frames[0].feedback == "Ready for squat"
    said = messages(frames)
    assert "Go lower" in said
    assert "Good depth" in said
    assert "Return to standing" in said
    assert "Full rep! Rep 1 of 5 done." in said
    assert frames[-1].rep_count == 1 and frames[-1].partial_count == 0
    observation = analyzer.observations[0]
    assert observation.issues == ()
    assert 85 <= observation.metrics["min_knee_angle_degrees"] <= 100
    assert observation.metrics["max_torso_lean_degrees"] == pytest.approx(10, abs=0.1)


def test_full_rep_message_goes_away_after_the_hold_time() -> None:
    frames = feed(SquatAnalyzer(), [squat_angles(90, 3)], rest_frames=60)
    assert frames[-1].feedback == "Ready for squat"
    assert messages(frames)[-2] == "Full rep! Rep 1 of 5 done."


def test_partial_rep_is_flagged_and_not_counted() -> None:
    analyzer = SquatAnalyzer()
    frames = feed(analyzer, [squat_angles(150, 3)])  # leaves 155, never reaches 145
    notice = next(f.feedback for f in frames if f.partial_count)
    assert notice.startswith("Partial rep, not counted: it didn't fit the rule.")
    assert "145°" in notice
    assert analyzer.observations == [] and frames[-1].partial_count == 1
    assert frames[-1].rep_count == 0


def test_dip_that_never_leaves_standing_is_ignored() -> None:
    analyzer = SquatAnalyzer()
    frames = feed(analyzer, [squat_angles(160, 3)])
    assert frames[-1].partial_count == 0 and analyzer.observations == []


def test_full_set_after_five_full_reps_and_a_partial_does_not_count() -> None:
    analyzer = SquatAnalyzer()
    movements = [squat_angles(90, 3)] * 2 + [squat_angles(150, 3)]
    movements += [squat_angles(90, 3)] * 3
    frames = feed(analyzer, movements, rest_frames=40)
    said = messages(frames)
    assert any(text.startswith("Partial rep") for text in said)
    assert "Full rep! Set 1 complete: 5 full reps done." in said
    assert frames[-1].sets_completed == 1 and frames[-1].reps_in_set == 0
    assert len(analyzer.observations) == 5 and frames[-1].partial_count == 1


def test_form_issues_become_issue_codes_and_scores() -> None:
    analyzer = SquatAnalyzer()
    feed(
        analyzer,
        [
            squat_angles(125, 3),  # shallow
            squat_angles(90, 3, lean=55),  # leaning forward
            squat_angles(90, 1.2),  # too fast
        ],
    )
    assert [o.issues for o in analyzer.observations] == [
        ("not_deep_enough",),
        ("leaning_forward",),
        ("too_fast",),
    ]
    result = analyzer.result("test")
    assert result.rep_count == 3
    assert [rep.score for rep in result.reps] == [90, 70, 90]


def test_lean_warning_shows_while_leaning() -> None:
    frames = feed(SquatAnalyzer(), [squat_angles(90, 3, lean=55)])
    assert "Keep your torso more upright" in messages(frames)
    assert any(f.form_warning for f in frames)


def test_no_person_and_prototype_guards_explain_themselves() -> None:
    unreliable = "Unable to reliably assess"
    assert SquatAnalyzer().update(None, 0.0, SIZE, SIZE).feedback == unreliable

    lunge = pose(175)
    for part in ("ankle", "heel", "foot_index"):  # far leg well apart from the near one
        old = lunge[f"right_{part}"]
        lunge[f"right_{part}"] = Landmark(0.9, old.y, 0.95, 0.95)
    # Make the left side the stronger one, so it is the near side.
    for part in ("shoulder", "hip", "knee", "ankle", "heel", "foot_index"):
        lunge[f"right_{part}"] = Landmark(
            lunge[f"right_{part}"].x, lunge[f"right_{part}"].y, 0.8, 0.8
        )
    out = SquatAnalyzer().update(lunge, 0.0, SIZE, SIZE)
    assert out.feedback == "Feet are too far apart for a side-view squat"
    assert not out.assessment_valid

    facing = pose(175)
    facing["left_shoulder"] = Landmark(0.3, 0.2, 0.95, 0.95)
    facing["right_shoulder"] = Landmark(0.7, 0.2, 0.95, 0.95)
    assert (
        SquatAnalyzer().update(facing, 0.0, SIZE, SIZE).feedback
        == "Turn sideways to the camera"
    )

    cut_off = pose(175)
    for side in ("left", "right"):
        cut_off[f"{side}_foot_index"] = Landmark(0.5, 0.99, 0.95, 0.95)
    assert (
        SquatAnalyzer().update(cut_off, 0.0, SIZE, SIZE).feedback
        == "Move back so your full body is visible"
    )


def test_a_rep_over_the_time_limit_is_dropped() -> None:
    config = replace(Config(), max_rep_duration_seconds=1.0)
    analyzer = SquatAnalyzer(config)
    feed(analyzer, [squat_angles(90, 4)])
    assert analyzer.observations == []


def test_tracking_gap_during_a_rep_drops_it() -> None:
    analyzer = SquatAnalyzer()
    t = 0.0
    for angle in [175.0] * 5 + [150.0, 120.0]:
        analyzer.update(pose(angle), t, SIZE, SIZE)
        t += 1 / FPS
    t += 1.0  # tracking lost for over 0.75 s
    for angle in [120.0, 175.0, 175.0]:
        analyzer.update(pose(angle), t, SIZE, SIZE)
        t += 1 / FPS
    assert analyzer.observations == []


def test_keypoint_json_gives_a_contract_result() -> None:
    samples = [(175.0, 10.0)] * 8 + squat_angles(90, 3) + [(175.0, 10.0)] * 8
    frames = []
    for index, (angle, lean) in enumerate(samples):
        landmarks = {
            name: [lm.x, lm.y, lm.visibility, lm.presence]
            for name, lm in pose(angle, lean).items()
        }
        frames.append(
            {
                "index": index,
                "time_seconds": round(index / FPS, 3),
                "landmarks": landmarks,
            }
        )
    frames[3]["landmarks"] = None  # one frame without a person
    data = {"video": {"width": SIZE, "height": SIZE, "fps": 15.0}, "frames": frames}
    result = analyze_squat(json.loads(json.dumps(data))).result("test")
    assert result.status == "complete" and result.rep_count == 1
    assert result.form_score == 100


def test_editing_the_json_changes_the_rule(tmp_path) -> None:
    raw = json.loads(CONFIG_PATH.read_text("utf-8"))
    raw["bottom_entry_knee_angle"] = 152.0  # a squat to 150 degrees now counts
    path = tmp_path / "squat.json"
    path.write_text(json.dumps(raw), "utf-8")
    analyzer = SquatAnalyzer(load_config(path))
    feed(analyzer, [squat_angles(150, 3)])
    assert len(analyzer.observations) == 1


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"bottom_entry_knee_angle": 170.0}, "knee angles"),
        ({"reps_per_set": 0}, "reps_per_set"),
        ({"standing_knee": 165.0}, "unexpected keyword"),
    ],
)
def test_bad_config_fails_with_a_clear_message(change, message, tmp_path) -> None:
    path = tmp_path / "squat.json"
    path.write_text(json.dumps(change), "utf-8")
    with pytest.raises(ValueError, match=message):
        load_config(path)
