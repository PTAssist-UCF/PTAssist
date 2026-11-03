"""The sessions and session_results tables: uploaded videos and their analysis.

The model class is ExerciseSession, not Session, because routes also use SQLAlchemy's
Session (the database connection), and two classes named Session would clash.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.plan import PlanExercise


class SessionStatus(StrEnum):
    PROCESSING = "processing"  # uploaded, waiting for the analysis
    COMPLETE = "complete"  # analyzed: the result has the reps and scores
    FAILED = "failed"  # not analyzed: the result has the reason


class ExerciseSession(Base):
    """One uploaded video, which is one set of one exercise in a plan.

    The frontend polls status. Once it is complete or failed, the session has a
    SessionResult with the details, including the failure reason.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'complete', 'failed')", name="status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The plan exercise this video is for. Through it, the plan's patient owns the
    # session. A plan exercise that has sessions can't be deleted, so results are kept.
    plan_exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan_exercises.id"))
    status: Mapped[str] = mapped_column(String(20))
    # When the video was uploaded, which is also when processing started.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    plan_exercise: Mapped[PlanExercise] = relationship()
    # None while processing.
    result: Mapped["SessionResult | None"] = relationship(back_populates="session")


class SessionResult(Base):
    """The analysis result of a finished session, complete or failed.

    session_id is the primary key, so a session has at most one result. The result is
    saved once and never changed (see Session lifecycle in backend/README.md).
    """

    __tablename__ = "session_results"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    # The whole AnalysisResult as JSON (app/schemas/analysis_contract.py), checked with
    # AnalysisResult.model_validate before saving. No separate columns: Postgres can
    # read fields inside it, for example result->>'form_score'.
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[ExerciseSession] = relationship(back_populates="result")
