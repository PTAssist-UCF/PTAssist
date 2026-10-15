"""Synthetic geometry, including the prototype's non-square frame examples."""

import math

import pytest

from app.analysis.geometry import (
    distance,
    joint_angle,
    lean_from_vertical,
    midpoint,
    point,
    signed_distance_to_line,
    signed_segment_angle,
)
from app.analysis.landmarks import Landmark


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (Landmark(0.5, 0.25), Landmark(0.5, 0.75), 180),
        (Landmark(0.6875, 0.5), Landmark(0.5, 0.75), 90),
        (Landmark(0.6875, 0.25), Landmark(0.5, 0.25), 45),
        (Landmark(0.6875, 0.25), Landmark(0.5, 0.75), 135),
        (Landmark(0.5, 0.25), Landmark(0.5, 0.375), 0),
    ],
)
def test_joint_angles_on_a_non_square_frame(
    a: Landmark, b: Landmark, expected: float
) -> None:
    joint = Landmark(0.5, 0.5)
    assert joint_angle(a, joint, b, 640, 480) == pytest.approx(expected)
    assert joint_angle(b, joint, a, 640, 480) == pytest.approx(expected)


def test_geometry_is_invariant_to_image_scaling_and_translation() -> None:
    a, joint, b = Landmark(0.1875, 0.25), Landmark(0, 0.5), Landmark(0, 0.25)
    assert joint_angle(a, joint, b, 1280, 960) == pytest.approx(45)


@pytest.mark.parametrize(
    ("shoulder", "expected"),
    [
        (Landmark(0.5, 0.35), 0),
        (Landmark(0.6875, 0.35), 45),
        (Landmark(0.3125, 0.35), 45),
        (Landmark(0.6875, 0.6), 90),
    ],
)
def test_unsigned_lean_from_vertical(shoulder: Landmark, expected: float) -> None:
    assert lean_from_vertical(shoulder, Landmark(0.5, 0.6), 640, 480) == pytest.approx(
        expected
    )


@pytest.mark.parametrize("a_is_joint", [True, False])
def test_coincident_joint_endpoints_are_rejected(a_is_joint: bool) -> None:
    joint, other = Landmark(0.5, 0.5), Landmark(0.5, 0.7)
    a, b = (joint, other) if a_is_joint else (other, joint)
    with pytest.raises(ValueError, match="Coincident"):
        joint_angle(a, joint, b, 640, 480)


def test_coincident_torso_is_rejected() -> None:
    with pytest.raises(ValueError, match="Coincident"):
        lean_from_vertical(Landmark(0.5, 0.5), Landmark(0.5, 0.5), 640, 480)


@pytest.mark.parametrize(("width", "height"), [(0, 480), (640, 0), (-1, 480)])
def test_invalid_frame_dimensions_are_rejected(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        point(Landmark(0.5, 0.5), width, height)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("coordinate", ["x", "y"])
def test_nonfinite_coordinates_are_rejected(bad: float, coordinate: str) -> None:
    landmark = Landmark(**{coordinate: bad, "y" if coordinate == "x" else "x": 0.5})
    with pytest.raises(ValueError, match="finite"):
        joint_angle(landmark, Landmark(0.5, 0.5), Landmark(0.5, 0.7), 640, 480)


def test_distance_uses_pixels_and_allows_coincident_points() -> None:
    a, b = Landmark(0.25, 0.25), Landmark(0.4375, 0.5)
    assert distance(a, b, 640, 480) == pytest.approx(math.sqrt(2) * 120)
    assert distance(b, a, 640, 480) == pytest.approx(math.sqrt(2) * 120)
    assert distance(a, a, 640, 480) == 0
    assert distance(a, b, 1280, 960) == pytest.approx(math.sqrt(2) * 240)


def test_distance_normalized_by_body_length_is_scale_independent() -> None:
    shoulder, hip = Landmark(0.5, 0.25), Landmark(0.5, 0.75)
    wrist = Landmark(0.6875, 0.25)
    for width, height in [(640, 480), (1280, 960)]:
        torso_length = distance(shoulder, hip, width, height)
        assert distance(
            shoulder, wrist, width, height, reference_length_pixels=torso_length
        ) == pytest.approx(0.5)


def test_midpoint_preserves_normalized_coordinates_and_lower_confidence() -> None:
    a, b = Landmark(0.25, 0.25, 0.9, 0.7), Landmark(0.75, 0.5, 0.6, 0.8)
    center = midpoint(a, b)
    assert center == Landmark(0.5, 0.375, 0.6, 0.7)
    assert midpoint(b, a) == center
    assert midpoint(a, a) == a
    assert point(center, 640, 480) == (320, 180)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_midpoint_rejects_nonfinite_coordinates(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        midpoint(Landmark(0.5, 0.5), Landmark(bad, 0.5))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -0.1, 1.1])
