"""Patient uploads and session status, scoped through the owning plan."""

import logging
import uuid
from typing import Annotated

from azure.core.exceptions import AzureError
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.current_user import CurrentUser
from app.db import get_db
from app.models import (
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    SessionStatus,
    TherapistPatient,
)
from app.schemas.session import SessionResponse
from app.storage.blob import Storage, get_storage
from app.uploads import validate_video

router = APIRouter(tags=["sessions"])
logger = logging.getLogger(__name__)
Database = Annotated[Session, Depends(get_db)]


def get_owned_plan_exercise(
    plan_exercise_id: Annotated[uuid.UUID, Form()], user: CurrentUser, db: Database
) -> PlanExercise:
    """Authorize before resolving storage or inspecting video contents."""
    if user.role != Role.PATIENT:
        raise HTTPException(403, "Only patients can upload exercise videos")
    target = db.scalar(
        select(PlanExercise)
        .join(Plan)
        .where(PlanExercise.id == plan_exercise_id, Plan.patient_id == user.id)
    )
    if target is None:
        raise HTTPException(404, "Plan exercise not found")
    return target


@router.post("/sessions", status_code=201, response_model=SessionResponse)
def create_session(
    target: Annotated[PlanExercise, Depends(get_owned_plan_exercise)],
    # Keep the binary marker explicit for OpenAPI consumers such as Orval.
    video: Annotated[UploadFile, File(json_schema_extra={"format": "binary"})],
    db: Database,
    storage: Annotated[Storage, Depends(get_storage)],
) -> SessionResponse:
    info = validate_video(video)
    session_id = uuid.uuid4()
    key = f"sessions/{session_id}{info.extension}"
    session = ExerciseSession(
        id=session_id,
        plan_exercise_id=target.id,
        status=SessionStatus.PROCESSING,
        video_key=key,
    )
    upload_started = False
    try:
        db.add(session)
        db.flush()
        response = SessionResponse.model_validate(session)
        upload_started = True
        storage.upload(key, video.file, info.content_type)
        db.commit()
    except (AzureError, SQLAlchemyError, OSError):
        db.rollback()
        if upload_started:
            try:
                storage.delete(key)
            except (AzureError, OSError):
                # Only a generated session UUID is logged. Cleanup failure must
                # not replace the original response or expose a video URL.
                logger.warning("Upload cleanup failed for session %s", session_id)
        raise HTTPException(
            503, "Could not save the video. Please try again."
        ) from None
    # SCRUM-45 adds the background analysis handoff. This task leaves it processing.
    return response


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: uuid.UUID, user: CurrentUser, db: Database
) -> SessionResponse:
    query = (
        select(ExerciseSession)
        .join(PlanExercise)
        .join(Plan)
        .where(ExerciseSession.id == session_id)
    )
    if user.role == Role.PATIENT:
        query = query.where(Plan.patient_id == user.id)
    elif user.role == Role.THERAPIST:
        linked_patients = select(TherapistPatient.patient_id).where(
            TherapistPatient.therapist_id == user.id
        )
        query = query.where(Plan.patient_id.in_(linked_patients))
    else:
        raise HTTPException(403, "Unsupported user role")
    session = db.scalar(query)
    if session is None:
        raise HTTPException(404, "Session not found")
    return SessionResponse.model_validate(session)
