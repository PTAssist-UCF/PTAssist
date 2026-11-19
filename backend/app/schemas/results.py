"""Response models for a patient's sessions, a session's result, and their progress.

A result is the AnalysisResult of the analysis contract (analysis_contract.py), so the
frontend's generated types match what the AI service and the backend agree on.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import ExerciseKind, SessionStatus
from app.schemas.analysis_contract import AnalysisResult


class SessionSummary(BaseModel):
    """One session (one uploaded video, one set) in a patient's list, without its
    result. id, plan_exercise_id, status, and created_at are as in SessionResponse."""

    id: uuid.UUID
    plan_exercise_id: uuid.UUID
    exercise_name: str  # the exercise's name in the API, such as "squat"
    exercise_display_name: str  # what people see, such as "Squat"
    status: SessionStatus
    created_at: datetime  # when the video was uploaded


class SessionResultResponse(SessionSummary):
    """One session with its analysis result."""

    # The whole saved result (docs/analysis-result.md), complete or failed. A failed
    # one has the reason in error_code and error_message. None while the session is
    # processing: the result and the final status are saved together.
    result: AnalysisResult | None


class ProgressPoint(BaseModel):
    """One complete session of an exercise: a point on the progress chart.

    The numbers are copied from the session's result. Exactly one of rep_count (for
    exercises done in reps) and hold_seconds (for holds) is set. form_score is null
    when no rep or hold was seen, which is not a score of 0.
    """

    session_id: uuid.UUID
    created_at: datetime  # when the video was uploaded: the chart's time axis
    form_score: int | None
    rep_count: int | None
    hold_seconds: float | None
    # Always set for a complete result. Scores from different versions may not be
    # comparable, so a chart can mark where it changes (docs/analysis-result.md).
    analyzer_version: str


class ExerciseProgress(BaseModel):
    """One exercise's complete sessions, oldest first, from all the patient's plans."""

    exercise_name: str
    exercise_display_name: str
    # "reps": chart rep_count. "hold" (the plank): chart hold_seconds.
    exercise_kind: ExerciseKind
    sessions: list[ProgressPoint]
