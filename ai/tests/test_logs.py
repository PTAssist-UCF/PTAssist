"""Tests for the structured logs (app/logs.py, SCRUM-83).

app/logs.py is an exact copy of backend/app/logs.py, whose tests cover the format, the
fields, and the masking. These check that the copy is still exact (the backend runs the
same check), and that POST /analyze logs its session id, never the video link.
"""

import io
import json
import logging
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis.framework import RepObservation, build_rep_result
from app.analysis_contract import AnalysisResult
from app.logs import HANDLER_NAME, configure_logging
from app.main import STUB_VERSION, app

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ORIGINAL = REPO_ROOT / "backend" / "app" / "logs.py"
AI_COPY = REPO_ROOT / "ai" / "app" / "logs.py"

# Calls the app directly in memory: no server or network needed.
client = TestClient(app)

SESSION_ID = "3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41"
# A read link like the ones the backend sends. The signature is made up.
VIDEO_URL = (
    f"http://azurite:10000/devstoreaccount1/videos/sessions/{SESSION_ID}.mp4"
    "?se=2026-11-24T00%3A31%3A24Z&sp=r&sv=2025-01-05&sr=b&sig=s3cr3t"
)


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    """The service's log lines during the test, set up as app/main.py does but written
    to a buffer. Puts the logging setup back as it was afterwards."""
    root = logging.getLogger()
    # Only the service's own handler: pytest adds and removes its own itself.
    service_handlers = [h for h in root.handlers if h.get_name() == HANDLER_NAME]
    root_level = root.level
    app_level = logging.getLogger("app").level
    stream = io.StringIO()
    configure_logging("ai", stream=stream)
    yield stream
    for handler in [h for h in root.handlers if h.get_name() == HANDLER_NAME]:
        root.removeHandler(handler)
    for handler in service_handlers:
        root.addHandler(handler)
    root.setLevel(root_level)
    logging.getLogger("app").setLevel(app_level)


def json_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    """Each line written to the buffer, parsed."""
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def analyze(exercise: str) -> None:
    response = client.post(
        "/analyze",
        json={"session_id": SESSION_ID, "exercise": exercise, "video_url": VIDEO_URL},
    )
    assert response.status_code == 200


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


def test_analyze_logs_its_session_id_and_never_the_video_link(logs) -> None:
    analyze("squat")

    started, finished = json_lines(logs)
    assert started["message"] == f"Analysis of session {SESSION_ID} started"
    assert finished["message"] == f"Analysis of session {SESSION_ID} finished: complete"
    for line in (started, finished):
        assert (line["service"], line["session_id"]) == ("ai", SESSION_ID)
    assert finished["outcome"] == "complete"
    assert finished["analyzer_version"] == STUB_VERSION
    assert finished["duration_seconds"] >= 0
    assert "azurite" not in logs.getvalue()
    assert "s3cr3t" not in logs.getvalue()


def test_a_failed_analysis_logs_its_error_code(logs) -> None:
    analyze("jumping_jacks")

    finished = json_lines(logs)[-1]
    assert finished["message"] == (
        f"Analysis of session {SESSION_ID} finished: failed with unknown_exercise"
    )
    assert (finished["outcome"], finished["error_code"]) == (
        "failed",
        "unknown_exercise",
    )


def test_a_failed_download_is_logged_with_the_session_id_and_never_the_link(
    logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An exercise with a real analyzer, so the request goes through the download step.
    def fake_analyzer(keypoints: dict[str, Any], version: str) -> AnalysisResult:
        return build_rep_result([RepObservation(0, 3)], {}, version)

    def refuse(url: str, timeout: float) -> None:
        raise urllib.error.URLError(f"cannot reach {url}")

    monkeypatch.setitem(main.ANALYZERS, "fake_exercise", fake_analyzer)
    monkeypatch.setattr(main, "open_video", refuse)

    analyze("fake_exercise")

    started, warning, finished = json_lines(logs)
    assert warning["level"] == "WARNING"
    assert warning["message"].startswith(f"Download failed for session {SESSION_ID}")
    for line in (started, warning, finished):
        assert line["session_id"] == SESSION_ID
    assert finished["error_code"] == "analysis_error"
    assert "azurite" not in logs.getvalue()
    assert "s3cr3t" not in logs.getvalue()
