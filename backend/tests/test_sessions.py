"""Uploads use synthetic clips, real ffprobe, PostgreSQL, and private Azurite."""

import logging
import subprocess
import uuid
from functools import cache

import httpx
import pytest
from azure.core.exceptions import AzureError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import uploads
from app.db import engine
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
from app.schemas.analysis_contract import (
    ERROR_MESSAGES,
    MAX_VIDEO_SECONDS,
    MIN_VIDEO_SECONDS,
    AnalysisResult,
)


@pytest.fixture(scope="session")
def make_video(tmp_path_factory):
    directory = tmp_path_factory.mktemp("synthetic-videos")

    @cache
    def make(extension=".mp4", seconds=MIN_VIDEO_SECONDS):
        path = directory / f"{seconds}{extension}"
        codec = "libvpx-vp9" if extension == ".webm" else "libx264"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=16x16:r=10",
                "-t",
                str(seconds),
                "-an",
                "-c:v",
                codec,
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return path.read_bytes()

    return make


@pytest.fixture
def assignment(db):
    therapist = User(
        clerk_id="user_t", email="therapist@example.com", role=Role.THERAPIST
    )
    patient = User(clerk_id="user_p", email="patient@example.com", role=Role.PATIENT)
    other = User(clerk_id="user_other", email="other@example.com", role=Role.PATIENT)
    outsider = User(
        clerk_id="user_outsider", email="outsider@example.com", role=Role.THERAPIST
    )
    db.add_all([therapist, patient, other, outsider])
    db.flush()
    db.add(TherapistPatient(therapist_id=therapist.id, patient_id=patient.id))
    plan = Plan(therapist_id=therapist.id, patient_id=patient.id)
    squat = db.scalar(select(Exercise).where(Exercise.name == "squat"))
    target = PlanExercise(plan=plan, exercise=squat, reps=10, sets=3, times_per_week=3)
    db.add(target)
    db.commit()
    return target


def post_video(
    client,
    clerk,
    target,
    contents,
    filename="exercise.mp4",
    mime="video/mp4",
    user="user_p",
):
    return client.post(
        "/sessions",
        data={"plan_exercise_id": str(target.id)},
        files={"video": (filename, contents, mime)},
        headers=clerk.headers(user),
    )


def sessions_count(db):
    return db.scalar(select(func.count()).select_from(ExerciseSession))


@pytest.mark.parametrize(
    "extension,mime",
    [(".mp4", "video/mp4"), (".mov", "video/quicktime"), (".webm", "video/webm")],
)
def test_upload_stores_private_video_and_creates_processing_session(
    client, clerk, assignment, db, storage, make_video, extension, mime
):
    contents = make_video(extension)
    response = post_video(
        client, clerk, assignment, contents, "exercise" + extension, mime
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert set(result) == {"id", "plan_exercise_id", "status", "created_at"}
    assert result["status"] == "processing"
    assert result["plan_exercise_id"] == str(assignment.id)
    assert result["created_at"]
    saved = db.get(ExerciseSession, uuid.UUID(result["id"]))
    assert saved.video_key == f"sessions/{saved.id}{extension}"
    link = storage.read_url(saved.video_key)
    stored = httpx.get(link)
    assert stored.status_code == 200
    assert stored.content == contents
    assert stored.headers["content-type"] == mime
    assert httpx.get(link.split("?", 1)[0]).status_code == 403
    status = client.get("/sessions/" + result["id"], headers=clerk.headers("user_p"))
    assert status.status_code == 200
    # The background analysis has run by now (the fake AI service answered).
    assert status.json() == {**result, "status": "complete"}


def test_client_content_type_is_not_used_for_the_stored_blob(
    client, clerk, assignment, storage, db, make_video
):
    response = post_video(
        client, clerk, assignment, make_video(), mime="application/octet-stream"
    )
    assert response.status_code == 201
    saved = db.get(ExerciseSession, uuid.UUID(response.json()["id"]))
    assert (
        httpx.get(storage.read_url(saved.video_key)).headers["content-type"]
        == "video/mp4"
    )


@pytest.mark.parametrize("seconds", [MIN_VIDEO_SECONDS, MAX_VIDEO_SECONDS])
def test_duration_boundaries_are_accepted(
    client, clerk, assignment, make_video, seconds
):
    response = post_video(client, clerk, assignment, make_video(seconds=seconds))
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "seconds,error",
    [(MIN_VIDEO_SECONDS - 0.1, "too_short"), (MAX_VIDEO_SECONDS + 0.1, "too_long")],
)
def test_duration_outside_contract_is_rejected_without_session_or_upload(
    client, clerk, assignment, db, storage, make_video, monkeypatch, seconds, error
):
    def upload(*args):
        pytest.fail("Rejected video must not be stored")

    monkeypatch.setattr(storage, "upload", upload)
    response = post_video(client, clerk, assignment, make_video(seconds=seconds))
    assert response.status_code == 422
    assert response.json()["detail"] == ERROR_MESSAGES[error]
    assert sessions_count(db) == 0


