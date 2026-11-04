"""The background analysis (app/jobs/analysis.py): a session ends complete or failed.

The AI service is the FakeAIService from conftest.py, except in the two tests that need
real network behavior (an AI service that is down, and one that never answers): those
use sockets on this computer.
"""

import logging
import socket
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import engine
from app.jobs import analysis
from app.jobs.analysis import analyze_session
from app.models import (
    Exercise,
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    SessionResult,
    SessionStatus,
    User,
)
from app.schemas.analysis_contract import ERROR_MESSAGES, AnalysisResult
from app.storage.blob import Storage

VIDEO = b"synthetic video bytes"  # the fake AI service never opens it


@pytest.fixture
def session_id(db: Session, storage: Storage) -> uuid.UUID:
    """A squat session as POST /sessions leaves it: processing, with a stored video."""
    patient = User(clerk_id="user_p", email="patient@example.com", role=Role.PATIENT)
    therapist = User(
        clerk_id="user_t", email="therapist@example.com", role=Role.THERAPIST
    )
    db.add_all([patient, therapist])
    db.flush()
    squat = db.scalars(select(Exercise).where(Exercise.name == "squat")).one()
    plan = Plan(therapist_id=therapist.id, patient_id=patient.id)
    target = PlanExercise(plan=plan, exercise=squat, reps=10, sets=3, times_per_week=3)
    new_id, key = uuid.uuid4(), f"sessions/{uuid.uuid4()}.mp4"
    db.add(
        ExerciseSession(
            id=new_id,
            plan_exercise=target,
            status=SessionStatus.PROCESSING,
            video_key=key,
        )
    )
    db.commit()
    storage.upload(key, VIDEO, "video/mp4")
    return new_id


def outcome(session_id: uuid.UUID) -> tuple[str, dict[str, Any] | None]:
    """The session's status and saved result, read fresh from the database."""
    with Session(engine) as fresh:
        status = fresh.get(ExerciseSession, session_id).status
        saved = fresh.get(SessionResult, session_id)
        return status, None if saved is None else saved.result


def assert_backend_failure(session_id: uuid.UUID, error_code: str) -> None:
    """The session failed with a result the backend recorded itself."""
    status, saved = outcome(session_id)
    expected = AnalysisResult.failed(error_code, analyzer_version=None)
    assert status == SessionStatus.FAILED
    assert saved == expected.model_dump(mode="json")
    # It meets the contract, with the patient message for its code.
    checked = AnalysisResult.model_validate(saved)
    assert checked.error_message == ERROR_MESSAGES[error_code]


def test_a_complete_result_is_saved_and_completes_the_session(
    session_id, ai_service
) -> None:
    analyze_session(session_id)

    [request] = ai_service.requests
    assert request["session_id"] == str(session_id)
    assert request["exercise"] == "squat"
    assert httpx.get(request["video_url"]).content == VIDEO  # a working read link
    assert outcome(session_id) == (SessionStatus.COMPLETE, ai_service.body)


def test_a_failed_result_from_the_ai_service_is_saved_as_it_is(
    session_id, ai_service
) -> None:
    ai_service.body = AnalysisResult.failed(
        "no_person", analyzer_version="0.2.0-stub"
    ).model_dump(mode="json")

    analyze_session(session_id)

    assert outcome(session_id) == (SessionStatus.FAILED, ai_service.body)


@pytest.mark.parametrize("status_code", [500, 503, 422, 404])
def test_an_error_status_fails_the_session_as_unavailable(
    session_id, ai_service, status_code
) -> None:
    ai_service.status_code = status_code
    ai_service.body = {"detail": "synthetic error"}

    analyze_session(session_id)

    assert_backend_failure(session_id, "analysis_unavailable")


@pytest.mark.parametrize(
    "body",
    [b"<html>Bad gateway</html>", b"[]", b'{"status": "complete"}'],
    ids=["not JSON", "not an object", "fields missing"],
)
def test_an_answer_that_is_not_a_result_fails_the_session_as_unavailable(
    session_id, ai_service, body
) -> None:
    ai_service.body = body

    analyze_session(session_id)

    assert_backend_failure(session_id, "analysis_unavailable")


