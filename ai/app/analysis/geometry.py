"""2D image-plane geometry adapted from ptassist_squat/geometry.py in the POC."""

import math

from .landmarks import Landmark


def point(landmark: Landmark, width: int, height: int) -> tuple[float, float]:
    """Convert normalized coordinates to pixels, preserving the aspect ratio."""
    if width <= 0 or height <= 0:
        raise ValueError("Frame dimensions must be positive")
    x, y = landmark.x * width, landmark.y * height
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("Pixel coordinates must be finite")
    return x, y


def _normalize_distance(value: float, reference_length_pixels: float | None) -> float:
    if reference_length_pixels is None:
        return value
    if not math.isfinite(reference_length_pixels) or reference_length_pixels <= 0:
        raise ValueError("Reference length must be finite and positive")
    return value / reference_length_pixels


def distance(
    a: Landmark,
    b: Landmark,
    width: int,
    height: int,
    *,
    reference_length_pixels: float | None = None,
) -> float:
    """Return pixel distance, or a ratio to a supplied torso/limb length in pixels.

    Coincident points have distance zero. A reference length must be finite and
    positive; compute it with another call to distance using the same image size.
    """
    ax, ay = point(a, width, height)
    bx, by = point(b, width, height)
    return _normalize_distance(math.hypot(bx - ax, by - ay), reference_length_pixels)


def midpoint(a: Landmark, b: Landmark) -> Landmark:
    """Return a normalized midpoint with the lower visibility and presence scores.

    Averaging commutes with image scaling, so no frame dimensions are needed.
    Reject invalid inputs rather than making an unreliable joint appear reliable.
    """
    if not all(math.isfinite(value) for value in (a.x, a.y, b.x, b.y)):
        raise ValueError("Coordinates must be finite")
    if not all(
        0 <= score <= 1  # Also rejects NaN and infinity.
        for score in (a.visibility, a.presence, b.visibility, b.presence)
    ):
        raise ValueError("Confidence scores must be in [0, 1]")
    return Landmark(
        a.x / 2 + b.x / 2,
        a.y / 2 + b.y / 2,
        min(a.visibility, b.visibility),
        min(a.presence, b.presence),
    )


def _unit_vector(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if not math.isfinite(length) or length < 1e-6:
        raise ValueError("Coincident landmarks: segment needs finite, nonzero length")
    return dx / length, dy / length


def signed_segment_angle(
    a: Landmark,
    b: Landmark,
    c: Landmark,
    d: Landmark,
    width: int,
    height: int,
) -> float:
    """Return rotation from segment a->b to c->d in degrees [-180, 180].

    Image y increases downward, so positive rotation is clockwise on the image.
    Endpoint order matters; zero-length segments are rejected. Opposite segments
    lie at the +/-180 degree boundary, where the rotation direction is ambiguous.
    """
    ux, uy = _unit_vector(point(a, width, height), point(b, width, height))
    vx, vy = _unit_vector(point(c, width, height), point(d, width, height))
    return math.degrees(math.atan2(ux * vy - uy * vx, ux * vx + uy * vy))


def signed_distance_to_line(
    landmark: Landmark,
    line_start: Landmark,
    line_end: Landmark,
    width: int,
    height: int,
    *,
    reference_length_pixels: float | None = None,
) -> float:
    """Return signed perpendicular distance to the infinite line start->end.

    Units are pixels, or a ratio if a positive reference length is supplied.
    For a line pointing right, points below it have positive distance (image y
    increases downward). Reversing the endpoints reverses the sign. The projection
    is not clamped to the segment; coincident line endpoints are rejected.
    """
    sx, sy = point(line_start, width, height)
    ux, uy = _unit_vector((sx, sy), point(line_end, width, height))
    px, py = point(landmark, width, height)
    return _normalize_distance(ux * (py - sy) - uy * (px - sx), reference_length_pixels)


def joint_angle(
    a: Landmark, joint: Landmark, b: Landmark, width: int, height: int
) -> float:
    """Return the angle at joint in degrees [0, 180]; reject degenerate limbs."""
    return abs(signed_segment_angle(joint, a, joint, b, width, height))


def lean_from_vertical(
    shoulder: Landmark, hip: Landmark, width: int, height: int
) -> float:
    """Return unsigned torso lean in degrees [0, 90], as in the prototype."""
    ux, uy = _unit_vector(point(hip, width, height), point(shoulder, width, height))
    return math.degrees(math.atan2(abs(ux), abs(uy)))
