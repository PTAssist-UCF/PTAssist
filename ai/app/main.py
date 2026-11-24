"""The AI service's web server, with two endpoints: GET /health and POST /analyze.

The backend is the only caller. It sends a link to an exercise video, and we send back
the rep count (or hold time), form score, and feedback. The service is internal only
(it can't be reached from the internet), so it has no sign-in.

POST /analyze runs the real pipeline for exercises that have an analyzer:

    video -> keypoints (app/keypoints/) -> analysis (app/analysis/) -> result

Exercises without an analyzer yet still get a made-up result, marked by a "-stub"
analyzer version, so the backend and frontend can keep building against them.

Run it from the ai/ folder with `uvicorn app.main:app --reload --port 8001`, then open
http://localhost:8001/docs to try both endpoints in the browser. Real analysis needs
ffmpeg and the pose model (see README).
"""

import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NoReturn

from fastapi import FastAPI

from app.analysis_contract import AnalysisResult, AnalyzeRequest, Issue, RepResult
from app.keypoints.extract import DEFAULT_MODEL, extract_keypoints
from app.keypoints.video import VideoError
from app.logs import configure_logging, session_context
from app.schemas import HealthResponse

# Every log line goes to stdout, uvicorn's included: JSON (or text, with
# LOG_FORMAT=text), with the session id where there is one, and no personal data
# (app/logs.py, backend/README.md, Logs).
configure_logging("ai", os.environ.get("LOG_FORMAT") or "json")

logger = logging.getLogger(__name__)

# The version of our analysis code. It is saved with every result, so we can tell
# which results came from which version. Raise it whenever anything that can change a
# result changes: an exercise's analyzer or thresholds, the shared framework
# (penalties, scoring, feedback, rep splitting), or the keypoint step (MediaPipe or
# video normalization). Made-up results add "-stub" to it.
ANALYZER_VERSION = "0.4.0"
STUB_VERSION = f"{ANALYZER_VERSION}-stub"

# One analyzer per exercise name (app/analysis/exercises/). None yet: an exercise moves
# here from the lists below when its analyzer is merged.
Analyzer = Callable[[Mapping[str, Any], str], AnalysisResult]
ANALYZERS: dict[str, Analyzer] = {}

# Exercises that still get a made-up result until their analyzer exists. The plank is
# held for time; the others are done in reps. Names are plain strings: to add or rename
# an exercise, change it here and in the backend's exercise table.
HOLD_EXERCISES = {"plank"}
REP_EXERCISES = {"cat_cow", "shoulder_abduction", "side_leg_raise", "squat"}

# The backend gives up after 230 seconds (AI_SERVICE_TIMEOUT_SECONDS), so these limits
# leave time for pose detection. They are starting values for SCRUM-74 to confirm.
DOWNLOAD_DEADLINE_SECONDS = 60  # the whole download
DOWNLOAD_READ_TIMEOUT_SECONDS = 15  # one read from the connection
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024  # the backend's default upload limit

# Each analysis keeps the CPU busy, so more at once would only slow them all down
# until the backend gives up on them. Extra requests wait for a free slot.
MAX_CONCURRENT_ANALYSES = 2
ANALYSIS_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_ANALYSES)

app = FastAPI(title="PTAssist AI service")


@app.get("/health")
def health() -> HealthResponse:
    """Tells Docker and Azure that the service is up. Does no other work."""
    return HealthResponse(status="ok")


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> AnalysisResult:
    """Analyze one exercise video, or explain why it could not be analyzed.

    Every failure, a bug included, is a failed result, never a 500 error. Never log
    the video link: anyone who has it can watch the video until it expires.
    """
    # Every line logged inside carries the session id, so the analysis shows in the
    # session's trace next to the backend's lines (app/logs.py).
    with session_context(request.session_id):
        logger.info("Analysis of session %s started", request.session_id)
        started = time.monotonic()
        result = analyze_request(request)
        outcome = (
            f"failed with {result.error_code}" if result.error_code else "complete"
        )
        logger.info(
            "Analysis of session %s finished: %s",
            request.session_id,
            outcome,
            extra={
                "outcome": result.status,
                "error_code": result.error_code,
                "analyzer_version": result.analyzer_version,
                "duration_seconds": round(time.monotonic() - started, 3),
            },
        )
    return result


def analyze_request(request: AnalyzeRequest) -> AnalysisResult:
    """The result for one request: made up, failed, or from the exercise's analyzer."""
    if request.exercise in HOLD_EXERCISES:
        return stub_hold_result()
    if request.exercise in REP_EXERCISES:
        return stub_rep_result()
    analyzer = ANALYZERS.get(request.exercise)
    if analyzer is None:
        return AnalysisResult.failed("unknown_exercise", ANALYZER_VERSION)

    try:
        return run_analysis(request, analyzer)
    except Exception:
        logger.exception("Analysis failed for session %s", request.session_id)
        return AnalysisResult.failed("analysis_error", ANALYZER_VERSION)


