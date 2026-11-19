"""The cleanup of sessions stuck in processing (app/jobs/stuck_sessions.py, SCRUM-66).

A session still processing STUCK_SESSION_CUTOFF_SECONDS after its upload is saved as
failed with analysis_timed_out: when its status is read, and when the API starts.
Sessions are saved straight to the database, uploaded in the past by the database's own
clock, so no test waits for the cutoff.
"""

import json
import logging
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import engine
from app.jobs import stuck_sessions
from app.jobs.analysis import analyze_session
from app.jobs.stuck_sessions import fail_stuck_sessions
from app.main import app
from app.models import (
    Exercise,
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    SessionResult,
    SessionStatus,
    TherapistPatient,
    User,
)
from app.schemas.analysis_contract import AnalysisResult

EXAMPLES = Path(__file__).parents[2] / "docs" / "analysis-result-examples"
CUTOFF = stuck_sessions.STUCK_SESSION_CUTOFF_SECONDS
# How many seconds ago a session was uploaded: a minute past the cutoff (stuck), or a
# minute before it, when the analysis may still be waiting for the AI service.
STUCK = CUTOFF + 60
RECENT = CUTOFF - 60
# What the cleanup saves.
TIMED_OUT = AnalysisResult.failed(
    "analysis_timed_out", analyzer_version=None
).model_dump(mode="json")

# The routes that show a session's status.
ROUTES = {
    "status": "/sessions/{session_id}",
    "result": "/sessions/{session_id}/result",
    "list": "/patients/{patient_id}/sessions",
}


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def users(db: Session) -> dict[str, User]:
    """Two patients and two therapists. ther is linked to pat, and other_ther only to
    other_pat. A user's Clerk id is user_<name>."""
    users = {
        name: User(clerk_id=f"user_{name}", email=f"{name}@example.com", role=role)
        for name, role in [
            ("pat", Role.PATIENT),
            ("other_pat", Role.PATIENT),
            ("ther", Role.THERAPIST),
            ("other_ther", Role.THERAPIST),
        ]
    }
    db.add_all(users.values())
    db.flush()
    for therapist, patient in [("ther", "pat"), ("other_ther", "other_pat")]:
        db.add(
            TherapistPatient(
                therapist_id=users[therapist].id, patient_id=users[patient].id
            )
        )
    db.commit()
    return users


@pytest.fixture
def squats(db: Session, users: dict[str, User]) -> dict[str, PlanExercise]:
    """A squat in pat's plan, and one in other_pat's, by the patient's name."""
    squat = db.query(Exercise).filter_by(name="squat").one()
    targets = {}
    for therapist, patient in [("ther", "pat"), ("other_ther", "other_pat")]:
        plan = Plan(therapist_id=users[therapist].id, patient_id=users[patient].id)
        targets[patient] = PlanExercise(
            plan=plan, exercise=squat, reps=10, sets=3, times_per_week=3
        )
    db.add_all(targets.values())
    db.commit()
    return targets


def add_session(
    db: Session,
    target: PlanExercise,
    seconds_ago: float,
    result: dict[str, Any] | None = None,
) -> uuid.UUID:
    """A session uploaded that many seconds ago, by the database's clock: still
    processing, or finished with that result (complete or failed, as it says)."""
    session = ExerciseSession(
        plan_exercise=target,
        status=SessionStatus.PROCESSING if result is None else result["status"],
        video_key=f"sessions/{uuid.uuid4()}.mp4",
        created_at=func.now() - timedelta(seconds=seconds_ago),
    )
    if result is not None:
        session.result = SessionResult(result=result)
    db.add(session)
    db.commit()
    return session.id


def move_upload_back(session_id: uuid.UUID, seconds_ago: float) -> None:
    """Make the session's upload that many seconds ago, as time passing would."""
    with engine.begin() as connection:
        connection.execute(
            update(ExerciseSession)
            .where(ExerciseSession.id == session_id)
            .values(created_at=func.now() - timedelta(seconds=seconds_ago))
        )


def outcome(session_id: uuid.UUID) -> tuple[str, dict[str, Any] | None]:
    """The session's status and saved result, read fresh from the database."""
    with Session(engine) as fresh:
        status = fresh.get(ExerciseSession, session_id).status
        saved = fresh.get(SessionResult, session_id)
        return status, None if saved is None else saved.result


