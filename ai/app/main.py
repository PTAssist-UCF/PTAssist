"""The AI service's web server, with two endpoints: GET /health and POST /analyze.

The backend is the only caller. It sends a link to an exercise video, and we send back
the rep count, form score, and feedback. The service is internal only (it can't be
reached from the internet), so it has no sign-in.

POST /analyze is a stub for now: it ignores the video and always returns the same
made-up result. That lets the backend and frontend build against the real request and
response shapes while the real pipeline is written in Sprint 2:

    video -> keypoints (app/keypoints/) -> analysis (app/analysis/) -> result

Run it from the ai/ folder with `uvicorn app.main:app --reload --port 8001`, then open
http://localhost:8001/docs to try both endpoints in the browser.
"""

from fastapi import FastAPI

from app.schemas import AnalysisResult, AnalyzeRequest, HealthResponse, RepResult

# The version of our analysis code. It is saved with every result, so we can tell
# which results came from which version. Drop "-stub" once real analysis runs, and
# raise the version number whenever the analysis changes.
ANALYZER_VERSION = "0.1.0-stub"

app = FastAPI(title="PTAssist AI service")


@app.get("/health")
def health() -> HealthResponse:
    """Tells Docker and Azure that the service is up. Does no other work."""
    return HealthResponse(status="ok")


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> AnalysisResult:
    """Analyze one exercise video. STUB: returns the same result for every video."""
    # By the time this runs, FastAPI has already checked that the request matches
    # AnalyzeRequest. The real version will download request.video_url, find the body
    # keypoints in each frame, and run the analyzer for request.exercise.
    return AnalysisResult(
        status="complete",
        rep_count=3,
        form_score=82,  # the average of the three rep scores below
        reps=[
            RepResult(index=1, score=90, issues=[]),
            RepResult(index=2, score=85, issues=[]),
            RepResult(index=3, score=71, issues=["too_fast"]),
        ],
        feedback=["Slow down on the way back up."],
        error=None,
        analyzer_version=ANALYZER_VERSION,
    )
