"""The cleanup of sessions stuck in processing (SCRUM-66).

A session stays processing when its background analysis (app/jobs/analysis.py) could
not save anything: the database could not be reached, or the API stopped during the
analysis (a deploy, scaling in, a crash). The cleanup saves such a session as failed
with analysis_timed_out, as the analysis does when the AI service doesn't answer in
time, so the page polling the session stops waiting.

A session is stuck once it has been processing for longer than
STUCK_SESSION_CUTOFF_SECONDS, counted from its upload (created_at) by the database's
clock. That is longer than the analysis can wait for the AI service (app/config.py),
so the cleanup never fails a session the analysis is still waiting on.

It runs when the API starts, for every stuck session (app/main.py), and when a status
is read, for the sessions about to be shown (app/routes/sessions.py and results.py).

A session's result is saved once, so the cleanup follows the analysis's rule: it locks
the session's row and fails it only while it is still processing. An answer from the AI
service that arrives after that is dropped by the analysis.
"""

import logging
import uuid
from collections.abc import Collection
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import STUCK_SESSION_CUTOFF_SECONDS
from app.db import engine
from app.models import ExerciseSession, SessionResult, SessionStatus
from app.schemas.analysis_contract import AnalysisResult

logger = logging.getLogger(__name__)


def fail_stuck_sessions(
    db: Session, session_ids: Collection[uuid.UUID] | None = None
) -> list[uuid.UUID]:
    """Save the stuck sessions among session_ids (all of them if None) as failed with
    analysis_timed_out, and commit. Returns the ids of the sessions it failed."""
    query = (
        select(ExerciseSession)
        .where(
            ExerciseSession.status == SessionStatus.PROCESSING,
            # The database's clock, the one that set created_at.
            ExerciseSession.created_at
            < func.now() - timedelta(seconds=STUCK_SESSION_CUTOFF_SECONDS),
        )
        # Lock the rows, as the analysis does before it saves a result. A row someone
        # has locked already is being finished right now, by the analysis or by another
        # cleanup: skip it instead of waiting. So the cleanup never waits for the
        # analysis (or the other way round), and never replaces the result it saves.
        .with_for_update(skip_locked=True)
        # Fresh values from the locked rows, also for sessions this database session
        # has loaded already.
        .execution_options(populate_existing=True)
    )
    if session_ids is not None:
        query = query.where(ExerciseSession.id.in_(session_ids))
    stuck = db.scalars(query).all()
    if not stuck:
        return []
    timed_out = AnalysisResult.failed("analysis_timed_out", analyzer_version=None)
    for session in stuck:
        session.status = SessionStatus.FAILED
        result = timed_out.model_dump(mode="json")
        db.add(SessionResult(session_id=session.id, result=result))
    failed = [session.id for session in stuck]
    db.commit()
    for session_id in failed:
        # Only the session id: log lines never carry personal data.
        logger.warning(
            "Session %s failed with analysis_timed_out: stuck in processing",
            session_id,
        )
    return failed


def fail_stuck_sessions_at_startup() -> None:
    """Fail every stuck session, when the API starts. Never raises.

    Sessions left processing by an API that stopped have no analysis running for them
    any more. Those past the cutoff are failed here, the others when their status is
    read after they pass it. If this fails (the database can't be reached, say), the
    API still starts, and status reads fail stuck sessions later.
    """
    try:
        with Session(engine) as db:
            fail_stuck_sessions(db)
    except Exception as exc:
        # Only the exception's type: its message could hold query details.
        logger.error(
            "The cleanup of stuck sessions at start-up failed (%s)",
            type(exc).__name__,
        )