@pytest.mark.parametrize(
    "filename,mime,contents,status",
    [
        ("exercise.txt", "video/mp4", b"not video", 415),
        ("exercise.mp4", "text/html", b"not video", 415),
        ("exercise.mp4", "video/mp4", b"not video", 422),
        ("exercise.mp4", "video/mp4", b"", 422),
    ],
)
def test_wrong_type_or_unreadable_file_is_rejected(
    client,
    clerk,
    assignment,
    db,
    storage,
    monkeypatch,
    filename,
    mime,
    contents,
    status,
):
    monkeypatch.setattr(
        storage, "upload", lambda *args: pytest.fail("No upload expected")
    )
    response = post_video(client, clerk, assignment, contents, filename, mime)
    assert response.status_code == status
    assert sessions_count(db) == 0


@pytest.mark.parametrize(
    "content,filename",
    [
        (".webm", "exercise.mp4"),
        (".webm", "exercise.mov"),
        (".mp4", "exercise.webm"),
        (".mov", "exercise.webm"),
    ],
)
def test_real_container_must_match_extension(
    client, clerk, assignment, db, make_video, content, filename
):
    response = post_video(client, clerk, assignment, make_video(content), filename)
    assert response.status_code == 415
    assert sessions_count(db) == 0


@pytest.mark.parametrize(
    "content,filename,mime,stored_type",
    [
        # Some phones save an ISO MP4 with a .mov name.
        (".mp4", "exercise.mov", "video/quicktime", "video/mp4"),
        (".mov", "exercise.mp4", "video/mp4", "video/quicktime"),
    ],
)
def test_mp4_and_mov_names_are_interchangeable_and_stored_as_inspected(
    client,
    clerk,
    assignment,
    db,
    storage,
    make_video,
    content,
    filename,
    mime,
    stored_type,
):
    contents = make_video(content)
    response = post_video(client, clerk, assignment, contents, filename, mime)
    assert response.status_code == 201, response.text
    saved = db.get(ExerciseSession, uuid.UUID(response.json()["id"]))
    assert saved.video_key == f"sessions/{saved.id}{content}"
    stored = httpx.get(storage.read_url(saved.video_key))
    assert stored.content == contents
    assert stored.headers["content-type"] == stored_type


def test_inspection_timeout_is_a_server_error_not_a_bad_video(
    client, clerk, assignment, db, storage, make_video, monkeypatch
):
    contents = make_video()  # before subprocess.run is replaced below

    def too_slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffprobe", uploads.PROBE_TIMEOUT_SECONDS)

    monkeypatch.setattr(uploads.subprocess, "run", too_slow)
    monkeypatch.setattr(
        storage, "upload", lambda *args: pytest.fail("No upload expected")
    )
    response = post_video(client, clerk, assignment, contents)
    assert response.status_code == 503
    assert response.json()["detail"] != ERROR_MESSAGES["video_unreadable"]
    assert sessions_count(db) == 0


def test_size_is_checked_on_the_actual_file(
    client, clerk, assignment, db, make_video, monkeypatch
):
    contents = make_video()
    monkeypatch.setattr(uploads, "MAX_VIDEO_UPLOAD_BYTES", len(contents) - 1)
    response = post_video(client, clerk, assignment, contents)
    assert response.status_code == 413
    assert sessions_count(db) == 0


def test_size_equal_to_the_limit_is_accepted(
    client, clerk, assignment, make_video, monkeypatch
):
    contents = make_video()
    monkeypatch.setattr(uploads, "MAX_VIDEO_UPLOAD_BYTES", len(contents))
    assert post_video(client, clerk, assignment, contents).status_code == 201