@pytest.mark.parametrize("field", ["visibility", "presence"])
def test_midpoint_rejects_invalid_confidence(field: str, bad: float) -> None:
    with pytest.raises(ValueError, match="Confidence"):
        midpoint(Landmark(0.5, 0.5), Landmark(0.5, 0.5, **{field: bad}))


@pytest.mark.parametrize(
    ("end", "expected"),
    [
        (Landmark(0.6875, 0.5), 0),
        (Landmark(0.6875, 0.75), 45),
        (Landmark(0.5, 0.75), 90),
        (Landmark(0.5, 0.25), -90),
        (Landmark(0.6875, 0.25), -45),
        (Landmark(0.3125, 0.5), 180),
    ],
)
def test_signed_segment_angles_use_image_coordinates(
    end: Landmark, expected: float
) -> None:
    origin, right = Landmark(0.5, 0.5), Landmark(0.6875, 0.5)
    angle = signed_segment_angle(origin, right, origin, end, 640, 480)
    assert angle == pytest.approx(expected)
    reverse = signed_segment_angle(origin, end, origin, right, 640, 480)
    if expected == 180:
        assert abs(reverse) == pytest.approx(180)
    else:
        assert reverse == pytest.approx(-expected)


def test_segment_angle_supports_separate_origins_and_image_scaling() -> None:
    a, b = Landmark(0.125, 0.25), Landmark(0.3125, 0.25)
    c, d = Landmark(0.5, 0.5), Landmark(0.6875, 0.75)
    assert signed_segment_angle(a, b, c, d, 1280, 960) == pytest.approx(45)


@pytest.mark.parametrize("first_degenerate", [True, False])
def test_signed_segment_angle_rejects_either_degenerate_segment(
    first_degenerate: bool,
) -> None:
    a, b = Landmark(0.5, 0.5), Landmark(0.5, 0.75)
    endpoints = (a, a, a, b) if first_degenerate else (a, b, a, a)
    with pytest.raises(ValueError, match="nonzero"):
        signed_segment_angle(*endpoints, 640, 480)


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (Landmark(0.5, 0.75), 120),
        (Landmark(0.5, 0.25), -120),
        (Landmark(0.5, 0.5), 0),
        (Landmark(0.9, 0.75), 120),  # Projection beyond the segment endpoint.
    ],
)
def test_signed_distance_to_horizontal_line(p: Landmark, expected: float) -> None:
    a, b = Landmark(0.25, 0.5), Landmark(0.75, 0.5)
    assert signed_distance_to_line(p, a, b, 640, 480) == pytest.approx(expected)
    assert signed_distance_to_line(p, b, a, 640, 480) == pytest.approx(-expected)


def test_signed_distance_to_vertical_and_diagonal_lines() -> None:
    a, b, p = Landmark(0.5, 0.25), Landmark(0.5, 0.75), Landmark(0.6875, 0.5)
    assert signed_distance_to_line(p, a, b, 640, 480) == pytest.approx(-120)
    origin, diagonal = Landmark(0.25, 0.25), Landmark(0.4375, 0.5)
    assert signed_distance_to_line(a, origin, diagonal, 640, 480) == pytest.approx(
        -160 / math.sqrt(2)
    )


def test_line_distance_normalization_is_scale_independent() -> None:
    a, b, p = Landmark(0.25, 0.5), Landmark(0.75, 0.5), Landmark(0.5, 0.75)
    for width, height in [(640, 480), (1280, 960)]:
        assert signed_distance_to_line(
            p,
            a,
            b,
            width,
            height,
            reference_length_pixels=distance(a, b, width, height),
        ) == pytest.approx(0.375)


def test_signed_distance_rejects_coincident_line_endpoints() -> None:
    p, a = Landmark(0.5, 0.75), Landmark(0.5, 0.5)
    with pytest.raises(ValueError, match="nonzero"):
        signed_distance_to_line(p, a, a, 640, 480)


@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf])
def test_distances_reject_invalid_reference_lengths(bad: float) -> None:
    a, b, p = Landmark(0.25, 0.5), Landmark(0.75, 0.5), Landmark(0.5, 0.75)
    with pytest.raises(ValueError, match="Reference length"):
        distance(a, b, 640, 480, reference_length_pixels=bad)
    with pytest.raises(ValueError, match="Reference length"):
        signed_distance_to_line(p, a, b, 640, 480, reference_length_pixels=bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_distance_and_segment_helpers_reject_nonfinite_coordinates(bad: float) -> None:
    invalid, a, b = Landmark(bad, 0.5), Landmark(0.25, 0.5), Landmark(0.75, 0.5)
    with pytest.raises(ValueError, match="finite"):
        distance(invalid, a, 640, 480)
    with pytest.raises(ValueError, match="finite"):
        signed_segment_angle(a, b, a, invalid, 640, 480)
    with pytest.raises(ValueError, match="finite"):
        signed_distance_to_line(invalid, a, b, 640, 480)
