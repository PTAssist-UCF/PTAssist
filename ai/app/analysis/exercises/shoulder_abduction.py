"""Shoulder abduction analyzer, following docs/exercises/shoulder-abduction.md.

Front view: each arm is measured and counted on its own, then reps of the two arms
that start together become one "both" rep. Every number below is a starting value
from the spec, not a clinical target.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple

from app.analysis_contract import AnalysisResult

from ..framework import (
    IssueDefinition,
    RepObservation,
    RepSplitter,
    RepWindow,
    build_rep_result,
    samples_in_window,
)
from ..geometry import joint_angle, lean_from_vertical, midpoint, signed_segment_angle
from ..landmarks import Landmark, frame_landmarks
from ..smoothing import ExponentialSmoother
from ..visibility import is_frame_visible

NAME = "shoulder_abduction"

Side = Literal["left", "right"]
SIDES: tuple[Side, Side] = ("left", "right")
TORSO = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")

REST_DEGREES = 25.0
START_DEGREES = 35.0
COUNT_DEGREES = 60.0
HEIGHT_LIMIT_DEGREES = 80.0
ELBOW_CHECK_FROM_DEGREES = 55.0
ELBOW_LIMIT_DEGREES = 150.0
LEAN_LIMIT_DEGREES = 18.0
MIN_REP_SECONDS = 2.0
PAIR_WITHIN_SECONDS = 1.0

ISSUES = {
    "torso_lean": IssueDefinition(
        "You leaned your upper body to the side.",
        "Keep your body upright and lift only your arm.",
        30,
    ),
    "arm_not_high_enough": IssueDefinition(
        "Your arm did not reach shoulder height.",
        "Lift your arm higher, to shoulder height or above if you can.",
        10,
    ),
    "elbow_bent": IssueDefinition(
        "Your elbow bent as you lifted your arm.",
        "Keep your elbow straight as you lift and lower your arm.",
        10,
    ),
    "too_fast": IssueDefinition(
        "This rep took less than 2 seconds.",
        "Slow down: take at least 2 seconds for each rep.",
        10,
    ),
}


class Torso(NamedTuple):
    """One frame's torso line and lean, shared by both arms."""

    shoulder_mid: Landmark
    hip_mid: Landmark
    lean: float


class Sample(NamedTuple):
    """One frame's smoothed measurements for one arm."""

    time: float
    shoulder: float
    elbow: float
    lean: float


def _new_splitter() -> RepSplitter:
    return RepSplitter(START_DEGREES, COUNT_DEGREES, REST_DEGREES, "higher")


@dataclass
class Arm:
    """Everything tracked for one arm. Each angle has its own smoother."""

    side: Side
    splitter: RepSplitter = field(default_factory=_new_splitter)
    shoulder: ExponentialSmoother = field(default_factory=ExponentialSmoother)
    elbow: ExponentialSmoother = field(default_factory=ExponentialSmoother)
    samples: list[Sample] = field(default_factory=list)
    windows: list[RepWindow] = field(default_factory=list)


@dataclass(frozen=True)
class ArmRep:
    """One arm's counted rep, or two of them paired as a "both" rep."""

    side: Side | Literal["both"]
    start_seconds: float
    end_seconds: float
    issues: frozenset[str]  # never too_fast: that is checked on the final rep
    max_shoulder_degrees: float


def _torso(landmarks: Mapping[str, Landmark], width: int, height: int) -> Torso | None:
    """The torso line and lean, shared by both arms; None if not measurable."""
    if not is_frame_visible(landmarks, TORSO):
        return None
    try:
        shoulder_mid = midpoint(landmarks["left_shoulder"], landmarks["right_shoulder"])
        hip_mid = midpoint(landmarks["left_hip"], landmarks["right_hip"])
        lean = lean_from_vertical(shoulder_mid, hip_mid, width, height)
    except ValueError:  # Coincident joints: skip the frame.
        return None
    return Torso(shoulder_mid, hip_mid, lean)


def _measure(
    landmarks: Mapping[str, Landmark],
    side: Side,
    torso: Torso | None,
    width: int,
    height: int,
) -> tuple[float, float] | None:
    """The arm's shoulder and elbow angles; None if not measurable."""
    shoulder, elbow, wrist = f"{side}_shoulder", f"{side}_elbow", f"{side}_wrist"
    if torso is None or not is_frame_visible(landmarks, (elbow, wrist)):
        return None
    try:
        # abs(): the sign differs between the arms, and overhead reads -180 or 180.
        shoulder_angle = abs(
            signed_segment_angle(
                torso.shoulder_mid,
                torso.hip_mid,
                landmarks[shoulder],
                landmarks[elbow],
                width,
                height,
            )
        )
        elbow_angle = joint_angle(
            landmarks[shoulder], landmarks[elbow], landmarks[wrist], width, height
        )
    except ValueError:  # Coincident joints: skip the frame.
        return None
    return shoulder_angle, elbow_angle


