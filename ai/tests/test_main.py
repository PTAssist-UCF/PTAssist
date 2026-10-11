"""Tests for GET /health and the stub POST /analyze."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import AnalysisResult

# Calls the app directly in memory: no server or network needed.
client = TestClient(app)

# A request like the one the backend will send. The link is made up.
REQUEST = {
    "session_id": "3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41",
    "exercise": "exercise_1",
    "video_url": "http://127.0.0.1:10000/devstoreaccount1/videos/sessions/example.mp4",
}


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_returns_a_result_that_matches_the_schema() -> None:
    response = client.post("/analyze", json=REQUEST)

    assert response.status_code == 200
    # model_validate raises an error if the JSON does not match AnalysisResult.
    result = AnalysisResult.model_validate(response.json())
    assert result.status == "complete"
    assert result.rep_count == len(result.reps)
    assert result.error is None


@pytest.mark.parametrize("missing_field", REQUEST.keys())
def test_analyze_rejects_a_request_with_a_missing_field(missing_field: str) -> None:
    request = {key: value for key, value in REQUEST.items() if key != missing_field}

    response = client.post("/analyze", json=request)

    assert response.status_code == 422


def test_analyze_rejects_a_session_id_that_is_not_a_uuid() -> None:
    response = client.post("/analyze", json={**REQUEST, "session_id": "abc123"})

    assert response.status_code == 422
