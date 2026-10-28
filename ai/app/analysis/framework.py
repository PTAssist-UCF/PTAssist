"""Shared rep splitting, scoring, and feedback for exercise analyzers.

Exercise analyzers supply measurements and issue codes. This module does not read
video or know exercise-specific thresholds.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from app.analysis_contract import AnalysisResult, Issue, RepResult

NO_REPS_FEEDBACK = (
    "We didn't see a full rep or hold. "
    "Keep your whole body in the frame and finish each one."
)
GOOD_FORM_FEEDBACK = "Great form. Keep it up."


@dataclass(frozen=True)
class IssueDefinition:
    message: str
    tip: str
    penalty: int

    def __post_init__(self) -> None:
        if not self.message or not self.tip or self.penalty < 0:
            raise ValueError("issues need a message, a tip, and a nonnegative penalty")


@dataclass(frozen=True)
class RepObservation:
    start_seconds: float
    end_seconds: float
    issues: tuple[str, ...] = ()
    side: Literal["left", "right", "both"] | None = None
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class HoldObservation(RepObservation):
    # Required: a forgotten value would otherwise score the hold 0.
    good_form_seconds: float = field(kw_only=True)


@dataclass(frozen=True)
class RepWindow:
    start_seconds: float
    end_seconds: float


class RepSplitter:
    """Count complete threshold crossings, with a tracking-gap reset.

    `direction="lower"` is for measurements such as a knee angle that falls
    during a rep; `"higher"` is for measurements that rise. A return to the
    rest threshold before the count threshold discards a partial movement.
    """

    def __init__(
        self,
        start_threshold: float,
        count_threshold: float,
        rest_threshold: float,
        direction: Literal["lower", "higher"],
        max_gap_seconds: float = 0.75,
    ) -> None:
        if direction not in ("lower", "higher"):
            raise ValueError("direction must be lower or higher")
        values = (start_threshold, count_threshold, rest_threshold, max_gap_seconds)
        if not all(math.isfinite(value) for value in values) or max_gap_seconds <= 0:
            raise ValueError("thresholds must be finite and gap must be positive")
        # Negate a rising measurement so one set of comparisons serves both directions.
        self._sign = 1 if direction == "lower" else -1
        self._start = self._sign * start_threshold
        self._count = self._sign * count_threshold
        self._rest = self._sign * rest_threshold
        if not self._count <= self._start < self._rest:
            order = (
                "count <= start < rest"
                if direction == "lower"
                else "count >= start > rest"
            )
            raise ValueError(f"{direction} thresholds must be {order}")
        self.max_gap_seconds = max_gap_seconds
        self.reset()

    def reset(self) -> None:
        """Forget the current movement and wait for the start position."""
        self._last_time: float | None = None
        self._last_valid_time: float | None = None
        self._wait_for_rest()

    def _wait_for_rest(self) -> None:
        self._ready = False
        self._start_seconds: float | None = None
        self._reached_count = False

    def update(self, value: float | None, time_seconds: float) -> RepWindow | None:
        """Consume one frame and return a window only when a full rep finishes."""
        if not math.isfinite(time_seconds) or time_seconds < 0:
            raise ValueError("time_seconds must be finite and nonnegative")
        if self._last_time is not None and time_seconds <= self._last_time:
            raise ValueError("time_seconds must increase")
        if value is not None and not math.isfinite(value):
            raise ValueError("value must be finite or None")
        self._last_time = time_seconds
        if value is None:
            return None
        if (
            self._last_valid_time is not None
            and time_seconds - self._last_valid_time > self.max_gap_seconds
        ):
            self._wait_for_rest()
        self._last_valid_time = time_seconds

        value *= self._sign
        if value >= self._rest:
            window = None
            if self._start_seconds is not None and self._reached_count:
                window = RepWindow(self._start_seconds, time_seconds)
            self._wait_for_rest()
            self._ready = True
            return window
        if self._ready and self._start_seconds is None and value <= self._start:
            self._start_seconds = time_seconds
        if self._start_seconds is not None and value <= self._count:
            self._reached_count = True
        return None


def _round_score(value: float) -> int:
    return math.floor(value + 0.5)


def _validate_observations(observations: list[RepObservation]) -> None:
    last_start = -1.0
    for observation in observations:
        if (
            not math.isfinite(observation.start_seconds)
            or not math.isfinite(observation.end_seconds)
            or observation.start_seconds < 0
            or observation.end_seconds <= observation.start_seconds
            or observation.start_seconds < last_start
        ):
            raise ValueError("observations need ordered, positive-duration times")
        if len(set(observation.issues)) != len(observation.issues):
            raise ValueError("an issue may appear only once per rep or hold")
        last_start = observation.start_seconds


def _feedback(
    observations: list[RepObservation], definitions: dict[str, IssueDefinition]
) -> list[str]:
    if not observations:
        return [NO_REPS_FEEDBACK]
    frequency = Counter(code for obs in observations for code in obs.issues)
    if not frequency:
        return [GOOD_FORM_FEEDBACK]
    ranked = sorted(
        frequency,
        key=lambda code: (-frequency[code] * definitions[code].penalty, code),
    )
    return [definitions[code].tip for code in ranked[:3]]


def _issues(
    codes: tuple[str, ...], definitions: dict[str, IssueDefinition]
) -> list[Issue]:
    return [Issue(code=code, message=definitions[code].message) for code in codes]


def build_rep_result(
    observations: list[RepObservation],
    definitions: dict[str, IssueDefinition],
    analyzer_version: str,
) -> AnalysisResult:
    """Build a complete result for an exercise counted in reps."""
    _validate_observations(observations)
    reps = []
    for index, observation in enumerate(observations, start=1):
        penalty = sum(definitions[code].penalty for code in observation.issues)
        reps.append(
            RepResult(
                index=index,
                start_seconds=observation.start_seconds,
                end_seconds=observation.end_seconds,
                side=observation.side,
                score=max(0, 100 - penalty),
                issues=_issues(observation.issues, definitions),
                metrics=observation.metrics,
            )
        )
    form_score = (
        _round_score(sum(rep.score for rep in reps) / len(reps)) if reps else None
    )
    return AnalysisResult(
        status="complete",
        rep_count=len(reps),
        hold_seconds=None,
        form_score=form_score,
        reps=reps,
        feedback=_feedback(observations, definitions),
        error_code=None,
        error_message=None,
        analyzer_version=analyzer_version,
    )


def build_hold_result(
    observations: list[HoldObservation],
    definitions: dict[str, IssueDefinition],
    analyzer_version: str,
) -> AnalysisResult:
    """Build a time-weighted result for an exercise held in position."""
    _validate_observations(observations)
    reps = []
    total_good = 0.0
    total_duration = 0.0
    for index, observation in enumerate(observations, start=1):
        duration = observation.end_seconds - observation.start_seconds
        if (
            not math.isfinite(observation.good_form_seconds)
            or not 0 <= observation.good_form_seconds <= duration + 1e-9
        ):
            raise ValueError("good form time must be within the hold")
        good_seconds = min(observation.good_form_seconds, duration)
        total_good += good_seconds
        total_duration += duration
        reps.append(
            RepResult(
                index=index,
                start_seconds=observation.start_seconds,
                end_seconds=observation.end_seconds,
                side=observation.side,
                score=_round_score(100 * good_seconds / duration),
                issues=_issues(observation.issues, definitions),
                metrics={
                    **observation.metrics,
                    "good_form_seconds": round(good_seconds, 1),
                },
            )
        )
    return AnalysisResult(
        status="complete",
        rep_count=None,
        hold_seconds=max(
            (rep.end_seconds - rep.start_seconds for rep in reps), default=0.0
        ),
        form_score=_round_score(100 * total_good / total_duration) if reps else None,
        reps=reps,
        feedback=_feedback(observations, definitions),
        error_code=None,
        error_message=None,
        analyzer_version=analyzer_version,
    )