@pytest.mark.parametrize("user,status", [("user_other", 404), ("user_t", 403)])
def test_wrong_owner_and_wrong_role_cannot_upload(
    client, clerk, assignment, db, make_video, monkeypatch, user, status
):
    monkeypatch.setattr(
        "app.routes.sessions.validate_video",
        lambda *args: pytest.fail("No inspection expected"),
    )
    response = post_video(client, clerk, assignment, make_video(), user=user)
    assert response.status_code == status
    assert sessions_count(db) == 0


def test_missing_plan_exercise_is_not_found(client, clerk, assignment, make_video):
    response = client.post(
        "/sessions",
        data={"plan_exercise_id": str(uuid.uuid4())},
        files={"video": ("exercise.mp4", make_video(), "video/mp4")},
        headers=clerk.headers("user_p"),
    )
    assert response.status_code == 404


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_both_endpoints_require_authentication(
    client, clerk, assignment, make_video, headers
):
    created = post_video(client, clerk, assignment, make_video()).json()
    assert client.get("/sessions/" + created["id"], headers=headers).status_code == 401
    assert (
        client.post(
            "/sessions",
            data={"plan_exercise_id": str(assignment.id)},
            files={"video": ("exercise.mp4", make_video(), "video/mp4")},
            headers=headers,
        ).status_code
        == 401
    )


@pytest.mark.parametrize("user", ["user_other", "user_outsider"])
def test_session_status_is_hidden_from_other_patient_and_unlinked_therapist(
    client, clerk, assignment, make_video, user
):
    created = post_video(client, clerk, assignment, make_video()).json()
    response = client.get("/sessions/" + created["id"], headers=clerk.headers(user))
    assert response.status_code == 404


def test_linked_therapist_can_read_status(client, clerk, assignment, make_video):
    created = post_video(client, clerk, assignment, make_video()).json()
    response = client.get("/sessions/" + created["id"], headers=clerk.headers("user_t"))
    assert response.status_code == 200
    assert response.json() == {**created, "status": "complete"}


@pytest.mark.parametrize("status", [SessionStatus.COMPLETE, SessionStatus.FAILED])
def test_status_endpoint_returns_updated_state(
    client, clerk, assignment, make_video, db, status
):
    created = post_video(client, clerk, assignment, make_video()).json()
    session = db.get(ExerciseSession, uuid.UUID(created["id"]))
    session.status = status
    db.commit()
    response = client.get("/sessions/" + created["id"], headers=clerk.headers("user_p"))
    assert response.status_code == 200
    assert response.json()["status"] == status


def test_missing_session_is_not_found(client, clerk, assignment):
    response = client.get(f"/sessions/{uuid.uuid4()}", headers=clerk.headers("user_p"))
    assert response.status_code == 404


def test_storage_failure_leaves_no_session(
    client, clerk, assignment, db, storage, make_video, monkeypatch, ai_service
):
    keys = []
    original_upload = storage.upload

    def unavailable(key, data, content_type):
        keys.append(key)
        original_upload(key, b"partial synthetic upload", content_type)
        raise AzureError("synthetic storage failure")

    monkeypatch.setattr(storage, "upload", unavailable)
    response = post_video(client, clerk, assignment, make_video())
    assert response.status_code == 503
    assert "synthetic storage failure" not in response.text
    assert sessions_count(db) == 0
    assert len(keys) == 1
    assert httpx.get(storage.read_url(keys[0])).status_code == 404
    assert ai_service.requests == []  # nothing to analyze


def test_failed_commit_removes_the_uploaded_file(
    client, clerk, assignment, db, storage, make_video, monkeypatch, ai_service
):
    keys = []
    original_upload = storage.upload

    def remember(key, data, content_type):
        keys.append(key)
        original_upload(key, data, content_type)

    def fail_commit(self):
        raise SQLAlchemyError("synthetic database failure")

    monkeypatch.setattr(storage, "upload", remember)
    monkeypatch.setattr(Session, "commit", fail_commit)
    response = post_video(client, clerk, assignment, make_video())
    assert response.status_code == 503
    assert sessions_count(db) == 0
    assert len(keys) == 1
    assert httpx.get(storage.read_url(keys[0])).status_code == 404
    assert ai_service.requests == []  # nothing to analyze


