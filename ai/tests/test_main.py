"""Tests for GET /health and POST /analyze.

Real analysis is tested with the download and keypoint steps replaced, so the tests
need no network, ffmpeg, or pose model.
"""

import http.server
import io
import threading
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis.framework import RepObservation, build_rep_result
from app.analysis_contract import ERROR_MESSAGES, AnalysisResult
from app.keypoints.extract import DEFAULT_MODEL
from app.keypoints.video import NormalizeError, VideoError, VideoTimeoutError
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


class FakeResponse(io.BytesIO):
    """An in-memory stand-in for a download, with no Content-Length header."""

    headers: dict[str, str] = {}


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# The five agreed exercise names (docs/analysis-result.md, Exercise names). Written out
# here on purpose, so a typo or rename in app/main.py fails a test.
def test_every_agreed_exercise_has_an_analyzer_or_a_stub() -> None:
    known = set(main.ANALYZERS) | main.HOLD_EXERCISES | main.REP_EXERCISES
    assert known == {
        "cat_cow",
        "plank",
        "shoulder_abduction",
        "side_leg_raise",
        "squat",
    }
    assert not set(main.ANALYZERS) & (main.HOLD_EXERCISES | main.REP_EXERCISES)


@pytest.mark.parametrize(
    "exercise", ["cat_cow", "shoulder_abduction", "side_leg_raise", "squat"]
)
def test_stub_returns_reps_for_an_exercise_done_in_reps(exercise: str) -> None:
    result = analyze(exercise)

    assert result.status == "complete"
    assert result.rep_count == len(result.reps) > 0
    assert result.hold_seconds is None
    assert result.analyzer_version == main.STUB_VERSION


@pytest.mark.parametrize("exercise", ["plank"])
def test_stub_returns_a_hold_time_for_a_hold_exercise(exercise: str) -> None:
    result = analyze(exercise)

    assert result.status == "complete"
    assert result.rep_count is None
    assert result.hold_seconds is not None and result.hold_seconds > 0
    assert result.analyzer_version == main.STUB_VERSION


def fake_analyzer(keypoints: dict[str, Any], version: str) -> AnalysisResult:
    """Stands in for a real analyzer: one rep, whatever the keypoints say."""
    return build_rep_result([RepObservation(0, 3)], {}, version)


@pytest.fixture
def fake_exercise(monkeypatch: pytest.MonkeyPatch) -> str:
    """Register an exercise with an analyzer, and return its name."""
    monkeypatch.setitem(main.ANALYZERS, "fake_exercise", fake_analyzer)
    return "fake_exercise"


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch, fake_exercise: str) -> dict[str, Any]:
    """Replace the download and keypoint steps; tests set what extraction returns."""
    frame = {"index": 0, "time_seconds": 0.0, "landmarks": {"nose": [0.5, 0.5, 1, 1]}}
    calls: dict[str, Any] = {"keypoints": {"frames": [frame]}}

    def fake_download(url: str, target: Path) -> None:
        target.write_bytes(b"video")
        calls["url"], calls["video"] = url, target

    def fake_extract(video: Path, model: Path) -> dict[str, Any]:
        calls["model"] = model
        calls["free_slots"] = main.ANALYSIS_SLOTS._value
        if isinstance(calls["keypoints"], Exception):
            raise calls["keypoints"]
        return calls["keypoints"]

    monkeypatch.setattr(main, "download", fake_download)
    monkeypatch.setattr(main, "extract_keypoints", fake_extract)
    return calls


def test_an_exercise_with_an_analyzer_runs_the_real_pipeline(
    pipeline: dict[str, Any], fake_exercise: str
) -> None:
    result = analyze(fake_exercise)

    assert result.status == "complete" and result.rep_count == 1
    assert result.analyzer_version == main.ANALYZER_VERSION
    assert pipeline["url"] == REQUEST["video_url"]
    assert pipeline["model"] == DEFAULT_MODEL
    assert not pipeline["video"].exists()  # the downloaded copy is deleted


def test_each_analysis_holds_a_slot_while_it_runs(
    pipeline: dict[str, Any], fake_exercise: str
) -> None:
    analyze(fake_exercise)

    assert pipeline["free_slots"] == main.MAX_CONCURRENT_ANALYSES - 1
    assert main.ANALYSIS_SLOTS._value == main.MAX_CONCURRENT_ANALYSES


def test_a_temp_folder_failure_is_a_failed_result_not_a_500(
    monkeypatch: pytest.MonkeyPatch, fake_exercise: str
) -> None:
    def disk_full(**options: object) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr(main.tempfile, "TemporaryDirectory", disk_full)

    assert analyze(fake_exercise).error_code == "analysis_error"


@pytest.mark.parametrize(
    ("problem", "error_code"),
    [
        (VideoError("not a video"), "video_unreadable"),
        (VideoTimeoutError("too slow"), "analysis_error"),  # not the patient's fault
        (NormalizeError("full disk"), "analysis_error"),  # not the patient's fault
        (RuntimeError("bug"), "analysis_error"),
    ],
)
def test_keypoint_failures_return_a_failed_result(
    pipeline: dict[str, Any], fake_exercise: str, problem: Exception, error_code: str
) -> None:
    pipeline["keypoints"] = problem

    result = analyze(fake_exercise)

    assert result.status == "failed" and result.error_code == error_code
    assert result.analyzer_version == main.ANALYZER_VERSION


