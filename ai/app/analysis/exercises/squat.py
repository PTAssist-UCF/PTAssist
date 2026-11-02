"""The squat analyzer: a state machine ported from the AI team's prototype.

It follows `ptassist_squat/analysis.py` on the `Jonathan-AI-Test` branch (same states,
guards, and messages), using the shared helpers in app/analysis/. It reads landmarks,
never video. Feed `SquatAnalyzer.update` one frame at a time: each call returns a
`FrameResult` whose `feedback` is a running message, as in the prototype. After a clip,
`result` builds the usual AnalysisResult from `RepObservation`s.

The numbers are in squat.json next to this file. The issue wording and penalties are
`ISSUES` below. Spec: docs/exercises/squat.md.
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.analysis.framework import IssueDefinition, RepObservation, build_rep_result
from app.analysis.geometry import joint_angle, lean_from_vertical
from app.analysis.landmarks import Landmark
from app.analysis.smoothing import ExponentialSmoother
from app.analysis_contract import AnalysisResult

CONFIG_PATH = Path(__file__).with_name("squat.json")

# The joints the near side must show. Like the prototype, this includes heel and toe.
REQUIRED = ("shoulder", "hip", "knee", "ankle", "heel", "foot_index")

ISSUES = {
    "leaning_forward": IssueDefinition(
        "Your chest leaned far forward.", "Keep your chest up as you squat.", 30
    ),
    "not_deep_enough": IssueDefinition(
        "Your squat was not very deep.",
        "Sit your hips lower, as far as feels comfortable.",
        10,
    ),
    "too_fast": IssueDefinition(
        "This rep took less than 2 seconds.",
        "Slow down: take at least 2 seconds for each rep.",
        10,
    ),
}


class State(StrEnum):
    STANDING = "STANDING"
    DESCENDING = "DESCENDING"
    BOTTOM = "BOTTOM"
    ASCENDING = "ASCENDING"


@dataclass(frozen=True)
class Config:
    """Every threshold. Defaults are the prototype's; squat.json overrides them."""

    min_landmark_confidence: float = 0.65
    frame_margin: float = 0.025
    max_side_width_to_torso: float = 0.75
    min_opposite_ankle_confidence: float = 0.65
    min_opposite_foot_confidence: float = 0.6
    max_ankle_separation_to_torso: float = 0.6
    side_switch_advantage: float = 0.12
    smoothing_tau_seconds: float = 0.12
    max_missing_seconds: float = 0.75
    standing_knee_angle: float = 165.0
    start_descending_knee_angle: float = 155.0
    bottom_entry_knee_angle: float = 145.0
    ascent_from_bottom_degrees: float = 6.0
    depth_knee_angle: float = 110.0
    excessive_torso_lean_degrees: float = 45.0
    max_rep_duration_seconds: float = 12.0
    min_rep_seconds: float = 2.0
    # Added for live feedback: full reps in a set, and how long a rep message stays.
    reps_per_set: int = 5
    message_hold_seconds: float = 2.0

    def __post_init__(self) -> None:
        numbers = [getattr(self, f.name) for f in fields(self)]
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("every setting must be a finite number")
        if not (
            self.bottom_entry_knee_angle
            <= self.start_descending_knee_angle
            < self.standing_knee_angle
        ):
            raise ValueError(
                "knee angles must satisfy bottom_entry <= start_descending < standing"
            )
        if self.reps_per_set < 1:
            raise ValueError("reps_per_set must be at least 1")


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read squat.json. Raises ValueError that names the file and the bad key."""
    try:
        return Config(**json.loads(path.read_text("utf-8")))
    except (TypeError, ValueError) as error:  # unknown key, bad JSON, bad number
        raise ValueError(f"{path.name}: {error}") from error


@dataclass
class Angles:
    knee: float
    torso: float


@dataclass
class FrameResult:
    state: str
    rep_count: int  # full reps counted, over the whole clip
    partial_count: int  # partial reps (not counted)
    sets_completed: int
    reps_in_set: int  # full reps in the current set
    side: str | None
    reliability: float
    angles: Angles | None
    feedback: str  # the running message to show right now
    assessment_valid: bool
    form_warning: bool = False


class SquatAnalyzer:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        self.reset()

    def reset(self) -> None:
        """Start over for a new clip."""
        config = self.config
        self.state = State.STANDING
        self.ready = False
        self.side: str | None = None
        self.last_valid_time: float | None = None
        self.attempt: dict[str, float] | None = None
        self.observations: list[RepObservation] = []
        self.partial_count = 0
        self.sets_completed = 0
        self.reps_in_set = 0
        self._smoothers = {
            name: ExponentialSmoother(
                config.smoothing_tau_seconds, config.max_missing_seconds
            )
            for name in ("knee", "torso")
        }
        self.smoothed: Angles | None = None
        self._notice: tuple[str, float] | None = None  # (text, show until)

    @property
    def rep_count(self) -> int:
        return len(self.observations)

    def result(self, analyzer_version: str) -> AnalysisResult:
        """The shared result for a finished clip: reps, form score, and feedback."""
        return build_rep_result(self.observations, ISSUES, analyzer_version)

    def _clear_attempt(self) -> None:
        self.state = State.STANDING
        self.ready = False
        self.attempt = None
        self.smoothed = None
        for smoother in self._smoothers.values():
            smoother.reset()

    def _side_score(self, landmarks: Mapping[str, Landmark], side: str) -> float:
        points = [landmarks.get(f"{side}_{part}") for part in REQUIRED]
        if any(p is None for p in points):
            return 0.0
        confidences = [p.confidence for p in points if p is not None]
        return min(confidences) * 0.7 + sum(confidences) / len(confidences) * 0.3

    def _choose_side(self, landmarks: Mapping[str, Landmark]) -> tuple[str, float]:
        scores = {side: self._side_score(landmarks, side) for side in ("left", "right")}
        candidate = max(scores, key=lambda side: scores[side])
        if (
            self.side
            and scores[self.side] + self.config.side_switch_advantage
            >= scores[candidate]
        ):
            candidate = self.side
        self.side = candidate
        points = [landmarks.get(f"{candidate}_{part}") for part in REQUIRED]
        reliability = (
            min(p.confidence for p in points if p is not None) if all(points) else 0.0
        )
        return candidate, reliability

    def _in_frame(self, point: Landmark) -> bool:
        margin = self.config.frame_margin
        return margin <= point.x <= 1 - margin and margin <= point.y <= 1 - margin

    def _result(
        self,
        side: str | None,
        reliability: float,
        feedback: str,
        timestamp: float,
        valid: bool = False,
        form_warning: bool = False,
    ) -> FrameResult:
        if valid and self._notice and timestamp < self._notice[1]:
            feedback = self._notice[0]
        return FrameResult(
            self.state.value,
            self.rep_count,
            self.partial_count,
            self.sets_completed,
            self.reps_in_set,
            side,
            reliability,
            self.smoothed if valid else None,
            feedback,
            valid,
            form_warning,
        )

    def _lost_tracking(self, timestamp: float) -> None:
        gap_limit = self.config.max_missing_seconds
        if (
            self.last_valid_time is not None
            and timestamp - self.last_valid_time > gap_limit
        ):
            self._clear_attempt()

    def update(
        self,
        landmarks: Mapping[str, Landmark] | None,
        timestamp: float,
        width: int,
        height: int,
    ) -> FrameResult:
        """Consume one frame (None when no person was found) and return its message."""
        config = self.config
        side, reliability = self._choose_side(landmarks) if landmarks else (None, 0.0)
        if (
            landmarks is None
            or side is None
            or reliability < config.min_landmark_confidence
        ):
            self._lost_tracking(timestamp)
            return self._result(
                side, reliability, "Unable to reliably assess", timestamp
            )

        nose = landmarks.get("nose")
        if nose is None or nose.confidence < config.min_landmark_confidence:
            return self._result(
                side,
                min(reliability, nose.confidence if nose else 0.0),
                "Unable to reliably assess",
                timestamp,
            )
        reliability = min(reliability, nose.confidence)
        shoulder, hip, knee, ankle, heel, foot = (
            landmarks[f"{side}_{part}"] for part in REQUIRED
        )
        if not all(self._in_frame(p) for p in (shoulder, hip, knee, ankle, heel, foot)):
            self._lost_tracking(timestamp)
            return self._result(
                side, reliability, "Move back so your full body is visible", timestamp
            )
        if not self._in_frame(nose):
            return self._result(
                side, reliability, "Move back so your full body is visible", timestamp
            )

        torso_length = math.hypot(
            (shoulder.x - hip.x) * width, (shoulder.y - hip.y) * height
        )
        if torso_length < 15:
            return self._result(
                side, reliability, "Unable to reliably assess", timestamp
            )

        # Guard: tell a side-view squat from a lunge, using the far leg's feet.
        opposite = "right" if side == "left" else "left"
        other_ankle = landmarks.get(f"{opposite}_ankle")
        other_heel = landmarks.get(f"{opposite}_heel")
        other_foot = landmarks.get(f"{opposite}_foot_index")
        ankle_reliable = (
            other_ankle is not None
            and other_ankle.confidence >= config.min_opposite_ankle_confidence
            and self._in_frame(other_ankle)
        )
        foot_reliable = (
            other_heel is not None
            and other_foot is not None
            and other_heel.confidence >= config.min_opposite_foot_confidence
            and other_foot.confidence >= config.min_opposite_foot_confidence
            and self._in_frame(other_heel)
            and self._in_frame(other_foot)
        )
        if not ankle_reliable and not foot_reliable:
            if any(
                p is not None
                and p.confidence >= config.min_opposite_foot_confidence
                and not self._in_frame(p)
                for p in (other_ankle, other_heel, other_foot)
            ):
                return self._result(
                    side, reliability, "Move back so both feet are visible", timestamp
                )
            return self._result(
                side,
                reliability,
                "Unable to reliably distinguish squat from lunge",
                timestamp,
            )
        stance_candidates = []
        if ankle_reliable and other_ankle is not None:
            stance_candidates.append(
                abs(ankle.x - other_ankle.x) * width / torso_length
            )
        if foot_reliable and other_heel is not None and other_foot is not None:
            stance_candidates.append(abs(heel.x - other_heel.x) * width / torso_length)
            stance_candidates.append(abs(foot.x - other_foot.x) * width / torso_length)
        if max(stance_candidates) > config.max_ankle_separation_to_torso:
            self._clear_attempt()
            return self._result(
                side,
                reliability,
                "Feet are too far apart for a side-view squat",
                timestamp,
            )

        # Guard: the body must be side-on to the camera.
        pairs = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
        if all(
            name in landmarks
            and landmarks[name].confidence >= config.min_landmark_confidence
            for name in pairs
        ):
            shoulder_width = (
                abs(landmarks["left_shoulder"].x - landmarks["right_shoulder"].x)
                * width
            )
            hip_width = abs(landmarks["left_hip"].x - landmarks["right_hip"].x) * width
            if (
                max(shoulder_width, hip_width) / torso_length
                > config.max_side_width_to_torso
            ):
                return self._result(
                    side, reliability, "Turn sideways to the camera", timestamp
                )

        try:
            raw_knee = joint_angle(hip, knee, ankle, width, height)
            raw_torso = lean_from_vertical(shoulder, hip, width, height)
        except ValueError:
            return self._result(
                side, reliability, "Unable to reliably assess", timestamp
            )

        self._lost_tracking(timestamp)
        knee_angle = self._smoothers["knee"].update(raw_knee, timestamp)
        torso_lean = self._smoothers["torso"].update(raw_torso, timestamp)
        assert knee_angle is not None and torso_lean is not None
        self.smoothed = angles = Angles(knee_angle, torso_lean)
        self.last_valid_time = timestamp

        self._advance_state(angles, timestamp)

        shallow_after_bottom = (
            self.state in (State.BOTTOM, State.ASCENDING)
            and self.attempt is not None
            and self.attempt["minimum_knee_angle"] > config.depth_knee_angle
        )
        lean_warning = angles.torso >= config.excessive_torso_lean_degrees
        form_warning = lean_warning or shallow_after_bottom
        if lean_warning:
            feedback = "Keep your torso more upright"
        elif self.state == State.ASCENDING:
            feedback = "Return to standing"
        elif (
            self.state == State.BOTTOM
            and self.attempt
            and self.attempt["minimum_knee_angle"] <= config.depth_knee_angle
        ):
            feedback = "Good depth"
        elif self.state in (State.DESCENDING, State.BOTTOM):
            feedback = "Go lower"
        else:
            feedback = "Ready for squat" if self.ready else "Stand upright to start"
        return self._result(side, reliability, feedback, timestamp, True, form_warning)

    def _advance_state(self, angles: Angles, timestamp: float) -> None:
        config = self.config
        if self.state == State.STANDING:
            if angles.knee >= config.standing_knee_angle:
                self.ready = True
            if self.ready and angles.knee <= config.start_descending_knee_angle:
                self.state = State.DESCENDING
                self.attempt = {
                    "start_time": timestamp,
                    "minimum_knee_angle": angles.knee,
                    "maximum_torso_lean": angles.torso,
                }
            return
        if self.attempt is None:
            return
        attempt = self.attempt
        attempt["minimum_knee_angle"] = min(attempt["minimum_knee_angle"], angles.knee)
        attempt["maximum_torso_lean"] = max(attempt["maximum_torso_lean"], angles.torso)
        if timestamp - attempt["start_time"] > config.max_rep_duration_seconds:
            self._clear_attempt()
        elif self.state == State.DESCENDING:
            if angles.knee <= config.bottom_entry_knee_angle:
                self.state = State.BOTTOM
            elif angles.knee >= config.standing_knee_angle:
                self._partial_rep(attempt, timestamp)
        elif self.state == State.BOTTOM:
            if (
                angles.knee
                >= attempt["minimum_knee_angle"] + config.ascent_from_bottom_degrees
            ):
                self.state = State.ASCENDING
        elif self.state == State.ASCENDING:
            if angles.knee >= config.standing_knee_angle:
                self._full_rep(attempt, timestamp)
            elif angles.knee <= attempt["minimum_knee_angle"] + 2:
                self.state = State.BOTTOM

    def _show(self, text: str, timestamp: float) -> None:
        self._notice = (text, timestamp + self.config.message_hold_seconds)

    def _partial_rep(self, attempt: dict[str, float], timestamp: float) -> None:
        """Back to standing without reaching the bottom: not a rep."""
        self.partial_count += 1
        self.state = State.STANDING
        self.attempt = None
        self.ready = True
        self._show(
            "Partial rep, not counted: it didn't fit the rule. Your knees bent to "
            f"{attempt['minimum_knee_angle']:.0f}° and need to reach "
            f"{self.config.bottom_entry_knee_angle:.0f}° or less. Squat lower.",
            timestamp,
        )

    def _full_rep(self, attempt: dict[str, float], timestamp: float) -> None:
        config = self.config
        start = attempt["start_time"]
        lowest = attempt["minimum_knee_angle"]
        lean = attempt["maximum_torso_lean"]
        issues = tuple(
            code
            for code, broken in (
                ("leaning_forward", lean >= config.excessive_torso_lean_degrees),
                ("not_deep_enough", lowest > config.depth_knee_angle),
                ("too_fast", timestamp - start < config.min_rep_seconds),
            )
            if broken
        )
        self.observations.append(
            RepObservation(
                start,
                timestamp,
                issues=issues,
                metrics={
                    "min_knee_angle_degrees": round(lowest, 1),
                    "max_torso_lean_degrees": round(lean, 1),
                },
            )
        )
        self.state = State.STANDING
        self.attempt = None
        self.ready = True
        self.reps_in_set += 1
        text = f"Full rep! Rep {self.reps_in_set} of {config.reps_per_set} done."
        if self.reps_in_set >= config.reps_per_set:
            self.sets_completed += 1
            text = (
                f"Full rep! Set {self.sets_completed} complete: "
                f"{config.reps_per_set} full reps done."
            )
            self.reps_in_set = 0
        if issues:
            text += " " + " ".join(ISSUES[code].message for code in issues)
        self._show(text, timestamp)


def analyze_squat(
    keypoints: Mapping[str, Any], config: Config | None = None
) -> SquatAnalyzer:
    """Run a whole keypoint JSON (format in ai/README.md); call `.result(version)`."""
    analyzer = SquatAnalyzer(config)
    width, height = keypoints["video"]["width"], keypoints["video"]["height"]
    for frame in keypoints["frames"]:
        pose = frame["landmarks"]
        landmarks = (
            None
            if pose is None
            else {name: Landmark(*values) for name, values in pose.items()}
        )
        analyzer.update(landmarks, frame["time_seconds"], width, height)
    return analyzer