def test_no_database_connection_is_held_while_checking_and_storing_the_video(
    client, clerk, assignment, db, storage, make_video, monkeypatch
):
    """Inspection and a large upload can take minutes. Holding a pooled connection
    meanwhile would let a few slow uploads use up the pool."""
    contents = make_video()
    plan_exercise_id = str(assignment.id)
    db.rollback()  # this test's own session gives its connection back too
    original_upload = storage.upload
    in_use = []

    def check(video):
        in_use.append(engine.pool.checkedout())
        return uploads.validate_video(video)

    def upload(key, data, content_type):
        in_use.append(engine.pool.checkedout())
        original_upload(key, data, content_type)

    monkeypatch.setattr("app.routes.sessions.validate_video", check)
    monkeypatch.setattr(storage, "upload", upload)
    response = client.post(
        "/sessions",
        data={"plan_exercise_id": plan_exercise_id},
        files={"video": ("exercise.mp4", contents, "video/mp4")},
        headers=clerk.headers("user_p"),
    )
    assert response.status_code == 201, response.text
    assert in_use == [0, 0]
    assert sessions_count(db) == 1


def test_upload_is_analyzed_in_the_background_and_ends_complete(
    client, clerk, assignment, db, storage, make_video, ai_service
):
    contents = make_video()
    response = post_video(client, clerk, assignment, contents)
    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "processing"  # answered before the analysis ran
    [request] = ai_service.requests
    assert request["session_id"] == created["id"]
    assert request["exercise"] == "squat"
    assert httpx.get(request["video_url"]).content == contents  # a working read link
    status = client.get("/sessions/" + created["id"], headers=clerk.headers("user_p"))
    assert status.json()["status"] == "complete"
    saved = db.get(SessionResult, uuid.UUID(created["id"]))
    assert saved.result == ai_service.body


def test_upload_with_the_ai_service_down_ends_failed(
    client, clerk, assignment, db, make_video, ai_service
):
    ai_service.error = httpx.ConnectError("Connection refused")
    created = post_video(client, clerk, assignment, make_video()).json()
    status = client.get("/sessions/" + created["id"], headers=clerk.headers("user_p"))
    assert status.json()["status"] == "failed"
    saved = db.get(SessionResult, uuid.UUID(created["id"]))
    assert saved.result == AnalysisResult.failed(
        "analysis_unavailable", analyzer_version=None
    ).model_dump(mode="json")


def test_upload_schedules_the_analysis_once_the_session_is_saved(
    client, clerk, assignment, make_video, monkeypatch
):
    videos = []
    scheduled = []

    def check(video):
        videos.append(video)
        return uploads.validate_video(video)

    def analyze(session_id):
        # Like the job, outside the request: the session must already be committed.
        with Session(engine) as other:
            status = other.get(ExerciseSession, session_id).status
        # The upload's temporary file must not stay on disk during the analysis.
        scheduled.append((session_id, status, videos[0].file.closed))

    monkeypatch.setattr("app.routes.sessions.validate_video", check)
    monkeypatch.setattr("app.routes.sessions.analyze_session", analyze)
    response = post_video(client, clerk, assignment, make_video())
    assert response.status_code == 201
    assert scheduled == [(uuid.UUID(response.json()["id"]), "processing", True)]


def test_filename_and_video_details_are_not_logged(
    client, clerk, assignment, make_video, caplog, ai_service
):
    filename = "private-patient-name.mp4"
    caplog.set_level(logging.INFO)
    response = post_video(client, clerk, assignment, make_video(), filename)
    assert response.status_code == 201
    assert filename not in caplog.text
    assert "Bearer " not in caplog.text
    # The background analysis logs the session id, never the video's read link.
    assert response.json()["id"] in caplog.text
    assert ai_service.requests[0]["video_url"] not in caplog.text
    assert "sig=" not in caplog.text


def test_openapi_describes_upload_form_and_response():
    from app.main import app

    spec = app.openapi()
    operation = spec["paths"]["/sessions"]["post"]
    assert operation["operationId"] == "create_session"
    assert operation["tags"] == ["sessions"]
    form = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body = spec["components"]["schemas"][form["$ref"].split("/")[-1]]
    assert set(body["required"]) == {"plan_exercise_id", "video"}
    assert body["properties"]["video"]["format"] == "binary"
