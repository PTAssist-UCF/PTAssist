"""Structured logs (app/logs.py, SCRUM-83): the JSON lines, the session id, and what is
kept out of them. tests/test_sessions.py follows one whole upload through the logs.

The `logs` fixture (tests/conftest.py) sets up logging as the API does, but writes to a
buffer that the tests read back.

The AI service writes its logs with an exact copy of app/logs.py. The first test fails
when someone changes one file without the other, and the AI service runs the same check.
"""

import asyncio
import io
import logging
import re
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.concurrency import run_in_threadpool

from app.logs import HANDLER_NAME, configure_logging, redact, session_context

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ORIGINAL = REPO_ROOT / "backend" / "app" / "logs.py"
AI_COPY = REPO_ROOT / "ai" / "app" / "logs.py"

SESSION_ID = uuid.UUID("2f1c7a4e-8d3b-4c55-9a1e-6b0d4e2f3a10")
OTHER_SESSION_ID = uuid.UUID("9b8e1d02-55c4-4e0f-8f6a-0c3d7e1a2b45")
# Our own code's loggers are under "app".
logger = logging.getLogger("app.test_logs")
# uvicorn's access line: client address, method, path with query, HTTP version, status.
ACCESS_LINE = '%s - "%s %s HTTP/%s" %d'
CLIENT = "203.0.113.7:51234"


def access_logger() -> logging.Logger:
    """uvicorn's access logger, at the level uvicorn gives it (the fixture restores
    it)."""
    access = logging.getLogger("uvicorn.access")
    access.setLevel(logging.INFO)
    return access


def test_ai_copy_of_logs_matches_backend_original() -> None:
    # read_text turns Windows line endings into "\n", so only real differences count.
    backend_original = BACKEND_ORIGINAL.read_text(encoding="utf-8")
    ai_copy = AI_COPY.read_text(encoding="utf-8")

    assert ai_copy == backend_original, (
        "ai/app/logs.py must be an exact copy of backend/app/logs.py. If you changed "
        "the AI copy, make the same change in backend/app/logs.py first, because the "
        "command below overwrites the AI copy. Then, from the repo root, run: "
        "cp backend/app/logs.py ai/app/logs.py "
        "(run pytest with -vv to see the whole difference)"
    )


def test_a_line_is_one_json_object(logs) -> None:
    logger.info("Analysis of session %s started", SESSION_ID)
    [line] = logs.lines()
    assert line == {
        "time": line["time"],
        "level": "INFO",
        "service": "api",
        "logger": "app.test_logs",
        "message": f"Analysis of session {SESSION_ID} started",
    }
    # UTC, to the millisecond, such as 2026-11-23T18:04:05.123Z.
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", line["time"])
    logged_at = datetime.fromisoformat(line["time"])
    assert abs(datetime.now(UTC) - logged_at) < timedelta(minutes=1)


def test_fields_follow_the_message_in_a_fixed_order(logs) -> None:
    logger.warning(
        "Analysis of session %s failed",
        SESSION_ID,
        extra={
            "error_code": "no_person",
            "duration_seconds": 1.5,
            "status_code": 200,
            "session_id": SESSION_ID,
        },
    )
    [line] = logs.lines()
    assert list(line)[5:] == [
        "session_id",
        "status_code",
        "duration_seconds",
        "error_code",
    ]
    # Ids and codes as text, numbers as numbers.
    assert line["session_id"] == str(SESSION_ID)
    assert (line["status_code"], line["duration_seconds"]) == (200, 1.5)
    assert line["error_code"] == "no_person"


def test_fields_that_are_not_listed_are_dropped(logs) -> None:
    logger.info(
        "Signed in",
        extra={
            "session_id": SESSION_ID,
            "email": "jane@example.com",
            "headers": {"Authorization": "Bearer s3cr3t"},
            "video_url": "http://azurite:10000/videos/1.mp4?sig=s3cr3t",
        },
    )
    [line] = logs.lines()
    assert set(line) == {"time", "level", "service", "logger", "message", "session_id"}
    assert "jane" not in logs.text
    assert "s3cr3t" not in logs.text


def test_session_context_adds_the_id_to_every_line_inside(logs) -> None:
    with session_context(SESSION_ID):
        logger.info("ours")
        logging.getLogger("httpx").warning("a library's")
    logger.info("after")
    assert [line.get("session_id") for line in logs.lines()] == [
        str(SESSION_ID),
        str(SESSION_ID),
        None,
    ]


