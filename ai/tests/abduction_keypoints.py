"""Synthetic front-view arm lifts, in the documented keypoint JSON."""

import math
from typing import Any, NamedTuple

WIDTH, HEIGHT, FPS = 720, 1280, 15
START_SECONDS = 1.0  # standing still before the first keyframe
GOOD, POOR = 0.9, 0.3  # confidence scores: passes or fails the 0.65 check


class Pose(NamedTuple):
    """Shoulder angles, torso lean, and elbow angle, all in degrees."""

    left: float = 5.0
    right: float = 5.0
    lean: float = 2.0
    elbow: float = 175.0


REST = Pose()


def lift(
    left: float = 0.0,
    right: float = 0.0,
    seconds: float = 4.0,
    lean: float = 2.0,
    elbow: float = 175.0,
) -> list[tuple[float, Pose]]:
    """Keyframes (duration, pose): lift, hold at the top, lower, rest.

    `left` and `right` are the top angles; an arm left at 0 stays at its side.
    """
    top = Pose(left or REST.left, right or REST.right, lean, elbow)
    return [
        (seconds * 0.4, top),
        (seconds * 0.2, top),
        (seconds * 0.4, REST),
        (1.0, REST),
    ]


def _rotate(point: tuple[float, float], pivot: tuple[float, float], degrees: float):
    """Turn a point around a pivot, keeping the distance between them."""
    angle = math.radians(degrees)
    x, y = point[0] - pivot[0], point[1] - pivot[1]
    return (
        pivot[0] + x * math.cos(angle) - y * math.sin(angle),
        pivot[1] + x * math.sin(angle) + y * math.cos(angle),
    )


def landmarks(pose: Pose) -> dict[str, tuple[float, float]]:
    """Normalized joints of a patient facing the camera.

    Their left arm is on the image's right. Arms are 2 x 120 pixels, the torso 300.
    """
    hip_mid = (360.0, 750.0)
    points = {"left_hip": (420.0, 750.0), "right_hip": (300.0, 750.0)}
    for side, offset, angle in (("left", 1, pose.left), ("right", -1, pose.right)):
        shoulder = (360.0 + offset * 80, 450.0)
        theta = math.radians(angle)
        direction = (offset * math.sin(theta), math.cos(theta))
        elbow = (shoulder[0] + 120 * direction[0], shoulder[1] + 120 * direction[1])
        straight = (elbow[0] + 120 * direction[0], elbow[1] + 120 * direction[1])
        wrist = _rotate(straight, elbow, offset * (180 - pose.elbow))
        points |= {
            f"{side}_shoulder": _rotate(shoulder, hip_mid, pose.lean),
            f"{side}_elbow": _rotate(elbow, hip_mid, pose.lean),
            f"{side}_wrist": _rotate(wrist, hip_mid, pose.lean),
        }
    return {name: (x / WIDTH, y / HEIGHT) for name, (x, y) in points.items()}


def keypoints(
    keyframes: list[tuple[float, Pose]],
    *,
    hidden: dict[str, tuple[float, float]] | None = None,
    missing: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Sample linear keyframes at 15 fps into the documented keypoint JSON.

    `hidden` maps a joint to a (start, end) time when its confidence is poor.
    `missing` is a (start, end) time with no person at all.
    """
    times, poses = [0.0, START_SECONDS], [REST, REST]
    for duration, pose in keyframes:
        times.append(times[-1] + duration)
        poses.append(pose)

    frames = []
    for index in range(int(times[-1] * FPS) + 1):
        t = round(index / FPS, 3)
        k = next(
            i for i in range(1, len(times)) if t <= times[i] or i == len(times) - 1
        )
        share = min(1.0, (t - times[k - 1]) / (times[k] - times[k - 1]))
        pose = Pose(
            *(a + share * (b - a) for a, b in zip(poses[k - 1], poses[k], strict=True))
        )
        joints = None
        if not (missing and missing[0] <= t < missing[1]):
            joints = {}
            for name, (x, y) in landmarks(pose).items():
                window = (hidden or {}).get(name)
                score = POOR if window and window[0] <= t < window[1] else GOOD
                joints[name] = [x, y, score, score]
        frames.append({"index": index, "time_seconds": t, "landmarks": joints})
    return {
        "video": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": float(FPS),
            "frame_count": len(frames),
        },
        "model": "pose_landmarker_full.task",
        "frames": frames,
    }
