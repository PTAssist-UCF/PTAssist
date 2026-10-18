"""Synthetic visibility checks and their use before geometry and smoothing."""

import math

import pytest

from app.analysis.geometry import joint_angle
from app.analysis.landmarks import Landmark
from app.analysis.smoothing import ExponentialSmoother
from app.analysis.visibility import is_frame_visible, visibility_mask

REQUIRED = ("hip", "knee", "ankle")


def visible_frame() -> dict[str, Landmark]:
    return {
        "hip": Landmark(0.5, 0.25),
        "knee": Landmark(0.5, 0.5),
        "ankle": Landmark(0.5, 0.75),
    }


def test_only_required_joints_affect_visibility() -> None:
    frame = visible_frame()
    frame["wrist"] = Landmark(math.nan, math.inf, 0, 0)
    assert is_frame_visible(frame, REQUIRED)


def test_missing_required_joint_or_empty_pose_is_rejected() -> None:
    frame = visible_frame()
    del frame["knee"]
    assert not is_frame_visible(frame, REQUIRED)
    assert not is_frame_visible({}, REQUIRED)


@pytest.mark.parametrize("score", [0.64, -0.1, 1.1, math.nan, math.inf])
@pytest.mark.parametrize("field", ["visibility", "presence"])
def test_both_confidence_scores_must_be_valid(field: str, score: float) -> None:
    frame = visible_frame()
    frame["knee"] = Landmark(0.5, 0.5, **{field: score})
    assert not is_frame_visible(frame, REQUIRED)


def test_confidence_and_margin_boundaries_are_inclusive() -> None:
    frame = {"knee": Landmark(0.025, 0.975, 0.65, 0.65)}
    assert is_frame_visible(frame, ["knee"])
    assert frame["knee"].confidence == 0.65
    assert Landmark(0.5, 0.5, 0.9, 0.7).confidence == 0.7


@pytest.mark.parametrize("bad", [-0.1, 0.024, 0.976, 1.1, math.nan, math.inf])
@pytest.mark.parametrize("coordinate", ["x", "y"])
def test_out_of_frame_or_invalid_coordinates_are_rejected(
    coordinate: str, bad: float
) -> None:
    frame = visible_frame()
    frame["knee"] = Landmark(
        **{coordinate: bad, "y" if coordinate == "x" else "x": 0.5}
    )
    assert not is_frame_visible(frame, REQUIRED)


def test_analyzers_can_override_threshold_and_margin() -> None:
    frame = {"knee": Landmark(0, 1, 0.5, 0.5)}
    assert is_frame_visible(frame, ["knee"], min_confidence=0.5, frame_margin=0)
    assert not is_frame_visible(frame, ["knee"])


@pytest.mark.parametrize("threshold", [-0.1, 1.1, math.nan, math.inf])
def test_invalid_threshold_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        visibility_mask([], REQUIRED, min_confidence=threshold)


@pytest.mark.parametrize("margin", [-0.1, 0.5, math.nan, math.inf])
def test_invalid_margin_is_rejected(margin: float) -> None:
    with pytest.raises(ValueError, match="frame_margin"):
        is_frame_visible(visible_frame(), REQUIRED, frame_margin=margin)


def test_required_joints_cannot_be_empty_even_for_no_frames() -> None:
    with pytest.raises(ValueError, match="required joint"):
        is_frame_visible(visible_frame(), [])
    with pytest.raises(ValueError, match="required joint"):
        visibility_mask([], [])
    assert visibility_mask([], REQUIRED) == []


def test_mask_preserves_all_frames_and_accepts_generators() -> None:
    frames = [visible_frame(), {}, visible_frame()]
    assert visibility_mask(iter(frames), iter(REQUIRED)) == [True, False, True]
    assert frames[1] == {}


def test_filter_geometry_and_smoothing_preserve_a_tracking_gap() -> None:
    frames = [visible_frame(), {}, visible_frame()]
    frames[2]["hip"] = Landmark(0.6875, 0.5)
    smoother = ExponentialSmoother()
    measurements = []
    for frame, timestamp, valid in zip(
        frames, [0, 0.1, 1], visibility_mask(frames, REQUIRED), strict=True
    ):
        angle = (
            joint_angle(frame["hip"], frame["knee"], frame["ankle"], 640, 480)
            if valid
            else None
        )
        measurements.append(smoother.update(angle, timestamp))
    assert measurements == [180, None, 90]
