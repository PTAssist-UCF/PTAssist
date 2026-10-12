"""Tests for GET /health and the stub POST /analyze."""

import pytest
from fastapi.testclient import TestClient

from app.analysis_contract import ERROR_MESSAGES, AnalysisResult
from app.main import app

# Calls the app directly in memory: no server or network needed.
client = TestClient(app)

# A request like the one the backend will send. The link is made up.
REQUEST = {
    "session_id": "3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41",
    "exercise": "squat",
    "video_url": "http://127.0.0.1:10000/devstoreaccount1/videos/sessions/example.mp4",
}


def analyze(exercise: str) -> AnalysisResult:
    """Call POST /analyze for one exercise and check the answer matches the contract."""
    response = client.post("/analyze", json={**REQUEST, "exercise": exercise})

    assert response.status_code == 200
    # model_validate raises an error if the JSON does not match AnalysisResult.
    return AnalysisResult.model_validate(response.json())


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# The five agreed exercise names (docs/analysis-result.md, Exercise names). Written out
# here on purpose, so a typo or rename in app/main.py fails a test.
@pytest.mark.parametrize(
    "exercise", ["cat_cow", "shoulder_abduction", "side_leg_raise", "squat"]
)
def test_analyze_returns_reps_for_an_exercise_done_in_reps(exercise: str) -> None:
    result = analyze(exercise)

    assert result.status == "complete"
    assert result.rep_count == len(result.reps) > 0
    assert result.hold_seconds is None


@pytest.mark.parametrize("exercise", ["plank"])
def test_analyze_returns_a_hold_time_for_a_hold_exercise(exercise: str) -> None:
    result = analyze(exercise)

    assert result.status == "complete"
    assert result.rep_count is None
    assert result.hold_seconds is not None and result.hold_seconds > 0


def test_analyze_fails_for_an_unknown_exercise() -> None:
    result = analyze("jumping_jacks")

    assert result.status == "failed"
    assert result.error_code == "unknown_exercise"
    assert result.error_message == ERROR_MESSAGES["unknown_exercise"]


@pytest.mark.parametrize("missing_field", REQUEST.keys())
def test_analyze_rejects_a_request_with_a_missing_field(missing_field: str) -> None:
    request = {key: value for key, value in REQUEST.items() if key != missing_field}

    response = client.post("/analyze", json=request)

    assert response.status_code == 422


def test_analyze_rejects_a_session_id_that_is_not_a_uuid() -> None:
    response = client.post("/analyze", json={**REQUEST, "session_id": "abc123"})

    assert response.status_code == 422
