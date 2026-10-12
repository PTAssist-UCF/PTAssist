"""The AI service's web server, with two endpoints: GET /health and POST /analyze.

The backend is the only caller. It sends a link to an exercise video, and we send back
the rep count (or hold time), form score, and feedback. The service is internal only
(it can't be reached from the internet), so it has no sign-in.

POST /analyze is a stub for now: it ignores the video and returns a made-up result for
the kind of exercise it was asked about. That lets the backend and frontend build
against the real request and result shapes (app/analysis_contract.py) while the real
pipeline is written in Sprint 2:

    video -> keypoints (app/keypoints/) -> analysis (app/analysis/) -> result

Run it from the ai/ folder with `uvicorn app.main:app --reload --port 8001`, then open
http://localhost:8001/docs to try both endpoints in the browser.
"""

from fastapi import FastAPI

from app.analysis_contract import AnalysisResult, AnalyzeRequest, Issue, RepResult
from app.schemas import HealthResponse

# The version of our analysis code. It is saved with every result, so we can tell
# which results came from which version. Drop "-stub" once real analysis runs, and
# raise the version number whenever anything that can change a result changes: an
# exercise's analyzer or thresholds, the shared framework (penalties, scoring, feedback,
# rep splitting), or the keypoint step (MediaPipe or video normalization).
ANALYZER_VERSION = "0.1.0-stub"

# The exercises the stub knows. The plank is held for time; the others are done in
# reps. Names are plain strings: to add or rename an exercise, change it here (later,
# in app/analysis/exercises/) and in the backend's exercise table.
HOLD_EXERCISES = {"plank"}
REP_EXERCISES = {"cat_cow", "shoulder_abduction", "side_leg_raise", "squat"}

app = FastAPI(title="PTAssist AI service")


@app.get("/health")
def health() -> HealthResponse:
    """Tells Docker and Azure that the service is up. Does no other work."""
    return HealthResponse(status="ok")


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> AnalysisResult:
    """Analyze one exercise video. STUB: returns a made-up result for every video."""
    # By the time this runs, FastAPI has already checked that the request matches
    # AnalyzeRequest. The real version will download request.video_url, find the body
    # keypoints in each frame, and run the analyzer for request.exercise. It will wrap
    # that work in try/except, so a failed download or an unexpected error (a bug)
    # returns AnalysisResult.failed("analysis_error", ANALYZER_VERSION) instead of a
    # 500 error. Never log the video link.
    if request.exercise in HOLD_EXERCISES:
        return stub_hold_result()
    if request.exercise in REP_EXERCISES:
        return stub_rep_result()
    return AnalysisResult.failed("unknown_exercise", ANALYZER_VERSION)


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
        analyzer_version=ANALYZER_VERSION,
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
        analyzer_version=ANALYZER_VERSION,
    )