def test_session_contexts_nest(logs) -> None:
    with session_context(SESSION_ID):
        with session_context(OTHER_SESSION_ID):
            logger.info("inner")
        logger.info("outer again")
    assert [line["session_id"] for line in logs.lines()] == [
        str(OTHER_SESSION_ID),
        str(SESSION_ID),
    ]


def test_a_session_id_given_to_the_line_wins(logs) -> None:
    with session_context(SESSION_ID):
        logger.warning(
            "Session %s failed",
            OTHER_SESSION_ID,
            extra={"session_id": OTHER_SESSION_ID},
        )
    [line] = logs.lines()
    assert line["session_id"] == str(OTHER_SESSION_ID)


def test_the_session_id_follows_into_a_worker_thread(logs) -> None:
    """As in FastAPI, where sync routes and background tasks run in worker threads."""

    async def request() -> None:
        with session_context(SESSION_ID):
            await run_in_threadpool(logger.info, "in a worker thread")

    asyncio.run(request())
    [line] = logs.lines()
    assert line["session_id"] == str(SESSION_ID)


def test_other_threads_do_not_see_the_session_id(logs) -> None:
    """Another request, served at the same time, gets no session id from this one."""
    inside = threading.Event()
    logged = threading.Event()

    def other_request() -> None:
        inside.wait(timeout=5)
        logger.info("another request")
        logged.set()

    thread = threading.Thread(target=other_request)
    thread.start()
    with session_context(SESSION_ID):
        inside.set()
        logged.wait(timeout=5)
    thread.join()
    [line] = logs.lines()
    assert line["message"] == "another request"
    assert "session_id" not in line


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        (
            "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzM2NyM3QifQ.s3cr3t",
            "Authorization: Bearer [redacted]",
        ),
        (
            "token eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzM2NyM3QifQ.s3cr3t here",
            "token [redacted] here",
        ),
        ("CLERK_SECRET_KEY=sk_test_s3cr3t", "CLERK_SECRET_KEY=[redacted]"),
        ("for jane.doe+s3cr3t@example.co.uk now", "for [redacted email] now"),
        (
            "GET http://azurite:10000/devstoreaccount1/videos/sessions/1.mp4"
            "?se=2026-11-23&sp=r&sig=s3cr3t%2B",
            "GET http://azurite:10000/devstoreaccount1/videos/sessions/1.mp4"
            "?[redacted]",
        ),
        (
            '{"video_url": "https://pt.blob.core.windows.net/v/1.mp4?sig=s3cr3t"}',
            '{"video_url": "https://pt.blob.core.windows.net/v/1.mp4?[redacted]"}',
        ),
        (
            "http://localhost:5173/callback#token=s3cr3t",
            "http://localhost:5173/callback#[redacted]",
        ),
        ("sv=2025-01-05&sig=s3cr3t&se=1", "sv=2025-01-05&sig=[redacted]&se=1"),
        (
            "AccountName=devstoreaccount1;AccountKey=s3cr3t==;BlobEndpoint=x",
            "AccountName=devstoreaccount1;AccountKey=[redacted];BlobEndpoint=x",
        ),
        (
            "postgresql+psycopg://ptassist:s3cr3t@db:5432/ptassist",
            "postgresql+psycopg://ptassist:[redacted]@db:5432/ptassist",
        ),
    ],
    ids=[
        "bearer token",
        "jwt",
        "clerk key",
        "email",
        "read link",
        "read link in json",
        "link fragment",
        "signature",
        "storage key",
        "database password",
    ],
)
def test_redact_masks_the_secret_and_keeps_the_rest(text: str, masked: str) -> None:
    assert redact(text) == masked
    assert "s3cr3t" not in redact(text)


@pytest.mark.parametrize(
    "text",
    [
        f"Analysis of session {SESSION_ID} failed with analysis_timed_out: no answer",
        f"GET /sessions/{SESSION_ID}/result 200",
        "Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)",
        "Ready? Yes.",
    ],
)
def test_redact_leaves_ordinary_lines_alone(text: str) -> None:
    assert redact(text) == text


def test_messages_fields_and_tracebacks_are_redacted(logs) -> None:
    """The safety net, for a line that breaks the rule."""
    try:
        raise RuntimeError("could not read http://azurite:10000/v/1.mp4?sig=s3cr3t")
    except RuntimeError:
        logger.exception(
            "Upload for jane@example.com failed",
            extra={"error_type": "Bearer s3cr3t-s3cr3t-s3cr3t-s3cr3t"},
        )
    [line] = logs.lines()
    assert line["message"] == "Upload for [redacted email] failed"
    assert line["error_type"] == "Bearer [redacted]"
    assert (
        "RuntimeError: could not read http://azurite:10000/v/1.mp4?[redacted]"
        in (line["exception"])
    )
    assert "s3cr3t" not in logs.text
    assert "jane" not in logs.text