def _update(
    arm: Arm, measured: tuple[float, float] | None, lean: float | None, time: float
) -> None:
    """Smooth one frame's arm angles and feed the arm's rep splitter."""
    if measured is None:
        shoulder, elbow = None, None
    else:
        shoulder, elbow = measured
    shoulder = arm.shoulder.update(shoulder, time)
    elbow = arm.elbow.update(elbow, time)
    if shoulder is not None and elbow is not None and lean is not None:
        arm.samples.append(Sample(time, shoulder, elbow, lean))
    if window := arm.splitter.update(shoulder, time):
        arm.windows.append(window)


def _arm_rep(arm: Arm, window: RepWindow) -> ArmRep:
    """Check the form rules over one arm's whole rep."""
    rep = samples_in_window(arm.samples, window)
    max_shoulder = max(sample.shoulder for sample in rep)
    min_elbow = min(
        sample.elbow for sample in rep if sample.shoulder >= ELBOW_CHECK_FROM_DEGREES
    )
    failed = {
        "torso_lean": max(sample.lean for sample in rep) > LEAN_LIMIT_DEGREES,
        "arm_not_high_enough": max_shoulder < HEIGHT_LIMIT_DEGREES,
        "elbow_bent": min_elbow < ELBOW_LIMIT_DEGREES,
    }
    return ArmRep(
        arm.side,
        window.start_seconds,
        window.end_seconds,
        frozenset(code for code, is_failed in failed.items() if is_failed),
        max_shoulder,
    )


def _observation(rep: ArmRep) -> RepObservation:
    """A finished rep; too_fast is checked here, on the rep's own start and end."""
    issues = rep.issues
    if rep.end_seconds - rep.start_seconds < MIN_REP_SECONDS:
        issues |= {"too_fast"}
    return RepObservation(
        rep.start_seconds,
        rep.end_seconds,
        tuple(code for code in ISSUES if code in issues),
        side=rep.side,
        metrics={"max_shoulder_angle_degrees": round(rep.max_shoulder_degrees, 1)},
    )


def _pair(reps: list[ArmRep]) -> list[RepObservation]:
    """Join reps of the two arms that start within PAIR_WITHIN_SECONDS of each other.

    In the order they started, each unpaired rep pairs with the next unpaired rep of
    the other arm, if that one starts in time. A rep with no partner keeps its side.
    """
    reps = sorted(reps, key=lambda rep: rep.start_seconds)
    taken: set[int] = set()
    observations = []
    for index, rep in enumerate(reps):
        if index in taken:
            continue
        # The next unpaired rep of the other arm, if there is one.
        partner_index = None
        for later in range(index + 1, len(reps)):
            if later not in taken and reps[later].side != rep.side:
                partner_index = later
                break

        if partner_index is not None:
            partner = reps[partner_index]
            starts_together = (
                partner.start_seconds - rep.start_seconds <= PAIR_WITHIN_SECONDS
            )
        else:
            starts_together = False

        if starts_together:
            taken.add(partner_index)
            rep = ArmRep(
                "both",
                rep.start_seconds,
                max(rep.end_seconds, partner.end_seconds),
                rep.issues | partner.issues,
                min(rep.max_shoulder_degrees, partner.max_shoulder_degrees),
            )
        observations.append(_observation(rep))
    return observations


def analyze(keypoints: Mapping[str, Any], analyzer_version: str) -> AnalysisResult:
    """Count arm lifts and check their form in keypoint data from app.keypoints."""
    width, height = keypoints["video"]["width"], keypoints["video"]["height"]
    arms = [Arm(side) for side in SIDES]
    lean_smoother = ExponentialSmoother()

    for frame in keypoints["frames"]:
        time = frame["time_seconds"]
        landmarks = frame_landmarks(frame)
        torso = _torso(landmarks, width, height)
        lean = lean_smoother.update(torso.lean if torso else None, time)
        for arm in arms:
            measured = _measure(landmarks, arm.side, torso, width, height)
            _update(arm, measured, lean, time)

    reps = [_arm_rep(arm, window) for arm in arms for window in arm.windows]
    return build_rep_result(_pair(reps), ISSUES, analyzer_version)