def read(client, clerk, user: str, route: str, patient: User, session_id):
    """GET one of ROUTES as user_<user>, about this patient's session."""
    path = ROUTES[route].format(patient_id=patient.id, session_id=session_id)
    return client.get(path, headers=clerk.headers(f"user_{user}"))


def status_shown(route: str, body: Any, session_id: uuid.UUID) -> str:
    """The session's status in a route's answer."""
    if route == "list":
        [status] = [item["status"] for item in body if item["id"] == str(session_id)]
        return status
    return body["status"]


# Status reads


@pytest.mark.parametrize("user", ["pat", "ther"])
@pytest.mark.parametrize("route", ROUTES)
def test_a_stuck_session_becomes_failed_when_its_status_is_read(
    client, clerk, db, users, squats, route, user
) -> None:
    """The ticket's "done when". The patient's and their linked therapist's reads both
    save the backend's analysis_timed_out result, and answer with the new status."""
    session_id = add_session(db, squats["pat"], STUCK)

    response = read(client, clerk, user, route, users["pat"], session_id)

    assert response.status_code == 200
    assert status_shown(route, response.json(), session_id) == "failed"
    if route == "result":
        assert response.json()["result"] == TIMED_OUT
    assert outcome(session_id) == (SessionStatus.FAILED, TIMED_OUT)


@pytest.mark.parametrize("route", ROUTES)
def test_a_session_within_the_cutoff_stays_processing(
    client, clerk, db, users, squats, route
) -> None:
    """The analysis may still be waiting for the AI service, so it is left alone."""
    session_id = add_session(db, squats["pat"], RECENT)

    response = read(client, clerk, "pat", route, users["pat"], session_id)

    assert response.status_code == 200
    assert status_shown(route, response.json(), session_id) == "processing"
    if route == "result":
        assert response.json()["result"] is None
    assert outcome(session_id) == (SessionStatus.PROCESSING, None)


def test_the_list_fails_only_its_stuck_sessions(
    client, clerk, db, users, squats
) -> None:
    """Finished sessions keep their results however old they are, a recent one stays
    processing, and another patient's stuck session is not in the list, so it waits
    for a read of its own."""
    complete = add_session(db, squats["pat"], STUCK + 120, example("squat"))
    failed = add_session(db, squats["pat"], STUCK + 60, example("failed-no-person"))
    stuck = add_session(db, squats["pat"], STUCK)
    recent = add_session(db, squats["pat"], RECENT)
    theirs = add_session(db, squats["other_pat"], STUCK)

    response = read(client, clerk, "pat", "list", users["pat"], None)

    assert [(item["id"], item["status"]) for item in response.json()] == [
        (str(recent), "processing"),
        (str(stuck), "failed"),
        (str(failed), "failed"),
        (str(complete), "complete"),
    ]
    assert outcome(stuck) == (SessionStatus.FAILED, TIMED_OUT)
    assert outcome(failed) == (SessionStatus.FAILED, example("failed-no-person"))
    assert outcome(complete) == (SessionStatus.COMPLETE, example("squat"))
    assert outcome(recent) == (SessionStatus.PROCESSING, None)
    assert outcome(theirs) == (SessionStatus.PROCESSING, None)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("user", ["other_pat", "other_ther"])
def test_a_read_by_another_patient_or_an_unlinked_therapist_changes_nothing(
    client, clerk, db, users, squats, route, user
) -> None:
    """Wrong owner: the usual 404, and the session stays as it was. Only a read that
    may show the session fails it."""
    session_id = add_session(db, squats["pat"], STUCK)

    response = read(client, clerk, user, route, users["pat"], session_id)

    assert response.status_code == 404
    assert outcome(session_id) == (SessionStatus.PROCESSING, None)


@pytest.mark.parametrize("route", ROUTES)
def test_a_read_in_the_wrong_role_changes_nothing(
    client, clerk, db, users, squats, route
) -> None:
    """Wrong role: a patient made a therapist keeps their sessions (promote_therapist
    --force), but no longer sees them, so their reads fail nothing either."""
    session_id = add_session(db, squats["pat"], STUCK)
    users["pat"].role = Role.THERAPIST
    db.commit()

    response = read(client, clerk, "pat", route, users["pat"], session_id)

    assert response.status_code == 404
    assert outcome(session_id) == (SessionStatus.PROCESSING, None)


def test_logs_carry_only_the_session_id_and_the_outcome(
    client, clerk, db, users, squats, caplog
) -> None:
    session_id = add_session(db, squats["pat"], STUCK)

    read(client, clerk, "pat", "status", users["pat"], session_id)

    assert f"Session {session_id} failed with analysis_timed_out" in caplog.text
    assert "pat@example.com" not in caplog.text


