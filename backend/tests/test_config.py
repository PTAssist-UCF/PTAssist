"""Settings in app/config.py: defaults and checks, as the API reads them at start-up."""

import runpy
from typing import Any

import pytest

import app.config


def read_settings() -> dict[str, Any]:
    """Run app/config.py again with the current environment, apart from the app's
    own copy of the settings."""
    return runpy.run_path(app.config.__file__)


def test_upload_limit_defaults_to_500_mib(monkeypatch: pytest.MonkeyPatch) -> None:
    """Small enough for the temporary disk of an Azure container, which holds about
    twice the upload while it is checked."""
    monkeypatch.delenv("MAX_VIDEO_UPLOAD_BYTES", raising=False)
    assert read_settings()["MAX_VIDEO_UPLOAD_BYTES"] == 500 * 1024**2


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
