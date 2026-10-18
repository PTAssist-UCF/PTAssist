"""Reject frames with unreliable required joints without changing frame indices."""

from collections.abc import Iterable, Mapping

from .landmarks import Landmark


def _is_visible(
    landmarks: Mapping[str, Landmark],
    required_joints: tuple[str, ...],
    min_confidence: float,
    frame_margin: float,
) -> bool:
    for name in required_joints:
        landmark = landmarks.get(name)
        if landmark is None:
            return False
        # Chained comparisons are False for NaN and infinity, so those fail too.
        if not all(
            min_confidence <= score <= 1
            for score in (landmark.visibility, landmark.presence)
        ):
            return False
        if not (
            frame_margin <= landmark.x <= 1 - frame_margin
            and frame_margin <= landmark.y <= 1 - frame_margin
        ):
            return False
    return True


def is_frame_visible(
    landmarks: Mapping[str, Landmark],
    required_joints: Iterable[str],
    *,
    min_confidence: float = 0.65,
    frame_margin: float = 0.025,
) -> bool:
    """Require all named joints in frame with visibility and presence >= threshold.

    Missing joints, invalid confidence scores, and out-of-frame coordinates fail
    closed. Unused joints do not affect the result. Defaults follow the squat POC;
    each analyzer can choose its own threshold and margin.
    """
    return visibility_mask(
        [landmarks],
        required_joints,
        min_confidence=min_confidence,
        frame_margin=frame_margin,
    )[0]


def visibility_mask(
    frames: Iterable[Mapping[str, Landmark]],
    required_joints: Iterable[str],
    *,
    min_confidence: float = 0.65,
    frame_margin: float = 0.025,
) -> list[bool]:
    """Return one decision per frame, retaining indices for timestamps and gaps."""
    names = tuple(required_joints)
    if not names:
        raise ValueError("At least one required joint must be specified")
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be in [0, 1]")
    if not 0 <= frame_margin < 0.5:
        raise ValueError("frame_margin must be in [0, 0.5)")
    return [_is_visible(frame, names, min_confidence, frame_margin) for frame in frames]
