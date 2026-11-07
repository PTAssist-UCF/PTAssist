"""Patient uploads and session status, scoped through the owning plan.

A stored upload is handed to the background analysis (app/jobs/analysis.py).
"""

import contextlib
import logging
import uuid
from typing import Annotated

from azure.core.exceptions import AzureError
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.current_user import CurrentUser
from app.db import get_db
from app.jobs.analysis import analyze_session
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
    background_tasks: BackgroundTasks,
) -> SessionResponse:
    plan_exercise_id = target.id
    # End the transaction the sign-in and ownership checks opened, so its database
    # connection goes back to the pool. Checking the video (up to 15 seconds of
    # ffprobe) and storing it (up to MAX_VIDEO_UPLOAD_BYTES) can take minutes, and a
    # few slow uploads holding connections that long would use up the pool. The checks
    # only read, and get_current_user has already committed a new user's row.
    db.rollback()
    info = validate_video(video)
    session_id = uuid.uuid4()
    key = f"sessions/{session_id}{info.extension}"
    try:
        storage.upload(key, video.file, info.content_type)
        # The session row only once the video is stored, in a short transaction.
        session = ExerciseSession(
            id=session_id,
            plan_exercise_id=plan_exercise_id,
            status=SessionStatus.PROCESSING,
            video_key=key,
        )
        db.add(session)
        db.flush()
        response = SessionResponse.model_validate(session)
        db.commit()
    except (AzureError, SQLAlchemyError, OSError):
        db.rollback()
        # No orphan blob: delete the video, even a partly uploaded one. No orphan row
        # either: the row is committed only after the upload succeeded.
        try:
            storage.delete(key)
        except (AzureError, OSError):
            # Only a generated session UUID is logged. Cleanup failure must
            # not replace the original response or expose a video URL.
            logger.warning("Upload cleanup failed for session %s", session_id)
        raise HTTPException(
            503, "Could not save the video. Please try again."
        ) from None
    # FastAPI closes the upload only after background tasks finish. Close it now, so
    # its temporary file (up to MAX_VIDEO_UPLOAD_BYTES) is not kept on disk during
    # the analysis, which can take minutes. An error here must not stop the analysis:
    # the session is committed, and an exception would cancel the background task.
    with contextlib.suppress(OSError):
        video.file.close()
    # Runs after the response is sent; the job opens its own database session.
    background_tasks.add_task(analyze_session, session_id)
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
