"""A patient's sessions, each session's analysis result, and progress per exercise.

Read only. Patients and therapists use the same routes: a patient sees only their own
data, and a therapist only their linked patients' (can_see_patient). Anyone else gets
404, the same answer as for an id that doesn't exist, so it never tells whether a
patient or a session exists. Uploads, and the status the upload page polls, are in
sessions.py.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.current_user import CurrentUser
from app.auth.ownership import can_see_patient
from app.db import get_db
from app.models import (
    Exercise,
    ExerciseSession,
    Plan,
    PlanExercise,
    SessionResult,
    SessionStatus,
)
from app.schemas.analysis_contract import AnalysisResult
from app.schemas.results import (
    ExerciseProgress,
    ProgressPoint,
    SessionResultResponse,
    SessionSummary,
)

router = APIRouter(tags=["results"])
Database = Annotated[Session, Depends(get_db)]


def summary_fields(session: ExerciseSession, exercise: Exercise) -> dict[str, Any]:
    """The SessionSummary fields of a session. SessionResultResponse adds the result."""
    return {
        "id": session.id,
        "plan_exercise_id": session.plan_exercise_id,
        "exercise_name": exercise.name,
        "exercise_display_name": exercise.display_name,
        "status": session.status,
        "created_at": session.created_at,
    }


@router.get("/patients/{patient_id}/sessions")
def list_patient_sessions(
    patient_id: uuid.UUID, user: CurrentUser, db: Database
) -> list[SessionSummary]:
    """The patient's sessions from all their plans, newest first, without results."""
    if not can_see_patient(db, user, patient_id):
        raise HTTPException(404, "Patient not found")
    rows = db.execute(
        select(ExerciseSession, Exercise)
        .join(ExerciseSession.plan_exercise)
        .join(PlanExercise.plan)
        .join(PlanExercise.exercise)
        .where(Plan.patient_id == patient_id)
        # The id only keeps a fixed order for uploads made at the same instant.
        .order_by(ExerciseSession.created_at.desc(), ExerciseSession.id)
    )
    return [
        SessionSummary(**summary_fields(session, exercise))
        for session, exercise in rows
    ]


@router.get("/sessions/{session_id}/result")
def get_session_result(
    session_id: uuid.UUID, user: CurrentUser, db: Database
) -> SessionResultResponse:
    """One session with its analysis result, which is null while it is processing."""
    # The status and the result in one query, so they agree: the analysis job can
    # save the result and the new status between two queries. LEFT OUTER JOIN gives
    # None for the result while the session is processing.
    row = db.execute(
        select(ExerciseSession, Exercise, Plan.patient_id, SessionResult.result)
        .join(ExerciseSession.plan_exercise)
        .join(PlanExercise.plan)
        .join(PlanExercise.exercise)
        .outerjoin(ExerciseSession.result)
        .where(ExerciseSession.id == session_id)
    ).one_or_none()
    # Another patient's session, an unlinked therapist, or a former patient's
    # therapist: the same 404 as an unknown id, as GET /sessions/{session_id} answers.
    if row is None or not can_see_patient(db, user, row.patient_id):
        raise HTTPException(404, "Session not found")
    session, exercise, _, saved = row
    # Checked against the contract on the way out, as it was before it was saved.
    result = None if saved is None else AnalysisResult.model_validate(saved)
    return SessionResultResponse(**summary_fields(session, exercise), result=result)


@router.get("/patients/{patient_id}/progress")
def get_patient_progress(
    patient_id: uuid.UUID, user: CurrentUser, db: Database
) -> list[ExerciseProgress]:
    """For each exercise, the patient's complete sessions, oldest first.

    Only complete sessions have numbers to chart, so failed and processing ones are
    left out, and so is an exercise without a complete session. Sessions of the same
    exercise in different plans are one list: it is the patient's progress.
    """
    if not can_see_patient(db, user, patient_id):
        raise HTTPException(404, "Patient not found")
    rows = db.execute(
        select(
            ExerciseSession.id,
            ExerciseSession.created_at,
            Exercise,
            SessionResult.result,
        )
        .join(ExerciseSession.plan_exercise)
        .join(PlanExercise.plan)
        .join(PlanExercise.exercise)
        .join(ExerciseSession.result)
        .where(
            Plan.patient_id == patient_id,
            ExerciseSession.status == SessionStatus.COMPLETE,
        )
        .order_by(Exercise.name, ExerciseSession.created_at, ExerciseSession.id)
    )
    progress: dict[uuid.UUID, ExerciseProgress] = {}  # by exercise id, in name order
    for session_id, created_at, exercise, saved in rows:
        result = AnalysisResult.model_validate(saved)
        if exercise.id not in progress:
            progress[exercise.id] = ExerciseProgress(
                exercise_name=exercise.name,
                exercise_display_name=exercise.display_name,
                exercise_kind=exercise.kind,
                sessions=[],
            )
        progress[exercise.id].sessions.append(
            ProgressPoint(
                session_id=session_id,
                created_at=created_at,
                form_score=result.form_score,
                rep_count=result.rep_count,
                hold_seconds=result.hold_seconds,
                analyzer_version=result.analyzer_version,
            )
        )
    return list(progress.values())