def test_access_lines_leave_out_the_address_and_query_string(logs) -> None:
    access = access_logger()
    path = f"/sessions/{str(SESSION_ID).upper()}/result"
    access.info(ACCESS_LINE, CLIENT, "GET", f"{path}?token=s3cr3t", "1.1", 200)
    access.info(ACCESS_LINE, CLIENT, "POST", "/sessions", "1.1", 201)
    polled, uploaded = logs.lines()
    # A path with a session id gets it as the line's session_id.
    assert polled == {
        "time": polled["time"],
        "level": "INFO",
        "service": "api",
        "logger": "uvicorn.access",
        "message": f"GET {path} 200",
        "session_id": str(SESSION_ID),
        "method": "GET",
        "path": path,
        "status_code": 200,
    }
    assert uploaded["message"] == "POST /sessions 201"
    assert "session_id" not in uploaded
    assert "203.0.113.7" not in logs.text
    assert "s3cr3t" not in logs.text


def test_a_path_from_any_logger_loses_its_query_string(logs) -> None:
    logger.info("Called", extra={"path": "/callback?token=s3cr3t"})
    [line] = logs.lines()
    assert line["path"] == "/callback"


def test_health_checks_that_work_are_not_logged(logs) -> None:
    """Docker Compose calls /health every 5 seconds."""
    access = access_logger()
    access.info(ACCESS_LINE, CLIENT, "GET", "/health", "1.1", 200)
    access.info(ACCESS_LINE, CLIENT, "GET", "/health", "1.1", 503)
    [line] = logs.lines()
    assert line["message"] == "GET /health 503"


def test_uvicorn_lines_are_written_as_json_too(logs) -> None:
    # uvicorn gives its loggers their own handlers before it imports the app.
    console = io.StringIO()
    for name in ("uvicorn", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        server_logger.addHandler(logging.StreamHandler(console))
        server_logger.setLevel(logging.INFO)
        server_logger.propagate = False
    logs.configure()
    logging.getLogger("uvicorn.error").info("Application startup complete.")
    logging.getLogger("uvicorn.access").info(
        ACCESS_LINE, CLIENT, "GET", "/exercises", "1.1", 200
    )
    assert [(line["logger"], line["message"]) for line in logs.lines()] == [
        ("uvicorn.error", "Application startup complete."),
        ("uvicorn.access", "GET /exercises 200"),
    ]
    assert console.getvalue() == ""


def test_access_lines_stay_off_when_uvicorn_turns_them_off(logs) -> None:
    # uvicorn --no-access-log: no handlers, and nothing passed on.
    access = access_logger()
    access.propagate = False
    logs.configure()
    access.info(ACCESS_LINE, CLIENT, "GET", "/exercises", "1.1", 200)
    assert logs.text == ""


def test_our_lines_show_from_info_and_libraries_from_warning(logs) -> None:
    """Some libraries log request URLs at INFO (the Azure SDK, httpx)."""
    logging.getLogger("app.jobs.analysis").info("ours")
    logging.getLogger("app.jobs.analysis").debug("our details")
    logging.getLogger("azure.core.pipeline").info("Request URL: http://azurite")
    logging.getLogger("httpx").warning("a library's warning")
    assert [line["message"] for line in logs.lines()] == ["ours", "a library's warning"]


def test_configuring_again_replaces_the_handler_and_keeps_others(logs, caplog) -> None:
    logs.configure()
    logs.configure()
    root = logging.getLogger()
    assert [h.get_name() for h in root.handlers].count(HANDLER_NAME) == 1
    assert caplog.handler in root.handlers
    logger.info("once")
    assert len(logs.lines()) == 1
    assert caplog.messages == ["once"]


def test_text_format_is_one_readable_line(logs) -> None:
    logs.configure("text")
    with session_context(SESSION_ID):
        logger.warning("Analysis failed", extra={"error_code": "no_person"})
    assert re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z WARNING app.test_logs: Analysis failed"
        rf" session_id={SESSION_ID} error_code=no_person\n",
        logs.text,
    )


def test_an_unknown_format_is_refused() -> None:
    with pytest.raises(ValueError, match="LOG_FORMAT must be one of: json, text"):
        configure_logging("api", "xml")
