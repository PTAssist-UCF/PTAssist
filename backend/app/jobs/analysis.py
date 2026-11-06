"""Background analysis: send an uploaded video to the AI service and save the outcome.

POST /sessions schedules analyze_session(session_id) as a FastAPI background task, which
runs after the upload response is sent (Session lifecycle in backend/README.md):

1. Load the session's video key and exercise name.
2. Make a short-lived read link to the video (app/storage/), and send it with the
   session id and exercise name to the AI service's POST /analyze.
3. Check the answer against the analysis contract, then save it as the session's
   SessionResult and set the session's status to complete or failed, together.

Every outcome is saved. Without a valid answer (the AI service can't be reached, answers
with an error, sends something that doesn't match the contract, or doesn't answer within
AI_SERVICE_TIMEOUT_SECONDS), the backend saves a failed result itself, so the AI service
can never leave a session processing. Only a database that can't be reached at all stops
the job from saving; the cleanup of sessions stuck in processing (SCRUM-66) covers that.

A session's result is saved once: an answer for a session that is no longer processing
is dropped.

The read link is a secret and results are health data, so log lines carry only the
session id and the outcome, never an exception's message or the AI service's answer.
"""

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import AI_SERVICE_TIMEOUT_SECONDS, AI_SERVICE_URL
from app.db import engine
from app.models import (
    Exercise,
    ExerciseSession,
    PlanExercise,
    SessionResult,
    SessionStatus,
)
from app.schemas.analysis_contract import AnalysisResult, AnalyzeRequest, ErrorCode
from app.storage.blob import get_storage

logger = logging.getLogger(__name__)

# Seconds to wait for a connection to the AI service. In Azure the connection goes to
# the Container Apps ingress, which accepts it at once, even while the AI container
# starts from zero. Only the answer can take long (AI_SERVICE_TIMEOUT_SECONDS).
CONNECT_TIMEOUT_SECONDS = 10


def ai_service_client() -> httpx.Client:
    """An HTTP client for the AI service. Tests replace it with a fake AI service."""
    return httpx.Client(
        base_url=AI_SERVICE_URL,
        timeout=httpx.Timeout(
            AI_SERVICE_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS
        ),
    )


def analyze_session(session_id: uuid.UUID) -> None:
    """Analyze one uploaded video and save the outcome. Never raises."""
    try:
        result = _analyze(session_id)
    except Exception as exc:
        # A bug must not leave the session processing. Log only the exception's type:
        # its message could hold the read link or part of the AI service's answer.
        logger.error(
            "Analysis of session %s crashed (%s)", session_id, type(exc).__name__
        )
        result = AnalysisResult.failed("analysis_unavailable", analyzer_version=None)
    if result is not None:
        _save(session_id, result)


def _analyze(session_id: uuid.UUID) -> AnalysisResult | None:
    """The result to save for the session, or None if there is nothing to analyze."""
    # A short read: the connection goes back to the pool before the long call below.
    with Session(engine) as db:
        row = db.execute(
            select(ExerciseSession.status, ExerciseSession.video_key, Exercise.name)
            .join(ExerciseSession.plan_exercise)
            .join(PlanExercise.exercise)
            .where(ExerciseSession.id == session_id)
        ).one_or_none()
    if row is None:
        logger.warning("Analysis of session %s skipped: no such session", session_id)
        return None
    status, video_key, exercise = row
    if status != SessionStatus.PROCESSING:
        logger.info("Analysis of session %s skipped: already %s", session_id, status)
        return None
    # The database requires a key, but an empty one can't be read either.
    if not video_key:
        return _backend_failure(session_id, "analysis_unavailable", "no stored video")
    request = AnalyzeRequest(
        session_id=session_id,
        exercise=exercise,
        # Valid for 15 minutes, longer than the call can last. Never log it.
        video_url=get_storage().read_url(video_key),
    )
    return _call_ai_service(request)


def _call_ai_service(request: AnalyzeRequest) -> AnalysisResult:
    """Call POST /analyze. Any answer that is not a valid result becomes a failure."""
    session_id = request.session_id
    try:
        with ai_service_client() as client:
            response = client.post("/analyze", json=request.model_dump(mode="json"))
    except httpx.ConnectTimeout:  # a timeout, but it never reached the AI service
        return _backend_failure(session_id, "analysis_unavailable", "no connection")
    except httpx.TimeoutException:
        return _backend_failure(session_id, "analysis_timed_out", "no answer in time")
    except httpx.HTTPError:  # refused, or the connection broke
        return _backend_failure(session_id, "analysis_unavailable", "no connection")
    if response.status_code != 200:
        return _backend_failure(
            session_id, "analysis_unavailable", f"HTTP {response.status_code}"
        )
    try:
        return AnalysisResult.model_validate(response.json())
    except ValueError:  # not JSON, or not a valid result (ValidationError included)
        return _backend_failure(
            session_id, "analysis_unavailable", "answer does not match the contract"
        )


def _backend_failure(
    session_id: uuid.UUID, error_code: ErrorCode, reason: str
) -> AnalysisResult:
    """A failure the backend records itself, with the standard patient message."""
    logger.warning(
        "Analysis of session %s failed with %s: %s", session_id, error_code, reason
    )
    return AnalysisResult.failed(error_code, analyzer_version=None)


def _save(session_id: uuid.UUID, result: AnalysisResult) -> None:
    """Save the result, or a failure in its place if the database refuses it."""
    if _store(session_id, result):
        return
    # The database may refuse something in the AI service's answer (Postgres JSON
    # can't hold the character \u0000, for example), so save a failure instead, which
    # still ends the session. If the database is down, this fails too, and the cleanup
    # of sessions stuck in processing (SCRUM-66) fails the session later.
    fallback = AnalysisResult.failed("analysis_unavailable", analyzer_version=None)
    if result != fallback:
        _store(session_id, fallback)


def _store(session_id: uuid.UUID, result: AnalysisResult) -> bool:
    """Save the result and the new status in one transaction. False if that failed."""
    try:
        with Session(engine) as db, db.begin():
            # Lock the session's row, so nothing else can finish it at the same time.
            session = db.scalar(
                select(ExerciseSession)
                .where(ExerciseSession.id == session_id)
                .with_for_update()
            )
            if session is None or session.status != SessionStatus.PROCESSING:
                # Finished meanwhile (or deleted). Its result is saved once: drop this.
                logger.info(
                    "Analysis of session %s dropped: already finished", session_id
                )
                return True
            session.status = SessionStatus(result.status)
            db.add(
                SessionResult(
                    session_id=session_id, result=result.model_dump(mode="json")
                )
            )
    except Exception as exc:
        logger.error(
            "Saving the analysis of session %s failed (%s)",
            session_id,
            type(exc).__name__,
        )
        return False
    outcome = f"failed with {result.error_code}" if result.error_code else "complete"
    logger.info("Analysis of session %s saved: %s", session_id, outcome)
    return True