# Start-up


def test_stuck_sessions_fail_when_the_api_starts(db, users, squats) -> None:
    """Every patient's, before the API takes a request. The others stay as they are."""
    stuck = add_session(db, squats["pat"], STUCK)
    theirs = add_session(db, squats["other_pat"], STUCK)
    recent = add_session(db, squats["pat"], RECENT)
    complete = add_session(db, squats["pat"], STUCK, example("squat"))

    with TestClient(app):  # runs the API's start-up
        assert outcome(stuck) == (SessionStatus.FAILED, TIMED_OUT)
        assert outcome(theirs) == (SessionStatus.FAILED, TIMED_OUT)
        assert outcome(recent) == (SessionStatus.PROCESSING, None)
        assert outcome(complete) == (SessionStatus.COMPLETE, example("squat"))


def test_the_api_starts_even_if_the_cleanup_fails(monkeypatch, caplog) -> None:
    """For example when the database can't be reached: status reads fail stuck
    sessions later. The log has the error's type, not its message."""

    def unreachable(db: Session, session_ids: Any = None) -> list[uuid.UUID]:
        raise SQLAlchemyError("synthetic database failure with private details")

    monkeypatch.setattr(stuck_sessions, "fail_stuck_sessions", unreachable)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert "SQLAlchemyError" in caplog.text
    assert "private details" not in caplog.text


# The background analysis


def test_an_answer_that_arrives_after_the_cleanup_is_dropped(
    client, clerk, db, users, squats, storage, ai_service, monkeypatch, caplog
) -> None:
    """While the analysis waits for the AI service, the session passes the cutoff and
    the page's next poll fails it. The complete result that arrives after that is
    dropped: the session keeps its analysis_timed_out result, and nothing crashes."""
    caplog.set_level(logging.INFO)
    session_id = add_session(db, squats["pat"], RECENT)
    answer = ai_service.handle
    polled = []

    def answer_late(request):
        move_upload_back(session_id, STUCK)
        polled.append(
            client.get(f"/sessions/{session_id}", headers=clerk.headers("user_pat"))
        )
        return answer(request)

    monkeypatch.setattr(ai_service, "handle", answer_late)

    analyze_session(session_id)

    assert [response.json()["status"] for response in polled] == ["failed"]
    assert len(ai_service.requests) == 1
    assert outcome(session_id) == (SessionStatus.FAILED, TIMED_OUT)
    assert f"Analysis of session {session_id} dropped" in caplog.text


def test_an_analysis_that_starts_after_the_cleanup_skips_the_session(
    db, users, squats, storage, ai_service
) -> None:
    """For example one that waited for a free worker thread on a busy API."""
    session_id = add_session(db, squats["pat"], STUCK)
    with Session(engine) as cleanup:
        assert fail_stuck_sessions(cleanup) == [session_id]

    analyze_session(session_id)

    assert ai_service.requests == []
    assert outcome(session_id) == (SessionStatus.FAILED, TIMED_OUT)


def test_a_session_the_analysis_is_saving_is_left_to_it(
    db, users, squats, storage, ai_service
) -> None:
    """The cleanup runs at the moment the analysis saves its result, after the
    analysis locked the session's row. The cleanup skips the session instead of
    waiting for the lock, and the analysis saves its result."""
    session_id = add_session(db, squats["pat"], STUCK)
    skipped = []

    def cleanup_runs_now(conn, cursor, statement, parameters, context, executemany):
        # The analysis's own lock, not the cleanup's (SKIP LOCKED).
        if skipped or "FOR UPDATE" not in statement or "SKIP LOCKED" in statement:
            return
        skipped.append(None)  # first, so the cleanup's own queries return above
        with Session(engine) as cleanup:
            # Without SKIP LOCKED the cleanup would wait for the analysis, which waits
            # for this function: fail after 2 seconds instead of hanging.
            cleanup.execute(text("SET LOCAL lock_timeout = '2s'"))
            skipped[0] = fail_stuck_sessions(cleanup, [session_id])

    event.listen(engine, "after_cursor_execute", cleanup_runs_now)
    try:
        analyze_session(session_id)
    finally:
        event.remove(engine, "after_cursor_execute", cleanup_runs_now)

    assert skipped == [[]]  # the cleanup ran, and failed nothing
    assert outcome(session_id) == (SessionStatus.COMPLETE, ai_service.body)
