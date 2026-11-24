"""The shoulder abduction analyzer, following docs/exercises/shoulder-abduction.md.

Front view: each arm is measured and counted on its own, then reps of the two arms
that start together become one "both" rep. It reads landmarks, never video.

The numbers are in shoulder_abduction.json next to this file. They are starting
values from the spec, not clinical targets. The issue wording and penalties are
`ISSUES` below.
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Literal, NamedTuple

from app.analysis.framework import (
    IssueDefinition,
    RepObservation,
    RepSplitter,
    RepWindow,
    build_rep_result,
    samples_in_window,
)
from app.analysis.geometry import (
    joint_angle,
    lean_from_vertical,
    midpoint,
    signed_segment_angle,
)
from app.analysis.landmarks import Landmark, frame_landmarks
from app.analysis.smoothing import ExponentialSmoother
from app.analysis.visibility import is_frame_visible
from app.analysis_contract import AnalysisResult

CONFIG_PATH = Path(__file__).with_name("shoulder_abduction.json")

Side = Literal["left", "right"]
SIDES: tuple[Side, Side] = ("left", "right")
TORSO = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")

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


@dataclass(frozen=True)
class Config:
    """Every threshold. Defaults are the spec's; shoulder_abduction.json overrides them.

    Angles are in degrees. The shoulder angle is between the torso and the upper arm.
    """

    min_landmark_confidence: float = 0.65
    frame_margin: float = 0.025
    smoothing_tau_seconds: float = 0.12
    max_missing_seconds: float = 0.75
    # A rep starts above start, counts once above count, and ends back below rest.
    rest_shoulder_angle: float = 25.0
    start_shoulder_angle: float = 35.0
    count_shoulder_angle: float = 60.0
    # arm_not_high_enough: the rep's highest shoulder angle is below this.
    shoulder_height_angle: float = 80.0
    # elbow_bent: the elbow angle is below bent_elbow_angle while the shoulder angle
    # is at least elbow_check_from_shoulder_angle.
    elbow_check_from_shoulder_angle: float = 55.0
    bent_elbow_angle: float = 150.0
    # torso_lean: the torso leans more than this from vertical.
    excessive_torso_lean_degrees: float = 18.0
    # too_fast: the rep took less than this.
    min_rep_seconds: float = 2.0
    # Reps of the two arms that start this close together are one "both" rep.
    pair_within_seconds: float = 1.0

    def __post_init__(self) -> None:
        numbers = [getattr(self, f.name) for f in fields(self)]
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("every setting must be a finite number")
        if not (
            self.rest_shoulder_angle
            < self.start_shoulder_angle
            <= self.count_shoulder_angle
        ):
            raise ValueError("shoulder angles must satisfy rest < start <= count")


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read shoulder_abduction.json. Raises ValueError that names the file and key."""
    try:
        return Config(**json.loads(path.read_text("utf-8")))
    except (TypeError, ValueError) as error:  # unknown key, bad JSON, bad number
        raise ValueError(f"{path.name}: {error}") from error


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


@dataclass
class Arm:
    """Everything tracked for one arm. Each angle has its own smoother."""

    side: Side
    splitter: RepSplitter
    shoulder: ExponentialSmoother
    elbow: ExponentialSmoother
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


def _new_arm(side: Side, config: Config) -> Arm:
    """A fresh arm whose splitter and smoothers use the config's numbers."""
    splitter = RepSplitter(
        config.start_shoulder_angle,
        config.count_shoulder_angle,
        config.rest_shoulder_angle,
        "higher",
        config.max_missing_seconds,
    )
    shoulder = ExponentialSmoother(
        config.smoothing_tau_seconds, config.max_missing_seconds
    )
    elbow = ExponentialSmoother(
        config.smoothing_tau_seconds, config.max_missing_seconds
    )
    return Arm(side, splitter, shoulder, elbow)


def _is_visible(
    landmarks: Mapping[str, Landmark], joints: tuple[str, ...], config: Config
) -> bool:
    return is_frame_visible(
        landmarks,
        joints,
        min_confidence=config.min_landmark_confidence,
        frame_margin=config.frame_margin,
    )


def _torso(
    landmarks: Mapping[str, Landmark], width: int, height: int, config: Config
) -> Torso | None:
    """The torso line and lean, shared by both arms; None if not measurable."""
    if not _is_visible(landmarks, TORSO, config):
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
    config: Config,
) -> tuple[float, float] | None:
    """The arm's shoulder and elbow angles; None if not measurable."""
    shoulder, elbow, wrist = f"{side}_shoulder", f"{side}_elbow", f"{side}_wrist"
    if torso is None or not _is_visible(landmarks, (elbow, wrist), config):
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


def _arm_rep(arm: Arm, window: RepWindow, config: Config) -> ArmRep:
    """Check the form rules over one arm's whole rep."""
    rep = samples_in_window(arm.samples, window)
    max_shoulder = max(sample.shoulder for sample in rep)
    min_elbow = min(
        sample.elbow
        for sample in rep
        if sample.shoulder >= config.elbow_check_from_shoulder_angle
    )
    max_lean = max(sample.lean for sample in rep)
    failed = {
        "torso_lean": max_lean > config.excessive_torso_lean_degrees,
        "arm_not_high_enough": max_shoulder < config.shoulder_height_angle,
        "elbow_bent": min_elbow < config.bent_elbow_angle,
    }
    return ArmRep(
        arm.side,
        window.start_seconds,
        window.end_seconds,
        frozenset(code for code, is_failed in failed.items() if is_failed),
        max_shoulder,
    )


def _observation(rep: ArmRep, config: Config) -> RepObservation:
    """A finished rep; too_fast is checked here, on the rep's own start and end."""
    issues = rep.issues
    if rep.end_seconds - rep.start_seconds < config.min_rep_seconds:
        issues |= {"too_fast"}
    return RepObservation(
        rep.start_seconds,
        rep.end_seconds,
        tuple(code for code in ISSUES if code in issues),
        side=rep.side,
        metrics={"max_shoulder_angle_degrees": round(rep.max_shoulder_degrees, 1)},
    )


def _pair(reps: list[ArmRep], config: Config) -> list[RepObservation]:
    """Join reps of the two arms that start within pair_within_seconds of each other.

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
                partner.start_seconds - rep.start_seconds <= config.pair_within_seconds
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
        observations.append(_observation(rep, config))
    return observations


def analyze_shoulder_abduction(
    keypoints: Mapping[str, Any], analyzer_version: str, config: Config | None = None
) -> AnalysisResult:
    """Count arm lifts and check their form in a whole keypoint JSON (ai/README.md).

    Without a config, the numbers come from shoulder_abduction.json.
    """
    config = config or load_config()
    width, height = keypoints["video"]["width"], keypoints["video"]["height"]
    arms = [_new_arm(side, config) for side in SIDES]
    lean_smoother = ExponentialSmoother(
        config.smoothing_tau_seconds, config.max_missing_seconds
    )

    for frame in keypoints["frames"]:
        time = frame["time_seconds"]
        landmarks = frame_landmarks(frame)
        torso = _torso(landmarks, width, height, config)
        lean = lean_smoother.update(torso.lean if torso else None, time)
        for arm in arms:
            measured = _measure(landmarks, arm.side, torso, width, height, config)
            _update(arm, measured, lean, time)

    reps = [_arm_rep(arm, window, config) for arm in arms for window in arm.windows]
    return build_rep_result(_pair(reps, config), ISSUES, analyzer_version)
