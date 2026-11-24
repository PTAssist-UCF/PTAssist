"""Settings in app/config.py: defaults and checks, as the API reads them at start-up."""

import re
import runpy
from pathlib import Path
from typing import Any

import pytest

import app.config

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_APP_VIDEO_CHECKS = REPO_ROOT / "frontend" / "src" / "utils" / "videoValidation.ts"


def read_settings() -> dict[str, Any]:
    """Run app/config.py again with the current environment, apart from the app's
    own copy of the settings."""
    return runpy.run_path(app.config.__file__)


def test_upload_limit_defaults_to_500_mib(monkeypatch: pytest.MonkeyPatch) -> None:
    """Small enough for the temporary disk of an Azure container, which holds about
    twice the upload while it is checked."""
    monkeypatch.delenv("MAX_VIDEO_UPLOAD_BYTES", raising=False)
    assert read_settings()["MAX_VIDEO_UPLOAD_BYTES"] == 500 * 1024**2


def test_web_app_checks_the_same_upload_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The web app refuses a larger file before uploading it, with the API's 413
    message, so its copy of the limit must be the default here. Change both together."""
    monkeypatch.delenv("MAX_VIDEO_UPLOAD_BYTES", raising=False)
    [web_app_limit] = re.findall(
        r"export const MAX_VIDEO_UPLOAD_BYTES = (\d+);",
        WEB_APP_VIDEO_CHECKS.read_text(),
    )
    assert int(web_app_limit) == read_settings()["MAX_VIDEO_UPLOAD_BYTES"]


@pytest.mark.parametrize("value", ["0", "-1"])
def test_upload_limit_must_be_positive(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAX_VIDEO_UPLOAD_BYTES", value)
    with pytest.raises(ValueError, match="MAX_VIDEO_UPLOAD_BYTES"):
        read_settings()


def test_ai_service_timeout_fits_between_the_analysis_target_and_azure_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Longer than the 3 minutes a 2-minute clip may take, shorter than the 240 seconds
    after which Azure ends the request (docs/analysis-result.md, Clip limits and
    timing)."""
    monkeypatch.delenv("AI_SERVICE_TIMEOUT_SECONDS", raising=False)
    assert 180 < read_settings()["AI_SERVICE_TIMEOUT_SECONDS"] < 240


@pytest.mark.parametrize("value", ["0", "-5", "nan", "inf"])
def test_ai_service_timeout_must_be_a_positive_number(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("AI_SERVICE_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="AI_SERVICE_TIMEOUT_SECONDS"):
        read_settings()


def test_stuck_session_cutoff_is_longer_than_the_analysis_waits_for_the_ai_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """By default 30 seconds more than the 10 seconds to connect plus the 230 to
    answer, and no longer than the web app's 300-second polling timeout
    (docs/analysis-result.md, Clip limits and timing)."""
    monkeypatch.delenv("AI_SERVICE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("STUCK_SESSION_CUTOFF_SECONDS", raising=False)
    assert read_settings()["STUCK_SESSION_CUTOFF_SECONDS"] == 270


@pytest.mark.parametrize("value", ["", None], ids=["empty", "unset"])
def test_stuck_session_cutoff_follows_the_ai_service_timeout(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    monkeypatch.setenv("AI_SERVICE_TIMEOUT_SECONDS", "200")
    if value is None:
        monkeypatch.delenv("STUCK_SESSION_CUTOFF_SECONDS", raising=False)
    else:
        monkeypatch.setenv("STUCK_SESSION_CUTOFF_SECONDS", value)
    assert read_settings()["STUCK_SESSION_CUTOFF_SECONDS"] == 240


@pytest.mark.parametrize("value", ["241", "600"])
def test_stuck_session_cutoff_can_be_set(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.delenv("AI_SERVICE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("STUCK_SESSION_CUTOFF_SECONDS", value)
    assert read_settings()["STUCK_SESSION_CUTOFF_SECONDS"] == float(value)


@pytest.mark.parametrize("value", ["240", "230", "100", "0", "-1", "nan", "inf"])
def test_stuck_session_cutoff_must_be_longer_than_the_ai_service_wait(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """With the default timeout the analysis may wait 240 seconds for the AI service, so
    a cutoff of 240 or less could fail a session it is still waiting on."""
    monkeypatch.delenv("AI_SERVICE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("STUCK_SESSION_CUTOFF_SECONDS", value)
    with pytest.raises(ValueError, match="STUCK_SESSION_CUTOFF_SECONDS"):
        read_settings()


def test_a_longer_ai_service_timeout_needs_a_longer_stuck_session_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cutoff set by hand is checked against the timeout it runs with."""
    monkeypatch.setenv("AI_SERVICE_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("STUCK_SESSION_CUTOFF_SECONDS", "300")
    with pytest.raises(ValueError, match="STUCK_SESSION_CUTOFF_SECONDS"):
        read_settings()


@pytest.mark.parametrize("value", [None, ""])
def test_log_format_defaults_to_json(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """JSON lines, which backend/README.md (Logs) shows how to filter by session."""
    if value is None:
        monkeypatch.delenv("LOG_FORMAT", raising=False)
    else:
        monkeypatch.setenv("LOG_FORMAT", value)
    assert read_settings()["LOG_FORMAT"] == "json"