def test_a_video_with_nobody_in_it_fails_with_no_person(
    pipeline: dict[str, Any], fake_exercise: str
) -> None:
    for frame in pipeline["keypoints"]["frames"]:
        frame["landmarks"] = None

    result = analyze(fake_exercise)

    assert result.error_code == "no_person"
    assert result.error_message == ERROR_MESSAGES["no_person"]


def test_an_analyzer_crash_returns_analysis_error(
    pipeline: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fake_exercise: str
) -> None:
    def crash(keypoints: dict[str, Any], version: str) -> AnalysisResult:
        raise ZeroDivisionError

    monkeypatch.setitem(main.ANALYZERS, fake_exercise, crash)

    assert analyze(fake_exercise).error_code == "analysis_error"


def test_download_failure_returns_analysis_error_without_logging_the_link(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fake_exercise: str,
) -> None:
    def refuse(url: str, timeout: float) -> None:
        raise urllib.error.URLError(f"cannot reach {url}")

    monkeypatch.setattr(main, "open_video", refuse)

    result = analyze(fake_exercise)

    assert result.error_code == "analysis_error"
    assert "Download failed" in caplog.text
    assert REQUEST["video_url"] not in caplog.text
    assert "example.mp4" not in caplog.text


def test_download_streams_the_video_to_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(main, "open_video", lambda url, timeout: FakeResponse(b"bytes"))
    target = tmp_path / "video"

    main.download("https://storage.example/video.mov?sig=abc", target)

    assert target.read_bytes() == b"bytes"


def test_download_stops_at_the_size_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(main, "open_video", lambda url, timeout: FakeResponse(b"bytes"))
    monkeypatch.setattr(main, "MAX_VIDEO_BYTES", 3)

    with pytest.raises(ValueError, match="too large"):
        main.download("https://storage.example/video.mov", tmp_path / "video")


def test_download_stops_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(main, "open_video", lambda url, timeout: FakeResponse(b"bytes"))
    monkeypatch.setattr(main, "DOWNLOAD_DEADLINE_SECONDS", -1)

    with pytest.raises(TimeoutError, match="too long"):
        main.download("https://storage.example/video.mov", tmp_path / "video")


@pytest.fixture
def video_server() -> Iterator[str]:
    """A real local web server whose paths behave like a storage service gone wrong."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/whole":
                self.send_response(200)
                self.send_header("Content-Length", "5")
                self.end_headers()
                self.wfile.write(b"bytes")
            elif self.path == "/cut-off":
                # Promises 10 bytes, sends 5, then closes the connection.
                self.send_response(200)
                self.send_header("Content-Length", "10")
                self.end_headers()
                self.wfile.write(b"bytes")
                self.close_connection = True
            elif self.path == "/huge":
                self.send_response(200)
                self.send_header("Content-Length", str(main.MAX_VIDEO_BYTES + 1))
                self.end_headers()
            elif self.path == "/redirect-ftp":
                self.send_response(302)
                self.send_header("Location", "ftp://internal.example/video.mp4")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif self.path == "/redirect-http":
                self.send_response(302)
                self.send_header("Location", "/whole")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_download_saves_a_whole_video_from_a_real_server(
    video_server: str, tmp_path: Path
) -> None:
    target = tmp_path / "video"

    main.download(f"{video_server}/whole", target)

    assert target.read_bytes() == b"bytes"


def test_download_fails_when_the_server_sends_less_than_it_promised(
    video_server: str, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="ended early"):
        main.download(f"{video_server}/cut-off", tmp_path / "video")


def test_download_refuses_a_video_that_says_it_is_too_large(
    video_server: str, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="too large"):
        main.download(f"{video_server}/huge", tmp_path / "video")


@pytest.mark.parametrize("path", ["/redirect-ftp", "/redirect-http"])
def test_download_does_not_follow_redirects(
    video_server: str, path: str, tmp_path: Path
) -> None:
    with pytest.raises(urllib.error.HTTPError, match="Redirects are not followed"):
        main.download(f"{video_server}{path}", tmp_path / "video")


def test_a_cut_off_download_returns_analysis_error(
    video_server: str, monkeypatch: pytest.MonkeyPatch, fake_exercise: str
) -> None:
    extracted: list[Path] = []
    monkeypatch.setattr(
        main, "extract_keypoints", lambda video, model: extracted.append(video)
    )

    response = client.post(
        "/analyze",
        json={
            **REQUEST,
            "exercise": fake_exercise,
            "video_url": f"{video_server}/cut-off",
        },
    )

    assert response.status_code == 200
    assert AnalysisResult.model_validate(response.json()).error_code == "analysis_error"
    assert extracted == []  # the partial video was never analyzed


def test_downloads_ignore_proxy_settings_from_the_environment(
    video_server: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A proxy that nothing listens on: the download fails if it goes through it.
    for name in ("http_proxy", "HTTP_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "")
    monkeypatch.setattr(main, "VIDEO_OPENER", main.build_video_opener())
    target = tmp_path / "video"

    main.download(f"{video_server}/whole", target)

    assert target.read_bytes() == b"bytes"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://host/video.mp4"])
def test_download_refuses_links_that_are_not_http(url: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="http or https"):
        main.download(url, tmp_path / "video")


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