def run_analysis(request: AnalyzeRequest, analyzer: Analyzer) -> AnalysisResult:
    """Download the video, find the keypoints, and run the exercise's analyzer."""
    with (
        ANALYSIS_SLOTS,
        tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir,
    ):
        video = Path(temp_dir) / "video"
        try:
            download(request.video_url, video)
        except Exception as error:
            # The error text can contain the link, so log only its type.
            name = type(error).__name__
            logger.warning(
                "Download failed for session %s: %s", request.session_id, name
            )
            return AnalysisResult.failed("analysis_error", ANALYZER_VERSION)
        try:
            keypoints = extract_keypoints(video, DEFAULT_MODEL)
        except VideoError:
            return AnalysisResult.failed("video_unreadable", ANALYZER_VERSION)

    if not any(frame["landmarks"] for frame in keypoints["frames"]):
        return AnalysisResult.failed("no_person", ANALYZER_VERSION)
    return analyzer(keypoints, ANALYZER_VERSION)


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Fail on any redirect instead of following it.

    urllib follows redirects on its own, to any host and even to ftp:// links, so a
    redirect would get around the http(s) check in download(). The storage service
    never redirects a video link, so a redirect fails like any other download error.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> NoReturn:
        raise urllib.error.HTTPError(
            req.full_url, code, "Redirects are not followed", headers, fp
        )


def build_video_opener() -> urllib.request.OpenerDirector:
    """An opener that refuses redirects and ignores proxy settings in the environment.

    The empty ProxyHandler replaces the default one, which would read http_proxy.
    """
    return urllib.request.build_opener(
        RefuseRedirects(), urllib.request.ProxyHandler({})
    )


VIDEO_OPENER = build_video_opener()


def open_video(url: str, timeout: float) -> Any:
    """Open the video link. Tests replace this to avoid the network."""
    return VIDEO_OPENER.open(url, timeout=timeout)


def download(url: str, target: Path) -> None:
    """Save the video at an http(s) link to target, within the time and size limits."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("The video link must be http or https")
    deadline = time.monotonic() + DOWNLOAD_DEADLINE_SECONDS
    size = 0
    with (
        open_video(url, timeout=DOWNLOAD_READ_TIMEOUT_SECONDS) as response,
        target.open("wb") as file,
    ):
        # When the server says how big the video is, refuse a video that is too large
        # before reading it, and check below that all of it arrived.
        length_header = response.headers.get("Content-Length")
        expected = int(length_header) if length_header is not None else None
        if expected is not None and expected > MAX_VIDEO_BYTES:
            raise ValueError("The video is too large")
        # read1 returns as soon as data arrives, so a slow trickle still meets the
        # deadline check. read(n) would keep waiting until it had all n bytes.
        while chunk := response.read1(DOWNLOAD_CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_VIDEO_BYTES:
                raise ValueError("The video is too large")
            if time.monotonic() > deadline:
                raise TimeoutError("The video took too long to download")
            file.write(chunk)
        # If the connection closes early, urllib returns what arrived without an
        # error. A cut-off video must not be analyzed or called unreadable.
        if expected is not None and size != expected:
            raise ValueError("The download ended early")


def stub_rep_result() -> AnalysisResult:
    """A made-up result for an exercise done in reps: 3 reps, one of them too fast.

    Every exercise done in reps gets this same result, so side is always None here.
    A real side leg raise has left and right reps: see
    docs/analysis-result-examples/side-leg-raise.json.
    """
    return AnalysisResult(
        status="complete",
        rep_count=3,
        hold_seconds=None,
        form_score=97,  # the average of the three rep scores below, rounded
        reps=[
            RepResult(
                index=1,
                start_seconds=1.2,
                end_seconds=3.9,
                side=None,
                score=100,
                issues=[],
                metrics={},
            ),
            RepResult(
                index=2,
                start_seconds=4.4,
                end_seconds=6.1,
                side=None,
                score=90,
                issues=[
                    Issue(code="too_fast", message="This rep took less than 2 seconds.")
                ],
                metrics={},
            ),
            RepResult(
                index=3,
                start_seconds=6.8,
                end_seconds=9.6,
                side=None,
                score=100,
                issues=[],
                metrics={},
            ),
        ],
        feedback=["Slow down: take at least 2 seconds for each rep."],
        error_code=None,
        error_message=None,
        analyzer_version=STUB_VERSION,
    )


def stub_hold_result() -> AnalysisResult:
    """A made-up result for a hold exercise: one 22-second plank, hips sagging a bit."""
    return AnalysisResult(
        status="complete",
        rep_count=None,
        hold_seconds=22.0,  # the longest unbroken hold (here the only one)
        form_score=77,  # 17 of the 22 seconds were in good form
        reps=[
            RepResult(
                index=1,
                start_seconds=2.0,
                end_seconds=24.0,
                side=None,
                score=77,
                issues=[
                    Issue(
                        code="hips_sagging",
                        message="Your hips dropped below your shoulders.",
                    )
                ],
                metrics={"good_form_seconds": 17.0},
            ),
        ],
        feedback=["Squeeze your glutes to keep your hips level with your shoulders."],
        error_code=None,
        error_message=None,
        analyzer_version=STUB_VERSION,
    )