@pytest.mark.parametrize(
    "change",
    [
        {"rep_count": 99},  # must equal the number of reps
        {"analyzer_version": None},  # a complete result needs one
        {"error_code": "no_person"},  # a complete result has no error
        {"form_score": 101},  # 0 to 100
    ],
    ids=["rep_count", "analyzer_version", "error_code", "form_score"],
)
def test_a_result_that_breaks_the_contract_fails_the_session_as_unavailable(
    session_id, ai_service, change
) -> None:
    ai_service.body = {**ai_service.body, **change}

    analyze_session(session_id)

    assert_backend_failure(session_id, "analysis_unavailable")


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("Connection refused"),
        httpx.ConnectTimeout("Timed out while connecting"),
        httpx.RemoteProtocolError("Server disconnected without sending a response"),
        httpx.ReadError("Connection reset by peer"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_a_failed_connection_fails_the_session_as_unavailable(
    session_id, ai_service, error
) -> None:
    ai_service.error = error

    analyze_session(session_id)

    assert_backend_failure(session_id, "analysis_unavailable")


def test_no_answer_in_time_fails_the_session_as_timed_out(
    session_id, ai_service
) -> None:
    ai_service.error = httpx.ReadTimeout("Timed out while waiting for the answer")

    analyze_session(session_id)

    assert_backend_failure(session_id, "analysis_timed_out")


@pytest.fixture
def refused_port() -> Iterator[int]:
    """A port on this computer that refuses connections: bound, but not listening."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        yield sock.getsockname()[1]


@pytest.fixture
def silent_port() -> Iterator[int]:
    """A port on this computer that accepts connections but never answers."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        yield sock.getsockname()[1]


def test_an_ai_service_that_is_down_fails_the_session_as_unavailable(
    session_id, refused_port, monkeypatch
) -> None:
    monkeypatch.setattr(analysis, "AI_SERVICE_URL", f"http://127.0.0.1:{refused_port}")

    analyze_session(session_id)

    assert_backend_failure(session_id, "analysis_unavailable")


def test_an_ai_service_that_never_answers_fails_the_session_as_timed_out(
    session_id, silent_port, monkeypatch
) -> None:
    monkeypatch.setattr(analysis, "AI_SERVICE_URL", f"http://127.0.0.1:{silent_port}")
    monkeypatch.setattr(analysis, "AI_SERVICE_TIMEOUT_SECONDS", 0.5)
    started = time.monotonic()

    analyze_session(session_id)

    # httpx's own default timeout is 5 seconds: AI_SERVICE_TIMEOUT_SECONDS applies.
    assert time.monotonic() - started < 4
    assert_backend_failure(session_id, "analysis_timed_out")


def test_a_finished_session_is_not_analyzed_again(session_id, ai_service) -> None:
    analyze_session(session_id)
    first = outcome(session_id)
    ai_service.body = AnalysisResult.failed(
        "no_person", analyzer_version="0.2.0-stub"
    ).model_dump(mode="json")

    analyze_session(session_id)  # for example, a task that ran twice

    assert len(ai_service.requests) == 1
    assert outcome(session_id) == first


def test_a_session_that_finished_during_the_call_keeps_its_result(
    session_id, ai_service, monkeypatch
) -> None:
    """For example, failed by the cleanup of stuck sessions (SCRUM-66) meanwhile."""
    timed_out = AnalysisResult.failed("analysis_timed_out", analyzer_version=None)
    answer = ai_service.handle

    def finish_first(request: httpx.Request) -> httpx.Response:
        with Session(engine) as other, other.begin():
            other.get(ExerciseSession, session_id).status = SessionStatus.FAILED
            other.add(
                SessionResult(
                    session_id=session_id, result=timed_out.model_dump(mode="json")
                )
            )
        return answer(request)

    monkeypatch.setattr(ai_service, "handle", finish_first)

    analyze_session(session_id)

    assert len(ai_service.requests) == 1
    assert outcome(session_id) == (
        SessionStatus.FAILED,
        timed_out.model_dump(mode="json"),
    )


def test_a_session_without_a_video_fails_without_calling_the_ai_service(
    session_id, ai_service
) -> None:
    # The database requires a key; an empty one is the only "missing" key it allows.
    with engine.begin() as connection:
        connection.execute(
            update(ExerciseSession)
            .where(ExerciseSession.id == session_id)
            .values(video_key="")
        )

    analyze_session(session_id)

    assert ai_service.requests == []
    assert_backend_failure(session_id, "analysis_unavailable")


def test_a_missing_session_is_skipped(db, ai_service) -> None:
    analyze_session(uuid.uuid4())  # no error

    assert ai_service.requests == []
    assert db.scalars(select(SessionResult)).all() == []


def test_an_unexpected_error_fails_the_session(
    session_id, ai_service, monkeypatch, caplog
) -> None:
    def broken_storage() -> Storage:
        raise RuntimeError("synthetic bug with private details")

    monkeypatch.setattr(analysis, "get_storage", broken_storage)

    analyze_session(session_id)  # no error

    assert ai_service.requests == []
    assert_backend_failure(session_id, "analysis_unavailable")
    assert "RuntimeError" in caplog.text
    assert "private details" not in caplog.text


def test_a_result_the_database_refuses_is_saved_as_a_failure(
    session_id, ai_service
) -> None:
    # Valid for the contract, but Postgres JSON can't hold the character \u0000.
    ai_service.body = {**ai_service.body, "feedback": ["Keep\u0000going"]}

    analyze_session(session_id)

    assert_backend_failure(session_id, "analysis_unavailable")


def test_logs_carry_only_the_session_id_and_the_outcome(
    session_id, ai_service, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    ai_service.status_code = 500

    analyze_session(session_id)

    assert str(session_id) in caplog.text
    assert "analysis_unavailable" in caplog.text
    assert ai_service.requests[0]["video_url"] not in caplog.text
    assert "sig=" not in caplog.text
    assert "patient@example.com" not in caplog.text
